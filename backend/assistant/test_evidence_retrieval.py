"""Tests for structured source-page retrieval and its failure reporting."""

from types import SimpleNamespace

import pytest
import requests

from backend.assistant.price_enrichment import PriceEnrichmentService
from backend.assistant.price_extractor import (
    ProductPageFetcher,
    extract_price_from_html,
)
from backend.assistant.models import ProductSearchResult

URL = "https://shop.example/products/iphone-17"


class FakeResponse:
    def __init__(self, status_code=200, text="", content_type="text/html"):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}


def patch_get(monkeypatch, response=None, error=None):
    def fake_get(*_args, **_kwargs):
        if error is not None:
            raise error
        return response

    monkeypatch.setattr("backend.assistant.price_extractor.requests.get", fake_get)


def test_successful_retrieval_reports_status_and_time(monkeypatch):
    patch_get(monkeypatch, FakeResponse(200, "<html>ok</html>"))
    outcome = ProductPageFetcher().fetch_outcome(URL)
    assert outcome.ok is True
    assert outcome.status == "retrieved"
    assert outcome.html == "<html>ok</html>"
    assert outcome.http_status == 200
    assert outcome.retrieved_at
    assert outcome.url == URL


def test_not_found_reports_http_status_and_reason(monkeypatch):
    patch_get(monkeypatch, FakeResponse(404, "<html>nope</html>"))
    outcome = ProductPageFetcher().fetch_outcome(URL)
    assert outcome.ok is False
    assert outcome.status == "http_error"
    assert outcome.http_status == 404
    assert "404" in outcome.reason


def test_forbidden_is_reported_as_blocked(monkeypatch):
    patch_get(monkeypatch, FakeResponse(403, "<html>denied</html>"))
    outcome = ProductPageFetcher().fetch_outcome(URL)
    assert outcome.status == "blocked"
    assert outcome.http_status == 403
    assert "403" in outcome.reason


def test_timeout_is_reported(monkeypatch):
    patch_get(monkeypatch, error=requests.Timeout("slow"))
    outcome = ProductPageFetcher(timeout=3).fetch_outcome(URL)
    assert outcome.status == "timeout"
    assert "3 seconds" in outcome.reason


def test_network_error_is_reported(monkeypatch):
    patch_get(monkeypatch, error=requests.ConnectionError("down"))
    outcome = ProductPageFetcher().fetch_outcome(URL)
    assert outcome.status == "network_error"


def test_non_html_content_type_is_reported(monkeypatch):
    patch_get(monkeypatch, FakeResponse(200, "{}", content_type="application/json"))
    outcome = ProductPageFetcher().fetch_outcome(URL)
    assert outcome.status == "non_html"
    assert "json" in outcome.reason.lower()


def test_anti_bot_page_is_reported_as_blocked(monkeypatch):
    patch_get(monkeypatch, FakeResponse(200, "<html>Please complete the CAPTCHA</html>"))
    outcome = ProductPageFetcher().fetch_outcome(URL)
    assert outcome.status == "blocked"


def test_private_host_is_unfetchable():
    outcome = ProductPageFetcher().fetch_outcome("http://127.0.0.1/admin")
    assert outcome.status == "unfetchable"
    assert outcome.html is None


def test_structured_jsonld_is_extracted_from_retrieved_html(monkeypatch):
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"Apple iPhone 17","sku":"IP17",
     "offers":{"@type":"Offer","price":"799.00","priceCurrency":"USD",
               "availability":"https://schema.org/InStock"}}
    </script></head><body></body></html>
    """
    patch_get(monkeypatch, FakeResponse(200, html))
    outcome = ProductPageFetcher().fetch_outcome(URL)
    evidence = extract_price_from_html(
        outcome.html, URL, product_title="iPhone 17"
    )
    assert evidence.verified is True
    assert evidence.amount == 799.00
    assert evidence.availability == "https://schema.org/InStock"


class OutcomeFetcher:
    """Fetcher exposing fetch_outcome, mirroring ProductPageFetcher."""

    def __init__(self, outcome):
        self.outcome = outcome

    def fetch_outcome(self, url):
        return self.outcome

    def fetch(self, url):  # pragma: no cover - not used when fetch_outcome exists
        return self.outcome.html


def make_product(**overrides):
    payload = dict(
        id="p1",
        product_reference="p1",
        title="iPhone 17",
        source_url=URL,
        source_domain="shop.example",
        result_type="product",
        search_timestamp="2026-01-01T00:00:00Z",
    )
    payload.update(overrides)
    return ProductSearchResult(**payload)


def test_enrichment_records_failed_retrieval_reason():
    from backend.assistant.price_extractor import FetchOutcome

    outcome = FetchOutcome(
        url=URL,
        html=None,
        status="http_error",
        reason="the source product page was not found (HTTP 404)",
        http_status=404,
    )
    service = PriceEnrichmentService(fetcher=OutcomeFetcher(outcome), enabled=True)
    product = make_product()
    service.enrich([product], expected_currency="USD")
    assert product.price_verified is False
    assert product.retrieval_status == "http_error"
    assert product.retrieval_http_status == 404
    assert "404" in product.price_unverified_reason


def test_retrieval_outcome_survives_store_round_trip(tmp_path):
    from backend.assistant.evidence_store import ProductEvidenceStore

    store = ProductEvidenceStore(db_path=tmp_path / "evidence.db")
    product = make_product(
        retrieval_status="timeout",
        retrieval_reason="the source page did not respond within 8 seconds",
        retrieval_http_status=None,
    )
    store.save_search_results([product])
    stored = store.get_product(product.product_reference)
    assert stored["retrieval_status"] == "timeout"
    assert stored["retrieval_reason"] == "the source page did not respond within 8 seconds"


def test_enrichment_records_retrieved_status_and_availability(monkeypatch):
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"Apple iPhone 17","sku":"IP17",
     "offers":{"@type":"Offer","price":"799.00","priceCurrency":"USD",
               "availability":"https://schema.org/InStock"}}
    </script></head><body></body></html>
    """
    patch_get(monkeypatch, FakeResponse(200, html))
    service = PriceEnrichmentService(fetcher=ProductPageFetcher(), enabled=True)
    product = make_product()
    service.enrich([product], expected_currency="USD")
    assert product.retrieval_status == "retrieved"
    assert product.price_verified is True
    assert product.availability == "In stock"
