"""Tests for the Channel3 structured product provider.

All tests are fully mocked; no live Channel3 request is ever made (no API key
is required to run them).
"""

from __future__ import annotations

import json

import pytest

from backend.assistant import channel3_provider
from backend.assistant.channel3_provider import (
    Channel3ProviderError,
    Channel3SearchProvider,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self._text = text

    def json(self):
        if self._text is not None:
            raise ValueError("no json")
        return self._payload


def patch_post(monkeypatch, response=None, error=None, capture=None):
    def fake_post(url, json=None, headers=None, timeout=None):
        if capture is not None:
            capture["url"] = url
            capture["json"] = json
            capture["headers"] = headers
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(channel3_provider.requests, "post", fake_post)


SAMPLE_PRODUCT = {
    "id": "c3-prod-1",
    "title": "Sony WH-1000XM5 Wireless Headphones",
    "description": "Industry-leading noise cancellation.",
    "brands": [{"id": "sony", "name": "Sony"}],
    "images": [
        {"url": "https://cdn.example/image-secondary.jpg", "is_main_image": False},
        {"url": "https://cdn.example/image-main.jpg", "is_main_image": True},
    ],
    "category": {"slug": "headphones", "title": "Headphones"},
    "offers": [
        {
            "url": "https://merchant.example/products/xm5",
            "domain": "merchant.example",
            "price": {"price": 349.99, "compare_at_price": 399.99, "currency": "USD"},
            "availability": "InStock",
            "condition": "new",
        }
    ],
}


def test_unconfigured_provider_raises_503():
    provider = Channel3SearchProvider(api_key="")
    assert provider.configured is False
    with pytest.raises(Channel3ProviderError) as error:
        provider.search_with_diagnostics("headphones")
    assert error.value.status_code == 503


def test_request_uses_verified_schema(monkeypatch):
    capture = {}
    patch_post(monkeypatch, response=FakeResponse(200, {"products": []}), capture=capture)
    provider = Channel3SearchProvider(api_key="secret", timeout=5)
    provider.search_with_diagnostics(
        "noise cancelling headphones",
        budget=400.0,
        currency="usd",
        country="us",
        category="electronics",
        max_results=25,
    )

    body = capture["json"]
    assert body["limit"] == 25
    assert body["filters"] == {"price": {"max_price": 400.0}}
    assert body["config"] == {"country": "US", "currency": "USD"}
    assert "electronics" in body["query"]
    # The old (rejected) top-level fields must never be sent.
    for forbidden in ("max_price", "currency", "country", "category"):
        assert forbidden not in body
    assert capture["headers"]["x-api-key"] == "secret"


def test_limit_is_clamped_to_documented_maximum(monkeypatch):
    capture = {}
    patch_post(monkeypatch, response=FakeResponse(200, {"products": []}), capture=capture)
    Channel3SearchProvider(api_key="k").search_with_diagnostics("x", max_results=100)
    assert capture["json"]["limit"] == Channel3SearchProvider.MAX_LIMIT


def test_parses_products_and_offers_into_evidence(monkeypatch):
    patch_post(monkeypatch, response=FakeResponse(200, {"products": [SAMPLE_PRODUCT]}))
    outcome = Channel3SearchProvider(api_key="k").search_with_diagnostics("xm5")

    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.title.startswith("Sony WH-1000XM5")
    assert result.price == 349.99
    assert result.price_currency == "USD"
    # Channel3 structured offers start as CANDIDATE; they become VERIFIED only
    # after independent retailer-page verification via price enrichment.
    assert result.price_verified is False
    assert result.price_method == "channel3_structured"
    assert result.price_confidence == "medium"
    assert result.source_url == "https://merchant.example/products/xm5"
    assert result.source_domain == "merchant.example"
    assert result.seller == "merchant.example"
    assert result.availability == "In stock"
    assert result.condition == "new"
    assert result.image_url == "https://cdn.example/image-main.jpg"
    assert result.provider == "channel3"
    assert result.is_fallback is False
    assert result.evidence_status == "CANDIDATE"
    assert result.conflicts == []
    assert result.offer_count == 1
    assert "not been independently verified" in result.price_unverified_reason
    assert outcome.diagnostics.provider == "channel3"
    assert outcome.diagnostics.provider_result_count == 1
    assert outcome.diagnostics.accepted_count == 1


def test_selects_cheapest_in_stock_offer(monkeypatch):
    product = {
        **SAMPLE_PRODUCT,
        "offers": [
            {
                "url": "https://a.example/p",
                "domain": "a.example",
                "price": {"price": 300.0, "currency": "USD"},
                "availability": "OutOfStock",
                "condition": "new",
            },
            {
                "url": "https://b.example/p",
                "domain": "b.example",
                "price": {"price": 360.0, "currency": "USD"},
                "availability": "InStock",
                "condition": "new",
            },
        ],
    }
    patch_post(monkeypatch, response=FakeResponse(200, {"products": [product]}))
    outcome = Channel3SearchProvider(api_key="k").search_with_diagnostics("x")
    result = outcome.results[0]
    assert result.price == 360.0
    assert result.source_domain == "b.example"
    assert result.offer_count == 2


def test_mixed_conditions_are_flagged_as_conflict(monkeypatch):
    product = {
        **SAMPLE_PRODUCT,
        "offers": [
            {
                "url": "https://a.example/p",
                "domain": "a.example",
                "price": {"price": 300.0, "currency": "USD"},
                "availability": "InStock",
                "condition": "new",
            },
            {
                "url": "https://b.example/p",
                "domain": "b.example",
                "price": {"price": 180.0, "currency": "USD"},
                "availability": "InStock",
                "condition": "used",
            },
        ],
    }
    patch_post(monkeypatch, response=FakeResponse(200, {"products": [product]}))
    result = Channel3SearchProvider(api_key="k").search_with_diagnostics("x").results[0]
    assert result.evidence_status == "CONFLICT"
    assert result.price_verified is False
    assert result.conflicts


def test_product_without_offers_is_rejected(monkeypatch):
    product = {**SAMPLE_PRODUCT, "offers": []}
    patch_post(monkeypatch, response=FakeResponse(200, {"products": [product]}))
    outcome = Channel3SearchProvider(api_key="k").search_with_diagnostics("x")
    assert outcome.results == []
    assert outcome.diagnostics.rejected_count == 1
    assert outcome.diagnostics.rejection_reasons.get("no_offers") == 1


def test_auth_failure_is_a_safe_502(monkeypatch):
    patch_post(monkeypatch, response=FakeResponse(401, {}))
    with pytest.raises(Channel3ProviderError) as error:
        Channel3SearchProvider(api_key="bad").search_with_diagnostics("x")
    assert error.value.status_code == 502


def test_rate_limit_maps_to_429(monkeypatch):
    patch_post(monkeypatch, response=FakeResponse(429, {}))
    with pytest.raises(Channel3ProviderError) as error:
        Channel3SearchProvider(api_key="k").search_with_diagnostics("x")
    assert error.value.status_code == 429


def test_server_error_maps_to_503(monkeypatch):
    patch_post(monkeypatch, response=FakeResponse(500, {}))
    with pytest.raises(Channel3ProviderError) as error:
        Channel3SearchProvider(api_key="k").search_with_diagnostics("x")
    assert error.value.status_code == 503


def test_malformed_json_is_rejected(monkeypatch):
    patch_post(monkeypatch, response=FakeResponse(200, text="not json"))
    with pytest.raises(Channel3ProviderError) as error:
        Channel3SearchProvider(api_key="k").search_with_diagnostics("x")
    assert error.value.status_code == 502


def test_unexpected_shape_is_rejected(monkeypatch):
    patch_post(monkeypatch, response=FakeResponse(200, {"unexpected": 1}))
    with pytest.raises(Channel3ProviderError) as error:
        Channel3SearchProvider(api_key="k").search_with_diagnostics("x")
    assert error.value.status_code == 502


def test_timeout_maps_to_503(monkeypatch):
    import requests

    patch_post(monkeypatch, error=requests.Timeout("slow"))
    with pytest.raises(Channel3ProviderError) as error:
        Channel3SearchProvider(api_key="k").search_with_diagnostics("x")
    assert error.value.status_code == 503


def test_channel3_offer_without_currency_is_candidate(monkeypatch):
    """Channel3 offer without an explicit currency stays CANDIDATE."""
    product = {
        **SAMPLE_PRODUCT,
        "offers": [
            {
                "url": "https://merchant.example/products/xm5",
                "domain": "merchant.example",
                "price": {"price": 349.99},
                "availability": "InStock",
                "condition": "new",
            }
        ],
    }
    patch_post(monkeypatch, response=FakeResponse(200, {"products": [product]}))
    result = Channel3SearchProvider(api_key="k").search_with_diagnostics("xm5").results[0]
    assert result.evidence_status == "CANDIDATE"
    assert result.price_verified is False
    assert "currency" in result.price_unverified_reason.lower()


def test_channel3_offer_without_price_is_rejected(monkeypatch):
    """Channel3 offer without a usable price is rejected."""
    product = {
        **SAMPLE_PRODUCT,
        "offers": [
            {
                "url": "https://merchant.example/products/xm5",
                "domain": "merchant.example",
                "price": {"currency": "USD"},
                "availability": "InStock",
                "condition": "new",
            }
        ],
    }
    patch_post(monkeypatch, response=FakeResponse(200, {"products": [product]}))
    outcome = Channel3SearchProvider(api_key="k").search_with_diagnostics("xm5")
    assert outcome.results == []
    assert outcome.diagnostics.rejection_reasons.get("no_usable_offer") == 1


def test_channel3_structured_offer_is_not_independently_verified(monkeypatch):
    """Channel3 sets evidence_status=CANDIDATE, not VERIFIED, until enrichment."""
    patch_post(monkeypatch, response=FakeResponse(200, {"products": [SAMPLE_PRODUCT]}))
    outcome = Channel3SearchProvider(api_key="k").search_with_diagnostics("xm5")
    result = outcome.results[0]
    # Price comes from the provider but is not independently verified yet.
    assert result.price_verified is False
    assert result.evidence_status == "CANDIDATE"
    assert result.price_method == "channel3_structured"
    assert result.price_confidence == "medium"
