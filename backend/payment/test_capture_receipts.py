"""Capture outcomes must be recorded as persistent receipts."""

from unittest.mock import Mock, patch

import pytest

from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry
from backend.payment.receipts import ReceiptStatus, ReceiptStore


def make_service(tmp_path, amount="50.00", category="services"):
    paypal = Mock()
    registry = OrderRegistry(tmp_path / "checkout.db")
    receipts = ReceiptStore(tmp_path / "receipts.db")
    registry.register_checkout_order(
        "ORDER-RECEIPT-1",
        amount,
        "USD",
        "agent-001",
        category,
        "Sandbox merchant",
        "user-1",
        transaction_id="TXN-RECEIPT-1",
    )
    paypal.verify_order.return_value = {
        "verified": True,
        "status": "APPROVED",
        "order_id": "ORDER-RECEIPT-1",
        "amount": amount,
        "currency": "USD",
        "purchase_units": [{"amount": {"value": amount, "currency_code": "USD"}}],
    }
    service = GuardedCaptureService(
        paypal_client=paypal,
        order_registry=registry,
        receipt_store=receipts,
    )
    return service, paypal, receipts


def test_confirmed_capture_records_completed_receipt(tmp_path):
    service, paypal, receipts = make_service(tmp_path)
    paypal.capture_order.return_value = {"status": "COMPLETED", "id": "CAP-1"}

    result = service.capture_registered_order("ORDER-RECEIPT-1")

    assert result["success"] is True
    assert result.get("receipt_id")
    receipt = receipts.get_receipt(result["receipt_id"])
    assert receipt["status"] == ReceiptStatus.COMPLETED
    assert receipt["capture_id"] == "CAP-1"
    assert receipt["user_id"] == "user-1"
    assert receipt["order_id"] == "ORDER-RECEIPT-1"


@patch("backend.payment.capture_service.evaluate_transaction")
def test_block_decision_records_blocked_receipt(mock_evaluate, tmp_path):
    service, _paypal, receipts = make_service(tmp_path)
    mock_evaluate.return_value = {
        "final_decision": "BLOCK",
        "risk_assessment": {"score": 90, "level": "HIGH"},
    }

    result = service.capture_registered_order("ORDER-RECEIPT-1")

    assert result["success"] is False
    receipt = receipts.get_receipt_by_order_id("ORDER-RECEIPT-1")
    assert receipt["status"] == ReceiptStatus.BLOCKED
    assert receipt["risk_score"] == 90


@patch("backend.payment.capture_service.evaluate_transaction")
def test_review_decision_records_review_required_receipt(mock_evaluate, tmp_path):
    service, _paypal, receipts = make_service(tmp_path)
    mock_evaluate.return_value = {
        "final_decision": "REVIEW",
        "risk_assessment": {"score": 50, "level": "MEDIUM"},
    }

    service.capture_registered_order("ORDER-RECEIPT-1")

    receipt = receipts.get_receipt_by_order_id("ORDER-RECEIPT-1")
    assert receipt["status"] == ReceiptStatus.REVIEW_REQUIRED


def test_uncertain_capture_records_pending_receipt(tmp_path):
    service, paypal, receipts = make_service(tmp_path)
    paypal.capture_order.side_effect = TimeoutError("timeout")

    result = service.capture_registered_order("ORDER-RECEIPT-1")

    assert result["success"] is False
    assert "reconciliation required" in result["reason"].lower()
    receipt = receipts.get_receipt_by_order_id("ORDER-RECEIPT-1")
    assert receipt["status"] == ReceiptStatus.PENDING


def test_receipt_recording_failure_does_not_break_capture(tmp_path):
    service, paypal, receipts = make_service(tmp_path)
    paypal.capture_order.return_value = {"status": "COMPLETED", "id": "CAP-2"}
    receipts.get_receipt_by_order_id = Mock(side_effect=RuntimeError("store down"))

    result = service.capture_registered_order("ORDER-RECEIPT-1")

    assert result["success"] is True
    assert "receipt_id" not in result


def test_blocked_capture_overwrites_stale_receipt_decision(tmp_path):
    """A blocked capture must not leave a stale ALLOW decision on the receipt."""
    service, paypal, receipts = make_service(tmp_path)
    receipts.create_receipt(
        status=ReceiptStatus.PENDING,
        order_id="ORDER-RECEIPT-1",
        decision="ALLOW",
        amount="50.00",
    )
    paypal.verify_order.return_value = {"verified": False, "reason": "Amount mismatch."}

    result = service.capture_registered_order("ORDER-RECEIPT-1")

    assert result["success"] is False
    receipt = receipts.get_receipt_by_order_id("ORDER-RECEIPT-1")
    assert receipt["status"] == ReceiptStatus.BLOCKED
    assert receipt["decision"] == "BLOCK"


def test_processed_order_returns_recorded_outcome_without_recapturing(tmp_path):
    """A legitimate retry of a processed order echoes the stored outcome."""
    service, paypal, receipts = make_service(tmp_path)
    paypal.capture_order.return_value = {"status": "COMPLETED", "id": "CAP-7"}

    first = service.capture_registered_order("ORDER-RECEIPT-1")
    assert first["success"] is True

    replay = service.capture_registered_order("ORDER-RECEIPT-1")

    assert replay["success"] is True
    assert replay["decision"] == "ALLOW"
    assert paypal.capture_order.call_count == 1
