"""Tests for reference-based Guard Buy decision, review, and Sandbox checkout."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.assistant.checkout_service import AssistantCheckoutService
from backend.assistant.evidence_store import ProductEvidenceStore
from backend.assistant.guard_buy_service import GuardBuyError, GuardBuyService
from backend.assistant.models import (
    GuardBuyCheckoutRequest,
    GuardBuyRequest,
    GuardBuyReviewRequest,
    ProductSearchResult,
)
from backend.assistant.router import guard_buy_review
from backend.auth.models import User
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalClient


def make_result(
    *,
    reference="prod_test",
    title="Test Headphones",
    url="https://shop.example/products/headphones",
    price=99.99,
    verified=True,
    currency="USD",
    result_type="product",
):
    return ProductSearchResult(
        id=reference,
        product_reference=reference,
        title=title,
        source_url=url,
        source_domain="shop.example",
        retailer="shop.example",
        price=price,
        price_verified=verified,
        availability="InStock",
        currency=currency,
        result_type=result_type,
        search_timestamp="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def store(tmp_path):
    return ProductEvidenceStore(db_path=tmp_path / "evidence.db")


@pytest.fixture
def registry(tmp_path):
    return OrderRegistry(db_path=tmp_path / "orders.db")


@pytest.fixture
def mock_paypal():
    client = Mock(spec=PayPalClient)
    client.create_order.return_value = {
        "id": "PAYPAL-GB-1",
        "status": "CREATED",
        "links": [
            {
                "href": "https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-GB-1",
                "rel": "approve",
            }
        ],
    }
    return client


@pytest.fixture
def service(store, registry, mock_paypal, tmp_path, monkeypatch):
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(tmp_path / "guard_audit.jsonl"))
    checkout_service = AssistantCheckoutService(
        order_registry=registry, paypal_client=mock_paypal
    )
    return GuardBuyService(store, checkout_service=checkout_service)


def test_allow_for_affordable_verified_product(service, store):
    store.save_search_results([make_result(price=99.99)], category="electronics")
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test"), user_id="user-1"
    )

    assert response.decision == "ALLOW"
    assert response.checkout_available is True
    assert response.amount == 99.99
    assert response.price == 99.99
    assert response.price_verified is True
    assert response.availability == "InStock"
    assert response.source_domain == "shop.example"
    assert response.decision_reference
    assert response.audit_reference
    assert response.evaluation["final_decision"] == "ALLOW"


def test_unverified_price_requires_review_without_payment(service, store):
    store.save_search_results([make_result(price=None, verified=False)])
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test"), user_id="user-1"
    )

    assert response.decision == "REVIEW"
    assert response.checkout_available is False
    assert response.amount is None
    assert response.price_verified is False
    assert response.checkout_amount_verified is False
    assert response.availability == "InStock"
    assert any("price is not verified" in reason.lower() for reason in response.reasons)


def test_non_usd_evidence_is_blocked(service, store):
    store.save_search_results([make_result(currency="EUR")])
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test"), user_id="user-1"
    )

    assert response.decision == "BLOCK"
    assert response.payment_status == "BLOCKED"
    assert response.checkout_available is False


def test_unknown_or_article_reference_is_rejected(service, store):
    with pytest.raises(GuardBuyError) as error:
        service.decide(GuardBuyRequest(product_reference="prod_missing"), user_id="u")
    assert error.value.status_code == 404

    store.save_search_results([make_result(reference="prod_article", result_type="article")])
    with pytest.raises(GuardBuyError):
        service.decide(GuardBuyRequest(product_reference="prod_article"), user_id="u")


def test_block_decision_never_creates_a_paypal_order(service, store, mock_paypal):
    store.save_search_results([make_result(price=100000.0)])
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test"), user_id="user-1"
    )
    assert response.decision == "BLOCK"

    checkout = service.checkout(
        response.decision_reference, user_id="user-1", idempotency_key="block-1"
    )
    assert checkout.decision == "BLOCK"
    assert checkout.payment_status == "NOT_CAPTURED"
    mock_paypal.create_order.assert_not_called()


def test_review_requires_explicit_approval_and_recheck(store, registry, mock_paypal, monkeypatch, tmp_path):
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(tmp_path / "review_audit.jsonl"))

    decisions = iter(["REVIEW", "ALLOW"])

    class FakePaymentService:
        agents = {"agent-001": SimpleNamespace(spending_limit=10000)}

        def check_payment(self, **_kwargs):
            return {"decision": next(decisions, "ALLOW"), "reason": "fake"}

    def fake_evaluate(*_args, **_kwargs):
        decision = next(eval_decisions, "ALLOW")
        return {
            "final_decision": decision,
            "risk_score": 40,
            "risk_level": "LOW",
            "decision_reason": "fake recheck",
            "transaction_id": "TXN-FAKE",
        }

    eval_decisions = iter(["REVIEW", "ALLOW"])
    checkout_service = AssistantCheckoutService(
        order_registry=registry,
        payment_service=FakePaymentService(),
        paypal_client=mock_paypal,
    )
    guard = GuardBuyService(store, checkout_service=checkout_service, evaluate=fake_evaluate)
    store.save_search_results([make_result()], category="electronics")

    response = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert response.decision == "REVIEW"
    assert response.checkout_available is False

    # Checkout before approval must not create a payment.
    pre = guard.checkout(response.decision_reference, user_id="u", idempotency_key="pre")
    assert pre.decision == "REVIEW"
    mock_paypal.create_order.assert_not_called()

    approved = guard.approve_review(response.decision_reference, True, "reviewer-1")
    assert approved.decision == "ALLOW"
    assert approved.checkout_available is True

    checkout = guard.checkout(
        response.decision_reference, user_id="u", idempotency_key="post"
    )
    assert checkout.decision == "ALLOW"
    assert "paypal.com" in checkout.approval_url
    mock_paypal.create_order.assert_called_once()


def test_checkout_is_idempotent_for_duplicate_clicks(service, store, mock_paypal):
    store.save_search_results([make_result(price=49.99)])
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test"), user_id="user-1"
    )
    assert response.decision == "ALLOW"

    first = service.checkout(
        response.decision_reference, user_id="user-1", idempotency_key="dup-key"
    )
    second = service.checkout(
        response.decision_reference, user_id="user-1", idempotency_key="dup-key"
    )

    assert first.order_id == second.order_id == "PAYPAL-GB-1"
    assert first.checkout_amount_verified is True
    mock_paypal.create_order.assert_called_once()

    # A second order with a new key is refused because the decision was consumed.
    third = service.checkout(
        response.decision_reference, user_id="user-1", idempotency_key="dup-key-2"
    )
    assert third.decision == "BLOCK"
    mock_paypal.create_order.assert_called_once()


def test_paypal_order_uses_authorized_verified_amount(service, store, mock_paypal):
    """The Sandbox order must be created for exactly the authorized, verified amount."""
    store.save_search_results([make_result(price=49.99)], category="electronics")
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test"), user_id="user-1"
    )
    assert response.decision == "ALLOW"
    assert response.amount == 49.99

    checkout = service.checkout(
        response.decision_reference, user_id="user-1", idempotency_key="amount-e7"
    )
    assert checkout.decision == "ALLOW"
    assert checkout.total_amount == 49.99

    # The browser never supplies the amount; it must equal stored verified evidence.
    kwargs = mock_paypal.create_order.call_args.kwargs
    assert kwargs["amount"] == "49.99"
    assert kwargs["currency"] == "USD"


def test_checkout_amount_is_revalidated_against_stored_evidence(
    service, store, mock_paypal
):
    store.save_search_results([make_result(price=49.99)])
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test"), user_id="user-1"
    )
    assert response.decision == "ALLOW"
    assert response.checkout_amount_verified is True

    # Simulate tampering with the recorded amount after the decision was made.
    with store._connect() as connection:
        connection.execute(
            "UPDATE guard_buy_decisions SET amount = ? WHERE decision_reference = ?",
            ("1.00", response.decision_reference),
        )

    checkout = service.checkout(
        response.decision_reference, user_id="user-1", idempotency_key="tamper"
    )
    assert checkout.decision == "BLOCK"
    assert checkout.payment_status == "NOT_CAPTURED"
    assert checkout.checkout_amount_verified is False
    assert "does not match" in checkout.reason
    mock_paypal.create_order.assert_not_called()


def test_checkout_blocks_when_price_is_no_longer_verified(service, store, mock_paypal):
    store.save_search_results([make_result(price=49.99)])
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test"), user_id="user-1"
    )
    assert response.decision == "ALLOW"

    with store._connect() as connection:
        connection.execute(
            "UPDATE product_evidence SET price_verified = 0 WHERE reference = ?",
            ("prod_test",),
        )

    checkout = service.checkout(
        response.decision_reference, user_id="user-1", idempotency_key="unverified"
    )
    assert checkout.decision == "BLOCK"
    assert "no longer verified" in checkout.reason
    mock_paypal.create_order.assert_not_called()


def test_duplicate_guard_buy_requests_reuse_idempotent_decision(service, store):
    store.save_search_results([make_result(price=25.0)])
    first = service.decide(
        GuardBuyRequest(product_reference="prod_test", idempotency_key="gb-click"),
        user_id="u",
    )
    second = service.decide(
        GuardBuyRequest(product_reference="prod_test", idempotency_key="gb-click"),
        user_id="u",
    )
    assert first.decision_reference == second.decision_reference


def test_client_supplied_identity_amount_and_url_are_not_accepted():
    # The request schema intentionally excludes identity, price, and URL fields.
    fields = set(GuardBuyRequest.model_fields)
    assert fields == {"product_reference", "quantity", "agent_id", "idempotency_key"}
    assert set(GuardBuyCheckoutRequest.model_fields) == {
        "decision_reference",
        "idempotency_key",
    }


def test_quantity_is_bounded_and_multiplies_server_side_amount(service, store):
    store.save_search_results([make_result(price=10.0)])
    response = service.decide(
        GuardBuyRequest(product_reference="prod_test", quantity=3), user_id="u"
    )
    assert response.amount == 30.0
    # checkout re-derives the amount; a client cannot change it.
    assert "amount" not in GuardBuyRequest.model_fields


def _sequence_guard(store, registry, mock_paypal, monkeypatch, tmp_path, payment_decisions, eval_decisions):
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(tmp_path / "seq_audit.jsonl"))
    payments = iter(payment_decisions)
    evaluations = iter(eval_decisions)

    class FakePaymentService:
        agents = {"agent-001": SimpleNamespace(spending_limit=10000)}

        def check_payment(self, **_kwargs):
            return {"decision": next(payments, "REVIEW"), "reason": "fake policy check"}

    def fake_evaluate(*_args, **_kwargs):
        decision = next(evaluations, "REVIEW")
        return {
            "final_decision": decision,
            "risk_score": 50,
            "risk_level": "MEDIUM",
            "decision_reason": "fake risk check",
            "transaction_id": "TXN-SEQ",
        }

    checkout_service = AssistantCheckoutService(
        order_registry=registry,
        payment_service=FakePaymentService(),
        paypal_client=mock_paypal,
    )
    return GuardBuyService(store, checkout_service=checkout_service, evaluate=fake_evaluate)


def test_approval_that_stays_review_keeps_checkout_blocked(
    store, registry, mock_paypal, monkeypatch, tmp_path
):
    guard = _sequence_guard(
        store, registry, mock_paypal, monkeypatch, tmp_path,
        ["REVIEW", "REVIEW", "REVIEW"], ["REVIEW", "REVIEW", "REVIEW"],
    )
    store.save_search_results([make_result(price=6000.0)], category="electronics")

    decision = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert decision.decision == "REVIEW"
    mock_paypal.create_order.assert_not_called()

    approved = guard.approve_review(decision.decision_reference, True, "reviewer-1")
    assert approved.decision == "REVIEW"
    assert approved.checkout_available is False
    mock_paypal.create_order.assert_not_called()

    checkout = guard.checkout(
        decision.decision_reference, user_id="u", idempotency_key="still-review"
    )
    assert checkout.decision == "REVIEW"
    assert checkout.payment_status == "NOT_CAPTURED"
    mock_paypal.create_order.assert_not_called()


def test_approval_that_becomes_block_rejects_checkout(
    store, registry, mock_paypal, monkeypatch, tmp_path
):
    guard = _sequence_guard(
        store, registry, mock_paypal, monkeypatch, tmp_path,
        ["REVIEW", "BLOCK"], ["REVIEW", "BLOCK"],
    )
    store.save_search_results([make_result(price=6000.0)], category="electronics")

    decision = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert decision.decision == "REVIEW"

    approved = guard.approve_review(decision.decision_reference, True, "reviewer-2")
    assert approved.decision == "BLOCK"

    checkout = guard.checkout(
        decision.decision_reference, user_id="u", idempotency_key="block-after-review"
    )
    assert checkout.decision == "BLOCK"
    assert checkout.payment_status == "NOT_CAPTURED"
    mock_paypal.create_order.assert_not_called()


def test_rejecting_review_records_reviewer_and_blocks(
    store, registry, mock_paypal, monkeypatch, tmp_path
):
    guard = _sequence_guard(
        store, registry, mock_paypal, monkeypatch, tmp_path,
        ["REVIEW"], ["REVIEW"],
    )
    store.save_search_results([make_result(price=6000.0)], category="electronics")
    decision = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")

    rejected = guard.approve_review(decision.decision_reference, False, "reviewer-3")
    assert rejected.decision == "BLOCK"
    record = store.get_decision(decision.decision_reference)
    assert record["reviewed_by"] == "reviewer-3"
    assert record["reviewed_at"]


def test_review_endpoint_is_authenticated_and_records_reviewer(
    store, registry, mock_paypal, monkeypatch, tmp_path
):
    guard = _sequence_guard(
        store, registry, mock_paypal, monkeypatch, tmp_path,
        ["REVIEW", "ALLOW"], ["REVIEW", "ALLOW"],
    )
    store.save_search_results([make_result(price=6000.0)], category="electronics")
    decision = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert decision.decision == "REVIEW"
    mock_paypal.create_order.assert_not_called()

    reviewer = User(id="reviewer-9", primary_email="r@example.com", full_name="Reviewer")
    result = guard_buy_review(
        request=GuardBuyReviewRequest(
            decision_reference=decision.decision_reference, approved=True
        ),
        guard_buy_service=guard,
        current_user=reviewer,
    )

    assert result.decision == "ALLOW"
    assert result.checkout_available is True
    record = store.get_decision(decision.decision_reference)
    assert record["reviewed_by"] == "reviewer-9"
    assert record["status"] == "ACTIVE"


def test_approving_unverified_price_review_reports_structured_outcome(
    service, store, mock_paypal
):
    """Approving a review whose amount was never verified must not 409.

    It must return an honest structured outcome (still REVIEW, no payment) so the
    UI can explain that the source price has to be verified before checkout.
    """
    store.save_search_results([make_result(price=None, verified=False)])
    decision = service.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert decision.decision == "REVIEW"
    assert decision.amount is None

    approved = service.approve_review(decision.decision_reference, True, "reviewer-x")
    assert approved.decision == "REVIEW"
    assert approved.checkout_available is False
    assert "verified amount" in (approved.reason or "").lower()

    mock_paypal.create_order.assert_not_called()

    record = store.get_decision(decision.decision_reference)
    assert record["reviewed_by"] == "reviewer-x"
    assert record["status"] == "PENDING"

    checkout = service.checkout(
        decision.decision_reference, user_id="u", idempotency_key="unverified-1"
    )
    assert checkout.decision == "REVIEW"
    assert checkout.payment_status == "NOT_CAPTURED"
    mock_paypal.create_order.assert_not_called()


def test_review_endpoint_returns_structured_error_code_for_unknown_reference(
    service,
):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        guard_buy_review(
            request=GuardBuyReviewRequest(
                decision_reference="does-not-exist", approved=True
            ),
            guard_buy_service=service,
            current_user=User(id="reviewer", primary_email="r@example.com", full_name="R"),
        )
    assert raised.value.status_code == 404
    assert raised.value.detail["code"] == "unknown_decision"
    assert raised.value.detail["message"]

