from unittest.mock import Mock

from backend.payment.paypal_service import PayPalPaymentService


def test_verified_order():
    client = Mock()
    client.verify_order.return_value = {
        "verified": True,
        "reason": "Order verified",
        "order_id": "TEST-ORDER-1",
        "status": "COMPLETED",
    }

    service = PayPalPaymentService(client)

    result = service.verify_order(
        "TEST-ORDER-1", 5000, "INR"
    )

    assert result["verified"] is True
    client.verify_order.assert_called_once()


def test_empty_order_id_is_rejected():
    client = Mock()
    service = PayPalPaymentService(client)

    result = service.verify_order("", 5000, "INR")

    assert result["verified"] is False
    client.verify_order.assert_not_called()


def test_paypal_failure_fails_closed():
    client = Mock()
    client.verify_order.side_effect = RuntimeError("API error")
    service = PayPalPaymentService(client)

    result = service.verify_order(
        "TEST-ORDER-2", 5000, "INR"
    )

    assert result["verified"] is False
    assert "failed" in result["reason"].lower()