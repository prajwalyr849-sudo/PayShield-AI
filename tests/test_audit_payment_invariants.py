"""Regression tests for PayShield AI payment consistency and audit invariants."""

from unittest.mock import Mock, patch
from pathlib import Path

import os
import pytest
from fastapi.testclient import TestClient

from backend.main import app, payment_service, order_registry, receipt_store
from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry
from backend.payment.receipts import ReceiptStore, ReceiptStatus
from backend.assistant.guard_buy_service import GuardBuyService, GuardBuyRequest
from backend.assistant.evidence_store import ProductEvidenceStore


@pytest.fixture
def test_setup(tmp_path):
    registry = OrderRegistry(tmp_path / "test_reg.db")
    store = ReceiptStore(tmp_path / "test_receipts.db")
    paypal = Mock()
    service = GuardedCaptureService(
        paypal_client=paypal,
        order_registry=registry,
        receipt_store=store,
    )
    return service, paypal, registry, store


def test_reserve_conflict_with_pending_receipt_returns_pending(test_setup):
    """A concurrent/repeated capture while order is PENDING returns PENDING, not a synthetic BLOCK."""
    service, paypal, registry, store = test_setup
    order_id = "ORDER-PENDING-001"

    registry.register_checkout_order(
        order_id, "99.00", "USD", "agent-001", "electronics", "Sony", "user-1"
    )
    store.create_receipt(
        status=ReceiptStatus.PENDING,
        order_id=order_id,
        decision="ALLOW",
        amount=99.00,
        currency="USD",
        reason="Awaiting buyer approval",
    )
    # Reserve the order as if another capture worker is currently processing it
    assert registry.reserve_order(order_id) is True

    result = service.capture_registered_order(order_id)

    assert result["success"] is False
    assert result["decision"] == "ALLOW"
    assert result["payment_status"] == "PENDING"
    assert "currently being processed" in result["reason"]
    paypal.capture_order.assert_not_called()

    # Verify that the receipt in database was NOT corrupted into BLOCKED
    saved = store.get_receipt_by_order_id(order_id)
    assert saved["status"] == ReceiptStatus.PENDING
    assert saved["decision"] == "ALLOW"


def test_completed_capture_repeat_returns_full_snapshots_and_preserves_receipt(test_setup):
    """Repeated capture calls for an already COMPLETED order echo complete snapshots and never corrupt the receipt."""
    service, paypal, registry, store = test_setup
    order_id = "ORDER-COMPLETED-001"

    registry.register_checkout_order(
        order_id, "49.99", "USD", "agent-001", "services", "Cloud Hosting", "user-2"
    )
    store.create_receipt(
        status=ReceiptStatus.COMPLETED,
        order_id=order_id,
        decision="ALLOW",
        capture_id="CAPTURE-999",
        amount=49.99,
        currency="USD",
        risk_score=10,
        risk_level="LOW",
        snapshots={
            "risk": {"score": 10, "level": "LOW"},
            "policy": {"decision": "ALLOW", "reason": "Within limits"},
            "product": {"title": "Cloud Hosting", "evidence_status": "VERIFIED"},
            "payment": {"capture": {"id": "CAPTURE-999", "status": "COMPLETED"}},
        },
    )
    registry.mark_processed(order_id)

    # Simulate repeated return page refresh or second callback
    result = service.capture_registered_order(order_id)

    assert result["success"] is True
    assert result["decision"] == "ALLOW"
    assert result["payment_status"] == "COMPLETED"
    assert "already captured" in result["reason"]
    assert result["capture"]["id"] == "CAPTURE-999"
    assert result["risk_assessment"]["score"] == 10
    assert result["policy_result"]["decision"] == "ALLOW"
    paypal.capture_order.assert_not_called()

    # Verify database receipt remains pristine with all risk and capture references intact
    saved = store.get_receipt_by_order_id(order_id)
    assert saved["status"] == ReceiptStatus.COMPLETED
    assert saved["capture_id"] == "CAPTURE-999"
    assert saved["risk_score"] == 10
    assert saved["risk_level"] == "LOW"


def test_completed_receipt_never_downgraded_by_failed_write(test_setup):
    """Direct receipt updates must protect COMPLETED receipts from being downgraded to BLOCKED."""
    service, paypal, registry, store = test_setup
    order_id = "ORDER-PROTECTED-001"

    receipt_id = store.create_receipt(
        status=ReceiptStatus.COMPLETED,
        order_id=order_id,
        decision="ALLOW",
        capture_id="CAPTURE-XYZ",
        amount=25.00,
    )

    # Attempt to write a BLOCKED status into this existing receipt
    service._record_capture_receipt(
        order_id,
        {"success": False, "decision": "BLOCK", "reason": "Attempted overwrite"},
    )

    saved = store.get_receipt(receipt_id)
    assert saved["status"] == ReceiptStatus.COMPLETED
    assert saved["decision"] == "ALLOW"
    assert saved["capture_id"] == "CAPTURE-XYZ"


def test_paypal_order_already_completed_reconciles_safely(test_setup):
    """When PayPal reports an order is already COMPLETED, PayShield reconciles without attempting a duplicate capture."""
    service, paypal, registry, store = test_setup
    order_id = "ORDER-PAYPAL-DONE-001"

    registry.register_checkout_order(
        order_id, "120.00", "USD", "agent-001", "office", "Office Depot", "user-3"
    )

    # verify_order returns unapproved because it was already captured
    paypal.verify_order.return_value = {
        "verified": False,
        "reason": "Order is not approved for capture.",
    }
    # get_order confirms it is COMPLETED with capture details
    paypal.get_order.return_value = {
        "id": order_id,
        "status": "COMPLETED",
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {"id": "CAPTURE-RECON-777", "status": "COMPLETED"}
                    ]
                }
            }
        ],
    }

    result = service.capture_registered_order(order_id)

    assert result["success"] is True
    assert result["payment_status"] == "COMPLETED"
    assert result["decision"] == "ALLOW"
    assert result["capture"]["id"] == "CAPTURE-RECON-777"
    assert "reconciled" in result["reason"].lower()
    paypal.capture_order.assert_not_called()
    assert registry.is_processed(order_id) is True


def test_guard_buy_product_evidence_status_preserved(tmp_path):
    """Guard Buy service must persist evidence_status inside product snapshot."""
    from backend.assistant.models import ProductSearchResult

    evidence_store = ProductEvidenceStore(tmp_path / "evidence.db")
    receipt_store = ReceiptStore(tmp_path / "receipts.db")
    service = GuardBuyService(
        evidence_store=evidence_store,
        receipt_store=receipt_store,
    )

    prod = ProductSearchResult(
        id="prod-bose-01",
        product_reference="prod-bose-01",
        title="Bose QuietComfort 45",
        source_url="https://example.com/bose",
        source_domain="example.com",
        retailer="Bose Official",
        price=229.00,
        currency="USD",
        price_verified=True,
        availability="IN_STOCK",
        category="electronics",
        evidence_status="VERIFIED",
        result_type="product",
        search_timestamp="2026-01-01T00:00:00Z",
    )
    product_refs = evidence_store.save_search_results([prod], category="electronics")
    product_ref = product_refs[0]

    req = GuardBuyRequest(
        product_reference=product_ref,
        quantity=1,
        agent_id="agent-001",
        idempotency_key="guard-buy-test-key-1",
    )

    res = service.decide(req, user_id="test-alex")
    assert res.decision == "ALLOW"

    receipt = receipt_store.get_receipt_by_decision_reference(res.decision_reference)
    assert receipt is not None
    product_snap = receipt["snapshots"]["product"]
    assert product_snap["evidence_status"] == "VERIFIED"
    assert product_snap["retailer"] == "Bose Official"


def test_integrations_purchases_evaluates_with_agent_spending_limit():
    """Valid purchases for allowed categories must not be artificially blocked by a 0 baseline."""
    client = TestClient(app)

    payload = {
        "transaction_id": "TX-INT-EVAL-001",
        "external_order_id": "EXT-ORD-001",
        "agent_id": "agent-001",
        "authenticated_client_id": "client-test-01",
        "user_id": "user-integration",
        "merchant_name": "Verified Electronics Inc",
        "category": "electronics",
        "currency": "USD",
        "subtotal": "150.00",
        "total": "150.00",
        "items": [
            {
                "name": "Wireless Keyboard",
                "quantity": 1,
                "unit_price": "150.00",
            }
        ],
    }

    os.environ["PAYSHIELD_INTEGRATION_API_KEY"] = "test-integration-key"

    with patch("backend.main.PayPalClient") as MockPayPalClient:
        instance = MockPayPalClient.return_value
        instance.create_order.return_value = {
            "id": "PAYPAL-ORDER-INT-1",
            "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkout?token=1"}],
        }

        response = client.post(
            "/integrations/purchases",
            json=payload,
            headers={
                "Idempotency-Key": "idemp-int-test-001",
                "X-PayShield-API-Key": "test-integration-key",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["evaluation"]["policy_result"]["decision"] == "ALLOW"
    assert data["decision"] == "ALLOW"
    assert data["evaluation"]["risk_assessment"]["score"] < 50
    assert data["evaluation"]["risk_assessment"]["level"] in ("LOW", "MEDIUM")
    assert data["payment_status"] == "AWAITING_BUYER_APPROVAL"


def test_policy_limits_consistent_across_code_paths():
    """main.py, decision_engine.py, and capture_service.py must share
    DEFAULT_CONSTITUTION so policy limits are identical everywhere."""
    from backend.policy.engine import DEFAULT_CONSTITUTION
    from backend.main import constitution as main_constitution
    from backend.policy.decision_engine import policy as de_policy

    # main.py uses DEFAULT_CONSTITUTION via import alias
    assert main_constitution is DEFAULT_CONSTITUTION
    # decision_engine.py uses DEFAULT_CONSTITUTION via import alias
    assert de_policy is DEFAULT_CONSTITUTION
    # Values match the canonical configuration
    assert DEFAULT_CONSTITUTION.max_auto_payment == 10000
    assert DEFAULT_CONSTITUTION.approval_limit == 60000
    assert DEFAULT_CONSTITUTION.blocked_categories == ["gift_cards"]


def test_integration_purchase_allow_creates_pending_receipt(tmp_path, monkeypatch):
    """An ALLOW integration purchase must create an AWAITING_BUYER_APPROVAL receipt
    bound to the PayPal order ID and transaction ID."""
    from unittest.mock import patch
    from backend.main import app
    from backend.payment.receipts import ReceiptStore, ReceiptStatus
    from fastapi.testclient import TestClient

    import os
    import uuid
    os.environ["PAYSHIELD_INTEGRATION_API_KEY"] = "test-integration-key"
    tmp_receipts = os.path.join(str(tmp_path), "receipts.db")
    tmp_store = ReceiptStore(tmp_receipts)
    run_id = uuid.uuid4().hex[:8]
    idempotency_key = f"idemp-int-receipt-{run_id}"
    order_id_value = f"PAYPAL-ORDER-{run_id}"

    # Monkeypatch the module-level receipt_store so submit_purchase uses our temp store
    import backend.main
    monkeypatch.setattr(backend.main, "receipt_store", tmp_store)

    client = TestClient(app)
    payload = {
        "transaction_id": "TX-INT-RECEIPT-001",
        "external_order_id": "EXT-ORD-RECEIPT-001",
        "agent_id": "agent-001",
        "authenticated_client_id": "client-test-01",
        "user_id": "user-integration-receipt",
        "merchant_name": "Verified Electronics Inc",
        "category": "electronics",
        "currency": "USD",
        "subtotal": "150.00",
        "total": "150.00",
        "items": [
            {"name": "Wireless Keyboard", "quantity": 1, "unit_price": "150.00"}
        ],
    }

    with patch("backend.main.PayPalClient") as MockPayPalClient:
        instance = MockPayPalClient.return_value
        instance.create_order.return_value = {
            "id": order_id_value,
            "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkout?token=1"}],
        }

        response = client.post(
            "/integrations/purchases",
            json=payload,
            headers={
                "Idempotency-Key": idempotency_key,
                "X-PayShield-API-Key": "test-integration-key",
            },
        )

    assert response.status_code == 200
    data = response.json()
    order_id = data["order_id"]

    # Receipt must exist, bound to order_id and transaction_id
    receipt = tmp_store.get_receipt_by_order_id(order_id)
    assert receipt is not None, f"No receipt found for order_id={order_id}; all receipts={tmp_store.list_receipts()}"
    assert receipt["status"] == ReceiptStatus.AWAITING_BUYER_APPROVAL
    assert receipt["decision"] == "ALLOW"
    assert receipt["transaction_id"] == "TX-INT-RECEIPT-001"
    assert receipt["order_id"] == order_id
    assert receipt["amount"] == "150.00"
    assert receipt["currency"] == "USD"


def test_integration_purchase_paypal_failure_creates_failed_receipt(tmp_path, monkeypatch):
    """When PayPal order creation fails after authorization ALLOW, a FAILED
    receipt must be recorded so the attempt is not lost."""
    from unittest.mock import patch
    from backend.main import app
    from backend.payment.paypal_client import PayPalAPIError
    from backend.payment.receipts import ReceiptStore, ReceiptStatus
    from fastapi.testclient import TestClient

    import os
    os.environ["PAYSHIELD_INTEGRATION_API_KEY"] = "test-integration-key"
    tmp_receipts = os.path.join(str(tmp_path), "receipts.db")
    tmp_store = ReceiptStore(tmp_receipts)
    idempotency_key = f"idemp-int-fail-{tmp_path.name}"

    # Monkeypatch the module-level receipt_store so submit_purchase uses our temp store
    import backend.main
    monkeypatch.setattr(backend.main, "receipt_store", tmp_store)

    client = TestClient(app)
    payload = {
        "transaction_id": "TX-INT-FAIL-001",
        "external_order_id": "EXT-ORD-FAIL-001",
        "agent_id": "agent-001",
        "authenticated_client_id": "client-test-01",
        "user_id": "user-integration-fail",
        "merchant_name": "Verified Electronics Inc",
        "category": "electronics",
        "currency": "USD",
        "subtotal": "150.00",
        "total": "150.00",
        "items": [
            {"name": "Wireless Keyboard", "quantity": 1, "unit_price": "150.00"}
        ],
    }

    with patch("backend.main.PayPalClient") as MockPayPalClient:
        instance = MockPayPalClient.return_value
        instance.create_order.side_effect = PayPalAPIError(
            "order creation", 502, "INTERNAL_ERROR", "PayPal down", "debug-123"
        )

        response = client.post(
            "/integrations/purchases",
            json=payload,
            headers={
                "Idempotency-Key": idempotency_key,
                "X-PayShield-API-Key": "test-integration-key",
            },
        )

    assert response.status_code == 502

    # A FAILED receipt must exist for the attempt
    receipt = tmp_store.get_receipt_by_idempotency_key(
        f"purchase:{payload['transaction_id']}"
    )
    assert receipt is not None, f"No receipt found; all receipts={tmp_store.list_receipts()}"
    assert receipt["status"] == ReceiptStatus.FAILED
    assert receipt["decision"] == "ALLOW"
    assert receipt["transaction_id"] == "TX-INT-FAIL-001"
    assert "PayPal down" in receipt["reason"]
