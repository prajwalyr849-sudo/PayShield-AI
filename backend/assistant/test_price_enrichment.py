"""Tests for source-verified price enrichment and its Guard Buy integration."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from backend.assistant.checkout_service import AssistantCheckoutService
from backend.assistant.evidence_store import ProductEvidenceStore
from backend.assistant.guard_buy_service import GuardBuyService
from backend.assistant.models import GuardBuyRequest, ProductSearchResult
from backend.assistant.price_enrichment import PriceEnrichmentService
from backend.payment.order_registry import OrderRegistry
from backend.payment.paypal_client import PayPalClient

URL = "https://shop.example/products/sony-wh-1000xm5"
JSONLD_VALID = """
<html><head><script type="application/ld+json">
{"@type":"Product","name":"Sony WH-1000XM5 Headphones","sku":"WH1000XM5",
 "offers":{"@type":"Offer","price":"348.00","priceCurrency":"USD"}}
</script></head><body></body></html>
"""


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.pages.get(url)


def make_product(url=URL, *, snippet="", result_type="product", reference="p1"):
    return ProductSearchResult(
        id=reference,
        product_reference=reference,
        title="Sony WH-1000XM5",
        source_url=url,
        source_domain="shop.example",
        snippet=snippet,
        retailer="shop.example",
        result_type=result_type,
        search_timestamp="2026-01-01T00:00:00Z",
    )


def test_enrich_attaches_verified_source_price():
    service = PriceEnrichmentService(fetcher=FakeFetcher({URL: JSONLD_VALID}), enabled=True)
    results = service.enrich([make_product()], expected_currency="USD")
    product = results[0]
    assert product.price == 348.00
    assert product.price_verified is True
    assert product.price_method == "json_ld"
    assert product.price_type == "selling_price"
    assert product.price_source_url == URL
    assert product.price_retrieved_at
    assert product.price_unverified_reason == ""


def test_unreachable_page_falls_back_to_unverified_snippet_price():
    service = PriceEnrichmentService(fetcher=FakeFetcher({}), enabled=True)
    results = service.enrich(
        [make_product(snippet="Sony WH-1000XM5 now $348.00")], expected_currency="USD"
    )
    product = results[0]
    assert product.price == 348.00
    assert product.price_verified is False
    assert product.price_method == "snippet"
    assert product.price_confidence == "low"
    assert "could not be retrieved" in product.price_unverified_reason


def test_disabled_enrichment_leaves_prices_untouched():
    service = PriceEnrichmentService(fetcher=FakeFetcher({URL: JSONLD_VALID}), enabled=False)
    product = make_product()
    service.enrich([product], expected_currency="USD")
    assert product.price is None
    assert product.price_verified is False
    assert product.price_unverified_reason == ""


def test_non_products_are_not_enriched_and_not_fetched():
    fetcher = FakeFetcher({URL: JSONLD_VALID})
    service = PriceEnrichmentService(fetcher=fetcher, enabled=True)
    article = make_product(result_type="article")
    service.enrich([article], expected_currency="USD")
    assert article.price is None
    assert fetcher.calls == []
    assert article.price_unverified_reason == ""


def test_enrichment_is_bounded_to_first_products():
    second_url = "https://shop.example/products/second"
    fetcher = FakeFetcher({URL: JSONLD_VALID, second_url: JSONLD_VALID})
    service = PriceEnrichmentService(fetcher=fetcher, enabled=True, max_products=1)
    first = make_product(reference="p1")
    second = make_product(url=second_url, reference="p2")
    service.enrich([first, second], expected_currency="USD")
    assert first.price_verified is True
    assert second.price is None
    assert "skipped" in second.price_unverified_reason
    assert fetcher.calls == [URL]


def test_enriched_price_drives_guard_buy_allow(tmp_path):
    store = ProductEvidenceStore(db_path=tmp_path / "evidence.db")
    service = PriceEnrichmentService(fetcher=FakeFetcher({URL: JSONLD_VALID}), enabled=True)
    product = make_product()
    service.enrich([product], expected_currency="USD")
    store.save_search_results([product], category="electronics")

    registry = OrderRegistry(db_path=tmp_path / "orders.db")
    guard = GuardBuyService(
        store,
        checkout_service=AssistantCheckoutService(
            order_registry=registry, paypal_client=Mock(spec=PayPalClient)
        ),
    )
    response = guard.decide(GuardBuyRequest(product_reference="p1"), user_id="u")
    assert response.decision == "ALLOW"
    assert response.amount == 348.00
    assert response.price_verified is True
    assert response.checkout_amount_verified is True


def test_channel3_candidate_enriched_to_verified():
    """Channel3 result starts as CANDIDATE, enrichment promotes to VERIFIED."""
    # Channel3 result: price_verified=False, evidence_status=CANDIDATE
    now = datetime.now(timezone.utc).isoformat()
    product = ProductSearchResult(
        id="c3_test",
        product_reference="c3_test",
        title="Sony WH-1000XM5",
        source_url=URL,
        source_domain="shop.example",
        retailer="shop.example",
        price=348.00,
        price_verified=False,
        price_currency="USD",
        price_method="channel3_structured",
        price_confidence="medium",
        price_source_url=URL,
        price_retrieved_at=now,
        price_unverified_reason="Channel3 structured offer has not been independently verified against the retailer page.",
        availability="In stock",
        result_type="product",
        currency="USD",
        search_timestamp=now,
        provider="channel3",
        is_fallback=False,
        evidence_status="CANDIDATE",
        condition="new",
        variant="",
        offer_count=1,
        evidence_reasons=["Channel3 structured offer from shop.example"],
        conflicts=[],
    )
    service = PriceEnrichmentService(fetcher=FakeFetcher({URL: JSONLD_VALID}), enabled=True)
    results = service.enrich([product], expected_currency="USD")
    enriched = results[0]
    assert enriched.price_verified is True
    assert enriched.evidence_status == "VERIFIED"
    assert enriched.price_method == "json_ld"


def test_stale_evidence_stays_candidate_after_enrichment():
    """Enrichment with stale timestamp keeps evidence as CANDIDATE."""
    old_timestamp = "2020-01-01T00:00:00Z"
    product = ProductSearchResult(
        id="c3_test",
        product_reference="c3_test",
        title="Sony WH-1000XM5",
        source_url=URL,
        source_domain="shop.example",
        retailer="shop.example",
        price=348.00,
        price_verified=True,
        price_currency="USD",
        price_method="channel3_structured",
        price_confidence="medium",
        price_source_url=URL,
        price_retrieved_at=old_timestamp,
        price_unverified_reason="",
        availability="In stock",
        result_type="product",
        currency="USD",
        search_timestamp=old_timestamp,
        provider="channel3",
        is_fallback=False,
        evidence_status="VERIFIED",
        condition="new",
        variant="",
        offer_count=1,
        evidence_reasons=["Channel3 structured offer from shop.example"],
        conflicts=[],
    )
    service = PriceEnrichmentService(fetcher=FakeFetcher({URL: JSONLD_VALID}), enabled=True)
    results = service.enrich([product], expected_currency="USD")
    enriched = results[0]
    # Stale evidence -> downgrade to CANDIDATE even though price was verified
    assert enriched.evidence_status == "CANDIDATE"


def test_currency_mismatch_stays_candidate():
    """Price in non-USD currency stays CANDIDATE after enrichment."""
    product = ProductSearchResult(
        id="c3_test",
        product_reference="c3_test",
        title="Sony WH-1000XM5",
        source_url=URL,
        source_domain="shop.example",
        retailer="shop.example",
        price=348.00,
        price_verified=False,
        price_currency="EUR",
        price_method="channel3_structured",
        price_confidence="medium",
        price_source_url=URL,
        price_retrieved_at="2026-01-01T00:00:00Z",
        price_unverified_reason="Channel3 structured offer has not been independently verified against the retailer page.",
        availability="In stock",
        result_type="product",
        currency="EUR",
        search_timestamp="2026-01-01T00:00:00Z",
        provider="channel3",
        is_fallback=False,
        evidence_status="CANDIDATE",
        condition="new",
        variant="",
        offer_count=1,
        evidence_reasons=["Channel3 structured offer from shop.example"],
        conflicts=[],
    )
    service = PriceEnrichmentService(fetcher=FakeFetcher({URL: JSONLD_VALID}), enabled=True)
    results = service.enrich([product], expected_currency="USD")
    enriched = results[0]
    # Currency mismatch -> not verified, stays CANDIDATE
    assert enriched.evidence_status == "CANDIDATE"
    assert enriched.price_verified is False
