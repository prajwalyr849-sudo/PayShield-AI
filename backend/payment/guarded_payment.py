from backend.payment.models import Transaction
from backend.payment.paypal_client import PayPalClient
from backend.payment.order_registry import OrderRegistry
from backend.payshield.service import evaluate_transaction


class GuardedPaymentService:
    """Verify and evaluate orders before any payment capture."""

    def __init__(self, paypal_client=None, order_registry=None):
        self.paypal = paypal_client or PayPalClient()
        self.registry = order_registry or OrderRegistry()

    def verify_before_capture(
        self,
        order_id: str,
        expected_amount,
        expected_currency: str = "USD",
        decision: str = "BLOCK",
        buyer_approved: bool = False,
        user_id: str = "unknown",
        merchant_name: str = "unknown",
        merchant_category: str = "unknown",
        payment_method: str = "paypal",
        agent_name: str = "unknown",
        agent_confidence: float = 0.0,
    ) -> dict:
        """Run guarded pre-capture checks. Does not capture funds."""

        if not isinstance(order_id, str) or not order_id.strip():
            return {
                "success": False,
                "decision": "BLOCK",
                "reason": "PayPal order ID is required.",
            }

        order_id = order_id.strip()

        if not buyer_approved:
            return {
                "success": False,
                "decision": "BLOCK",
                "reason": "Buyer approval is required.",
                "order_id": order_id,
            }

        # Compatibility with existing tests and callers.
        # This supplied value cannot independently authorize a payment.
        if decision in ("REVIEW", "BLOCK"):
            return {
                "success": False,
                "decision": "BLOCK",
                "reason": "PayShield did not authorize the payment.",
                "order_id": order_id,
            }

        if decision != "ALLOW":
            return {
                "success": False,
                "decision": "BLOCK",
                "reason": "Invalid payment decision.",
                "order_id": order_id,
            }

        try:
            amount = float(expected_amount)
            if amount <= 0:
                raise ValueError("Expected amount must be positive.")

            if not expected_currency or not isinstance(expected_currency, str):
                raise ValueError("Expected currency is required.")

            currency = expected_currency.strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                raise ValueError("Expected currency must be a 3-letter code.")
        except (TypeError, ValueError) as exc:
            return {
                "success": False,
                "decision": "BLOCK",
                "reason": f"Validation failed: {exc}",
                "order_id": order_id,
            }

        
        try:
            if self.registry.is_processed(order_id):
                return{
                    "success":False,
                    "decision":"BLOCK",
                    "reason":"Order has already been processed",
                    "order_id":order_id,
                }

            reserved = self.registry.reserve_order(order_id)

        except (AttributeError,OSError,ValueError):
            return{
                "success":False,
                "decision":"BLOCK",
                "reason":"Unable to reserve order safely",
                "order_id":order_id,

            }


        if not reserved:
            return {
                "success": False,
                "decision": "BLOCK",
                "reason": "Order is already reserved or processed.",
                "order_id": order_id,
            }

        try:
            verification = self.paypal.verify_order(
                order_id=order_id,
                expected_amount=amount,
                expected_currency=currency,
            )

            if not isinstance(verification, dict):
                self.registry.release_reservation(order_id)
                return {
                    "success": False,
                    "decision": "BLOCK",
                    "reason": "PayPal returned an invalid verification response.",
                    "order_id": order_id,
                }

            if not verification.get("verified", False):
                self.registry.release_reservation(order_id)
                return {
                    "success": False,
                    "decision": "BLOCK",
                    "reason": verification.get(
                        "reason",
                        "PayPal order verification failed.",
                    ),
                    "order_id": order_id,
                }

            transaction = Transaction(
                transaction_id=order_id,
                user_id=user_id,
                merchant_category=merchant_category,
                merchant_name=merchant_name,
                amount=amount,
                currency=currency,
                payment_method=payment_method,
                agent_name=agent_name,
                agent_confidence=agent_confidence,
            )

            result = evaluate_transaction(transaction)

            if not isinstance(result, dict):
                self.registry.release_reservation(order_id)
                return {
                    "success": False,
                    "decision": "BLOCK",
                    "reason": "PayShield returned an invalid decision.",
                    "order_id": order_id,
                }

            actual_decision = result.get(
                "final_decision",
                result.get("decision", "BLOCK"),
            )

            if actual_decision not in ("ALLOW", "REVIEW", "BLOCK"):
                actual_decision = "BLOCK"

            if actual_decision != "ALLOW":
                self.registry.release_reservation(order_id)
                return {
                    "success": False,
                    "decision": actual_decision,
                    "reason": result.get(
                        "decision_reason",
                        "PayShield did not authorize the payment.",
                    ),
                    "risk_assessment": result.get("risk_assessment"),
                    "order_id": order_id,
                }

            # Reservation remains active until the future capture workflow
            # completes or explicitly resolves the order.
            return {
                "success": True,
                "decision": "ALLOW",
                "reason": "Pre-capture checks passed. No payment captured.",
                "order_id": order_id,
                "risk_assessment": result.get("risk_assessment"),
            }

        except Exception:
            # Fail closed. Do not release on an unexpected exception because
            # the state of external processing may be uncertain.
            return {
                "success": False,
                "decision": "BLOCK",
                "reason": "Payment verification or evaluation failed.",
                "order_id": order_id,
            }