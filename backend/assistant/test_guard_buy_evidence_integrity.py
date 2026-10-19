"""Guard Buy integrity tests for identity matching and evidence binding."""

from unittest.mock import Mock

import pytest

from backend.assistant.checkout_service import AssistantCheckoutService
from backend.assistant.evidence_store import ProductEvidenceStore
from backend.assistant.guard_buy_service import GuardBuyError, GuardBuyService
from backend.assistant.models import GuardBuyRequest, ProductSearchResult
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalClient


def make_result(
    *,
    reference="prod_test",
    title="Apple iPhone 17 128GB",
    price=799.0,
    verified=True,
    identity_match="UNKNOWN",
    identity_reasons=None,
    evidence_status="",
    conflicts=None,
    provider="channel3",
    is_fallback=False,
):
    return ProductSearchResult(
        id=reference,
        product_reference=reference,
        title=title,
        source_url="https://shop.example/products/iphone-17",
        source_domain="shop.example",
        retailer="shop.example",
        price=price,
        price_verified=verified,
        currency="USD",
        availability="In stock",
        result_type="product",
        identity_match=identity_match,
        identity_reasons=list(identity_reasons or []),
        evidence_status=evidence_status,
        conflicts=list(conflicts or []),
        provider=provider,
        is_fallback=is_fallback,
        search_timestamp="2026-01-01T00:00:00Z",
    )


@pytest.fixture
def store(tmp_path):
    return ProductEvidenceStore(db_path=tmp_path / "evidence.db")


@pytest.fixture
def guard(store, tmp_path, monkeypatch):
    monkeypatch.setenv("PAYSHIELD_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    registry = OrderRegistry(db_path=tmp_path / "orders.db")
    return GuardBuyService(
        store,
        checkout_service=AssistantCheckoutService(
            order_registry=registry, paypal_client=Mock(spec=PayPalClient)
        ),
    )


def test_identity_mismatch_requires_review_and_never_allows(guard, store):
    store.save_search_results(
        [
            make_result(
                title="Restored iPhone 14 Pro Max 256GB",
                identity_match="MISMATCH",
                identity_reasons=["model/generation differs: requested 17, candidate 14"],
            )
        ]
    )
    response = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert response.decision == "REVIEW"
    assert response.checkout_available is False
    assert response.amount is None
    assert response.identity_match == "MISMATCH"
    assert any("does not match" in reason for reason in response.reasons)


def test_identity_partial_match_is_allowed_but_flagged(guard, store):
    store.save_search_results(
        [
            make_result(
                identity_match="PARTIAL_MATCH",
                identity_reasons=["storage differs: requested 256gb, candidate 128gb"],
            )
        ]
    )
    response = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert response.decision == "ALLOW"
    assert response.identity_match == "PARTIAL_MATCH"
    assert any("partially matches" in reason for reason in response.reasons)


def test_identity_survives_store_round_trip(guard, store):
    store.save_search_results(
        [
            make_result(
                identity_match="MISMATCH",
                identity_reasons=["condition differs: requested new, candidate refurbished"],
            )
        ]
    )
    product = store.get_product("prod_test")
    assert product["identity_match"] == "MISMATCH"
    assert product["identity_reasons"] == [
        "condition differs: requested new, candidate refurbished"
    ]


def test_unknown_or_missing_evidence_never_auto_allows(guard):
    with pytest.raises(GuardBuyError) as error:
        guard.decide(GuardBuyRequest(product_reference="does-not-exist"), user_id="u")
    assert error.value.status_code == 404
    assert error.value.code == "unknown_product"


def test_unverified_price_reference_requires_review(guard, store):
    store.save_search_results([make_result(price=None, verified=False)])
    response = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert response.decision == "REVIEW"
    assert response.amount is None


def test_client_cannot_submit_identity_or_amount_fields():
    assert set(GuardBuyRequest.model_fields) == {
        "product_reference",
        "quantity",
        "agent_id",
        "idempotency_key",
    }


def test_conflicting_offers_require_review_even_with_verified_price(guard, store):
    store.save_search_results(
        [
            make_result(
                evidence_status="CONFLICT",
                conflicts=["merchant offers mix new and used condition"],
            )
        ]
    )
    response = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert response.decision == "REVIEW"
    assert response.checkout_available is False
    assert response.amount is None
    assert response.evidence_status == "CONFLICT"
    assert any("conflict" in reason.lower() for reason in response.reasons)


def test_evidence_provenance_is_exposed_in_decision(guard, store):
    store.save_search_results(
        [make_result(provider="channel3", is_fallback=False, evidence_status="VERIFIED")]
    )
    response = guard.decide(GuardBuyRequest(product_reference="prod_test"), user_id="u")
    assert response.provider == "channel3"
    assert response.is_fallback is False
    assert response.evidence_status == "VERIFIED"
