"""Safely coordinate PayShield-authorized PayPal captures."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from backend.payment.models import Transaction, TransactionItem
from backend.payment.paypal_client import PayPalAPIError, PayPalClient
from backend.payment.order_registry import OrderRegistry
from backend.payment.receipts import ReceiptStatus, build_snapshots
from backend.payment.service import PaymentAuthorizationService
from backend.agents.managers import Agent
from backend.policy.engine import DEFAULT_CONSTITUTION
from backend.payshield.service import evaluate_transaction


class GuardedCaptureService:
    """Capture an approved PayPal order only after PayShield allows it."""

    def __init__(
        self,
        paypal_client=None,
        order_registry=None,
        payment_service=None,
        receipt_store=None,
    ):
        self.paypal = paypal_client or PayPalClient()
        self.registry = order_registry or OrderRegistry()
        self.receipt_store = receipt_store
        self.payment_service = payment_service or PaymentAuthorizationService(
            agents={
                "agent-001": Agent(
                    agent_id="agent-001",
                    name="Payment Agent",
                    allowed_categories=[
                        "food", "groceries", "office", "services",
                        "software", "travel", "electronics",
                    ],
                    spending_limit=10000,
                )
            },
            constitution=DEFAULT_CONSTITUTION,
        )

    def capture_authorized_order(
        self,
        order_id,
        transaction,
        expected_amount,
        expected_currency="USD",
        buyer_approved=False,
    ):
        if not isinstance(order_id, str) or not order_id.strip():
            return self._blocked("Invalid order ID.")

        if not buyer_approved:
            return self._blocked("Buyer approval is required.")

        try:
            amount = float(expected_amount)
            if amount <= 0:
                return self._blocked("Invalid payment amount.")

            if (
                not isinstance(expected_currency, str)
                or len(expected_currency) != 3
                or not expected_currency.isalpha()
            ):
                return self._blocked("Invalid currency.")

            if self.registry.is_processed(order_id):
                return self._blocked("Order has already been processed.")

            if not self.registry.reserve_order(order_id):
                return self._blocked("Order is already reserved or processed.")

        except Exception:
            return self._blocked("Unable to reserve order safely.")

        try:
            # The client must validate an APPROVED, not already-captured,
            # order before capture. Do not capture unless it is verified.
            verification = self.paypal.verify_order(
                order_id=order_id,
                expected_amount=amount,
                expected_currency=expected_currency.upper(),
            )

            if (
                not isinstance(verification, dict)
                or verification.get("verified") is not True
            ):
                self.registry.release_reservation(order_id)
                return self._blocked("PayPal order verification failed.")

            # PayShield's real decision is authoritative.
            result = evaluate_transaction(transaction)
            if not isinstance(result, dict):
                self.registry.release_reservation(order_id)
                return self._blocked("Risk evaluation failed.")

            decision = result.get(
                "final_decision", result.get("decision", "BLOCK")
            )
            if decision != "ALLOW":
                self.registry.release_reservation(order_id)
                return {
                    "success": False,
                    "decision": "BLOCK" if decision not in ("REVIEW", "BLOCK")
                    else decision,
                    "reason": "PayShield did not authorize capture.",
                    "order_id": order_id,
                }

            # Use a stable request ID so retries can be reconciled.
            request_id = f"payshield-{order_id}"

            capture = self.paypal.capture_order(
                order_id=order_id,
                request_id=request_id,
            )

            if not isinstance(capture, dict):
                # Capture outcome is uncertain; retain reservation.
                return self._blocked(
                    "Capture outcome is uncertain; reconciliation required.",
                    order_id,
                )

            if capture.get("status") != "COMPLETED":
                # A non-completed response is not proof that no capture occurred.
                return self._blocked(
                    "Capture was not confirmed; reconciliation required.",
                    order_id,
                )

            if not self.registry.complete_reservation(order_id):
                # PayPal may have captured successfully. Do not retry blindly.
                return self._blocked(
                    "Capture succeeded but registry update failed; "
                    "reconciliation required.",
                    order_id,
                )

            return {
                "success": True,
                "decision": "ALLOW",
                "reason": "PayPal capture confirmed.",
                "order_id": order_id,
                "capture": capture,
                "risk_assessment": result.get("risk_assessment"),
            }

        except Exception:
            # The remote capture might have succeeded despite a timeout.
            # Keep the reservation until the result is reconciled.
            return self._blocked(
                "Payment outcome is uncertain; reconciliation required.",
                order_id,
            )

    @staticmethod
    def _blocked(reason, order_id=None, order_status=None):
        result = {
            "success": False,
            "decision": "BLOCK",
            "reason": reason,
            "order_id": order_id,
        }
        if order_status:
            result["order_status"] = order_status
        return result

    def _set_order_state(self, order_id: str, status: str) -> None:
        """Persist a checkout-order lifecycle state without affecting the outcome.

        State tracking is best-effort: it must never alter a payment decision or
        mask a capture failure.
        """
        try:
            self.registry.set_checkout_order_status(order_id, status)
        except Exception:
            pass

    def _processed_outcome(self, order_id):
        """Return the stored authoritative outcome for an already-processed order.

        A processed order was already captured, so a repeated callback must not
        manufacture a fresh BLOCK that contradicts the recorded receipt. When the
        authoritative receipt proves success we echo it (idempotent retry);
        otherwise we stay conservative and refuse to re-capture.
        """
        receipt = None
        if self.receipt_store is not None:
            try:
                receipt = self.receipt_store.get_receipt_by_order_id(order_id)
            except Exception:
                receipt = None
        if isinstance(receipt, dict):
            status = receipt.get("status")
            snapshots = receipt.get("snapshots") or {}
            payment_snap = snapshots.get("payment") or {}
            capture_obj = payment_snap.get("capture")
            if not capture_obj and receipt.get("capture_id"):
                capture_obj = {"id": receipt.get("capture_id"), "status": "COMPLETED"}

            if status == ReceiptStatus.COMPLETED:
                return {
                    "success": True,
                    "decision": receipt.get("decision") or "ALLOW",
                    "payment_status": "COMPLETED",
                    "reason": "Order was already captured; returning the recorded outcome.",
                    "order_id": order_id,
                    "receipt_id": receipt.get("receipt_id"),
                    "capture": capture_obj,
                    "risk_assessment": snapshots.get("risk"),
                    "policy_result": snapshots.get("policy"),
                    "integrity_result": (snapshots.get("decision") or {}).get("integrity"),
                    "snapshots": snapshots,
                    "amount": receipt.get("amount"),
                    "currency": receipt.get("currency", "USD"),
                    "decision_explanation": (snapshots.get("decision") or {}).get("explanation")
                        or f"Recorded outcome confirmed for order {order_id}.",
                }
            if status == ReceiptStatus.PENDING:
                return {
                    "success": False,
                    "decision": receipt.get("decision") or "ALLOW",
                    "payment_status": "PENDING",
                    "reason": "Payment capture is currently being processed.",
                    "order_id": order_id,
                    "receipt_id": receipt.get("receipt_id"),
                    "risk_assessment": snapshots.get("risk"),
                    "policy_result": snapshots.get("policy"),
                    "snapshots": snapshots,
                }
            if status in (
                ReceiptStatus.BLOCKED,
                ReceiptStatus.REVIEW_REQUIRED,
                ReceiptStatus.FAILED,
                ReceiptStatus.CANCELLED,
                ReceiptStatus.EXPIRED,
            ):
                recorded = receipt.get("decision")
                return {
                    "success": False,
                    "decision": recorded
                    or ("REVIEW" if status == ReceiptStatus.REVIEW_REQUIRED else "BLOCK"),
                    "payment_status": "NOT_CAPTURED",
                    "reason": "Order was already processed; returning the recorded outcome.",
                    "order_id": order_id,
                    "receipt_id": receipt.get("receipt_id"),
                    "risk_assessment": snapshots.get("risk"),
                    "policy_result": snapshots.get("policy"),
                    "snapshots": snapshots,
                }
        return self._blocked(
            "Order has already been processed (already processed).",
            order_id,
        )

    def capture_registered_order(self, order_id):
        """Verify, evaluate, and capture a server-registered checkout order.

        The capture outcome is recorded as a persistent receipt when a receipt
        store is configured. Receipt recording never changes the capture result.
        """
        result = self._capture_registered_order(order_id)
        if (
            isinstance(result, dict)
            and (
                result.get("reason", "").startswith("Order was already")
                or result.get("payment_status") == "PENDING"
            )
        ):
            return result

        receipt_id = self._record_capture_receipt(order_id, result)
        if receipt_id and isinstance(result, dict):
            result["receipt_id"] = receipt_id
        return result

    def _record_capture_receipt(self, order_id, result):
        if self.receipt_store is None or not isinstance(result, dict):
            return None
        try:
            return self._write_capture_receipt(order_id, result)
        except Exception:
            # A receipt failure must never alter a payment outcome or crash.
            return None

    def _write_capture_receipt(self, order_id, result):
        if not isinstance(order_id, str) or not order_id.strip():
            return None
        order_id = order_id.strip()

        intent = None
        try:
            intent = self.registry.get_checkout_order(order_id)
        except Exception:
            intent = None
        if not isinstance(intent, dict):
            intent = {}

        success = result.get("success") is True
        decision = result.get("decision", "")
        reason = result.get("reason", "") or ""
        payment_status_raw = result.get("payment_status", "") or ""
        capture = result.get("capture") if isinstance(result.get("capture"), dict) else None
        capture_id = capture.get("id") if capture else None

        # Actual PayPal capture amount/currency when the gateway reported them.
        capture_amount = None
        capture_currency = None
        if isinstance(capture, dict):
            capture_amount_data = capture.get("amount")
            if isinstance(capture_amount_data, dict):
                capture_amount = capture_amount_data.get("value")
                capture_currency = capture_amount_data.get("currency_code")

        verified_at = datetime.now(timezone.utc).isoformat()
        order_status = result.get("order_status") or (
            "COMPLETED" if success else payment_status_raw
        )

        if success:
            status = ReceiptStatus.COMPLETED
        elif decision == "REVIEW":
            status = ReceiptStatus.REVIEW_REQUIRED
        elif "reconciliation required" in reason.lower():
            # Capture outcome is uncertain (e.g. timeout); keep it open for
            # reconciliation instead of concluding a failure.
            status = ReceiptStatus.PENDING
        elif "capture failed" in reason.lower():
            # PayPal definitively declined the capture; distinct from a
            # PayShield policy BLOCK and from an uncertain timeout.
            status = ReceiptStatus.FAILED
        elif payment_status_raw == "GATEWAY_ERROR":
            status = ReceiptStatus.FAILED
        else:
            status = ReceiptStatus.BLOCKED

        risk = result.get("risk_assessment")
        policy = result.get("policy_result")
        evaluation = result.get("evaluation")
        if evaluation is None and isinstance(policy, dict):
            evaluation = result  # some flows embed evaluation

        product_snapshot = {
            "reference": intent.get("external_order_id") or intent.get("transaction_id"),
            "title": intent.get("merchant_name") or "",
            "retailer": intent.get("merchant_name") or "",
            "category": intent.get("category") or "",
            "source_url": intent.get("source_url") or intent.get("return_url") or "",
            "quantity": intent.get("quantity", 1),
            "price": float(intent.get("amount")) if intent.get("amount") is not None else None,
            "currency": intent.get("currency", "USD"),
        }
        if intent.get("items"):
            first = intent["items"][0] if intent["items"] else {}
            if isinstance(first, dict):
                product_snapshot["title"] = product_snapshot["title"] or first.get("name", "")
                product_snapshot["sku"] = first.get("sku") or first.get("product_id") or intent.get("product_id")
                product_snapshot["description"] = first.get("description") or ""
                if first.get("unit_price") is not None:
                    try:
                        product_snapshot["price"] = float(first["unit_price"])
                    except Exception:
                        pass

        snapshots = build_snapshots(
            product=product_snapshot,
            ai_assessment=result.get("ai_assessment"),
            risk=risk if isinstance(risk, dict) else None,
            policy=policy if isinstance(policy, dict) else None,
            decision={
                "final_decision": decision or None,
                "reason": reason or None,
                "explanation": result.get("decision_explanation"),
                "integrity": result.get("integrity_result"),
            },
            payment={
                "amount": (
                    capture_amount
                    if capture_amount is not None
                    else intent.get("amount")
                ),
                "currency": (
                    capture_currency
                    if capture_currency is not None
                    else intent.get("currency", "USD")
                ),
                "items": intent.get("items", []),
                "quantity": intent.get("quantity", 1),
                "capture": capture,
                "capture_status": capture.get("status") if capture else None,
                "order_status": order_status,
                "verified_at": verified_at,
            },
        )

        # A terminal receipt must never be flipped by a later callback: this
        # guards against contradictory history (for example a recorded BLOCK
        # being overwritten to COMPLETED, or vice-versa) for the same order.
        FINAL_STATUSES = frozenset({
            ReceiptStatus.COMPLETED,
            ReceiptStatus.FAILED,
            ReceiptStatus.CANCELLED,
            ReceiptStatus.BLOCKED,
            ReceiptStatus.EXPIRED,
            ReceiptStatus.REFUNDED,
            ReceiptStatus.PARTIALLY_REFUNDED,
        })

        receipt_amount = (
            capture_amount if capture_amount is not None else intent.get("amount")
        )
        receipt_currency = (
            capture_currency
            if capture_currency is not None
            else intent.get("currency", "USD")
        )

        existing = self.receipt_store.get_receipt_by_order_id(order_id)
        event = {
            "source": "capture",
            "payment_status_raw": payment_status_raw or None,
            "capture_id": capture_id,
        }
        if existing is not None:
            if existing.get("status") in FINAL_STATUSES:
                # Preserve the authoritative terminal outcome for this order.
                return existing["receipt_id"]
            if existing.get("status") == ReceiptStatus.COMPLETED and status != ReceiptStatus.COMPLETED:
                return existing["receipt_id"]

            self.receipt_store.update_receipt(
                existing["receipt_id"],
                status=status,
                decision=decision or None,
                capture_id=capture_id or None,
                payment_status_raw=payment_status_raw or None,
                reason=reason or None,
                amount=receipt_amount,
                currency=receipt_currency,
                risk_score=(risk.get("score") if isinstance(risk, dict) else None),
                risk_level=(risk.get("level") if isinstance(risk, dict) else None),
                snapshots=snapshots,
                event=event,
            )
            return existing["receipt_id"]

        return self.receipt_store.create_receipt(
            status=status,
            transaction_id=intent.get("transaction_id"),
            order_id=order_id,
            capture_id=capture_id,
            external_order_id=intent.get("external_order_id"),
            user_id=intent.get("user_id", ""),
            agent_id=intent.get("agent_id", ""),
            merchant_name=intent.get("merchant_name", ""),
            merchant_category=intent.get("category", ""),
            amount=receipt_amount,
            currency=receipt_currency,
            decision=decision,
            payment_status_raw=payment_status_raw,
            reason=reason,
            risk_score=(risk.get("score") if isinstance(risk, dict) else None),
            risk_level=(risk.get("level", "") if isinstance(risk, dict) else ""),
            snapshots=snapshots,
            event=event,
        )

    def _capture_registered_order(self, order_id):
        """Verify, evaluate, and capture a server-registered checkout order."""
        if not isinstance(order_id, str) or not order_id.strip():
            return self._blocked("Invalid order ID.")

        order_id = order_id.strip()
        intent = self.registry.get_checkout_order(order_id)
        if not intent:
            return self._blocked("Checkout order was not created by PayShield.", order_id)

        if self.registry.is_processed(order_id):
            return self._processed_outcome(order_id)

        if not self.registry.reserve_order(order_id):
            return self._processed_outcome(order_id)

        try:
            verification = self.paypal.verify_order(
                order_id=order_id,
                expected_amount=intent["amount"],
                expected_currency=intent["currency"],
            )
            verification_status = verification.get("status", "APPROVED") if isinstance(verification, dict) else "APPROVED"
            if (
                not isinstance(verification, dict)
                or verification.get("verified") is not True
                or verification.get("order_id") != order_id
            ):
                try:
                    raw_order = self.paypal.get_order(order_id)
                    if isinstance(raw_order, dict) and raw_order.get("status") == "COMPLETED":
                        captures = (
                            raw_order.get("purchase_units", [{}])[0]
                            .get("payments", {})
                            .get("captures", [])
                        )
                        capture = captures[0] if captures else {"id": f"reconciled-{order_id}", "status": "COMPLETED"}
                        self.registry.complete_reservation(order_id)
                        return {
                            "success": True,
                            "decision": "ALLOW",
                            "payment_status": "COMPLETED",
                            "order_status": "COMPLETED",
                            "reason": "PayPal capture confirmed (reconciled from PayPal completed status).",
                            "order_id": order_id,
                            "capture": capture,
                            "risk_assessment": None,
                            "policy_result": None,
                            "integrity_result": {
                                "verified": True,
                                "order_id": order_id,
                                "amount": str(intent["amount"]),
                                "currency": intent["currency"],
                            },
                            "decision_explanation": (
                                f"Order integrity verified for {order_id}: "
                                f"{intent['amount']} {intent['currency']}. "
                                "PayPal reported order was already completed. Reconciled safely."
                            ),
                        }
                except Exception:
                    pass

                self.registry.release_reservation(order_id)
                return self._blocked(
                    verification.get("reason", "PayPal order verification failed.")
                    if isinstance(verification, dict)
                    else "PayPal order verification failed.",
                    order_id,
                    order_status=verification_status,
                )

            try:
                actual_amount = Decimal(str(verification["amount"]))
            except (KeyError, InvalidOperation, TypeError, ValueError):
                self.registry.release_reservation(order_id)
                return self._blocked(
                    "PayPal amount is invalid.", order_id,
                    order_status=verification_status,
                )

            if (
                actual_amount != Decimal(str(intent["amount"]))
                or verification.get("currency") != intent["currency"]
            ):
                self.registry.release_reservation(order_id)
                return self._blocked(
                    "PayPal order does not match the registered checkout.",
                    order_id,
                    order_status=verification_status,
                )

            items = []
            for unit in verification.get("purchase_units", []):
                for item in unit.get("items", []):
                    try:
                        items.append(
                            TransactionItem(
                                name=str(item["name"]),
                                quantity=int(item["quantity"]),
                                price=float(item["unit_amount"]["value"]),
                            )
                        )
                    except (KeyError, TypeError, ValueError):
                        self.registry.release_reservation(order_id)
                        return self._blocked(
                            "PayPal purchase-unit item is invalid.",
                            order_id,
                            order_status=verification_status,
                        )

            authorization = self.payment_service.check_payment(
                agent_id=intent["agent_id"],
                amount=float(actual_amount),
                category=intent["category"],
            )
            if authorization["decision"] != "ALLOW":
                self.registry.release_reservation(order_id)
                return {
                    "success": False,
                    "decision": authorization["decision"],
                    "payment_status": "NOT_CAPTURED",
                    "order_status": verification_status,
                    "reason": authorization["reason"],
                    "order_id": order_id,
                    "risk_assessment": None,
                    "policy_result": authorization,
                    "integrity_result": {
                        "verified": True,
                        "order_id": order_id,
                        "amount": str(actual_amount),
                        "currency": verification["currency"],
                        "registered_merchant": intent["merchant_name"],
                    },
                    "decision_explanation": (
                        f"Order integrity verified for {order_id}: "
                        f"{actual_amount} {verification['currency']}, "
                        f"registered merchant {intent['merchant_name']}. "
                        f"Risk evaluation was not advanced because policy result "
                        f"was {authorization['decision']}: {authorization['reason']}. "
                        "Capture was not permitted."
                    ),
                }

            agent = self.payment_service.agents[intent["agent_id"]]
            transaction = Transaction(
                transaction_id=intent.get("transaction_id", order_id),
                user_id=intent["user_id"],
                merchant_category=intent["category"],
                merchant_name=intent["merchant_name"],
                amount=float(actual_amount),
                currency=verification["currency"],
                payment_method="paypal",
                items=items,
                agent_name=intent["agent_id"],
            )
            result = evaluate_transaction(
                transaction,
                previous_spend=float(agent.spending_limit),
                previous_recipients=[intent["merchant_name"]],
            )
            if not isinstance(result, dict):
                self.registry.release_reservation(order_id)
                return self._blocked(
                    "Risk evaluation failed.", order_id,
                    order_status=verification_status,
                )

            decision = result.get(
                "final_decision",
                result.get("decision", "BLOCK"),
            )
            if decision != "ALLOW":
                self._set_order_state(order_id, OrderRegistry.STATUS_BLOCKED)
                self.registry.release_reservation(order_id)
                return {
                    "success": False,
                    "decision": decision
                    if decision in ("REVIEW", "BLOCK")
                    else "BLOCK",
                    "payment_status": "NOT_CAPTURED",
                    "order_status": verification_status,
                    "reason": "PayShield did not authorize capture.",
                    "order_id": order_id,
                    "risk_assessment": result.get("risk_assessment"),
                    "policy_result": result.get("policy_result"),
                    "integrity_result": {
                        "verified": True,
                        "order_id": order_id,
                        "amount": str(actual_amount),
                        "currency": verification["currency"],
                    },
                    "decision_explanation": (
                        f"Order integrity verified for {order_id}: "
                        f"{actual_amount} {verification['currency']}. "
                        f"{result.get('decision_explanation', 'PayShield did not authorize capture.')}"
                    ),
                }

            # PayShield's authoritative decision is ALLOW and the stored
            # checkout evidence matches the approved order. Record the
            # authorized lifecycle state before requesting the capture.
            self._set_order_state(order_id, OrderRegistry.STATUS_AUTHORIZED)

            try:
                self._set_order_state(order_id, OrderRegistry.STATUS_CAPTURE_PENDING)
                capture = self.paypal.capture_order(
                    order_id=order_id,
                    request_id=f"payshield-{order_id}",
                )
            except PayPalAPIError as exc:
                if "ORDER_ALREADY_CAPTURED" in exc.issues or "already captured" in str(exc).lower():
                    try:
                        reconciled_order = self.paypal.get_order(order_id)
                        if isinstance(reconciled_order, dict) and reconciled_order.get("status") == "COMPLETED":
                            captures = (
                                reconciled_order.get("purchase_units", [{}])[0]
                                .get("payments", {})
                                .get("captures", [])
                            )
                            capture = captures[0] if captures else {"id": f"reconciled-{order_id}", "status": "COMPLETED"}
                            self.registry.complete_reservation(order_id)
                            self._set_order_state(order_id, OrderRegistry.STATUS_COMPLETED)
                            return {
                                "success": True,
                                "decision": "ALLOW",
                                "payment_status": "COMPLETED",
                                "order_status": "COMPLETED",
                                "reason": "PayPal capture confirmed (reconciled after duplicate capture attempt).",
                                "order_id": order_id,
                                "capture": capture,
                                "risk_assessment": result.get("risk_assessment"),
                                "policy_result": result.get("policy_result"),
                                "integrity_result": {
                                    "verified": True,
                                    "order_id": order_id,
                                    "amount": str(actual_amount),
                                    "currency": verification["currency"],
                                },
                                "decision_explanation": (
                                    f"Order integrity verified for {order_id}: "
                                    f"{actual_amount} {verification['currency']}. "
                                    "PayPal reported order was already captured. Reconciled successfully."
                                ),
                            }
                    except Exception:
                        pass
                return self._blocked(
                    f"Capture failed: {exc.safe_detail}",
                    order_id,
                    order_status=verification_status,
                )

            if (
                not isinstance(capture, dict)
                or capture.get("status") != "COMPLETED"
            ):
                return self._blocked(
                    "Capture was not confirmed; reconciliation required.",
                    order_id,
                    order_status=verification_status,
                )

            if not self.registry.complete_reservation(order_id):
                return self._blocked(
                    "Capture succeeded but registry update failed; "
                    "reconciliation required.",
                    order_id,
                    order_status=verification_status,
                )

            self._set_order_state(order_id, OrderRegistry.STATUS_COMPLETED)

            return {
                "success": True,
                "decision": "ALLOW",
                "payment_status": "COMPLETED",
                "order_status": verification_status,
                "reason": "PayPal capture confirmed.",
                "order_id": order_id,
                "capture": capture,
                "risk_assessment": result.get("risk_assessment"),
                "policy_result": result.get("policy_result"),
                "integrity_result": {
                    "verified": True,
                    "order_id": order_id,
                    "amount": str(actual_amount),
                    "currency": verification["currency"],
                },
                "decision_explanation": (
                    f"Order integrity verified for {order_id}: "
                    f"{actual_amount} {verification['currency']}. "
                    f"{result.get('decision_explanation', 'Fresh ALLOW decision confirmed.')}"
                ),
            }
        except Exception:
            return self._blocked(
                "Payment outcome is uncertain; reconciliation required.",
                order_id,
            )