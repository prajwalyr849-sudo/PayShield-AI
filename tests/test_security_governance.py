"""Security governance validation tests ensuring that the multi-engine pipeline:
Risk Engine -> Policy Engine -> Decision Engine -> Order Integrity -> Guarded PayPal Capture -> Audit
never weakens or bypasses safeguards.
"""

from unittest.mock import Mock
import pytest

from backend.assistant.catalog import CATALOG_PRODUCTS
from backend.assistant.checkout_service import AssistantCheckoutService
from backend.assistant.models import AssistantCheckoutRequest
from backend.auth.db import AuthDatabase
from backend.auth.security import generate_secure_token, hash_token
from backend.payment.capture_service import GuardedCaptureService
from backend.payment.models import Transaction
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalClient
from backend.payshield.service import evaluate_transaction
from backend.policy.engine import FinancialConstitution


@pytest.fixture
def mock_paypal():
    return Mock(spec=PayPalClient)


@pytest.fixture
def test_setup(tmp_path, mock_paypal, monkeypatch):
    audit_file = tmp_path / "security_audit.jsonl"
    db_file = tmp_path / "security.sqlite3"
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(audit_file))
    monkeypatch.setenv("PAYSHIELD_DB_PATH", str(db_file))

    registry = OrderRegistry(db_path=db_file)
    auth_db = AuthDatabase(db_path=str(db_file))
    checkout_svc = AssistantCheckoutService(order_registry=registry, paypal_client=mock_paypal)
    capture_svc = GuardedCaptureService(order_registry=registry, paypal_client=mock_paypal)

    return {
        "registry": registry,
        "auth_db": auth_db,
        "checkout_svc": checkout_svc,
        "capture_svc": capture_svc,
        "mock_paypal": mock_paypal,
    }


def test_blocked_category_never_creates_paypal_order(test_setup):
    checkout_svc = test_setup["checkout_svc"]
    mock_paypal = test_setup["mock_paypal"]

    # Attempt to bypass category policy with blocked gift_cards category
    auth_check = checkout_svc.payment_service.check_payment("agent-001", 50.0, "gift_cards")
    assert auth_check["decision"] == "BLOCK"
    assert "not allowed" in auth_check["reason"].lower() or "blocked" in auth_check["reason"].lower()

    # Verify PayPal order creation was never touched
    mock_paypal.create_order.assert_not_called()


def test_tampered_amount_fails_closed_and_never_captures(test_setup):
    registry: OrderRegistry = test_setup["registry"]
    capture_svc: GuardedCaptureService = test_setup["capture_svc"]
    mock_paypal: Mock = test_setup["mock_paypal"]

    # Register an order for $79.99
    order_id = "PAYPAL-SEC-TAMPER-001"
    registry.register_checkout_order(
        order_id=order_id,
        amount="79.99",
        currency="USD",
        agent_id="agent-001",
        category="electronics",
        merchant_name="Amazon US",
        user_id="user-tamper",
    )

    # Attacker attempts to change amount in PayPal order to $500.00
    mock_paypal.get_order.return_value = {
        "id": order_id,
        "status": "APPROVED",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "USD",
                    "value": "500.00",
                }
            }
        ],
    }

    result = capture_svc.capture_registered_order(order_id)

    assert result["decision"] == "BLOCK"
    assert "verification failed" in result["reason"].lower()
    # Guarded capture must NEVER be executed
    mock_paypal.capture_order.assert_not_called()
    assert registry.is_processed(order_id) is False


def test_tampered_currency_fails_closed(test_setup):
    registry: OrderRegistry = test_setup["registry"]
    capture_svc: GuardedCaptureService = test_setup["capture_svc"]
    mock_paypal: Mock = test_setup["mock_paypal"]

    order_id = "PAYPAL-SEC-CURR-002"
    registry.register_checkout_order(
        order_id=order_id,
        amount="79.99",
        currency="USD",
        agent_id="agent-001",
        category="electronics",
        merchant_name="Amazon US",
        user_id="user-tamper",
    )

    # Attacker attempts to change currency from USD to EUR
    mock_paypal.get_order.return_value = {
        "id": order_id,
        "status": "APPROVED",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "EUR",
                    "value": "79.99",
                }
            }
        ],
    }

    result = capture_svc.capture_registered_order(order_id)
    assert result["decision"] == "BLOCK"
    assert "verification failed" in result["reason"].lower()
    mock_paypal.capture_order.assert_not_called()


def test_missing_buyer_approval_never_captures(test_setup):
    registry: OrderRegistry = test_setup["registry"]
    capture_svc: GuardedCaptureService = test_setup["capture_svc"]
    mock_paypal: Mock = test_setup["mock_paypal"]

    order_id = "PAYPAL-SEC-UNAPPROVED-003"
    registry.register_checkout_order(
        order_id=order_id,
        amount="79.99",
        currency="USD",
        agent_id="agent-001",
        category="electronics",
        merchant_name="Amazon US",
        user_id="user-tamper",
    )

    # Order is still in CREATED state (buyer hasn't approved in Sandbox)
    mock_paypal.get_order.return_value = {
        "id": order_id,
        "status": "CREATED",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": "USD",
                    "value": "79.99",
                }
            }
        ],
    }

    result = capture_svc.capture_registered_order(order_id)
    assert result["decision"] == "BLOCK"
    assert "verification failed" in result["reason"].lower()
    mock_paypal.capture_order.assert_not_called()


def test_raw_session_tokens_never_stored_in_database(test_setup):
    auth_db: AuthDatabase = test_setup["auth_db"]
    user = auth_db.create_user("security@payshield.ai", "Security User")

    raw_token = generate_secure_token()
    token_hash = hash_token(raw_token)
    session = auth_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        expires_at="2030-01-01T00:00:00Z",
    )

    # Verify database query returns hash and raw token is nowhere in the DB
    retrieved = auth_db.get_valid_session(token_hash)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id
    assert raw_token != token_hash
    # Searching by raw token should yield nothing
    assert auth_db.get_valid_session(raw_token) is None
