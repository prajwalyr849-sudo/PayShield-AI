"""Tests for Assistant guarded checkout and purchasing integration."""

from unittest.mock import Mock
import pytest

from backend.assistant.checkout_service import AssistantCheckoutService
from backend.assistant.models import AssistantCheckoutRequest
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalClient


@pytest.fixture
def mock_paypal():
    client = Mock(spec=PayPalClient)
    client.create_order.return_value = {
        "id": "PAYPAL-ORDER-123",
        "status": "CREATED",
        "links": [
            {"href": "https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-ORDER-123", "rel": "approve"}
        ],
    }
    return client


@pytest.fixture
def checkout_service(tmp_path, mock_paypal, monkeypatch):
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(tmp_path / "checkout_audit.jsonl"))
    registry = OrderRegistry(db_path=tmp_path / "orders.db")
    return AssistantCheckoutService(order_registry=registry, paypal_client=mock_paypal)


def test_assistant_checkout_allowed_order_flow(checkout_service, mock_paypal):
    req = AssistantCheckoutRequest(
        product_id="prod-anker-q30",
        quantity=1,
        agent_id="agent-001",
        user_id="user-sam",
        idempotency_key="idemp-key-001",
    )
    res = checkout_service.process_checkout(req)

    assert res.decision == "ALLOW"
    assert res.payment_status == "AWAITING_BUYER_APPROVAL"
    assert res.order_id == "PAYPAL-ORDER-123"
    assert "paypal.com" in res.approval_url
    assert res.total_amount == 79.99
    assert res.evaluation is not None
    assert res.evaluation["final_decision"] == "ALLOW"
    mock_paypal.create_order.assert_called_once()

    # Replay with idempotency key returns identical cached response without re-calling PayPal
    mock_paypal.create_order.reset_mock()
    replay_res = checkout_service.process_checkout(req)
    assert replay_res.order_id == "PAYPAL-ORDER-123"
    assert replay_res.transaction_id == res.transaction_id
    mock_paypal.create_order.assert_not_called()


def test_assistant_checkout_unknown_product_raises(checkout_service):
    req = AssistantCheckoutRequest(
        product_id="non-existent-product",
        quantity=1,
    )
    with pytest.raises(ValueError) as exc:
        checkout_service.process_checkout(req)
    assert "not found in catalog" in str(exc.value)


def test_assistant_checkout_respects_spending_limit(checkout_service, mock_paypal):
    # Order quantity 50 of MacBook Air ($1499 * 50 = $74,950, which exceeds auto limit of 10k)
    req = AssistantCheckoutRequest(
        product_id="prod-macbook-air-m3",
        quantity=50,
        agent_id="agent-001",
    )
    res = checkout_service.process_checkout(req)

    # Exceeding constitution approval limit (60k) blocks payment
    assert res.decision == "BLOCK"
    assert res.payment_status == "BLOCKED"
    assert res.order_id is None
    assert res.approval_url is None
    # PayPal should NEVER be called for blocked transactions
    mock_paypal.create_order.assert_not_called()
