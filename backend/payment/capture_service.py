"""Safely coordinate PayShield-authorized PayPal captures."""

from decimal import Decimal, InvalidOperation

from backend.payment.models import Transaction, TransactionItem
from backend.payment.paypal_client import PayPalClient
from backend.payment.order_registry import OrderRegistry
from backend.payshield.service import evaluate_transaction


class GuardedCaptureService:
    """Capture an approved PayPal order only after PayShield allows it."""

    def __init__(self, paypal_client=None, order_registry=None):
        self.paypal = paypal_client or PayPalClient()
        self.registry = order_registry or OrderRegistry()

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
    def _blocked(reason, order_id=None):
        return {
            "success": False,
            "decision": "BLOCK",
            "reason": reason,
            "order_id": order_id,
        }

    def capture_registered_order(self, order_id):
        """Verify, evaluate, and capture a server-registered checkout order."""
        if not isinstance(order_id, str) or not order_id.strip():
            return self._blocked("Invalid order ID.")

        order_id = order_id.strip()
        intent = self.registry.get_checkout_order(order_id)
        if not intent:
            return self._blocked("Checkout order was not created by PayShield.", order_id)

        if self.registry.is_processed(order_id):
            return self._blocked("Order has already been processed.", order_id)

        if not self.registry.reserve_order(order_id):
            return self._blocked(
                "Order is already reserved or processed.",
                order_id,
            )

        try:
            verification = self.paypal.verify_order(
                order_id=order_id,
                expected_amount=intent["amount"],
                expected_currency=intent["currency"],
            )
            if (
                not isinstance(verification, dict)
                or verification.get("verified") is not True
                or verification.get("order_id") != order_id
            ):
                self.registry.release_reservation(order_id)
                return self._blocked(
                    verification.get("reason", "PayPal order verification failed.")
                    if isinstance(verification, dict)
                    else "PayPal order verification failed.",
                    order_id,
                )

            try:
                actual_amount = Decimal(str(verification["amount"]))
            except (KeyError, InvalidOperation, TypeError, ValueError):
                self.registry.release_reservation(order_id)
                return self._blocked("PayPal amount is invalid.", order_id)

            if (
                actual_amount != Decimal(str(intent["amount"]))
                or verification.get("currency") != intent["currency"]
            ):
                self.registry.release_reservation(order_id)
                return self._blocked(
                    "PayPal order does not match the registered checkout.",
                    order_id,
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
                        )

            transaction = Transaction(
                transaction_id=order_id,
                user_id=intent["user_id"],
                merchant_category=intent["category"],
                merchant_name=intent["merchant_name"],
                amount=float(actual_amount),
                currency=verification["currency"],
                payment_method="paypal",
                items=items,
                agent_name=intent["agent_id"],
            )
            result = evaluate_transaction(transaction)
            if not isinstance(result, dict):
                self.registry.release_reservation(order_id)
                return self._blocked("Risk evaluation failed.", order_id)

            decision = result.get(
                "final_decision",
                result.get("decision", "BLOCK"),
            )
            if decision != "ALLOW":
                self.registry.release_reservation(order_id)
                return {
                    "success": False,
                    "decision": decision
                    if decision in ("REVIEW", "BLOCK")
                    else "BLOCK",
                    "payment_status": "NOT_CAPTURED",
                    "reason": "PayShield did not authorize capture.",
                    "order_id": order_id,
                    "risk_assessment": result.get("risk_assessment"),
                }

            capture = self.paypal.capture_order(
                order_id=order_id,
                request_id=f"payshield-{order_id}",
            )
            if (
                not isinstance(capture, dict)
                or capture.get("status") != "COMPLETED"
            ):
                return self._blocked(
                    "Capture was not confirmed; reconciliation required.",
                    order_id,
                )

            if not self.registry.complete_reservation(order_id):
                return self._blocked(
                    "Capture succeeded but registry update failed; "
                    "reconciliation required.",
                    order_id,
                )

            return {
                "success": True,
                "decision": "ALLOW",
                "payment_status": "COMPLETED",
                "reason": "PayPal capture confirmed.",
                "order_id": order_id,
                "capture": capture,
                "risk_assessment": result.get("risk_assessment"),
            }
        except Exception:
            return self._blocked(
                "Payment outcome is uncertain; reconciliation required.",
                order_id,
            )