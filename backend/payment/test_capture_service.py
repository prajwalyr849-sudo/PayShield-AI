"""Tests for PayShield's guarded PayPal capture service."""

from unittest.mock import Mock, patch

import pytest

from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry


def make_service():
    """Create a service with mocked PayPal and registry dependencies."""
    paypal = Mock()
    registry = Mock()

    registry.is_processed.return_value = False
    registry.reserve_order.return_value = True
    registry.complete_reservation.return_value = True

    paypal.verify_order.return_value = {
        "verified": True,
        "status": "APPROVED",
        "order_id": "ORDER-TEST-1",
        "amount": "50",
        "currency": "USD",
    }

    service = GuardedCaptureService(
        paypal_client=paypal,
        order_registry=registry,
    )

    return service, paypal, registry


def run_evaluation(service, decision="ALLOW", transaction=None):
    """Run the service with a controlled risk decision."""
    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value={
            "final_decision": decision,
            "risk_assessment": {"risk_level": "LOW"},
        },
    ):
        return service.capture_authorized_order(
            order_id="ORDER-TEST-1",
            transaction=transaction or Mock(),
            expected_amount=50,
            expected_currency="USD",
            buyer_approved=True,
        )


def test_missing_buyer_approval_never_captures():
    service, paypal, registry = make_service()

    result = service.capture_authorized_order(
        order_id="ORDER-TEST-1",
        transaction=Mock(),
        expected_amount=50,
        expected_currency="USD",
        buyer_approved=False,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    paypal.capture_order.assert_not_called()
    registry.reserve_order.assert_not_called()


def test_authorized_order_captures_once_and_marks_processed():
    service, paypal, registry = make_service()

    paypal.capture_order.return_value = {
        "status": "COMPLETED",
        "id": "ORDER-TEST-1",
    }

    result = run_evaluation(service, decision="ALLOW")

    assert result["success"] is True
    assert result["decision"] == "ALLOW"
    paypal.capture_order.assert_called_once()
    registry.complete_reservation.assert_called_once_with(
        "ORDER-TEST-1"
    )


def test_capture_timeout_keeps_reservation_for_reconciliation():
    service, paypal, registry = make_service()

    paypal.capture_order.side_effect = TimeoutError(
        "Simulated network timeout"
    )

    result = run_evaluation(service, decision="ALLOW")

    assert result["success"] is False
    assert "reconciliation required" in result["reason"].lower()

    paypal.capture_order.assert_called_once()
    registry.complete_reservation.assert_not_called()
    registry.release_reservation.assert_not_called()


@pytest.mark.parametrize("decision", ["BLOCK", "REVIEW"])
def test_block_or_review_never_captures(decision):
    service, paypal, registry = make_service()

    result = run_evaluation(service, decision=decision)

    assert result["success"] is False
    assert result["decision"] == decision

    paypal.capture_order.assert_not_called()
    registry.release_reservation.assert_called_once_with(
        "ORDER-TEST-1"
    )
    registry.complete_reservation.assert_not_called()


def test_already_processed_order_is_never_captured():
    service, paypal, registry = make_service()

    registry.is_processed.return_value = True

    result = service.capture_authorized_order(
        order_id="ORDER-TEST-1",
        transaction=Mock(),
        expected_amount=50,
        expected_currency="USD",
        buyer_approved=True,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    paypal.verify_order.assert_not_called()
    paypal.capture_order.assert_not_called()
    registry.reserve_order.assert_not_called()


def make_registered_service(tmp_path):
    paypal = Mock()
    registry = OrderRegistry(tmp_path / "checkout.db")
    registry.register_checkout_order(
        "ORDER-REGISTERED-1",
        "50.00",
        "USD",
        "agent-001",
        "services",
        "Sandbox merchant",
        "sandbox-user",
    )
    service = GuardedCaptureService(
        paypal_client=paypal,
        order_registry=registry,
    )
    paypal.verify_order.return_value = {
        "verified": True,
        "status": "APPROVED",
        "order_id": "ORDER-REGISTERED-1",
        "amount": "50.00",
        "currency": "USD",
        "purchase_units": [{"amount": {"value": "50.00", "currency_code": "USD"}}],
    }
    return service, paypal, registry


@patch("backend.payment.capture_service.evaluate_transaction")
def test_registered_order_captures_only_after_paypal_verification(
    mock_evaluate,
    tmp_path,
):
    service, paypal, registry = make_registered_service(tmp_path)
    mock_evaluate.return_value = {
        "final_decision": "ALLOW",
        "risk_assessment": {"score": 0, "level": "LOW"},
    }
    paypal.capture_order.return_value = {"status": "COMPLETED", "id": "CAPTURE-1"}

    result = service.capture_registered_order("ORDER-REGISTERED-1")

    assert result["success"] is True
    assert result["payment_status"] == "COMPLETED"
    paypal.verify_order.assert_called_once_with(
        order_id="ORDER-REGISTERED-1",
        expected_amount="50.00",
        expected_currency="USD",
    )
    paypal.capture_order.assert_called_once_with(
        order_id="ORDER-REGISTERED-1",
        request_id="payshield-ORDER-REGISTERED-1",
    )
    assert registry.is_processed("ORDER-REGISTERED-1") is True


@pytest.mark.parametrize("decision", ["BLOCK", "REVIEW"])
@patch("backend.payment.capture_service.evaluate_transaction")
def test_registered_order_never_captures_block_or_review(
    mock_evaluate,
    decision,
    tmp_path,
):
    service, paypal, registry = make_registered_service(tmp_path)
    mock_evaluate.return_value = {
        "final_decision": decision,
        "risk_assessment": {"score": 80, "level": "HIGH"},
    }

    result = service.capture_registered_order("ORDER-REGISTERED-1")

    assert result["success"] is False
    assert result["decision"] == decision
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-REGISTERED-1") is False


def test_registered_order_amount_mismatch_never_captures(tmp_path):
    service, paypal, registry = make_registered_service(tmp_path)
    paypal.verify_order.return_value = {
        "verified": False,
        "reason": "Amount mismatch.",
    }

    result = service.capture_registered_order("ORDER-REGISTERED-1")

    assert result["success"] is False
    assert "amount mismatch" in result["reason"].lower()
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-REGISTERED-1") is False


@patch("backend.payment.capture_service.evaluate_transaction")
def test_registered_order_timeout_keeps_reservation(
    mock_evaluate,
    tmp_path,
):
    service, paypal, registry = make_registered_service(tmp_path)
    mock_evaluate.return_value = {
        "final_decision": "ALLOW",
        "risk_assessment": {"score": 0, "level": "LOW"},
    }
    paypal.capture_order.side_effect = TimeoutError("timeout")

    result = service.capture_registered_order("ORDER-REGISTERED-1")

    assert result["success"] is False
    assert "reconciliation required" in result["reason"].lower()
    assert registry.is_processed("ORDER-REGISTERED-1") is False
    assert registry.reserve_order("ORDER-REGISTERED-1") is False


def test_registered_order_duplicate_never_captures(tmp_path):
    service, paypal, registry = make_registered_service(tmp_path)
    registry.mark_processed("ORDER-REGISTERED-1")

    result = service.capture_registered_order("ORDER-REGISTERED-1")

    assert result["success"] is False
    assert "already been processed" in result["reason"]
    paypal.verify_order.assert_not_called()
    paypal.capture_order.assert_not_called()