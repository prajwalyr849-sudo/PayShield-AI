"""Secure checkout service connecting AI assistant recommendations to PayShield's
governed Risk Engine, Policy Engine, Order Integrity, and PayPal Sandbox workflow.
"""

import os
import uuid
from decimal import Decimal
from typing import Optional

from backend.agents.managers import Agent
from backend.assistant.catalog import CATALOG_PRODUCTS
from backend.assistant.models import (
    AssistantCheckoutRequest,
    AssistantCheckoutResponse,
    ProductItem,
)
from backend.payment.capture_service import GuardedCaptureService
from backend.payment.models import Transaction, TransactionItem
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalAPIError, PayPalClient
from backend.payment.service import PaymentAuthorizationService
from backend.payshield.service import evaluate_transaction
from backend.policy.engine import FinancialConstitution


class AssistantCheckoutService:
    """Executes guarded checkout for assistant-recommended purchases."""

    def __init__(
        self,
        order_registry: Optional[OrderRegistry] = None,
        payment_service: Optional[PaymentAuthorizationService] = None,
        paypal_client: Optional[PayPalClient] = None,
    ):
        self.order_registry = order_registry or OrderRegistry()
        if payment_service:
            self.payment_service = payment_service
        else:
            constitution = FinancialConstitution(
                max_auto_payment=10000,
                approval_limit=60000,
                blocked_categories=["gift_cards"],
            )
            agents = {
                "agent-001": Agent(
                    agent_id="agent-001",
                    name="Payment Agent",
                    allowed_categories=["food", "groceries", "office", "services", "software", "travel", "electronics"],
                    spending_limit=10000,
                )
            }
            self.payment_service = PaymentAuthorizationService(agents, constitution)
        self.paypal_client = paypal_client or PayPalClient()

    def start_authorized_checkout(
        self,
        *,
        amount: float,
        currency: str,
        agent_id: str,
        category: str,
        merchant_name: str,
        user_id: str,
        transaction_id: str,
        external_order_id: str,
        items: list[dict],
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Create and register a PayPal Sandbox order after an authoritative ALLOW.

        This is the only path that talks to PayPal for a Guard Buy checkout. It
        must never be called for REVIEW or BLOCK decisions.
        """
        if idempotency_key:
            previous = self.order_registry.get_idempotent_response(idempotency_key)
            if previous is not None:
                return previous

        frontend_url = os.getenv(
            "PAYSHIELD_FRONTEND_URL", "http://localhost:5173"
        ).rstrip("/")
        order = self.paypal_client.create_order(
            amount=f"{amount:.2f}",
            currency=currency.upper(),
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
            raise RuntimeError("PayPal did not return an approval link.")

        if not self.order_registry.register_checkout_order(
            order_id=order_id,
            amount=f"{amount:.2f}",
            currency=currency.upper(),
            agent_id=agent_id,
            category=category,
            merchant_name=merchant_name,
            user_id=user_id,
            transaction_id=transaction_id,
            external_order_id=external_order_id,
            items=items,
        ):
            raise RuntimeError("Checkout order was already registered.")

        response = {
            "transaction_id": transaction_id,
            "order_id": order_id,
            "decision": "ALLOW",
            "payment_status": "AWAITING_BUYER_APPROVAL",
            "approval_url": approval_url,
        }
        if idempotency_key:
            self.order_registry.save_idempotent_response(idempotency_key, response)
        return response

    def process_checkout(self, request: AssistantCheckoutRequest) -> AssistantCheckoutResponse:
        # 1. Idempotency check
        if request.idempotency_key:
            previous = self.order_registry.get_idempotent_response(request.idempotency_key)
            if previous is not None:
                return AssistantCheckoutResponse(**previous)

        # 2. Retrieve verified product from catalog
        product = next((p for p in CATALOG_PRODUCTS if p.id == request.product_id), None)
        if not product:
            raise ValueError(f"Product '{request.product_id}' not found in catalog.")

        total_amount = round(product.price * request.quantity, 2)
        txn_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        # 3. Agent and Constitution authorization check
        auth_check = self.payment_service.check_payment(
            agent_id=request.agent_id,
            amount=total_amount,
            category=product.category,
        )

        if auth_check["decision"] != "ALLOW":
            resp_data = {
                "transaction_id": txn_id,
                "product_id": product.id,
                "decision": auth_check["decision"],
                "payment_status": "REVIEW_REQUIRED" if auth_check["decision"] == "REVIEW" else "BLOCKED",
                "total_amount": total_amount,
                "currency": "USD",
                "reason": auth_check.get("reason", "Payment failed policy checks."),
                "evaluation": None,
            }
            if request.idempotency_key:
                self.order_registry.save_idempotent_response(request.idempotency_key, resp_data)
            return AssistantCheckoutResponse(**resp_data)

        # 4. Multi-engine evaluation: Risk Engine -> Policy Engine -> Decision Engine -> Audit
        transaction = Transaction(
            transaction_id=txn_id,
            user_id=request.user_id or "demo-user",
            merchant_category=product.category,
            merchant_name=product.merchant_name,
            amount=total_amount,
            currency="USD",
            payment_method="paypal",
            items=[
                TransactionItem(
                    name=product.title,
                    quantity=request.quantity,
                    price=product.price,
                )
            ],
            agent_name=request.agent_id,
        )

        known_merchants = list({p.merchant_name for p in CATALOG_PRODUCTS})
        agent_limit = 1000.0
        if self.payment_service and request.agent_id in self.payment_service.agents:
            agent_limit = float(self.payment_service.agents[request.agent_id].spending_limit)

        evaluation = evaluate_transaction(
            transaction,
            previous_spend=agent_limit,
            previous_recipients=known_merchants,
        )

        if evaluation["final_decision"] != "ALLOW":
            resp_data = {
                "transaction_id": txn_id,
                "product_id": product.id,
                "decision": evaluation["final_decision"],
                "payment_status": "REVIEW_REQUIRED" if evaluation["final_decision"] == "REVIEW" else "BLOCKED",
                "total_amount": total_amount,
                "currency": "USD",
                "reason": evaluation.get("decision_reason", "Risk assessment blocked this transaction."),
                "evaluation": evaluation,
            }
            if request.idempotency_key:
                self.order_registry.save_idempotent_response(request.idempotency_key, resp_data)
            return AssistantCheckoutResponse(**resp_data)

        # 5. Create PayPal Sandbox Order
        frontend_url = os.getenv("PAYSHIELD_FRONTEND_URL", "http://localhost:5173").rstrip("/")
        try:
            order = self.paypal_client.create_order(
                amount=f"{total_amount:.2f}",
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
                raise RuntimeError("PayPal did not return an approval link.")

            # 6. Register order with OrderRegistry for cryptographic integrity & anti-tamper
            self.order_registry.register_checkout_order(
                order_id=order_id,
                amount=f"{total_amount:.2f}",
                currency="USD",
                agent_id=request.agent_id,
                category=product.category,
                merchant_name=product.merchant_name,
                user_id=request.user_id or "demo-user",
                transaction_id=txn_id,
                external_order_id=f"EXT-{txn_id}",
                items=[{
                    "name": product.title,
                    "sku": product.id,
                    "quantity": request.quantity,
                    "unit_price": str(product.price),
                }],
            )

            resp_data = {
                "transaction_id": txn_id,
                "product_id": product.id,
                "order_id": order_id,
                "decision": "ALLOW",
                "payment_status": "AWAITING_BUYER_APPROVAL",
                "total_amount": total_amount,
                "currency": "USD",
                "approval_url": approval_url,
                "reason": "Payment authorized by PayShield Governance Engine.",
                "evaluation": evaluation,
            }
            if request.idempotency_key:
                self.order_registry.save_idempotent_response(request.idempotency_key, resp_data)
            return AssistantCheckoutResponse(**resp_data)

        except PayPalAPIError as exc:
            # Safe diagnostic failure without revealing credentials
            resp_data = {
                "transaction_id": txn_id,
                "product_id": product.id,
                "decision": "BLOCK",
                "payment_status": "GATEWAY_ERROR",
                "total_amount": total_amount,
                "currency": "USD",
                "reason": exc.safe_detail,
                "evaluation": evaluation,
            }
            return AssistantCheckoutResponse(**resp_data)
