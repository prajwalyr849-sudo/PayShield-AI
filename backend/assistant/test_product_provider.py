"""Tests for primary/fallback product-provider selection and provenance."""

from __future__ import annotations

import pytest

from backend.assistant.evidence_status import CANDIDATE, VERIFIED
from backend.assistant.models import ProductSearchResult, SearchDiagnostics
from backend.assistant.product_provider import (
    ProductProviderService,
    finalize_evidence_status,
)
from backend.assistant.search_provider import ProductSearchError, SearchOutcome


def make_result(*, reference="prod_1", price=10.0, price_verified=False):
    return ProductSearchResult(
        id=reference,
        product_reference=reference,
        title="Widget",
        source_url="https://shop.example/products/widget",
        source_domain="shop.example",
        price=price,
        price_verified=price_verified,
        currency="USD",
        result_type="product",
        search_timestamp="2026-01-01T00:00:00Z",
    )


class FakeProvider:
    def __init__(self, name, *, configured=True, results=None, error=None):
        self.provider_name = name
        self.configured = configured
        self._results = results or []
        self._error = error
        self.calls = 0

    def search_with_diagnostics(self, query, **kwargs):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return SearchOutcome(
            results=list(self._results),
            diagnostics=SearchDiagnostics(provider=self.provider_name, configured=True, query=query),
        )


def test_primary_is_used_and_stamped_when_configured():
    primary = FakeProvider("channel3", results=[make_result(price_verified=True)])
    service = ProductProviderService(primary, fallback=FakeProvider("endless-search"))
    outcome = service.search_with_diagnostics("widget")

    assert outcome.results[0].provider == "channel3"
    assert outcome.results[0].is_fallback is False
    assert outcome.diagnostics.fallback_used is False
    assert outcome.diagnostics.providers_attempted == ["channel3"]
    assert outcome.diagnostics.primary_provider == "channel3"


def test_fallback_is_used_when_primary_fails_and_is_clearly_labelled():
    primary = FakeProvider(
        "channel3", error=ProductSearchError("boom", 503)
    )
    fallback = FakeProvider("endless-search", results=[make_result(price_verified=True)])
    service = ProductProviderService(primary, fallback=fallback, fallback_enabled=True)
    outcome = service.search_with_diagnostics("widget")

    assert outcome.results[0].provider == "endless-search"
    assert outcome.results[0].is_fallback is True
    assert outcome.diagnostics.fallback_used is True
    assert outcome.diagnostics.provider == "endless-search"
    assert "channel3" in outcome.diagnostics.fallback_reason
    assert outcome.diagnostics.providers_attempted == ["channel3", "endless-search"]
    assert any("fallback provider" in note for note in outcome.diagnostics.notes)


def test_fallback_is_not_used_when_disabled():
    primary = FakeProvider("channel3", error=ProductSearchError("boom", 503))
    fallback = FakeProvider("endless-search", results=[make_result()])
    service = ProductProviderService(primary, fallback=fallback, fallback_enabled=False)
    with pytest.raises(ProductSearchError):
        service.search_with_diagnostics("widget")
    assert fallback.calls == 0


def test_unconfigured_primary_uses_enabled_fallback():
    primary = FakeProvider("channel3", configured=False)
    fallback = FakeProvider("endless-search", results=[make_result()])
    service = ProductProviderService(primary, fallback=fallback, fallback_enabled=True)
    outcome = service.search_with_diagnostics("widget")

    assert outcome.diagnostics.fallback_used is True
    assert "not configured" in outcome.diagnostics.fallback_reason
    assert outcome.results[0].is_fallback is True


def test_nothing_configured_raises_safe_error():
    primary = FakeProvider("channel3", configured=False)
    fallback = FakeProvider("endless-search", configured=False)
    service = ProductProviderService(primary, fallback=fallback, fallback_enabled=True)
    with pytest.raises(ProductSearchError) as error:
        service.search_with_diagnostics("widget")
    assert error.value.status_code == 503


def test_fallback_failure_is_reported():
    primary = FakeProvider("channel3", error=ProductSearchError("boom", 503))
    fallback = FakeProvider("endless-search", error=ProductSearchError("down", 503))
    service = ProductProviderService(primary, fallback=fallback, fallback_enabled=True)
    with pytest.raises(ProductSearchError) as error:
        service.search_with_diagnostics("widget")
    assert "fallback provider" in str(error.value)


def test_configured_reflects_any_available_provider():
    assert ProductProviderService(
        FakeProvider("channel3", configured=False), fallback=None
    ).configured is False
    assert ProductProviderService(
        FakeProvider("channel3", configured=True)
    ).configured is True
    assert ProductProviderService(
        FakeProvider("channel3", configured=False),
        fallback=FakeProvider("endless-search", configured=True),
        fallback_enabled=True,
    ).configured is True
    assert ProductProviderService(
        FakeProvider("channel3", configured=False),
        fallback=FakeProvider("endless-search", configured=True),
        fallback_enabled=False,
    ).configured is False


def test_finalize_evidence_status_upgrades_verified_fallback_result():
    result = make_result(price_verified=False)
    result.provider = "endless-search"
    finalize_evidence_status([result])
    assert result.evidence_status == CANDIDATE

    result.price_verified = True
    finalize_evidence_status([result])
    assert result.evidence_status == VERIFIED


def test_finalize_leaves_structured_results_untouched():
    result = make_result(price_verified=True)
    result.provider = "channel3"
    result.evidence_status = "CONFLICT"
    finalize_evidence_status([result])
    assert result.evidence_status == "CONFLICT"
