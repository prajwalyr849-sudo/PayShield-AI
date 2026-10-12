from unittest.mock import patch

from backend.payment.guarded_payment import GuardedPaymentService


def make_service():
    from unittest.mock import Mock

    paypal = Mock()
    registry = Mock()
    service = GuardedPaymentService(
        paypal_client=paypal,
        order_registry=registry,
    )

    registry.is_processed.return_value = False
    registry.reserve_order.return_value = True
    paypal.verify_order.return_value = {"verified": True}

    return service, paypal, registry


def test_review_never_proceeds():
    service, paypal, registry = make_service()

    result = service.verify_before_capture(
        order_id="ORDER-1",
        expected_amount=50,
        decision="REVIEW",
        buyer_approved=True,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    paypal.verify_order.assert_not_called()


def test_block_never_proceeds():
    service, paypal, registry = make_service()

    result = service.verify_before_capture(
        order_id="ORDER-2",
        expected_amount=50,
        decision="BLOCK",
        buyer_approved=True,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    paypal.verify_order.assert_not_called()


def test_missing_buyer_approval_is_rejected():
    service, paypal, registry = make_service()

    result = service.verify_before_capture(
        order_id="ORDER-3",
        expected_amount=50,
        decision="ALLOW",
        buyer_approved=False,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    paypal.verify_order.assert_not_called()


def test_processed_order_is_rejected():
    service, paypal, registry = make_service()
    registry.is_processed.return_value = True

    result = service.verify_before_capture(
        order_id="ORDER-4",
        expected_amount=50,
        expected_currency="USD",
        decision="ALLOW",
        buyer_approved=True,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    paypal.verify_order.assert_not_called()


@patch("backend.payment.guarded_payment.evaluate_transaction")
def test_verified_order_passes_pre_capture_checks(mock_evaluate):
    service, paypal, registry = make_service()

    mock_evaluate.return_value = {
        "final_decision": "ALLOW",
        "decision": "ALLOW",
        "decision_reason": "Policy and risk checks passed.",
        "risk_assessment": {"score": 0, "level": "LOW"},
    }

    result = service.verify_before_capture(
        order_id="ORDER-5",
        expected_amount=50,
        expected_currency="USD",
        decision="ALLOW",
        buyer_approved=True,
    )

    assert result["success"] is True
    assert result["decision"] == "ALLOW"
    assert "No payment captured" in result["reason"]


def test_verification_failure_releases_reservation():
    service, paypal, registry = make_service()

    paypal.verify_order.return_value = {
        "verified": False,
        "reason": "Order verification failed",
    }

    result = service.verify_before_capture(
        order_id="ORDER-RECOVERY-1",
        expected_amount=50,
        expected_currency="USD",
        decision="ALLOW",
        buyer_approved=True,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    registry.release_reservation.assert_called_once_with(
        "ORDER-RECOVERY-1"
    )


@patch("backend.payment.guarded_payment.evaluate_transaction")
def test_risk_block_releases_reservation(mock_evaluate):
    service, paypal, registry = make_service()

    mock_evaluate.return_value = {
        "final_decision": "BLOCK",
        "decision": "BLOCK",
        "decision_reason": "High risk",
        "risk_assessment": {"score": 90, "level": "HIGH"},
    }

    result = service.verify_before_capture(
        order_id="ORDER-RECOVERY-2",
        expected_amount=50,
        expected_currency="USD",
        decision="ALLOW",
        buyer_approved=True,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    registry.release_reservation.assert_called_once_with(
        "ORDER-RECOVERY-2"
    )

@patch("backend.payment.guarded_payment.evaluate_transaction")
def test_unexpected_evaluation_error_blocks_and_keeps_reservation(
    mock_evaluate,
):
    service, paypal, registry = make_service()

    mock_evaluate.side_effect = RuntimeError("Unexpected evaluation error")

    result = service.verify_before_capture(
        order_id="ORDER-RECOVERY-3",
        expected_amount=50,
        expected_currency="USD",
        decision="ALLOW",
        buyer_approved=True,
    )

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    registry.release_reservation.assert_not_called()