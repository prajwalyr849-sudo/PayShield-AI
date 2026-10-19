from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from backend.assistant.router import router as assistant_router
from backend.audit.audit_router import router as audit_router
from backend.auth.router import router as auth_router
from backend.auth.dependencies import get_optional_current_user
from backend.auth.models import User
from backend.settings.router import router as settings_router
import os
import sqlite3
from decimal import Decimal
from backend.payment.paypal_client import PayPalAPIError, PayPalClient
from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry
from backend.payment.receipts import ReceiptStatus, ReceiptStore, build_snapshots
from backend.payment.receipt_router import router as receipt_router
from backend.payment.models import Transaction, TransactionItem
from backend.payshield.service import evaluate_transaction


from backend.agents.managers import Agent
from backend.payment.service import PaymentAuthorizationService
from backend.policy.engine import DEFAULT_CONSTITUTION as constitution


app = FastAPI(
    title="PayShield AI",
    description="Trust and governance layer for agentic commerce",
    version="0.1.0"
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "PAYSHIELD_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Idempotency-Key", "X-PayShield-API-Key"],
)

app.include_router(audit_router)
app.include_router(auth_router)
app.include_router(assistant_router)
app.include_router(receipt_router)
app.include_router(settings_router)

agents = {
    "agent-001": Agent(
        agent_id="agent-001",
        name="Payment Agent",
        allowed_categories=["food", "groceries", "office", "services", "software", "travel", "electronics"],
        spending_limit=10000,
    )
}

payment_service = PaymentAuthorizationService(agents, constitution)
order_registry = OrderRegistry()
receipt_store = ReceiptStore()
capture_service = GuardedCaptureService(
    order_registry=order_registry,
    receipt_store=receipt_store,
    payment_service=payment_service,
)


class PaymentRequest(BaseModel):
    agent_id: str
    amount: float
    category: str


class PurchaseItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    sku: str = Field(default="", max_length=100)
    quantity: int = Field(gt=0, le=10000)
    unit_price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class PurchaseRequest(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=100)
    external_order_id: str = Field(min_length=1, max_length=100)
    agent_id: str = Field(min_length=1, max_length=100)
    authenticated_client_id: str = Field(min_length=1, max_length=100)
    merchant_name: str = Field(min_length=1, max_length=200)
    merchant_id: str = Field(default="", max_length=100)
    user_id: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    items: list[PurchaseItem] = Field(min_length=1, max_length=100)
    subtotal: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    tax: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    shipping: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    total: Decimal = Field(gt=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def validate_totals(self):
        calculated_subtotal = sum(
            (item.unit_price * item.quantity for item in self.items),
            Decimal("0"),
        )
        if calculated_subtotal != self.subtotal:
            raise ValueError("Subtotal does not match the supplied items.")
        calculated_total = (
            self.subtotal + self.tax + self.shipping - self.discount
        )
        if calculated_total != self.total or calculated_total <= 0:
            raise ValueError("Total does not match the purchase breakdown.")
        if self.currency.upper() != "USD":
            raise ValueError("PayPal Sandbox purchases must use USD.")
        return self


@app.get("/")
def root():
    return {
        "name": "PayShield AI",
        "status": "online"
    }


@app.get("/health")
def health():
    """Readiness probe exposing component status without any secrets."""
    db_path = os.getenv("PAYSHIELD_DB_PATH", "payshield_payments.sqlite3")
    db_status = "ok"
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_status = "unavailable"

    audit_path = os.getenv(
        "PAYSHIELD_AUDIT_LOG",
        os.path.join("data", "audit_log.jsonl"),
    )
    audit_status = (
        "ok"
        if os.path.exists(audit_path) and os.access(audit_path, os.R_OK)
        else "not_initialized"
    )
    base_url = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "application": {"name": app.title, "version": app.version},
        "components": {
            "api": {"status": "ok"},
            "database": {"status": db_status},
            "audit_log": {"status": audit_status},
        },
        "providers": {
            "channel3": {"configured": bool(os.getenv("CHANNEL3_API_KEY"))},
            "live_search_fallback": {
                "configured": bool(os.getenv("ENDLESS_SEARCH_KEY")),
                "enabled": os.getenv("PAYSHIELD_LIVE_SEARCH_FALLBACK", "").strip().lower()
                in ("1", "true", "yes"),
            },
            "paypal_sandbox": {"configured": "sandbox.paypal.com" in base_url.lower()},
        },
    }


@app.post("/check-payment")
def check_payment(payment: PaymentRequest):
    return payment_service.check_payment(
        payment.agent_id,
        payment.amount,
        payment.category,
    )


def require_integration_key(api_key: str | None) -> str:
    expected = os.getenv("PAYSHIELD_INTEGRATION_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Purchase integration is not configured.",
        )
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid integration credentials.")
    return expected


def _record_purchase_outcome(purchase, decision, reason, evaluation=None):
    """Persist a receipt for a non-captured purchase outcome."""
    try:
        evaluation = evaluation if isinstance(evaluation, dict) else {}
        receipt_store.create_receipt(
            status=(
                ReceiptStatus.REVIEW_REQUIRED
                if decision == "REVIEW"
                else ReceiptStatus.BLOCKED
            ),
            transaction_id=purchase.transaction_id,
            external_order_id=purchase.external_order_id,
            user_id=purchase.user_id,
            agent_id=purchase.agent_id,
            # A deterministic key keeps repeated integration submissions for the
            # same transaction from creating duplicate receipts.
            idempotency_key=f"purchase:{purchase.transaction_id}",
            merchant_name=purchase.merchant_name,
            merchant_category=purchase.category,
            amount=purchase.total,
            currency="USD",
            decision=decision,
            payment_status_raw="REVIEW_REQUIRED" if decision == "REVIEW" else "BLOCKED",
            reason=reason,
            risk_score=evaluation.get("risk_score"),
            risk_level=evaluation.get("risk_level", "") or "",
            snapshots=build_snapshots(
                risk=evaluation.get("risk_assessment"),
                policy=evaluation.get("policy_result"),
                decision={"final_decision": decision, "reason": reason},
                payment={
                    "amount": f"{purchase.total:.2f}",
                    "currency": "USD",
                    "items": [item.model_dump(mode="json") for item in purchase.items],
                },
            ),
            event={"source": "purchase_integration"},
        )
    except Exception:
        return


def _record_paypal_creation_failure(purchase, evaluation, reason: str) -> None:
    """Record a FAILED receipt when PayPal order creation fails after authorization.

    PayShield authorized the purchase (ALLOW) but the PayPal order could not be
    created. A FAILED receipt preserves the attempt so the transaction is not
    lost from the audit trail.
    """
    try:
        evaluation = evaluation if isinstance(evaluation, dict) else {}
        receipt_store.create_receipt(
            status=ReceiptStatus.FAILED,
            transaction_id=purchase.transaction_id,
            external_order_id=purchase.external_order_id,
            user_id=purchase.user_id,
            agent_id=purchase.agent_id,
            idempotency_key=f"purchase:{purchase.transaction_id}",
            merchant_name=purchase.merchant_name,
            merchant_category=purchase.category,
            amount=purchase.total,
            currency="USD",
            decision="ALLOW",
            payment_status_raw="FAILED",
            reason=reason,
            risk_score=evaluation.get("risk_score"),
            risk_level=evaluation.get("risk_level", "") or "",
            snapshots=build_snapshots(
                risk=evaluation.get("risk_assessment"),
                policy=evaluation.get("policy_result"),
                decision={"final_decision": "ALLOW", "reason": reason},
                payment={
                    "amount": f"{purchase.total:.2f}",
                    "currency": "USD",
                    "items": [item.model_dump(mode="json") for item in purchase.items],
                },
            ),
            event={"source": "purchase_integration", "stage": "paypal_creation_failed"},
        )
    except Exception:
        return


def _record_authorized_order_receipt(
    *,
    order_id: str,
    transaction_id: str | None,
    external_order_id: str | None,
    user_id: str,
    agent_id: str,
    merchant_name: str,
    merchant_category: str,
    amount,
    currency: str,
    evaluation: Optional[dict] = None,
    idempotency_key: str | None = None,
    reason: str = "PayPal order created; awaiting buyer approval.",
) -> None:
    """Persist a receipt when a PayPal order is created and authorized.

    This binds the receipt to the PayPal order ID and the payment-attempt ID at
    order-creation time, so the receipt tracks the attempt from the moment the
    order exists. Capture later updates the same receipt (idempotent by
    order_id) with the verified PayPal outcome.
    """
    try:
        evaluation = evaluation if isinstance(evaluation, dict) else {}
        receipt_store.create_receipt(
            status=ReceiptStatus.AWAITING_BUYER_APPROVAL,
            transaction_id=transaction_id,
            order_id=order_id,
            external_order_id=external_order_id,
            user_id=user_id or "",
            agent_id=agent_id or "",
            idempotency_key=idempotency_key,
            merchant_name=merchant_name or "",
            merchant_category=merchant_category or "",
            amount=amount,
            currency=currency,
            decision="ALLOW",
            payment_status_raw="AWAITING_BUYER_APPROVAL",
            reason=reason,
            risk_score=evaluation.get("risk_score"),
            risk_level=evaluation.get("risk_level", "") or "",
            snapshots=build_snapshots(
                risk=evaluation.get("risk_assessment"),
                policy=evaluation.get("policy_result"),
                decision={"final_decision": "ALLOW", "reason": reason},
                payment={
                    "amount": f"{float(amount):.2f}"
                    if amount is not None
                    else None,
                    "currency": currency,
                },
            ),
            event={"source": "paypal_order_created"},
        )
    except Exception:
        # A receipt failure must never block order creation.
        return


@app.post("/integrations/purchases")
def submit_purchase(
    purchase: PurchaseRequest,
    x_payshield_api_key: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    require_integration_key(x_payshield_api_key)
    if not idempotency_key or len(idempotency_key) > 200:
        raise HTTPException(status_code=400, detail="Idempotency-Key is required.")
    previous = order_registry.get_idempotent_response(idempotency_key)
    if previous is not None:
        return previous
    authorization = payment_service.check_payment(
        purchase.agent_id,
        float(purchase.total),
        purchase.category,
    )
    if authorization["decision"] != "ALLOW":
        response = {
            "transaction_id": purchase.transaction_id,
            "external_order_id": purchase.external_order_id,
            "decision": authorization["decision"],
            "payment_status": (
                "REVIEW_REQUIRED"
                if authorization["decision"] == "REVIEW"
                else "BLOCKED"
            ),
            "reason": authorization["reason"],
        }
        order_registry.save_idempotent_response(idempotency_key, response)
        _record_purchase_outcome(
            purchase,
            authorization["decision"],
            authorization["reason"],
            evaluation={"policy_result": authorization},
        )
        return response

    transaction = Transaction(
        transaction_id=purchase.transaction_id,
        user_id=purchase.user_id,
        merchant_category=purchase.category,
        merchant_name=purchase.merchant_name,
        amount=float(purchase.total),
        currency="USD",
        payment_method="paypal",
        items=[
            TransactionItem(
                name=item.name,
                quantity=item.quantity,
                price=float(item.unit_price),
            )
            for item in purchase.items
        ],
        agent_name=purchase.agent_id,
    )
    agent = agents.get(purchase.agent_id)
    spending_limit = float(agent.spending_limit) if agent else 10000.0
    evaluation = evaluate_transaction(
        transaction,
        previous_spend=spending_limit,
        previous_recipients=[purchase.merchant_name],
    )
    if evaluation["final_decision"] != "ALLOW":
        response = {
            **evaluation,
            "external_order_id": purchase.external_order_id,
            "payment_status": (
                "REVIEW_REQUIRED"
                if evaluation["final_decision"] == "REVIEW"
                else "BLOCKED"
            ),
        }
        order_registry.save_idempotent_response(idempotency_key, response)
        _record_purchase_outcome(
            purchase,
            evaluation["final_decision"],
            evaluation.get("decision_reason", ""),
            evaluation=evaluation,
        )
        return response

    # Atomically reserve the agent's spending budget for this purchase attempt.
    # The check and the reservation happen in a single transaction so that
    # concurrent requests cannot collectively exceed the configured budget.
    budget_reserved = order_registry.reserve_agent_budget(
        agent_id=purchase.agent_id,
        amount=float(purchase.total),
        idempotency_key=idempotency_key,
        spending_limit=spending_limit,
    )
    if not budget_reserved:
        response = {
            "transaction_id": purchase.transaction_id,
            "external_order_id": purchase.external_order_id,
            "decision": "BLOCK",
            "payment_status": "BLOCKED",
            "reason": (
                "Spending limit exceeded: this purchase would exceed the "
                "agent's configured spending budget."
            ),
        }
        order_registry.save_idempotent_response(idempotency_key, response)
        _record_purchase_outcome(
            purchase,
            "BLOCK",
            response["reason"],
            evaluation={"policy_result": {"decision": "BLOCK", "reason": response["reason"]}},
        )
        return response

    client = PayPalClient()
    frontend_url = os.getenv(
        "PAYSHIELD_FRONTEND_URL",
        "http://localhost:5173",
    ).rstrip("/")
    try:
        order = client.create_order(
            amount=f"{purchase.total:.2f}",
            currency="USD",
            return_url=f"{frontend_url}/checkout/return",
            cancel_url=f"{frontend_url}/checkout?cancelled=1",
        )
        order_id = order.get("id")
        approval_url = next(
            (
                link["href"]
                for link in order.get("links", [])
                if link.get("rel") in {"approve", "payer-action"}
            ),
            None,
        )
        if not order_id or not approval_url:
            raise RuntimeError("PayPal did not return a usable approval link.")
        if not order_registry.register_checkout_order(
            order_id=order_id,
            amount=f"{purchase.total:.2f}",
            currency="USD",
            agent_id=purchase.agent_id,
            category=purchase.category,
            merchant_name=purchase.merchant_name,
            user_id=purchase.user_id,
            transaction_id=purchase.transaction_id,
            external_order_id=purchase.external_order_id,
            items=[item.model_dump(mode="json") for item in purchase.items],
        ):
            # The PayPal order id is a duplicate: release the budget we just
            # reserved so it is available to other purchase attempts.
            order_registry.release_agent_budget(idempotency_key)
            raise HTTPException(status_code=409, detail="Purchase already submitted.")
        # Bind the PayPal order to this purchase attempt so capture can commit
        # or release the reserved budget against this order.
        order_registry.link_order_to_idempotency_key(order_id, idempotency_key)
        response = {
            "transaction_id": purchase.transaction_id,
            "external_order_id": purchase.external_order_id,
            "order_id": order_id,
            "decision": "ALLOW",
            "payment_status": "AWAITING_BUYER_APPROVAL",
            "approval_url": approval_url,
            "evaluation": evaluation,
        }
        order_registry.save_idempotent_response(idempotency_key, response)
        _record_authorized_order_receipt(
            order_id=order_id,
            transaction_id=purchase.transaction_id,
            external_order_id=purchase.external_order_id,
            user_id=purchase.user_id,
            agent_id=purchase.agent_id,
            merchant_name=purchase.merchant_name,
            merchant_category=purchase.category,
            amount=purchase.total,
            currency="USD",
            evaluation=evaluation,
            idempotency_key=idempotency_key,
        )
        return response
    except HTTPException:
        raise
    except PayPalAPIError as exc:
        order_registry.release_agent_budget(idempotency_key)
        _record_paypal_creation_failure(purchase, evaluation, exc.safe_detail)
        raise HTTPException(status_code=502, detail=exc.safe_detail) from exc
    except (RuntimeError, ValueError) as exc:
        order_registry.release_agent_budget(idempotency_key)
        _record_paypal_creation_failure(purchase, evaluation, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
class CreatePayPalOrderRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")
    agent_id: str = "agent-001"
    category: str = "services"
    merchant_name: str = "Sandbox merchant"
    user_id: str = "sandbox-user"


@app.post("/paypal/orders")
def create_paypal_order(
    request: CreatePayPalOrderRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    base_url = os.getenv(
        "PAYPAL_BASE_URL",
        "https://api-m.sandbox.paypal.com",
    )

    if "sandbox.paypal.com" not in base_url.lower():
        raise HTTPException(
            status_code=503,
            detail="PayShield is configured for Sandbox only.",
        )

    try:
        authorization = payment_service.check_payment(
            request.agent_id,
            float(request.amount),
            request.category,
        )
        if authorization["decision"] == "BLOCK":
            raise HTTPException(status_code=422, detail=authorization["reason"])

        client = PayPalClient()
        frontend_url = os.getenv(
            "PAYSHIELD_FRONTEND_URL",
            "http://localhost:5173",
        ).rstrip("/")
        order = client.create_order(
            amount=str(request.amount),
            currency=request.currency.upper(),
            return_url=f"{frontend_url}/checkout/return",
            cancel_url=f"{frontend_url}/checkout?cancelled=1",
        )
        order_id = order.get("id")
        # Bind the checkout -- and therefore its receipt -- to the authenticated
        # server-side identity whenever a session exists. The client-supplied
        # user_id is only a fallback for unauthenticated/integration use, so a
        # browser can never create a receipt under someone else's id.
        owner_id = (current_user.id if current_user else None) or request.user_id
        if not order_id or not order_registry.register_checkout_order(
            order_id=order_id,
            amount=f"{request.amount:.2f}",
            currency=request.currency,
            agent_id=request.agent_id,
            category=request.category,
            merchant_name=request.merchant_name,
            user_id=owner_id,
        ):
            raise RuntimeError("Unable to register checkout order.")

        # Bind a receipt to this PayPal order at creation time so the attempt is
        # tracked from order creation (linked to order ID and attempt), not only
        # after capture. Capture updates the same receipt idempotently.
        _record_authorized_order_receipt(
            order_id=order_id,
            transaction_id=None,
            external_order_id=None,
            user_id=owner_id,
            agent_id=request.agent_id,
            merchant_name=request.merchant_name,
            merchant_category=request.category,
            amount=f"{request.amount:.2f}",
            currency=request.currency.upper(),
            evaluation=None,
            idempotency_key=order_id,
        )

        approval_url = next(
            (
                link["href"]
                for link in order.get("links", [])
                if link.get("rel") in {"approve", "payer-action"}
            ),
            None,
        )
        if not approval_url:
            raise RuntimeError("PayPal did not return an approval link.")

        return {
            "order_id": order_id,
            "status": order.get("status"),
            "payment_status": "PAYER_ACTION_REQUIRED",
            "approval_url": approval_url,
            "links": order.get("links", []),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PayPalAPIError as exc:
        raise HTTPException(status_code=502, detail=exc.safe_detail) from exc
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="PayPal Sandbox order creation failed.",
        )


@app.post("/paypal/orders/{order_id}/capture")
def capture_paypal_order(order_id: str):
    result = capture_service.capture_registered_order(order_id)
    if result.get("reason", "").endswith("reconciliation required."):
        return result
    return result