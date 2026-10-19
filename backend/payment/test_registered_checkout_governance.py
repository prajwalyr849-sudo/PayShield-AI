from unittest.mock import Mock

import pytest

from backend.agents.managers import Agent
from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry
from backend.payment.service import PaymentAuthorizationService
from backend.policy.engine import FinancialConstitution
from backend.payment.models import Transaction
from backend.payshield.service import evaluate_transaction


def make_payment_service(limit=10000, categories=("electronics",), blocked=()):
    return PaymentAuthorizationService(
        agents={
            "agent-001": Agent(
                agent_id="agent-001",
                name="Test Agent",
                allowed_categories=categories,
                spending_limit=limit,
            )
        },
        constitution=FinancialConstitution(
            max_auto_payment=10000,
            approval_limit=60000,
            blocked_categories=list(blocked),
        ),
    )


def make_registered_service(tmp_path, amount="79.99", category="electronics",
                            merchant="Amazon US", payment_service=None):
    paypal = Mock()
    registry = OrderRegistry(tmp_path / "checkout.db")
    registry.register_checkout_order(
        "ORDER-REGRESSION-1",
        amount,
        "USD",
        "agent-001",
        category,
        merchant,
        "sandbox-user",
        transaction_id="TXN-REGRESSION-1",
    )
    paypal.verify_order.return_value = {
        "verified": True,
        "status": "APPROVED",
        "order_id": "ORDER-REGRESSION-1",
        "amount": amount,
        "currency": "USD",
        "purchase_units": [{"amount": {"value": amount, "currency_code": "USD"}}],
    }
    paypal.capture_order.return_value = {"status": "COMPLETED", "id": "CAPTURE-1"}
    return (
        GuardedCaptureService(
            paypal_client=paypal,
            order_registry=registry,
            payment_service=payment_service,
        ),
        paypal,
        registry,
    )


def test_valid_low_risk_sandbox_order_captures(tmp_path):
    service, paypal, registry = make_registered_service(tmp_path)

    result = service.capture_registered_order("ORDER-REGRESSION-1")

    assert result["success"] is True
    assert result["decision"] == "ALLOW"
    assert result["risk_assessment"]["score"] == 0
    assert result["policy_result"]["decision"] == "ALLOW"
    assert result["integrity_result"]["verified"] is True
    paypal.capture_order.assert_called_once()
    assert registry.is_processed("ORDER-REGRESSION-1") is True


def test_spending_limit_violation_never_captures(tmp_path):
    service, paypal, registry = make_registered_service(
        tmp_path,
        amount="79.99",
        payment_service=make_payment_service(limit=50),
    )

    result = service.capture_registered_order("ORDER-REGRESSION-1")

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    assert "spending limit" in result["reason"].lower()
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-REGRESSION-1") is False


def test_policy_block_never_captures(tmp_path):
    service, paypal, registry = make_registered_service(
        tmp_path,
        category="gift_cards",
        payment_service=make_payment_service(
            categories=("gift_cards",),
            blocked=("gift_cards",),
        ),
    )

    result = service.capture_registered_order("ORDER-REGRESSION-1")

    assert result["success"] is False
    assert result["decision"] == "BLOCK"
    assert "blocked" in result["reason"].lower()
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-REGRESSION-1") is False


def test_order_tampering_never_captures(tmp_path):
    service, paypal, registry = make_registered_service(tmp_path)
    paypal.verify_order.return_value["amount"] = "80.00"

    result = service.capture_registered_order("ORDER-REGRESSION-1")

    assert result["success"] is False
    assert "match" in result["reason"].lower()
    paypal.capture_order.assert_not_called()
    assert registry.is_processed("ORDER-REGRESSION-1") is False


def test_genuine_high_risk_transaction_remains_blocked():
    transaction = Transaction(
        transaction_id="TXN-HIGH-RISK",
        user_id="sandbox-user",
        merchant_category="electronics",
        merchant_name="Unknown Merchant",
        amount=60001,
        currency="USD",
        payment_method="paypal",
    )

    result = evaluate_transaction(transaction)

    assert result["risk_score"] == 100
    assert result["risk_level"] == "HIGH"
    assert result["final_decision"] == "BLOCK"
    assert result["risk_assessment"]["amount_risk"] == 60
    assert result["risk_assessment"]["recipient_risk"] == 40
