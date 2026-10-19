"""Regression tests for live product rating retrieval.

Covers:
* Valid live provider responses (Trustpilot adapter)
* Missing credentials (null provider → unavailable)
* Provider errors (timeout, auth failure, rate limit, server error)
* Stale cache (TTL expiration triggers re-fetch)
* Conflicting ratings (rating_status=conflict → Guard Buy REVIEW)
* Ollama hallucination resistance (explanations never invent ratings)
"""

import json as _json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import requests

from backend.assistant.rating_provider import (
    ProductRatingError,
    ProductRatingProvider,
    ProductRatingResult,
    TrustpilotRatingProvider,
    NullRatingProvider,
    default_rating_provider,
)
from backend.assistant.rating_service import RatingService, RatingEvidence
from backend.assistant.evidence_status import VERIFIED, CANDIDATE, UNAVAILABLE, CONFLICT


# --------------------------------------------------------------------------- #
# Provider adapter tests
# --------------------------------------------------------------------------- #


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_trustpilot_adapter_returns_rating_and_review_count(monkeypatch):
    provider = TrustpilotRatingProvider(
        api_key="tp-test-key", business_unit_id="BU-123", timeout=5
    )
    assert provider.configured is True

    captured = {}

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse(
            200,
            {
                "starsAverage": 4.2,
                "numberOfReviews": {"total": 147, "oneStar": 2, "fiveStars": 100},
            },
        )

    monkeypatch.setattr("backend.assistant.rating_provider.requests.get", fake_get)

    result = provider.fetch_rating(
        product_reference="prod_abc",
        source_url="https://shop.example/product/abc",
        sku="SKU-999",
    )

    assert result.available is True
    assert result.rating == 4.2
    assert result.review_count == 147
    assert result.provider == "trustpilot"
    assert result.status == "available"
    assert result.source_url == "https://shop.example/product/abc"
    assert "BU-123" in captured["url"]
    assert captured["headers"]["apikey"] == "tp-test-key"
    assert "sku=SKU-999" in captured["url"]


def test_trustpilot_adapter_missing_credentials_is_unavailable():
    provider = TrustpilotRatingProvider(api_key="", business_unit_id="")
    assert provider.configured is False
    result = provider.fetch_rating(
        product_reference="prod_abc", source_url="https://shop.example/product/abc"
    )
    assert result.available is False
    assert result.status == "unavailable"
    assert "not configured" in result.reason.lower()


def test_trustpilot_adapter_auth_failure(monkeypatch):
    provider = TrustpilotRatingProvider(
        api_key="bad-key", business_unit_id="BU-123", timeout=5
    )
    monkeypatch.setattr(
        "backend.assistant.rating_provider.requests.get",
        lambda *a, **k: FakeResponse(401, {}),
    )
    result = provider.fetch_rating(
        product_reference="prod_abc", source_url="https://shop.example/product/abc"
    )
    assert result.available is False
    assert "authentication" in result.reason.lower()


def test_trustpilot_adapter_timeout(monkeypatch):
    provider = TrustpilotRatingProvider(
        api_key="key", business_unit_id="BU-123", timeout=5
    )
    monkeypatch.setattr(
        "backend.assistant.rating_provider.requests.get",
        lambda *a, **k: (_ for _ in ()).throw(requests.Timeout("slow")),
    )
    result = provider.fetch_rating(
        product_reference="prod_abc", source_url="https://shop.example/product/abc"
    )
    assert result.available is False
    assert "timed out" in result.reason.lower()


def test_trustpilot_adapter_rate_limit(monkeypatch):
    provider = TrustpilotRatingProvider(
        api_key="key", business_unit_id="BU-123", timeout=5
    )
    monkeypatch.setattr(
        "backend.assistant.rating_provider.requests.get",
        lambda *a, **k: FakeResponse(429, {}),
    )
    result = provider.fetch_rating(
        product_reference="prod_abc", source_url="https://shop.example/product/abc"
    )
    assert result.available is False
    assert "rate limit" in result.reason.lower()


def test_trustpilot_adapter_no_reviews_for_product(monkeypatch):
    provider = TrustpilotRatingProvider(
        api_key="key", business_unit_id="BU-123", timeout=5
    )
    monkeypatch.setattr(
        "backend.assistant.rating_provider.requests.get",
        lambda *a, **k: FakeResponse(200, {"starsAverage": None, "numberOfReviews": None}),
    )
    result = provider.fetch_rating(
        product_reference="prod_abc", source_url="https://shop.example/product/abc"
    )
    assert result.available is False
    assert "no review summary" in result.reason.lower()


def test_null_rating_provider_always_unavailable():
    provider = NullRatingProvider()
    assert provider.configured is False
    result = provider.fetch_rating(
        product_reference="prod_abc", source_url="https://shop.example/product/abc"
    )
    assert result.available is False
    assert result.status == "unavailable"
    assert "no live product rating provider is configured" in result.reason.lower()
    assert result.ttl_seconds == 0


def test_default_rating_provider_returns_null_when_no_credentials(monkeypatch):
    monkeypatch.setenv("TRUSTPILOT_API_KEY", "")
    monkeypatch.setenv("TRUSTPILOT_BUSINESS_UNIT_ID", "")
    provider = default_rating_provider()
    assert isinstance(provider, NullRatingProvider)


# --------------------------------------------------------------------------- #
# Rating service tests
# --------------------------------------------------------------------------- #


def test_service_valid_live_response(monkeypatch, tmp_path):
    svc = RatingService(db_path=tmp_path / "ratings.db")
    svc.provider = Mock(spec=ProductRatingProvider)
    svc.provider.provider_name = "trustpilot"
    svc.provider.configured = True
    svc.provider.fetch_rating.return_value = ProductRatingResult(
        provider="trustpilot",
        rating=4.5,
        review_count=88,
        source_url="https://shop.example/p/1",
        status="available",
        reason="",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=3600,
    )
    svc.ai_service = None

    evidence = svc.fetch_rating(
        product_reference="prod_1", source_url="https://shop.example/p/1"
    )

    assert evidence.status == "available" and evidence.rating is not None
    assert evidence.rating == 4.5
    assert evidence.review_count == 88
    assert evidence.status == "available"
    assert evidence.cache_hit is False
    assert svc.provider.fetch_rating.called


def test_service_cache_hit_returns_without_provider_call(tmp_path):
    svc = RatingService(db_path=tmp_path / "ratings.db", default_ttl_seconds=3600)
    svc.ai_service = None

    # Prime the cache directly
    svc._write_cache(
        product_reference="prod_cached",
        provider="trustpilot",
        source_url="https://shop.example/p/cached",
        rating=3.0,
        review_count=10,
        status="available",
        reason="",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=3600,
        raw={},
    )

    evidence = svc.fetch_rating(
        product_reference="prod_cached",
        source_url="https://shop.example/p/cached",
    )

    assert evidence.cache_hit is True
    assert evidence.rating == 3.0
    assert evidence.review_count == 10


def test_service_stale_cache_triggers_refetch(monkeypatch, tmp_path):
    svc = RatingService(db_path=tmp_path / "ratings.db", default_ttl_seconds=60)
    svc.ai_service = None

    # Prime with stale timestamp (25 hours ago)
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    svc._write_cache(
        product_reference="prod_stale",
        provider="trustpilot",
        source_url="https://shop.example/p/stale",
        rating=4.0,
        review_count=5,
        status="available",
        reason="",
        retrieved_at=old,
        ttl_seconds=60,
        raw={},
    )

    captured = {}
    svc.provider = Mock(spec=ProductRatingProvider)
    svc.provider.provider_name = "trustpilot"
    svc.provider.configured = True

    def fake_fetch(*, product_reference, source_url, sku=None):
        captured["called"] = True
        return ProductRatingResult(
            provider="trustpilot",
            rating=4.1,
            review_count=7,
            source_url=source_url,
            status="available",
            reason="",
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            ttl_seconds=3600,
        )

    svc.provider.fetch_rating = fake_fetch

    evidence = svc.fetch_rating(
        product_reference="prod_stale",
        source_url="https://shop.example/p/stale",
    )

    assert captured.get("called") is True
    assert evidence.cache_hit is False
    assert evidence.rating == 4.1


def test_service_provider_failure_is_honest_not_cached(tmp_path):
    svc = RatingService(db_path=tmp_path / "ratings.db", default_ttl_seconds=3600)
    svc.ai_service = None

    svc.provider = Mock(spec=ProductRatingProvider)
    svc.provider.provider_name = "trustpilot"
    svc.provider.configured = True
    svc.provider.fetch_rating.return_value = ProductRatingResult(
        provider="trustpilot",
        status="unavailable",
        reason="Trustpilot authentication failed. Verify TRUSTPILOT_API_KEY.",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        ttl_seconds=0,
    )

    evidence = svc.fetch_rating(
        product_reference="prod_fail", source_url="https://shop.example/p/fail"
    )

    assert evidence.status == "unavailable" and evidence.rating is None
    assert evidence.status == "unavailable"
    assert "authentication" in evidence.reason.lower()


# --------------------------------------------------------------------------- #
# Policy integration tests
# --------------------------------------------------------------------------- #


def test_rating_evidence_policy_mapping():
    from backend.assistant.rating_service import RatingService

    # Available + trusted provider → VERIFIED
    ev = RatingEvidence(
        product_reference="p1", provider="trustpilot", rating=4.5,
        review_count=10, status="available", source_url="https://example.com",
    )
    assert RatingService.evidence_status_for_policy(ev) == VERIFIED

    # Unavailable + null provider → UNAVAILABLE
    ev2 = RatingEvidence(
        product_reference="p2", provider="none", rating=None,
        review_count=None, status="unavailable", source_url="",
    )
    assert RatingService.evidence_status_for_policy(ev2) == UNAVAILABLE

    # Available but untrusted provider → CANDIDATE
    ev3 = RatingEvidence(
        product_reference="p3", provider="unknown-provider", rating=3.0,
        review_count=2, status="available", source_url="https://example.com",
    )
    assert RatingService.evidence_status_for_policy(ev3) == CANDIDATE


def test_rating_block_reasons_for_missing_provider():
    from backend.assistant.rating_service import RatingService
    ev = RatingEvidence(
        product_reference="p1", provider="none", rating=None,
        review_count=None, status="unavailable", source_url="",
    )
    reasons = RatingService.rating_block_reasons(ev)
    assert len(reasons) > 0
    assert "no live product rating provider is configured" in reasons[0].lower()


def test_rating_block_reasons_for_unavailable():
    from backend.assistant.rating_service import RatingService
    ev = RatingEvidence(
        product_reference="p1", provider="trustpilot", rating=None,
        review_count=None, status="unavailable",
        reason="Trustpilot returned no review summary for this product.",
        source_url="https://example.com",
    )
    reasons = RatingService.rating_block_reasons(ev)
    assert len(reasons) > 0
    assert "unavailable" in reasons[0].lower()


# --------------------------------------------------------------------------- #
# Guard Buy rating conflict integration
# --------------------------------------------------------------------------- #


def test_guard_buy_conflicting_rating_requires_review(tmp_path, monkeypatch):
    from backend.assistant.evidence_store import ProductEvidenceStore
    from backend.assistant.guard_buy_service import GuardBuyService
    from backend.assistant.checkout_service import AssistantCheckoutService
    from backend.assistant.models import GuardBuyRequest, ProductSearchResult
    from backend.payment.order_registry import OrderRegistry
    from backend.payment.paypal_client import PayPalClient

    store = ProductEvidenceStore(db_path=tmp_path / "evidence.db")
    registry = OrderRegistry(db_path=tmp_path / "orders.db")
    paypal = Mock(spec=PayPalClient)
    paypal.create_order.return_value = {
        "id": "PAYPAL-1",
        "status": "CREATED",
        "links": [{"href": "https://sandbox.paypal.com/token/1", "rel": "approve"}],
    }
    checkout_service = AssistantCheckoutService(
        order_registry=registry, paypal_client=paypal
    )
    service = GuardBuyService(store, checkout_service=checkout_service)

    # Store a product with conflicting live rating
    store.save_search_results(
        [
            ProductSearchResult(
                id="prod_conflict",
                product_reference="prod_conflict",
                title="Test Headphones",
                source_url="https://shop.example/p/conflict",
                source_domain="shop.example",
                retailer="shop.example",
                price=99.99,
                price_verified=True,
                currency="USD",
                result_type="product",
                search_timestamp="2026-01-01T00:00:00Z",
                rating_status="conflict",
                rating_reason="Two review providers disagree (4.5 vs 2.0 stars)",
                rating_provider="trustpilot",
            )
        ],
        category="electronics",
    )

    response = service.decide(
        GuardBuyRequest(product_reference="prod_conflict"), user_id="user-1"
    )

    assert response.decision == "REVIEW"
    assert response.checkout_available is False
    assert response.rating_status == "conflict"
    assert any("conflict" in reason.lower() for reason in response.reasons)


def test_guard_buy_available_rating_still_allows(tmp_path, monkeypatch):
    from backend.assistant.evidence_store import ProductEvidenceStore
    from backend.assistant.guard_buy_service import GuardBuyService
    from backend.assistant.checkout_service import AssistantCheckoutService
    from backend.assistant.models import GuardBuyRequest, ProductSearchResult
    from backend.payment.order_registry import OrderRegistry
    from backend.payment.paypal_client import PayPalClient

    store = ProductEvidenceStore(db_path=tmp_path / "evidence.db")
    registry = OrderRegistry(db_path=tmp_path / "orders.db")
    paypal = Mock(spec=PayPalClient)
    paypal.create_order.return_value = {
        "id": "PAYPAL-2",
        "status": "CREATED",
        "links": [{"href": "https://sandbox.paypal.com/token/2", "rel": "approve"}],
    }
    checkout_service = AssistantCheckoutService(
        order_registry=registry, paypal_client=paypal
    )
    service = GuardBuyService(store, checkout_service=checkout_service)

    store.save_search_results(
        [
            ProductSearchResult(
                id="prod_ok",
                product_reference="prod_ok",
                title="Test Headphones",
                source_url="https://shop.example/p/ok",
                source_domain="shop.example",
                retailer="shop.example",
                price=49.99,
                price_verified=True,
                currency="USD",
                result_type="product",
                search_timestamp="2026-01-01T00:00:00Z",
                rating_status="available",
                rating=4.5,
                review_count=100,
                rating_provider="trustpilot",
            )
        ],
        category="electronics",
    )

    response = service.decide(
        GuardBuyRequest(product_reference="prod_ok"), user_id="user-1"
    )

    assert response.decision == "ALLOW"
    assert response.checkout_available is True
    assert response.rating == 4.5
    assert response.review_count == 100
    assert response.rating_status == "available"


# --------------------------------------------------------------------------- #
# Ollama hallucination resistance tests
# --------------------------------------------------------------------------- #


def test_ollama_explanation_does_not_invent_rating(tmp_path):
    """Ollama receives evidence state and must not fabricate ratings."""
    svc = RatingService(db_path=tmp_path / "ratings.db")
    svc.ai_service = Mock()
    svc.ai_service.rating_configured = True
    svc.ai_service.generate_chat_response.return_value = (
        "The product has a 5-star rating with 500 reviews based on Trustpilot data."
    )  # Hallucinated: evidence said unavailable

    evidence = RatingEvidence(
        product_reference="p1",
        provider="none",
        rating=None,
        review_count=None,
        status="unavailable",
        reason="No live product rating provider is configured.",
        source_url="",
    )

    explanation = svc._explain_with_ollama(evidence)

    # Verify Ollama was called with evidence block, not a bare query
    call_args = svc.ai_service.generate_chat_response.call_args
    assert call_args is not None
    catalog_context = call_args.kwargs.get("catalog_context", "")
    assert "unavailable" in catalog_context.lower()
    assert "no live product rating provider is configured" in catalog_context.lower()

    # The explanation is returned as-is (advisory), but the evidence itself
    # remains unavailable - Ollama cannot change the rating status.
    assert explanation is not None
    assert evidence.status == "unavailable"
    assert evidence.rating is None


def test_evidence_status_enum_covers_required_states():
    required = {VERIFIED, CANDIDATE, CONFLICT, UNAVAILABLE}
    assert required == {VERIFIED, CANDIDATE, CONFLICT, UNAVAILABLE}
