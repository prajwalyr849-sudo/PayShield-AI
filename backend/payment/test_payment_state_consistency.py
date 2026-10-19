"""Regression tests for PayShield PayPal payment-state and receipt consistency.

These tests guard the server-side invariants:

* BLOCK / REVIEW never trigger automatic capture.
* Capture happens only after the authoritative PayShield decision is ALLOW and
  the server-verified PayPal order still matches the registered checkout.
* Duplicate callbacks are idempotent (no double capture, no conflicting receipts).
* A browser return is not treated as proof of payment.
* Receipts distinguish the policy-stage result from the final authoritative
  PayShield decision and the actual PayPal capture status.
"""

from unittest.mock import Mock, patch

import pytest

from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalAPIError
from backend.payment.receipts import ReceiptStatus, ReceiptStore


def _verified_order_payload(amount="50.00", currency="USD", status="APPROVED"):
    return {
        "verified": True,
        "status": status,
        "order_id": "ORDER-CONSISTENCY-1",
        "amount": amount,
        "currency": currency,
        "purchase_units": [
            {"amount": {"value": amount, "currency_code": currency}}
        ],
    }


def make_service(tmp_path, receipt_store=None, amount="50.00"):
    paypal = Mock()
    registry = OrderRegistry(tmp_path / "checkout.db")
    registry.register_checkout_order(
        "ORDER-CONSISTENCY-1",
        amount,
        "USD",
        "agent-001",
        "services",
        "Sandbox merchant",
        "sandbox-user",
        transaction_id="TXN-CONSISTENCY-1",
    )
    paypal.verify_order.return_value = _verified_order_payload(amount)
    service = GuardedCaptureService(
        paypal_client=paypal,
        order_registry=registry,
        receipt_store=receipt_store,
    )
    return service, paypal, registry


def _evaluate(decision="ALLOW", policy_decision="ALLOW"):
    return {
        "final_decision": decision,
        "decision": decision,
        "policy_decision": policy_decision,
        "decision_reason": "Policy and risk checks passed.",
        "risk_assessment": {"score": 0, "level": "LOW"},
        "policy_result": {"decision": policy_decision, "reason": "policy ok"},
    }


def test_allow_followed_by_successful_capture_completes(tmp_path):
    """ALLOW + verified PayPal order -> COMPLETED receipt + single capture."""
    service, paypal, registry = make_service(tmp_path)
    receipts = ReceiptStore(tmp_path / "receipts.db")
    service.receipt_store = receipts
    paypal.capture_order.return_value = {"status": "COMPLETED", "id": "CAP-1"}

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value=_evaluate("ALLOW", "ALLOW"),
    ):
        result = service.capture_registered_order("ORDER-CONSISTENCY-1")

    assert result["success"] is True
    assert result["decision"] == "ALLOW"
    assert result["payment_status"] == "COMPLETED"
    paypal.capture_order.assert_called_once_with(
        order_id="ORDER-CONSISTENCY-1", request_id="payshield-ORDER-CONSISTENCY-1"
    )
    assert registry.is_processed("ORDER-CONSISTENCY-1") is True
    assert registry.get_checkout_order("ORDER-CONSISTENCY-1").get(
        "status"
    ) == OrderRegistry.STATUS_COMPLETED
    receipt = receipts.get_receipt_by_order_id("ORDER-CONSISTENCY-1")
    assert receipt["status"] == ReceiptStatus.COMPLETED
    assert receipt["decision"] == "ALLOW"
    assert receipt["capture_id"] == "CAP-1"
    # Capture status is recorded distinctly from the PayShield decision.
    assert receipt["snapshots"]["payment"]["capture"]["status"] == "COMPLETED"


def test_buyer_approval_still_pending_is_not_captured(tmp_path):
    """An order awaiting buyer approval must not be captured."""
    service, paypal, registry = make_service(tmp_path)
    # The PayPal order has not been approved by the buyer yet. Mirror the real
    # client: verify_order reports verified=False when status is not APPROVED.
    paypal.verify_order.return_value = {
        "verified": False,
        "status": "CREATED",
        "reason": "Order is not approved for capture.",
        "order_id": "ORDER-CONSISTENCY-1",
        "amount": "50.00",
        "currency": "USD",
    }

    result = service.capture_registered_order("ORDER-CONSISTENCY-1")

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-CONSISTENCY-1") is False


def test_block_prevents_capture(tmp_path):
    """A PayShield BLOCK must never reach PayPal capture."""
    service, paypal, registry = make_service(tmp_path)
    receipts = ReceiptStore(tmp_path / "receipts.db")
    service.receipt_store = receipts

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value=_evaluate("BLOCK", "ALLOW"),
    ):
        result = service.capture_registered_order("ORDER-CONSISTENCY-1")

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    assert result["payment_status"] == "NOT_CAPTURED"
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-CONSISTENCY-1") is False
    receipt = receipts.get_receipt_by_order_id("ORDER-CONSISTENCY-1")
    assert receipt["status"] == ReceiptStatus.BLOCKED
    assert receipt["decision"] == "BLOCK"


def test_review_prevents_automatic_capture(tmp_path):
    """A PayShield REVIEW must never trigger automatic capture."""
    service, paypal, registry = make_service(tmp_path)
    receipts = ReceiptStore(tmp_path / "receipts.db")
    service.receipt_store = receipts

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value=_evaluate("REVIEW", "ALLOW"),
    ):
        result = service.capture_registered_order("ORDER-CONSISTENCY-1")

    assert result["success"] is False
    assert result["decision"] == "REVIEW"
    assert result["payment_status"] == "NOT_CAPTURED"
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-CONSISTENCY-1") is False
    receipt = receipts.get_receipt_by_order_id("ORDER-CONSISTENCY-1")
    assert receipt["status"] == ReceiptStatus.REVIEW_REQUIRED
    assert receipt["decision"] == "REVIEW"


def test_duplicate_callback_after_completion_is_idempotent(tmp_path):
    """A repeated capture callback must not capture twice or conflict."""
    service, paypal, registry = make_service(tmp_path)
    receipts = ReceiptStore(tmp_path / "receipts.db")
    service.receipt_store = receipts
    paypal.capture_order.return_value = {"status": "COMPLETED", "id": "CAP-1"}

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value=_evaluate("ALLOW", "ALLOW"),
    ):
        first = service.capture_registered_order("ORDER-CONSISTENCY-1")
    assert first["success"] is True
    assert paypal.capture_order.call_count == 1

    replay = service.capture_registered_order("ORDER-CONSISTENCY-1")
    assert replay["success"] is True
    assert replay["decision"] == "ALLOW"
    assert "already captured" in replay["reason"]
    # No second capture request to PayPal.
    assert paypal.capture_order.call_count == 1
    assert registry.is_processed("ORDER-CONSISTENCY-1") is True
    receipt = receipts.get_receipt_by_order_id("ORDER-CONSISTENCY-1")
    assert receipt["status"] == ReceiptStatus.COMPLETED
    assert receipt["capture_id"] == "CAP-1"


def test_paypal_capture_failure_records_failed_not_completed(tmp_path):
    """A definitive PayPal capture failure is FAILED, never COMPLETED."""
    service, paypal, registry = make_service(tmp_path)
    receipts = ReceiptStore(tmp_path / "receipts.db")
    service.receipt_store = receipts
    paypal.capture_order.side_effect = PayPalAPIError(
        "capture", 402, "INVALID_PAYMENT", "Gateway declined capture", "debug-1"
    )

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value=_evaluate("ALLOW", "ALLOW"),
    ):
        result = service.capture_registered_order("ORDER-CONSISTENCY-1")

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    paypal.capture_order.assert_called_once()
    assert registry.is_processed("ORDER-CONSISTENCY-1") is False
    receipt = receipts.get_receipt_by_order_id("ORDER-CONSISTENCY-1")
    assert receipt["status"] == ReceiptStatus.FAILED
    assert receipt["decision"] == "BLOCK"


def test_paypal_capture_timeout_keeps_reservation_for_reconciliation(tmp_path):
    """A capture timeout is PENDING (uncertain) and is not retried blindly."""
    service, paypal, registry = make_service(tmp_path)
    receipts = ReceiptStore(tmp_path / "receipts.db")
    service.receipt_store = receipts
    paypal.capture_order.side_effect = TimeoutError("PayPal gateway timeout")

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value=_evaluate("ALLOW", "ALLOW"),
    ):
        result = service.capture_registered_order("ORDER-CONSISTENCY-1")

    assert result["success"] is False
    assert "reconciliation required" in result["reason"].lower()
    paypal.capture_order.assert_called_once()
    assert registry.is_processed("ORDER-CONSISTENCY-1") is False
    receipt = receipts.get_receipt_by_order_id("ORDER-CONSISTENCY-1")
    assert receipt["status"] == ReceiptStatus.PENDING


def test_amount_or_order_mismatch_before_capture_is_blocked(tmp_path):
    """A PayPal order that does not match the registered checkout is not captured."""
    service, paypal, registry = make_service(tmp_path, amount="50.00")
    receipts = ReceiptStore(tmp_path / "receipts.db")
    service.receipt_store = receipts
    # PayPal reports a different amount than the registered checkout.
    paypal.verify_order.return_value = _verified_order_payload(amount="99.00")

    result = service.capture_registered_order("ORDER-CONSISTENCY-1")

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    assert "match" in result["reason"].lower()
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-CONSISTENCY-1") is False
    receipt = receipts.get_receipt_by_order_id("ORDER-CONSISTENCY-1")
    assert receipt["status"] == ReceiptStatus.BLOCKED


def test_policy_allow_but_authoritative_block_shows_distinct_fields(tmp_path):
    """Policy ALLOW overridden by risk to BLOCK: no capture, receipt separates fields."""
    service, paypal, registry = make_service(tmp_path)
    receipts = ReceiptStore(tmp_path / "receipts.db")
    service.receipt_store = receipts
    # Policy stage allows, but the authoritative final decision blocks (e.g. HIGH risk).
    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value=_evaluate("BLOCK", "ALLOW"),
    ):
        result = service.capture_registered_order("ORDER-CONSISTENCY-1")

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    assert result["payment_status"] == "NOT_CAPTURED"
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-CONSISTENCY-1") is False

    receipt = receipts.get_receipt_by_order_id("ORDER-CONSISTENCY-1")
    assert receipt["status"] == ReceiptStatus.BLOCKED
    # Final authoritative PayShield decision.
    assert receipt["decision"] == "BLOCK"
    # Policy-stage result (distinct from the final decision).
    assert receipt["snapshots"]["policy"]["decision"] == "ALLOW"
    assert receipt["snapshots"]["decision"]["final_decision"] == "BLOCK"
    # No PayPal capture occurred.
    assert receipt["capture_id"] is None
    assert receipt["snapshots"]["payment"].get("capture") is None
