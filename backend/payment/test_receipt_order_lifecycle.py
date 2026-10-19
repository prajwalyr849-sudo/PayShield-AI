"""Regression tests for PayPal order-to-receipt lifecycle.

These tests guard Priority 3 behavior: every PayPal order created by PayShield
is bound to a receipt from creation, the receipt records the actual verified
PayPal outcome (status, capture, amount, currency, capture id, verification
timestamp), and terminal receipts can never be flipped by later callbacks.

PayPal is mocked -- no live money is used.
"""

from datetime import timezone
from unittest.mock import Mock, patch

import pytest

from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry
from backend.payment.receipts import ReceiptStore, ReceiptStatus
from backend.payment.paypal_client import PayPalAPIError

FAKE_CAPTURE = {
    "id": "CAPTURE-LIFECYCLE-1",
    "status": "COMPLETED",
    "amount": {"currency_code": "USD", "value": "25.00"},
}


def _verified(verified=True, status="APPROVED", amount="25.00", currency="USD",
              order_id="ORDER-LIFECYCLE-1"):
    return {
        "verified": verified,
        "status": status,
        "order_id": order_id,
        "amount": amount,
        "currency": currency,
        "purchase_units": [
            {"amount": {"value": amount, "currency_code": currency}}
        ],
    }


def _make_service(tmp_path, receipt_store=None, paypal=None):
    registry = OrderRegistry(tmp_path / "checkout.db")
    registry.register_checkout_order(
        "ORDER-LIFECYCLE-1",
        "25.00",
        "USD",
        "agent-001",
        "services",
        "Sandbox merchant",
        "sandbox-user",
        transaction_id="TXN-LIFECYCLE-1",
    )
    if paypal is None:
        paypal = Mock()
        paypal.verify_order.return_value = _verified()
        paypal.capture_order.return_value = dict(FAKE_CAPTURE)
    service = GuardedCaptureService(
        paypal_client=paypal,
        order_registry=registry,
        receipt_store=receipt_store,
    )
    return service, paypal, registry


def test_receipt_exists_at_order_creation_bound_to_order_id(tmp_path):
    """A receipt is linked to the PayPal order ID at creation (AWAITING_BUYER_APPROVAL)."""
    store = ReceiptStore(tmp_path / "receipts.db")
    service, paypal, registry = _make_service(tmp_path, receipt_store=store)
    paypal.capture_order.return_value = dict(FAKE_CAPTURE)

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value={
            "final_decision": "ALLOW",
            "risk_assessment": {"score": 0, "level": "LOW"},
            "policy_result": {"decision": "ALLOW", "reason": "within limit"},
        },
    ):
        result = service.capture_registered_order("ORDER-LIFECYCLE-1")

    assert result["success"] is True
    receipt = store.get_receipt_by_order_id("ORDER-LIFECYCLE-1")
    assert receipt is not None
    assert receipt["status"] == ReceiptStatus.COMPLETED
    assert receipt["decision"] == "ALLOW"
    assert receipt["order_id"] == "ORDER-LIFECYCLE-1"
    assert receipt["transaction_id"] == "TXN-LIFECYCLE-1"
    assert receipt["capture_id"] == "CAPTURE-LIFECYCLE-1"


def test_receipt_persists_actual_paypal_capture_data(tmp_path):
    """The receipt records actual PayPal capture amount/currency, status and timestamp."""
    store = ReceiptStore(tmp_path / "receipts.db")
    service, paypal, registry = _make_service(tmp_path, receipt_store=store)
    paypal.capture_order.return_value = dict(FAKE_CAPTURE)

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value={
            "final_decision": "ALLOW",
            "risk_assessment": {"score": 0, "level": "LOW"},
            "policy_result": {"decision": "ALLOW", "reason": "within limit"},
        },
    ):
        service.capture_registered_order("ORDER-LIFECYCLE-1")

    receipt = store.get_receipt_by_order_id("ORDER-LIFECYCLE-1")
    snap = receipt["snapshots"]["payment"]
    # Actual PayPal capture amount/currency, not just the registered intent.
    assert receipt["amount"] == "25.00"
    assert receipt["currency"] == "USD"
    assert receipt["capture_id"] == "CAPTURE-LIFECYCLE-1"
    assert snap["amount"] == "25.00"
    assert snap["currency"] == "USD"
    assert snap["capture_status"] == "COMPLETED"
    assert snap["order_status"] == "APPROVED"
    assert "verified_at" in snap and snap["verified_at"]


def test_receipt_separates_paypal_status_from_payshield_decision(tmp_path):
    """PayPal capture status and PayShield decision are distinct fields."""
    store = ReceiptStore(tmp_path / "receipts.db")
    service, paypal, registry = _make_service(tmp_path, receipt_store=store)
    paypal.capture_order.return_value = dict(FAKE_CAPTURE)

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value={
            "final_decision": "ALLOW",
            "risk_assessment": {"score": 12, "level": "LOW"},
            "policy_result": {"decision": "ALLOW", "reason": "within limit"},
        },
    ):
        result = service.capture_registered_order("ORDER-LIFECYCLE-1")

    assert result["decision"] == "ALLOW"
    assert result["payment_status"] == "COMPLETED"
    receipt = store.get_receipt_by_order_id("ORDER-LIFECYCLE-1")
    assert receipt["decision"] == "ALLOW"          # PayShield authorization
    assert receipt["status"] == ReceiptStatus.COMPLETED  # PayPal payment outcome
    assert receipt["snapshots"]["decision"]["final_decision"] == "ALLOW"
    assert receipt["snapshots"]["payment"]["capture"]["status"] == "COMPLETED"


def test_block_or_review_never_captures_no_receipt_completed(tmp_path):
    """BLOCK/REVIEW decisions never produce a COMPLETed receipt."""
    store = ReceiptStore(tmp_path / "receipts.db")

    for decision in ("BLOCK", "REVIEW"):
        order_id = f"ORDER-LIFECYCLE-{decision}"
        registry = OrderRegistry(tmp_path / f"checkout_{decision}.db")
        registry.register_checkout_order(
            order_id, "25.00", "USD", "agent-001", "services",
            "Sandbox merchant", "sandbox-user", transaction_id=f"TXN-{decision}",
        )
        paypal = Mock()
        paypal.verify_order.return_value = _verified(order_id=order_id)
        service = GuardedCaptureService(
            paypal_client=paypal, order_registry=registry, receipt_store=store,
        )

        with patch(
            "backend.payment.capture_service.evaluate_transaction",
            return_value={
                "final_decision": decision,
                "risk_assessment": {"score": 90, "level": "HIGH"},
                "policy_result": {"decision": "ALLOW", "reason": "within limit"},
            },
        ):
            result = service.capture_registered_order(order_id)

        assert result["success"] is False
        assert result["decision"] == decision
        assert result["payment_status"] == "NOT_CAPTURED"
        paypal.capture_order.assert_not_called()
        receipt = store.get_receipt_by_order_id(order_id)
        assert receipt["status"] != ReceiptStatus.COMPLETED
        assert receipt["decision"] == decision
        assert receipt["capture_id"] is None


def test_terminal_receipt_is_not_flipped_by_later_callback(tmp_path):
    """A recorded BLOCKED receipt is not overwritten to COMPLETED by a retry."""
    store = ReceiptStore(tmp_path / "receipts.db")
    service, paypal, registry = _make_service(tmp_path, receipt_store=store)
    # Pre-record a terminal BLOCKED receipt for this order (e.g. from a failed
    # earlier attempt or a manual block), then attempt capture again.
    store.create_receipt(
        status=ReceiptStatus.BLOCKED,
        order_id="ORDER-LIFECYCLE-1",
        transaction_id="TXN-LIFECYCLE-1",
        user_id="sandbox-user",
        agent_id="agent-001",
        merchant_name="Sandbox merchant",
        merchant_category="services",
        amount="25.00",
        currency="USD",
        decision="BLOCK",
        payment_status_raw="NOT_CAPTURED",
        reason="Earlier block.",
    )

    paypal.verify_order.return_value = _verified()
    paypal.capture_order.return_value = dict(FAKE_CAPTURE)
    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value={
            "final_decision": "ALLOW",
            "risk_assessment": {"score": 0, "level": "LOW"},
            "policy_result": {"decision": "ALLOW", "reason": "within limit"},
        },
    ):
        service.capture_registered_order("ORDER-LIFECYCLE-1")

    # The terminal BLOCKED receipt is not flipped to COMPLETED by a later
    # callback; history is preserved for this exact attempt.
    receipt = store.get_receipt_by_order_id("ORDER-LIFECYCLE-1")
    assert receipt["status"] == ReceiptStatus.BLOCKED
    assert receipt["decision"] == "BLOCK"
    assert receipt["capture_id"] is None


def test_api_failure_records_failed_not_completed(tmp_path):
    """A definitive PayPal API failure never produces a COMPLETED/fake-success receipt."""
    store = ReceiptStore(tmp_path / "receipts.db")
    service, paypal, registry = _make_service(tmp_path, receipt_store=store)
    paypal.capture_order.side_effect = PayPalAPIError(
        "capture", 402, "INVALID_PAYMENT", "Gateway declined capture", "debug-1"
    )

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value={
            "final_decision": "ALLOW",
            "risk_assessment": {"score": 0, "level": "LOW"},
            "policy_result": {"decision": "ALLOW", "reason": "within limit"},
        },
    ):
        result = service.capture_registered_order("ORDER-LIFECYCLE-1")

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    receipt = store.get_receipt_by_order_id("ORDER-LIFECYCLE-1")
    assert receipt["status"] == ReceiptStatus.FAILED
    assert receipt["status"] != ReceiptStatus.COMPLETED
    assert receipt["decision"] == "BLOCK"


def test_duplicate_callback_is_idempotent_no_double_capture(tmp_path):
    """Repeated capture callbacks do not double-capture or contradict the receipt."""
    store = ReceiptStore(tmp_path / "receipts.db")
    service, paypal, registry = _make_service(tmp_path, receipt_store=store)
    paypal.capture_order.return_value = dict(FAKE_CAPTURE)

    with patch(
        "backend.payment.capture_service.evaluate_transaction",
        return_value={
            "final_decision": "ALLOW",
            "risk_assessment": {"score": 0, "level": "LOW"},
            "policy_result": {"decision": "ALLOW", "reason": "within limit"},
        },
    ):
        first = service.capture_registered_order("ORDER-LIFECYCLE-1")
        second = service.capture_registered_order("ORDER-LIFECYCLE-1")

    assert first["success"] is True
    assert second["success"] is True
    assert paypal.capture_order.call_count == 1
    receipt = store.get_receipt_by_order_id("ORDER-LIFECYCLE-1")
    assert receipt["status"] == ReceiptStatus.COMPLETED
    assert receipt["capture_id"] == "CAPTURE-LIFECYCLE-1"
