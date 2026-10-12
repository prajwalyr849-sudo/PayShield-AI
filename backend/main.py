from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from backend.audit.audit_router import router as audit_router
import os
from decimal import Decimal
from backend.payment.paypal_client import PayPalAPIError, PayPalClient
from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry
from backend.payment.models import Transaction, TransactionItem
from backend.payshield.service import evaluate_transaction


from backend.agents.managers import Agent
from backend.payment.service import PaymentAuthorizationService
from backend.policy.engine import FinancialConstitution


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
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Idempotency-Key", "X-PayShield-API-Key"],
)

app.include_router(audit_router)
constitution = FinancialConstitution(
    max_auto_payment=10000,
    approval_limit=60000,
    blocked_categories=["gift_cards"]
)

agents = {
    "agent-001": Agent(
        agent_id="agent-001",
        name="Payment Agent",
        allowed_categories=["food", "groceries", "office", "services", "software", "travel"],
        spending_limit=10000,
    )
}

payment_service = PaymentAuthorizationService(agents, constitution)
order_registry = OrderRegistry()
capture_service = GuardedCaptureService(order_registry=order_registry)


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
    evaluation = evaluate_transaction(transaction)
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
            raise HTTPException(status_code=409, detail="Purchase already submitted.")
        return {
            "transaction_id": purchase.transaction_id,
            "external_order_id": purchase.external_order_id,
            "order_id": order_id,
            "decision": "ALLOW",
            "payment_status": "AWAITING_BUYER_APPROVAL",
            "approval_url": approval_url,
            "evaluation": evaluation,
        }
        if not order_registry.save_idempotent_response(idempotency_key, response):
            return order_registry.get_idempotent_response(idempotency_key) or response
        return response
    except HTTPException:
        raise
    except PayPalAPIError as exc:
        raise HTTPException(status_code=502, detail=exc.safe_detail) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
class CreatePayPalOrderRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")
    agent_id: str = "agent-001"
    category: str = "services"
    merchant_name: str = "Sandbox merchant"
    user_id: str = "sandbox-user"


@app.post("/paypal/orders")
def create_paypal_order(request: CreatePayPalOrderRequest):
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
        if not order_id or not order_registry.register_checkout_order(
            order_id=order_id,
            amount=f"{request.amount:.2f}",
            currency=request.currency,
            agent_id=request.agent_id,
            category=request.category,
            merchant_name=request.merchant_name,
            user_id=request.user_id,
        ):
            raise RuntimeError("Unable to register checkout order.")

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