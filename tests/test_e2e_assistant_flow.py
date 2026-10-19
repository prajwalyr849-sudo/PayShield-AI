"""End-to-End integration test covering the complete user and agent journey:
Discovery -> Intent Parsing -> 3-Product Curation -> PVS/WTS Scoring ->
Guarded Checkout -> Order Registry Registration -> PayPal Capture -> Audit Logging.
"""

import json
from unittest.mock import Mock
import pytest

from backend.assistant.ai_client import AssistantAIService
from backend.assistant.checkout_service import AssistantCheckoutService
from backend.assistant.models import AssistantCheckoutRequest, ShoppingQueryRequest
from backend.assistant.recommendation_engine import RecommendationEngine
from backend.assistant.scoring import ScoringEngine
from backend.payment.capture_service import GuardedCaptureService
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalClient


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    audit_file = tmp_path / "e2e_audit.jsonl"
    orders_db = tmp_path / "e2e_orders.sqlite3"
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(audit_file))
    monkeypatch.setenv("PAYSHIELD_DB_PATH", str(orders_db))

    order_registry = OrderRegistry(db_path=orders_db)

    mock_paypal = Mock(spec=PayPalClient)
    mock_paypal.create_order.return_value = {
        "id": "PAYPAL-E2E-ORDER-888",
        "status": "CREATED",
        "links": [
            {
                "href": "https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-E2E-ORDER-888",
                "rel": "approve",
            }
        ],
    }
    def mock_get_order(order_id):
        registered = order_registry.get_checkout_order(order_id)
        amt = registered["amount"] if registered else "79.99"
        return {
            "id": order_id,
            "status": "APPROVED",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": "USD",
                        "value": str(amt),
                    }
                }
            ],
        }

    def mock_verify_order(order_id, expected_amount, expected_currency="USD"):
        registered = order_registry.get_checkout_order(order_id)
        amt = registered["amount"] if registered else expected_amount
        curr = registered["currency"] if registered else expected_currency
        return {
            "verified": True,
            "status": "APPROVED",
            "order_id": order_id,
            "amount": str(amt),
            "currency": str(curr),
            "purchase_units": [
                {
                    "items": [
                        {
                            "name": "Wireless Headphones",
                            "quantity": 1,
                            "unit_amount": {"value": str(amt)},
                        }
                    ]
                }
            ],
        }

    mock_paypal.verify_order.side_effect = mock_verify_order
    mock_paypal.get_order.side_effect = mock_get_order
    mock_paypal.capture_order.return_value = {
        "id": "PAYPAL-E2E-ORDER-888",
        "status": "COMPLETED",
        "purchase_units": [
            {
                "payments": {
                    "captures": [
                        {
                            "id": "CAPTURE-E2E-123",
                            "status": "COMPLETED",
                            "amount": {"currency_code": "USD", "value": "79.99"},
                        }
                    ]
                }
            }
        ],
    }

    checkout_service = AssistantCheckoutService(
        order_registry=order_registry,
        paypal_client=mock_paypal,
    )
    capture_service = GuardedCaptureService(
        order_registry=order_registry,
        paypal_client=mock_paypal,
    )

    return {
        "audit_file": audit_file,
        "order_registry": order_registry,
        "mock_paypal": mock_paypal,
        "checkout_service": checkout_service,
        "capture_service": capture_service,
        "scoring_engine": ScoringEngine(),
        "ai_service": AssistantAIService(),
    }


def test_complete_end_to_end_shopping_and_governance_journey(test_env):
    ai_service: AssistantAIService = test_env["ai_service"]
    scoring_engine: ScoringEngine = test_env["scoring_engine"]
    rec_engine = RecommendationEngine(scoring_engine)
    checkout_service: AssistantCheckoutService = test_env["checkout_service"]
    capture_service: GuardedCaptureService = test_env["capture_service"]
    mock_paypal = test_env["mock_paypal"]
    audit_file = test_env["audit_file"]

    # Step 1: User asks assistant for product discovery
    raw_query = "Find high-performance wireless noise-cancelling headphones under $250 for travel"
    intent = ai_service.parse_intent(raw_query)

    assert intent.category == "electronics"
    assert intent.target_budget == 250.0
    assert any("noise" in r for r in intent.key_requirements) or "wireless" in intent.key_requirements

    # Step 2: Engine curates exactly 3 recommendations with evidence scoring
    recommendations = rec_engine.get_three_recommendations(intent)
    assert len(recommendations) == 3
    assert [r.rank for r in recommendations] == [1, 2, 3]

    for rec in recommendations:
        assert rec.value_score.overall_score >= 10
        assert rec.trust_score.overall_trust >= 10
        assert rec.product.data_source in {"live", "sourced", "demo"}
        assert len(rec.why_recommended) > 10

    # Step 3: User selects top recommended product for guarded checkout
    selected_product = recommendations[0].product
    checkout_req = AssistantCheckoutRequest(
        product_id=selected_product.id,
        quantity=1,
        agent_id="agent-001",
        user_id="user-alex-smith",
        idempotency_key="e2e-idemp-001",
    )

    checkout_res = checkout_service.process_checkout(checkout_req)

    assert checkout_res.decision == "ALLOW"
    assert checkout_res.payment_status == "AWAITING_BUYER_APPROVAL"
    assert checkout_res.order_id == "PAYPAL-E2E-ORDER-888"
    assert "paypal.com" in checkout_res.approval_url
    assert checkout_res.evaluation["payment_authorized"] is True
    mock_paypal.create_order.assert_called_once()

    # Step 4: Buyer approves order in PayPal Sandbox, and PayShield executes Guarded Capture
    capture_result = capture_service.capture_registered_order("PAYPAL-E2E-ORDER-888")
    print("\nCAPTURE RESULT:", capture_result)

    assert capture_result["success"] is True
    assert capture_result["payment_status"] == "COMPLETED"
    assert capture_result["decision"] == "ALLOW"
    mock_paypal.verify_order.assert_called_once()
    mock_paypal.capture_order.assert_called_once_with(
        order_id="PAYPAL-E2E-ORDER-888",
        request_id="payshield-PAYPAL-E2E-ORDER-888",
    )

    # Step 5: Double capture replay must strictly fail closed
    replay_result = capture_service.capture_registered_order("PAYPAL-E2E-ORDER-888")
    assert replay_result["decision"] == "BLOCK"
    assert "already processed" in replay_result["reason"]

    # Step 6: Verify persistent audit trail was recorded
    assert audit_file.exists()
    audit_lines = [json.loads(line) for line in audit_file.read_text(encoding="utf-8").strip().splitlines()]
    event_types = [entry.get("event_type") or entry.get("decision") for entry in audit_lines]
    assert len(audit_lines) >= 2
