"""Authoritative Guard Buy decision service.

The browser supplies only a stable product reference and a quantity. This
service re-reads the server-side evidence, derives the amount and currency on
the server, and runs the existing deterministic PayShield Risk, Policy, and
Decision engines. Ollama/browser input can never override the result.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Optional

from backend.assistant.checkout_service import AssistantCheckoutService
from backend.assistant.evidence_store import ProductEvidenceStore
from backend.assistant.models import (
    GuardBuyCheckoutResponse,
    GuardBuyRequest,
    GuardBuyResponse,
)
from backend.assistant.rating_service import RatingService
from backend.payment.models import Transaction, TransactionItem
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalAPIError, PayPalClient
from backend.payment.receipts import ReceiptStatus, build_snapshots
from backend.payment.service import PaymentAuthorizationService
from backend.payshield.service import evaluate_transaction


class GuardBuyError(RuntimeError):
    """A safe, user-facing Guard Buy failure."""

    def __init__(self, message: str, status_code: int = 400, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code or "guard_buy_error"


def _most_restrictive(*decisions: str) -> str:
    if "BLOCK" in decisions:
        return "BLOCK"
    if "REVIEW" in decisions:
        return "REVIEW"
    return "ALLOW"


def _receipt_status_for_decision(decision: str) -> str:
    if decision == "ALLOW":
        return ReceiptStatus.PENDING
    if decision == "REVIEW":
        return ReceiptStatus.REVIEW_REQUIRED
    return ReceiptStatus.BLOCKED


class GuardBuyService:
    """Runs reference-based Guard Buy decisions and guarded Sandbox checkout."""

    def __init__(
        self,
        evidence_store: ProductEvidenceStore,
        *,
        checkout_service: Optional[AssistantCheckoutService] = None,
        order_registry: Optional[OrderRegistry] = None,
        payment_service: Optional[PaymentAuthorizationService] = None,
        paypal_client: Optional[PayPalClient] = None,
        rating_service: Optional[RatingService] = None,
        receipt_store: Optional[Any] = None,
        evaluate: Callable[..., dict] = evaluate_transaction,
    ):
        self.checkout_service = checkout_service or AssistantCheckoutService(
            order_registry=order_registry, paypal_client=paypal_client
        )
        self.evidence_store = evidence_store
        self.order_registry = self.checkout_service.order_registry
        self.payment_service = self.checkout_service.payment_service
        self.paypal_client = self.checkout_service.paypal_client
        self.rating_service = rating_service
        self.receipt_store = receipt_store
        self._evaluate = evaluate

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------
    def decide(self, request: GuardBuyRequest, user_id: str) -> GuardBuyResponse:
        if request.idempotency_key:
            existing = self.evidence_store.get_decision_by_idempotency_key(
                request.idempotency_key
            )
            if existing is not None:
                return self._decision_to_response(existing)

        product = self.evidence_store.get_product(request.product_reference)
        if product is None or product.get("result_type") != "product":
            raise GuardBuyError(
                "Unknown or expired product reference. Run a live search again.",
                status_code=404,
                code="unknown_product",
            )

        currency = str(product.get("currency") or "USD").upper()
        quantity = request.quantity
        identity_match = str(product.get("identity_match") or "UNKNOWN").upper()
        identity_reasons = list(product.get("identity_reasons") or [])
        base = {
            "product_reference": product["reference"],
            "title": product.get("title", ""),
            "source_url": product.get("source_url", ""),
            "retailer": product.get("retailer") or product.get("source_domain", ""),
            "currency": currency,
            "quantity": quantity,
            "price": product.get("price"),
            "price_verified": bool(product.get("price_verified")),
            "price_currency": product.get("price_currency", ""),
            "price_type": product.get("price_type", ""),
            "price_method": product.get("price_method", ""),
            "price_unverified_reason": product.get("price_unverified_reason", ""),
            "availability": product.get("availability") or "Unknown",
            "source_domain": product.get("source_domain", ""),
            "category": product.get("category") or "",
            "identity_match": identity_match,
        }

        evidence = product.get("evidence") or {}
        evidence_status = str(evidence.get("evidence_status") or "").upper()
        base.update(
            {
                "provider": str(evidence.get("provider") or ""),
                "is_fallback": bool(evidence.get("is_fallback")),
                "evidence_status": evidence_status,
                "condition": str(evidence.get("condition") or ""),
                "seller": str(evidence.get("seller") or ""),
                "variant": str(evidence.get("variant") or ""),
            }
        )

        # Live rating evidence (advisory consumer sentiment). It is fetched
        # server-side and stored on the decision record, but it never overrides
        # the deterministic price/identity/policy checks.
        rating_status = str(product.get("rating_status") or "").lower()
        base.update(
            {
                "rating": product.get("rating"),
                "review_count": product.get("review_count"),
                "rating_status": rating_status,
                "rating_reason": product.get("rating_reason", ""),
                "rating_retrieved_at": product.get("rating_retrieved_at", ""),
                "rating_provider": product.get("rating_provider", ""),
            }
        )

        if currency != "USD":
            return self._store_and_respond(
                base=base,
                user_id=user_id,
                request=request,
                amount=None,
                decision="BLOCK",
                payment_status="BLOCKED",
                risk_score=None,
                risk_level="",
                reason="PayShield Guard Buy currently supports USD evidence only.",
                evaluation=None,
                status="BLOCKED",
                reasons=[
                    "The source evidence is denominated in "
                    f"{currency}, which PayShield Guard Buy cannot authorize."
                ],
            )

        if identity_match == "MISMATCH":
            # The stored evidence provably describes a different product (for
            # example a refurbished iPhone 14 Pro Max for an iPhone 17 request).
            # Never auto-allow; require an explicit human review.
            reasons = [
                "Stored product evidence does not match the requested product "
                "identity, so PayShield will not authorize an automatic payment.",
            ]
            reasons.extend(f"Identity check: {reason}" for reason in identity_reasons)
            reasons.append("An explicit review is required before any payment.")
            return self._store_and_respond(
                base=base,
                user_id=user_id,
                request=request,
                amount=None,
                decision="REVIEW",
                payment_status="REVIEW_REQUIRED",
                risk_score=None,
                risk_level="",
                reason=(
                    "The stored product identity conflicts with the request, so "
                    "PayShield requires review before any payment."
                ),
                evaluation=None,
                status="PENDING",
                reasons=reasons,
            )

        if evidence_status == "CONFLICT":
            # Merchant offers for this reference materially disagree (for example
            # a mixed new/used condition set). PayShield will not derive an
            # automatic amount from conflicting offers.
            conflicts = [
                str(item) for item in (evidence.get("conflicts") or []) if str(item).strip()
            ]
            reasons = [
                "The merchant offers for this product materially conflict, so "
                "PayShield will not authorize an automatic payment."
            ]
            reasons.extend(f"Conflicting evidence: {reason}" for reason in conflicts)
            reasons.append("An explicit review is required before any payment.")
            return self._store_and_respond(
                base=base,
                user_id=user_id,
                request=request,
                amount=None,
                decision="REVIEW",
                payment_status="REVIEW_REQUIRED",
                risk_score=None,
                risk_level="",
                reason=(
                    "Conflicting merchant offers prevent an automatic amount, so "
                    "PayShield requires review before any payment."
                ),
                evaluation=None,
                status="PENDING",
                reasons=reasons,
            )

        if rating_status == "conflict":
            # Conflicting live ratings from a review provider: PayShield will
            # not derive a buyer-sentiment signal from contradictory evidence.
            return self._store_and_respond(
                base=base,
                user_id=user_id,
                request=request,
                amount=None,
                decision="REVIEW",
                payment_status="REVIEW_REQUIRED",
                risk_score=None,
                risk_level="",
                reason=(
                    "Conflicting live product ratings prevent an automatic "
                    "buyer-sentiment assessment, so PayShield requires review."
                ),
                evaluation=None,
                status="PENDING",
                reasons=[
                    "Live product ratings conflict; no reliable sentiment signal.",
                    f"Rating provider note: {product.get('rating_reason', '')}",
                    "An explicit review is required before any payment.",
                ],
            )

        price = product.get("price")
        if price is None or not product.get("price_verified"):
            source_reason = product.get("price_unverified_reason") or (
                "The source did not provide a verifiable price."
            )
            return self._store_and_respond(
                base=base,
                user_id=user_id,
                request=request,
                amount=None,
                decision="REVIEW",
                payment_status="REVIEW_REQUIRED",
                risk_score=None,
                risk_level="",
                reason=(
                    "The source price could not be verified, so PayShield cannot "
                    "authorize an amount it cannot verify."
                ),
                evaluation=None,
                status="PENDING",
                reasons=[
                    f"Retail price is not verified from source: {source_reason}",
                    "An explicit review is required before any payment.",
                ],
            )

        amount = round(float(price) * quantity, 2)
        if amount <= 0:
            raise GuardBuyError(
                "Computed amount is invalid.", status_code=422, code="invalid_amount"
            )

        category = product.get("category") or "electronics"
        merchant_name = base["retailer"] or product.get("source_domain", "unknown")

        authorization = self.payment_service.check_payment(
            agent_id=request.agent_id,
            amount=amount,
            category=category,
        )
        transaction_id = f"GUARD-{uuid.uuid4().hex[:12].upper()}"
        transaction = Transaction(
            transaction_id=transaction_id,
            user_id=user_id or "guard-buy",
            merchant_category=category,
            merchant_name=merchant_name,
            amount=amount,
            currency="USD",
            payment_method="paypal",
            items=[
                TransactionItem(
                    name=product.get("title", "product"),
                    quantity=quantity,
                    price=float(price),
                )
            ],
            agent_name=request.agent_id,
        )
        previous_spend = self._agent_limit(request.agent_id)
        evaluation = self._evaluate(
            transaction,
            previous_spend=previous_spend,
            previous_recipients=[],
        )
        if not isinstance(evaluation, dict):
            raise GuardBuyError(
                "Risk evaluation failed.", status_code=502, code="evaluation_failed"
            )
        risk_score = evaluation.get("risk_score")
        risk_level = evaluation.get("risk_level", "")

        decision = _most_restrictive(
            authorization.get("decision", "BLOCK"),
            evaluation.get("final_decision", "BLOCK"),
        )

        reasons: list[str] = []
        if authorization.get("decision") != "ALLOW":
            reasons.append(
                authorization.get("reason", "PayShield policy did not authorize this.")
            )
        if evaluation.get("decision_reason"):
            reasons.append(evaluation["decision_reason"])
        if not reasons:
            reasons.append(
                f"Risk score {risk_score}/100 ({risk_level}) passed PayShield checks."
            )

        if identity_match == "PARTIAL_MATCH":
            detail = f" ({identity_reasons[0]})" if identity_reasons else ""
            reasons.append(
                "Identity check: the evidence only partially matches the requested "
                f"product{detail}."
            )

        if decision == "ALLOW":
            reason = "PayShield authorized this purchase. Sandbox checkout is enabled."
            reasons = [
                f"Risk score {risk_score}/100 ({risk_level}).",
                *[r for r in reasons if r],
            ]
        elif decision == "REVIEW":
            reason = "PayShield requires explicit human review before any payment."
            reasons.append("No payment will be created until review is approved.")
        else:
            reason = "PayShield blocked this purchase. No payment may be created."
            reasons.append("No payment will be created.")

        return self._store_and_respond(
            base=base,
            user_id=user_id,
            request=request,
            amount=amount,
            decision=decision,
            payment_status=(
                "READY_FOR_SANDBOX_CHECKOUT"
                if decision == "ALLOW"
                else "REVIEW_REQUIRED" if decision == "REVIEW" else "BLOCKED"
            ),
            risk_score=risk_score,
            risk_level=risk_level,
            reason=reason,
            evaluation=evaluation,
            status=("ACTIVE" if decision == "ALLOW" else ("PENDING" if decision == "REVIEW" else "BLOCKED")),
            reasons=reasons,
        )

    def _agent_limit(self, agent_id: str) -> float:
        agents = getattr(self.payment_service, "agents", {})
        agent = agents.get(agent_id) if hasattr(agents, "get") else None
        try:
            return float(getattr(agent, "spending_limit", 10000.0))
        except (TypeError, ValueError):
            return 10000.0

    def _record_decision_receipt(self, base, user_id, request, decision_reference,
                                 decision, payment_status, amount, risk_score,
                                 risk_level, reason, evaluation):
        """Persist an immutable receipt snapshot for a Guard Buy decision."""
        if self.receipt_store is None:
            return
        try:
            snapshots = build_snapshots(
                product={
                    "reference": base.get("product_reference"),
                    "title": base.get("title"),
                    "source_url": base.get("source_url"),
                    "source_domain": base.get("source_domain"),
                    "retailer": base.get("retailer"),
                    "price": base.get("price"),
                    "price_verified": base.get("price_verified", False),
                    "price_currency": base.get("price_currency", ""),
                    "availability": base.get("availability"),
                    "category": base.get("category"),
                    "evidence_status": base.get("evidence_status", ""),
                    "rating": base.get("rating"),
                    "review_count": base.get("review_count"),
                    "rating_status": base.get("rating_status", ""),
                    "rating_provider": base.get("rating_provider", ""),
                },
                risk=(
                    {"score": risk_score, "level": risk_level}
                    if risk_score is not None or risk_level else None
                ),
                policy=(
                    evaluation.get("policy_result")
                    if isinstance(evaluation, dict) else None
                ),
                decision={
                    "final_decision": decision,
                    "reason": reason,
                },
                payment={
                    "amount": None if amount is None else f"{float(amount):.2f}",
                    "currency": base.get("currency", "USD"),
                    "quantity": base.get("quantity", request.quantity),
                },
            )
            self.receipt_store.create_receipt(
                status=_receipt_status_for_decision(decision),
                order_id=None,
                decision_reference=decision_reference,
                idempotency_key=request.idempotency_key,
                user_id=user_id or "",
                agent_id=request.agent_id,
                merchant_name=base.get("retailer", ""),
                merchant_category=base.get("category") or "",
                amount=amount,
                currency=base.get("currency", "USD"),
                quantity=request.quantity,
                decision=decision,
                payment_status_raw=payment_status,
                reason=reason,
                risk_score=risk_score,
                risk_level=risk_level or "",
                snapshots=snapshots,
                event={"source": "guard_buy_decision"},
            )
        except Exception:
            return

    def _update_checkout_receipt(self, decision_reference, *, status, order_id=None,
                                 payment_status_raw=None, reason=None,
                                 risk_score=None, risk_level=None):
        if self.receipt_store is None:
            return
        try:
            receipt = self.receipt_store.get_receipt_by_decision_reference(
                decision_reference
            )
            if receipt is None:
                return
            self.receipt_store.update_receipt(
                receipt["receipt_id"],
                status=status,
                order_id=order_id,
                payment_status_raw=payment_status_raw,
                reason=reason,
                risk_score=risk_score,
                risk_level=risk_level,
                event={"source": "guard_buy_checkout"},
            )
        except Exception:
            return

    def _store_and_respond(
        self,
        *,
        base: dict,
        user_id: str,
        request: GuardBuyRequest,
        amount: Optional[float],
        decision: str,
        payment_status: str,
        risk_score: Optional[int],
        risk_level: str,
        reason: str,
        evaluation: Optional[dict],
        status: str,
        reasons: list[str],
    ) -> GuardBuyResponse:
        decision_reference = self.evidence_store.create_decision(
            product_reference=base["product_reference"],
            user_id=user_id,
            agent_id=request.agent_id,
            amount="0.00" if amount is None else f"{amount:.2f}",
            currency="USD",
            quantity=request.quantity,
            category=base.get("category") or "",
            merchant_name=base["retailer"],
            decision=decision,
            payment_status=payment_status,
            risk_score=risk_score,
            risk_level=risk_level,
            reason=reason,
            evaluation=evaluation,
            status=status,
            idempotency_key=request.idempotency_key,
        )
        self._record_decision_receipt(
            base, user_id, request, decision_reference, decision,
            payment_status, amount, risk_score, risk_level, reason, evaluation,
        )
        return GuardBuyResponse(
            decision=decision,
            payment_status=payment_status,
            product_reference=base["product_reference"],
            decision_reference=decision_reference,
            checkout_available=decision == "ALLOW",
            title=base["title"],
            source_url=base["source_url"],
            retailer=base["retailer"],
            price=base["price"],
            price_verified=base.get("price_verified", False),
            price_currency=base.get("price_currency", ""),
            price_type=base.get("price_type", ""),
            price_method=base.get("price_method", ""),
            price_unverified_reason=base.get("price_unverified_reason", ""),
            availability=base.get("availability", "Unknown"),
            identity_match=base.get("identity_match", "UNKNOWN"),
            source_domain=base.get("source_domain", ""),
            currency=base["currency"],
            quantity=base["quantity"],
            amount=amount,
            checkout_amount_verified=decision == "ALLOW" and amount is not None,
            risk_score=risk_score,
            risk_level=risk_level,
            reason=reason,
            reasons=reasons,
            audit_reference=(
                evaluation.get("transaction_id") if isinstance(evaluation, dict) else None
            ),
            evaluation=evaluation,
            provider=base.get("provider", ""),
            is_fallback=bool(base.get("is_fallback", False)),
            evidence_status=base.get("evidence_status", ""),
            condition=base.get("condition", ""),
            seller=base.get("seller", ""),
            variant=base.get("variant", ""),
            rating=base.get("rating"),
            review_count=base.get("review_count"),
            rating_status=base.get("rating_status", ""),
            rating_provider=base.get("rating_provider", ""),
        )

    def _decision_to_response(self, decision: dict) -> GuardBuyResponse:
        product = self.evidence_store.get_product(decision["product_reference"]) or {}
        evidence = product.get("evidence") or {}
        amount_text = decision.get("amount")
        try:
            amount = float(amount_text) if amount_text is not None else None
        except (TypeError, ValueError):
            amount = None
        decision_value = decision.get("decision", "BLOCK")
        return GuardBuyResponse(
            decision=decision_value,
            payment_status=decision.get("payment_status", "BLOCKED"),
            product_reference=decision["product_reference"],
            decision_reference=decision.get("decision_reference"),
            checkout_available=decision_value == "ALLOW" and decision.get("status") == "ACTIVE",
            title=product.get("title", ""),
            source_url=product.get("source_url", ""),
            retailer=product.get("retailer", ""),
            price=product.get("price"),
            price_verified=bool(product.get("price_verified")),
            price_currency=product.get("price_currency", ""),
            price_type=product.get("price_type", ""),
            price_method=product.get("price_method", ""),
            price_unverified_reason=product.get("price_unverified_reason", ""),
            availability=product.get("availability") or "Unknown",
            identity_match=str(product.get("identity_match") or "UNKNOWN").upper(),
            source_domain=product.get("source_domain", ""),
            currency=decision.get("currency", "USD"),
            quantity=decision.get("quantity", 1),
            amount=amount if amount and amount > 0 else None,
            checkout_amount_verified=(
                decision_value == "ALLOW" and amount is not None and amount > 0
            ),
            risk_score=decision.get("risk_score"),
            risk_level=decision.get("risk_level", ""),
            reason=decision.get("reason", ""),
            reasons=[decision.get("reason", "")] if decision.get("reason") else [],
            audit_reference=(
                decision.get("evaluation", {}).get("transaction_id")
                if isinstance(decision.get("evaluation"), dict)
                else None
            ),
            evaluation=decision.get("evaluation"),
            provider=str(evidence.get("provider") or ""),
            is_fallback=bool(evidence.get("is_fallback")),
            evidence_status=str(evidence.get("evidence_status") or ""),
            condition=str(evidence.get("condition") or ""),
            seller=str(evidence.get("seller") or ""),
            variant=str(evidence.get("variant") or ""),
            rating=product.get("rating"),
            review_count=product.get("review_count"),
            rating_status=str(product.get("rating_status") or ""),
            rating_provider=str(product.get("rating_provider") or ""),
        )

    # ------------------------------------------------------------------
    # Explicit review approval (REVIEW -> re-evaluate -> maybe ALLOW)
    # ------------------------------------------------------------------
    def approve_review(
        self, decision_reference: str, approved: bool, reviewer_user_id: str
    ) -> GuardBuyResponse:
        record = self.evidence_store.get_decision(decision_reference)
        if record is None:
            raise GuardBuyError(
                "Unknown Guard Buy decision reference.",
                status_code=404,
                code="unknown_decision",
            )

        if record.get("decision") != "REVIEW":
            return self._decision_to_response(record)

        if not approved:
            reason = "Reviewer rejected this purchase. No payment will be created."
            self.evidence_store.update_decision_after_review(
                decision_reference,
                decision="BLOCK",
                payment_status="BLOCKED",
                risk_score=record.get("risk_score"),
                risk_level=record.get("risk_level", ""),
                reason=reason,
                evaluation=record.get("evaluation"),
                reviewed_by=reviewer_user_id,
            )
            self._update_checkout_receipt(
                decision_reference,
                status=ReceiptStatus.BLOCKED,
                reason=reason,
                risk_score=record.get("risk_score"),
                risk_level=record.get("risk_level", ""),
            )
            return self._decision_to_response(
                {**record, "decision": "BLOCK", "status": "BLOCKED", "reason": reason}
            )

        product = self.evidence_store.get_product(record["product_reference"])
        if product is None:
            raise GuardBuyError(
                "Stored product evidence is no longer available.",
                status_code=409,
                code="stale_evidence",
            )

        # Derive the amount to re-evaluate from the current server-side verified
        # evidence. A review may have been created precisely because the price was
        # unverified (its recorded amount is then 0.00); approving it must never
        # fabricate a verifiable amount. If no verified amount can be derived, the
        # purchase still cannot proceed -- report that honestly as a structured
        # outcome instead of raising a conflict.
        amount = self._review_amount(record, product)
        if amount is None or amount <= 0:
            source_reason = product.get("price_unverified_reason") or (
                "the source did not provide a verifiable price"
            )
            reason = (
                "Review approved, but PayShield still cannot authorize this purchase: "
                f"no verified amount is available ({source_reason}). Verify the source "
                "price (re-run the search) before checkout."
            )
            self.evidence_store.update_decision_after_review(
                decision_reference,
                decision="REVIEW",
                payment_status="REVIEW_REQUIRED",
                risk_score=record.get("risk_score"),
                risk_level=record.get("risk_level", ""),
                reason=reason,
                evaluation=record.get("evaluation"),
                reviewed_by=reviewer_user_id,
            )
            self._update_checkout_receipt(
                decision_reference,
                status=ReceiptStatus.REVIEW_REQUIRED,
                reason=reason,
                risk_score=record.get("risk_score"),
                risk_level=record.get("risk_level", ""),
            )
            return self._decision_to_response(
                {
                    **record,
                    "decision": "REVIEW",
                    "status": "PENDING",
                    "reason": reason,
                    "reviewed_by": reviewer_user_id,
                }
            )

        category = product.get("category") or record.get("category") or "electronics"
        merchant_name = (
            product.get("retailer")
            or product.get("source_domain")
            or record.get("merchant_name", "unknown")
        )
        transaction_id = f"GUARD-{uuid.uuid4().hex[:12].upper()}"
        transaction = Transaction(
            transaction_id=transaction_id,
            user_id=record.get("user_id") or reviewer_user_id or "guard-buy",
            merchant_category=category,
            merchant_name=merchant_name,
            amount=amount,
            currency=record.get("currency", "USD"),
            payment_method="paypal",
            items=[
                TransactionItem(
                    name=product.get("title", "product"),
                    quantity=int(record.get("quantity", 1)),
                    price=float(amount) / max(1, int(record.get("quantity", 1))),
                )
            ],
            agent_name=record.get("agent_id", "agent-001"),
        )
        authorization = self.payment_service.check_payment(
            agent_id=record.get("agent_id", "agent-001"),
            amount=amount,
            category=category,
        )
        evaluation = self._evaluate(
            transaction,
            previous_spend=self._agent_limit(record.get("agent_id", "agent-001")),
            previous_recipients=[],
        )
        decision = _most_restrictive(
            authorization.get("decision", "BLOCK"),
            evaluation.get("final_decision", "BLOCK"),
        )
        reason = (
            "Review approved and PayShield re-evaluated the purchase as ALLOW."
            if decision == "ALLOW"
            else "PayShield re-evaluation still does not allow this purchase."
        )
        self.evidence_store.update_decision_after_review(
            decision_reference,
            decision=decision,
            payment_status=(
                "READY_FOR_SANDBOX_CHECKOUT"
                if decision == "ALLOW"
                else "REVIEW_REQUIRED" if decision == "REVIEW" else "BLOCKED"
            ),
            risk_score=evaluation.get("risk_score"),
            risk_level=evaluation.get("risk_level", ""),
            reason=reason,
            evaluation=evaluation,
            reviewed_by=reviewer_user_id,
        )
        self._update_checkout_receipt(
            decision_reference,
            status=_receipt_status_for_decision(decision),
            reason=reason,
            risk_score=evaluation.get("risk_score"),
            risk_level=evaluation.get("risk_level", ""),
        )
        return self._decision_to_response(
            {
                **record,
                "decision": decision,
                "status": "ACTIVE" if decision == "ALLOW" else "BLOCKED",
                "reason": reason,
                "evaluation": evaluation,
                "risk_score": evaluation.get("risk_score"),
                "risk_level": evaluation.get("risk_level", ""),
            }
        )

    @staticmethod
    def _amount_from_record(record: dict) -> Optional[float]:
        try:
            return float(record.get("amount"))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _review_amount(cls, record: dict, product: dict) -> Optional[float]:
        """Derive the amount to re-evaluate from current server-side evidence.

        Prefers the amount already recorded on an ALLOW-eligible review, but when
        that is missing/zero (a review created because the price was unverified)
        it re-derives from the stored verified price so a human approval can still
        proceed once the source price is verified. Returns ``None`` when no
        verified amount can be established.
        """
        recorded = cls._amount_from_record(record)
        if recorded is not None and recorded > 0:
            return recorded
        if not product.get("price_verified"):
            return None
        price = product.get("price")
        if price is None:
            return None
        if str(product.get("currency") or "USD").upper() != "USD":
            return None
        try:
            quantity = int(record.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1
        derived = round(float(price) * max(1, quantity), 2)
        return derived if derived > 0 else None

    @staticmethod
    def _revalidate_evidence(record: dict, product: dict) -> Optional[str]:
        """Return a blocking reason if stored evidence no longer matches, else None."""
        if not product.get("price_verified"):
            return (
                "Retail price is no longer verified from the source; checkout was blocked."
            )
        price = product.get("price")
        if price is None:
            return "Stored product evidence has no verified price; checkout was blocked."
        if str(product.get("currency") or "USD").upper() != "USD":
            return "Stored evidence is not in USD; checkout was blocked."
        try:
            quantity = int(record.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1
        expected = round(float(price) * max(1, quantity), 2)
        recorded = GuardBuyService._amount_from_record(record)
        if recorded is None or abs(expected - recorded) > 0.005:
            return (
                "Recorded amount does not match the stored verified evidence; "
                "checkout was blocked."
            )
        return None

    # ------------------------------------------------------------------
    # Guarded Sandbox checkout
    # ------------------------------------------------------------------
    def checkout(
        self, decision_reference: str, user_id: str, idempotency_key: str
    ) -> GuardBuyCheckoutResponse:
        if not idempotency_key:
            raise GuardBuyError(
                "An idempotency key is required.",
                status_code=400,
                code="idempotency_key_required",
            )

        cached = self.order_registry.get_idempotent_response(idempotency_key)
        if cached is not None:
            return GuardBuyCheckoutResponse(**cached)

        record = self.evidence_store.get_decision(decision_reference)
        if record is None:
            raise GuardBuyError(
                "Unknown Guard Buy decision reference.",
                status_code=404,
                code="unknown_decision",
            )

        amount = self._amount_from_record(record)
        product_reference = record["product_reference"]
        base_kwargs = {
            "product_reference": product_reference,
            "currency": record.get("currency", "USD"),
            "total_amount": amount,
            "checkout_amount_verified": False,
            "evaluation": record.get("evaluation"),
        }

        if record.get("decision") != "ALLOW":
            return GuardBuyCheckoutResponse(
                decision=record.get("decision", "BLOCK"),
                payment_status="NOT_CAPTURED",
                reason="PayShield did not authorize checkout for this decision.",
                **base_kwargs,
            )

        product = self.evidence_store.get_product(product_reference)
        if product is None:
            raise GuardBuyError(
                "Stored product evidence is no longer available.",
                status_code=409,
                code="stale_evidence",
            )
        if amount is None or amount <= 0:
            raise GuardBuyError(
                "This decision has no verified amount.",
                status_code=409,
                code="unverifiable_amount",
            )

        # Re-validate identity, currency, and amount against the stored evidence
        # before any payment is created. The browser can never change these.
        revalidation_error = self._revalidate_evidence(record, product)
        if revalidation_error:
            self.evidence_store.update_decision_after_review(
                decision_reference,
                decision="BLOCK",
                payment_status="NOT_CAPTURED",
                risk_score=record.get("risk_score"),
                risk_level=record.get("risk_level", ""),
                reason=revalidation_error,
                evaluation=record.get("evaluation"),
            )
            return GuardBuyCheckoutResponse(
                decision="BLOCK",
                payment_status="NOT_CAPTURED",
                reason=revalidation_error,
                **base_kwargs,
            )

        # Re-evaluate with the deterministic engines immediately before creating
        # a payment. Never trust the earlier decision alone.
        category = product.get("category") or record.get("category") or "electronics"
        merchant_name = (
            product.get("retailer")
            or product.get("source_domain")
            or record.get("merchant_name", "unknown")
        )
        transaction_id = f"GUARD-{uuid.uuid4().hex[:12].upper()}"
        transaction = Transaction(
            transaction_id=transaction_id,
            user_id=user_id or record.get("user_id") or "guard-buy",
            merchant_category=category,
            merchant_name=merchant_name,
            amount=amount,
            currency=record.get("currency", "USD"),
            payment_method="paypal",
            items=[
                TransactionItem(
                    name=product.get("title", "product"),
                    quantity=int(record.get("quantity", 1)),
                    price=float(amount) / max(1, int(record.get("quantity", 1))),
                )
            ],
            agent_name=record.get("agent_id", "agent-001"),
        )
        authorization = self.payment_service.check_payment(
            agent_id=record.get("agent_id", "agent-001"),
            amount=amount,
            category=category,
        )
        evaluation = self._evaluate(
            transaction,
            previous_spend=self._agent_limit(record.get("agent_id", "agent-001")),
            previous_recipients=[],
        )
        decision = _most_restrictive(
            authorization.get("decision", "BLOCK"),
            evaluation.get("final_decision", "BLOCK"),
        )
        if decision != "ALLOW":
            self.evidence_store.update_decision_after_review(
                decision_reference,
                decision=decision,
                payment_status="NOT_CAPTURED",
                risk_score=evaluation.get("risk_score"),
                risk_level=evaluation.get("risk_level", ""),
                reason="PayShield re-evaluation did not authorize checkout.",
                evaluation=evaluation,
            )
            self._update_checkout_receipt(
                decision_reference,
                status=_receipt_status_for_decision(decision),
                reason="PayShield re-evaluation did not authorize checkout.",
                risk_score=evaluation.get("risk_score"),
                risk_level=evaluation.get("risk_level", ""),
            )
            return GuardBuyCheckoutResponse(
                decision=decision,
                payment_status="NOT_CAPTURED",
                reason="PayShield re-evaluation did not authorize checkout.",
                **{**base_kwargs, "evaluation": evaluation},
            )

        # Atomically consume the decision so an order can be created only once.
        if not self.evidence_store.consume_decision(decision_reference):
            return GuardBuyCheckoutResponse(
                decision="BLOCK",
                payment_status="NOT_CAPTURED",
                reason="This decision has already been used for a checkout.",
                **base_kwargs,
            )

        try:
            order = self.checkout_service.start_authorized_checkout(
                amount=amount,
                currency=record.get("currency", "USD"),
                agent_id=record.get("agent_id", "agent-001"),
                category=category,
                merchant_name=merchant_name,
                user_id=user_id or record.get("user_id") or "guard-buy",
                transaction_id=transaction_id,
                external_order_id=f"EXT-{transaction_id}",
                items=[
                    {
                        "name": product.get("title", "product"),
                        "sku": product_reference,
                        "quantity": int(record.get("quantity", 1)),
                        "unit_price": f"{(amount / max(1, int(record.get('quantity', 1)))):.2f}",
                    }
                ],
                idempotency_key=None,
            )
        except PayPalAPIError as exc:
            return GuardBuyCheckoutResponse(
                decision="BLOCK",
                payment_status="GATEWAY_ERROR",
                reason=exc.safe_detail,
                **base_kwargs,
            )
        except (RuntimeError, ValueError) as exc:
            return GuardBuyCheckoutResponse(
                decision="BLOCK",
                payment_status="GATEWAY_ERROR",
                reason=str(exc),
                **base_kwargs,
            )

        response = {
            "decision": "ALLOW",
            "payment_status": order.get("payment_status", "AWAITING_BUYER_APPROVAL"),
            "product_reference": product_reference,
            "order_id": order.get("order_id"),
            "approval_url": order.get("approval_url"),
            "total_amount": amount,
            "currency": record.get("currency", "USD"),
            "checkout_amount_verified": True,
            "reason": "PayShield authorized Sandbox checkout. Awaiting buyer approval.",
            "evaluation": evaluation,
        }
        self.order_registry.save_idempotent_response(idempotency_key, response)
        self._update_checkout_receipt(
            decision_reference,
            status=ReceiptStatus.PENDING,
            order_id=order.get("order_id"),
            payment_status_raw=order.get("payment_status", "AWAITING_BUYER_APPROVAL"),
            reason=response["reason"],
            risk_score=evaluation.get("risk_score"),
            risk_level=evaluation.get("risk_level", ""),
        )
        return GuardBuyCheckoutResponse(**response)
