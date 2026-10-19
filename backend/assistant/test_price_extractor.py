"""Tests for server-side product price extraction and validation."""

from datetime import datetime, timezone

import pytest

from backend.assistant.price_extractor import (
    PriceEvidence,
    ProductPageFetcher,
    extract_from_snippet,
    extract_price_from_html,
)

URL = "https://shop.example/products/sony-wh-1000xm5"

JSONLD_VALID = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Sony WH-1000XM5 Headphones",
 "sku":"WH1000XM5",
 "offers":{"@type":"Offer","price":"348.00","priceCurrency":"USD",
           "availability":"https://schema.org/InStock"}}
</script></head><body>Sony WH-1000XM5</body></html>
"""

META_VALID = """
<html><head>
<meta property="product:price:amount" content="129.99">
<meta property="product:price:currency" content="USD">
</head><body>Headphones</body></html>
"""

MICRODATA_VALID = """
<html><body><div itemscope itemtype="https://schema.org/Product">
<span itemprop="price" content="59.50">$59.50</span>
<meta itemprop="priceCurrency" content="USD">
</div></body></html>
"""


def test_structured_jsonld_price_is_verified():
    evidence = extract_price_from_html(
        JSONLD_VALID, URL, product_title="Sony WH-1000XM5"
    )
    assert evidence.verified is True
    assert evidence.amount == 348.00
    assert evidence.currency == "USD"
    assert evidence.method == "json_ld"
    assert evidence.confidence == "high"
    assert evidence.price_type == "selling_price"
    assert evidence.source_url == URL
    assert evidence.retrieved_at


def test_meta_price_is_verified():
    evidence = extract_price_from_html(META_VALID, URL, product_title="Headphones")
    assert evidence.verified is True
    assert evidence.amount == 129.99
    assert evidence.method == "meta"
    assert evidence.currency == "USD"


def test_microdata_price_is_verified():
    evidence = extract_price_from_html(MICRODATA_VALID, URL, product_title="Widget")
    assert evidence.verified is True
    assert evidence.amount == 59.50
    assert evidence.method == "microdata"


def test_labelled_sale_price_is_preferred_over_mrp():
    html = (
        '<html><body><span>MRP $199.99</span> '
        '<span>Sale price $149.99</span></body></html>'
    )
    evidence = extract_price_from_html(html, URL, product_title="Widget")
    assert evidence.verified is True
    assert evidence.amount == 149.99
    assert evidence.price_type == "sale_price"
    assert evidence.method == "labelled_text"
    assert evidence.confidence == "medium"


def test_missing_price_is_unverified_with_reason():
    html = "<html><body><h1>Sony WH-1000XM5</h1><p>Great headphones</p></body></html>"
    evidence = extract_price_from_html(html, URL, product_title="Sony WH-1000XM5")
    assert evidence.amount is None
    assert evidence.verified is False
    assert evidence.method == "none"
    assert "did not expose" in evidence.reason


def test_currency_mismatch_is_not_verified():
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"Widget",
     "offers":{"@type":"Offer","price":"199.00","priceCurrency":"EUR"}}
    </script></head><body></body></html>
    """
    evidence = extract_price_from_html(html, URL, product_title="Widget")
    assert evidence.verified is False
    assert evidence.amount == 199.00
    assert "EUR" in evidence.reason and "USD" in evidence.reason


def test_stale_price_is_not_verified():
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"Widget",
     "offers":{"@type":"Offer","price":"10.00","priceCurrency":"USD",
               "priceValidUntil":"2020-01-01"}}
    </script></head><body></body></html>
    """
    evidence = extract_price_from_html(
        html,
        URL,
        product_title="Widget",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert evidence.verified is False
    assert "stale" in evidence.reason


def test_conflicting_offers_are_not_verified():
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"Widget","offers":[
      {"@type":"Offer","price":"100.00","priceCurrency":"USD"},
      {"@type":"Offer","price":"120.00","priceCurrency":"USD"}]}
    </script></head><body></body></html>
    """
    evidence = extract_price_from_html(html, URL, product_title="Widget")
    assert evidence.verified is False
    assert "conflicting" in evidence.reason
    assert evidence.amount is None


def test_aggregate_range_is_ambiguous():
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"Widget",
     "offers":{"@type":"AggregateOffer","lowPrice":"99.00","highPrice":"149.00",
               "priceCurrency":"USD"}}
    </script></head><body></body></html>
    """
    evidence = extract_price_from_html(html, URL, product_title="Widget")
    assert evidence.verified is False
    assert evidence.price_type == "aggregate"
    assert "range" in evidence.reason


def test_malformed_jsonld_falls_back_to_metadata():
    html = """
    <html><head>
    <script type="application/ld+json">{this is not json}</script>
    <meta property="product:price:amount" content="42.00">
    <meta property="product:price:currency" content="USD">
    </head><body></body></html>
    """
    evidence = extract_price_from_html(html, URL, product_title="Widget")
    assert evidence.verified is True
    assert evidence.amount == 42.00
    assert evidence.method == "meta"


def test_different_model_is_not_verified():
    html = """
    <html><head><script type="application/ld+json">
    {"@type":"Product","name":"Sony WH-1000XM4 Headphones","sku":"WH1000XM4",
     "offers":{"@type":"Offer","price":"248.00","priceCurrency":"USD"}}
    </script></head><body></body></html>
    """
    evidence = extract_price_from_html(
        html, URL, product_title="Sony WH-1000XM5"
    )
    assert evidence.verified is False
    assert "different product" in evidence.reason


def test_snippet_price_is_never_verified():
    evidence = extract_from_snippet("Buy the Sony WH-1000XM5 for $348.00 today", URL)
    assert evidence.amount == 348.00
    assert evidence.verified is False
    assert evidence.method == "snippet"
    assert evidence.confidence == "low"
    assert "snippet" in evidence.reason


def test_snippet_without_amount_has_no_price():
    evidence = extract_from_snippet("Sony WH-1000XM5 noise cancelling", URL)
    assert evidence.amount is None
    assert evidence.verified is False


def test_evidence_as_dict_shape():
    evidence = PriceEvidence(amount=10.0, verified=True, source_url=URL)
    data = evidence.as_dict()
    assert data["price"] == 10.0
    assert data["price_verified"] is True
    assert data["price_source_url"] == URL
    assert data["price_unverified_reason"] == ""


class _FakeResponse:
    def __init__(self, status_code=200, text="", content_type="text/html"):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}


def test_fetcher_refuses_private_and_invalid_hosts():
    fetcher = ProductPageFetcher()
    assert fetcher.fetch("http://127.0.0.1/admin") is None
    assert fetcher.fetch("http://localhost/internal") is None
    assert fetcher.fetch("ftp://shop.example/file") is None
    assert fetcher.fetch("") is None


def test_fetcher_returns_html_for_public_page(monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.price_extractor.requests.get",
        lambda *args, **kwargs: _FakeResponse(200, "<html>ok</html>"),
    )
    assert ProductPageFetcher().fetch("https://shop.example/products/1") == "<html>ok</html>"


@pytest.mark.parametrize(
    "response",
    [
        _FakeResponse(403, "<html>denied</html>"),
        _FakeResponse(200, "<html>Please complete the CAPTCHA</html>"),
        _FakeResponse(200, "{}", content_type="application/json"),
    ],
)
def test_fetcher_rejects_blocked_or_non_html(response, monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.price_extractor.requests.get",
        lambda *args, **kwargs: response,
    )
    assert ProductPageFetcher().fetch("https://shop.example/products/1") is None
