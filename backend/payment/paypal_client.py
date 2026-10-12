import logging
import os
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PAYPAL_SUPPORTED_CURRENCIES = frozenset({
    "AUD", "BRL", "CAD", "CNY", "CZK", "DKK", "EUR", "HKD",
    "HUF", "ILS", "JPY", "MYR", "MXN", "TWD", "NZD", "NOK",
    "PHP", "PLN", "GBP", "SGD", "SEK", "CHF", "THB", "USD",
})


class PayPalAPIError(RuntimeError):
    """Safe representation of a PayPal API error."""

    def __init__(self, operation, status_code, name, message, debug_id, issues=None):
        self.operation = operation
        self.status_code = status_code
        self.name = name
        self.message = message
        self.debug_id = debug_id
        self.issues = issues or []
        super().__init__(message)

    @property
    def safe_detail(self):
        if "CURRENCY_NOT_SUPPORTED" in self.issues:
            detail = (
                "PayPal does not support INR for this Orders API integration. "
                "Use USD only when the transaction is genuinely denominated in USD."
            )
        else:
            detail = f"PayPal {self.operation} failed: {self.message}"
        if self.debug_id:
            return f"{detail} (debug ID: {self.debug_id})"
        return detail


class PayPalClient:
    """Client for PayPal Checkout Orders API."""

    def __init__(self, base_url=None, timeout=15):
        self.base_url = (
            base_url
            or os.getenv(
                "PAYPAL_BASE_URL",
                "https://api-m.sandbox.paypal.com",
            )
        ).rstrip("/")

        if "sandbox.paypal.com" not in self.base_url.lower():
            raise ValueError("PayShield is configured for Sandbox only.")

        self.client_id = os.getenv("PAYPAL_CLIENT_ID")
        self.client_secret = os.getenv("PAYPAL_CLIENT_SECRET")
        self.timeout = timeout

    def get_access_token(self) -> str:
        """Obtain an OAuth access token from PayPal."""
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET "
                "in your environment."
            )

        response = requests.post(
            f"{self.base_url}/v1/oauth2/token",
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
            data={"grant_type": "client_credentials"},
            timeout=self.timeout,
        )
        self._raise_for_error(response, "authentication")

        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("PayPal did not return an access token.")

        return token

    @staticmethod
    def _raise_for_error(response, operation):
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            name = payload.get("name", "UNKNOWN")
            message = payload.get(
                "message",
                f"PayPal {operation} request failed.",
            )
            debug_id = payload.get("debug_id")
            issues = [
                detail.get("issue")
                for detail in payload.get("details", [])
                if isinstance(detail, dict) and detail.get("issue")
            ]
            logger.error(
                "PayPal %s failed: name=%s message=%s debug_id=%s",
                operation,
                name,
                message,
                debug_id,
            )
            raise PayPalAPIError(
                operation,
                response.status_code,
                name,
                message,
                debug_id,
                issues,
            ) from exc

    def get_order(self, order_id: str) -> dict:
        """Fetch an order directly from PayPal."""
        if not order_id or not order_id.strip():
            raise ValueError("PayPal order ID is required.")

        token = self.get_access_token()
        safe_order_id = quote(order_id.strip(), safe="")

        response = requests.get(
            f"{self.base_url}/v2/checkout/orders/{safe_order_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        self._raise_for_error(response, "order retrieval")
        return response.json()


    def create_order(
        self,
        amount: str,
        currency: str = "USD",
        return_url: str | None = None,
        cancel_url: str | None = None,
    ) -> dict:
        """Create a PayPal Sandbox order for checkout."""
        from decimal import Decimal, InvalidOperation

        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise ValueError("Invalid payment amount.")

        if not value.is_finite() or value <= 0:
            raise ValueError("Payment amount must be positive and finite.")

        if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
            raise ValueError("Currency must be a three-letter code.")
        currency = currency.upper()
        if currency not in PAYPAL_SUPPORTED_CURRENCIES:
            raise ValueError(
                "PayPal Orders API does not support INR for this integration. "
                "Use an INR-capable payment provider; do not convert this "
                "payment to USD."
            )

        token = self.get_access_token()
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency.upper(),
                        "value": f"{value:.2f}",
                    }
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "PAY_NOW",
                    }
                }
            },
        }
        if return_url and cancel_url:
            payload["application_context"] = {
                "return_url": return_url,
                "cancel_url": cancel_url,
            }

        response = requests.post(
            f"{self.base_url}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": __import__("uuid").uuid4().hex,
            },
            json=payload,
            timeout=self.timeout,
        )
        self._raise_for_error(response, "order creation")
        return response.json()

    def verify_order(
        self,
        order_id,
        expected_amount,
        expected_currency="USD",
    ):
        """Verify an approved PayPal order before attempting capture."""
        try:
            expected = Decimal(str(expected_amount))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("Expected amount must be a valid number.")

        if not expected.is_finite() or expected <= 0:
            raise ValueError("Expected amount must be positive and finite.")

        if (
            not isinstance(expected_currency, str)
            or len(expected_currency) != 3
            or not expected_currency.isalpha()
        ):
            raise ValueError("Currency must be a three-letter code.")

        order = self.get_order(order_id)

        if not isinstance(order, dict):
            return {"verified": False, "reason": "Invalid PayPal order response."}

        if order.get("id") != order_id:
            return {"verified": False, "reason": "PayPal order ID mismatch."}

        if order.get("status") != "APPROVED":
            return {
                "verified": False,
                "reason": "Order is not approved for capture.",
            }

        units = order.get("purchase_units", [])
        if len(units) != 1:
            return {
                "verified": False,
                "reason": "Expected exactly one purchase unit.",
            }

        amount_data = units[0].get("amount", {})
        if not isinstance(amount_data, dict):
            return {"verified": False, "reason": "Invalid order amount."}

        try:
            actual = Decimal(str(amount_data["value"]))
        except (KeyError, InvalidOperation, ValueError, TypeError):
            return {"verified": False, "reason": "Invalid order amount."}

        if not actual.is_finite() or actual != expected:
            return {"verified": False, "reason": "Amount mismatch."}

        actual_currency = amount_data.get("currency_code")
        if actual_currency != expected_currency.upper():
            return {"verified": False, "reason": "Currency mismatch."}

        return {
            "verified": True,
            "status": "APPROVED",
            "order_id": order_id,
            "amount": str(actual),
            "currency": actual_currency,
            "purchase_units": units,
        }

    def capture_order(self, order_id: str, request_id: str) -> dict:
        """Capture a buyer-approved PayPal order."""
        if not order_id or not order_id.strip():
            raise ValueError("PayPal order ID is required.")

        if not request_id or not request_id.strip():
            raise ValueError("PayPal request ID is required.")

        token = self.get_access_token()
        safe_order_id = quote(order_id.strip(), safe="")

        response = requests.post(
            f"{self.base_url}/v2/checkout/orders/"
            f"{safe_order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": request_id.strip(),
            },
            json={},
            timeout=self.timeout,
        )
        self._raise_for_error(response, "capture")
        return response.json()
