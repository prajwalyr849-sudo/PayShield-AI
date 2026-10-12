from backend.payment.paypal_client import PayPalClient


class PayPalPaymentService:
    """Verify PayPal orders before PayShield evaluates them."""

    def __init__(self, client=None):
        self.client = client or PayPalClient()

    def verify_order(
        self,
        order_id: str,
        expected_amount: float,
        expected_currency: str = "USD",
    ) -> dict:
        if not order_id or not order_id.strip():
            return {
                "verified": False,
                "reason": "PayPal order ID is required",
            }

        if expected_amount <= 0:
            return {
                "verified": False,
                "reason": "Expected amount must be positive",
            }

        try:
            result = self.client.verify_order(
                order_id=order_id,
                expected_amount=expected_amount,
                expected_currency=expected_currency,
            )
        except Exception:
            # Fail closed if PayPal verification fails.
            return {
                "verified": False,
                "reason": "PayPal order verification failed",
            }

        return result