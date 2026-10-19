from types import SimpleNamespace

import pytest

from backend.assistant.search_provider import EndlessSearchProvider, ProductSearchError


def fake_response(payload, status_code=200):
    return SimpleNamespace(status_code=status_code, json=lambda: payload)


def test_different_queries_generate_different_provider_requests(monkeypatch):
    calls = []

    def fake_get(_url, **kwargs):
        calls.append(kwargs)
        return fake_response({"results": []})

    monkeypatch.setattr("backend.assistant.search_provider.requests.get", fake_get)
    provider = EndlessSearchProvider(api_key="configured")

    provider.search("wireless headphones", budget=250, currency="USD", country="US")
    provider.search("ergonomic office chair", budget=400, currency="EUR", country="DE")

    first_us_call = next(call for call in calls if call["params"]["currency"] == "USD")
    euro_calls = [call for call in calls if call["params"]["currency"] == "EUR"]
    assert first_us_call["params"]["q"] != euro_calls[0]["params"]["q"]
    assert euro_calls[0]["params"]["country"] == "DE"


def test_bounded_plan_falls_back_to_base_query_and_images(monkeypatch):
    calls = []

    def fake_get(_url, **kwargs):
        params = kwargs["params"]
        calls.append((params["type"], params["q"]))
        if len(calls) == 1:
            return fake_response({"results": [{"title": "Category page", "url": "https://shop.example/category", "content": "Browse products"}]})
        return fake_response({"results": [{"title": "Headphones product", "url": "https://shop.example/products/headphones", "content": "Buy now"}]})

    monkeypatch.setattr("backend.assistant.search_provider.requests.get", fake_get)
    results = EndlessSearchProvider(api_key="configured").search(
        "headphones", budget=250, currency="USD", category="electronics"
    )

    assert calls == [
        ("web", "headphones electronics under 250 USD"),
        ("web", "headphones"),
        ("images", "headphones"),
    ]
    assert len(results) == 1
    assert results[0].source_url == "https://shop.example/products/headphones"


def test_empty_results_are_returned_without_demo_products(monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.search_provider.requests.get",
        lambda *_args, **_kwargs: fake_response({"results": []}),
    )

    assert EndlessSearchProvider(api_key="configured").search("rare item") == []


@pytest.mark.parametrize(
    ("status_code", "expected_status"),
    [(401, 502), (429, 429), (503, 503)],
)
def test_provider_failures_are_safe(status_code, expected_status, monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.search_provider.requests.get",
        lambda *_args, **_kwargs: fake_response({}, status_code),
    )

    with pytest.raises(ProductSearchError) as error:
        EndlessSearchProvider(api_key="configured").search("headphones")

    assert error.value.status_code == expected_status
    assert "{" not in str(error.value)


def test_result_preserves_source_and_never_invents_price(monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.search_provider.requests.get",
        lambda *_args, **_kwargs: fake_response(
            {"results": [{"title": "Live headphones", "url": "https://shop.example/item", "content": "Buy now. Evidence"}]}
        ),
    )

    result = EndlessSearchProvider(api_key="configured").search("headphones")[0]

    assert result.title == "Live headphones"
    assert result.source_url == "https://shop.example/item"
    assert result.snippet == "Buy now. Evidence"
    assert result.price is None
    assert result.price_verified is False


def test_articles_and_insecure_images_are_not_product_evidence(monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.search_provider.requests.get",
        lambda *_args, **_kwargs: fake_response(
            {
                "results": [
                    {
                        "title": "Best headphones buying guide",
                        "url": "https://editor.example/guide",
                        "content": "Review and comparison of models",
                        "image_url": "http://editor.example/image.jpg",
                    },
                    {
                        "title": "Wireless headphones",
                        "url": "https://shop.example/item",
                        "content": "Add to cart",
                        "price": 99.99,
                        "image_url": "https://shop.example/image.jpg",
                    },
                ]
            }
        ),
    )

    results = EndlessSearchProvider(api_key="configured").search("wireless headphones")

    assert len(results) == 1
    assert results[0].price == 99.99
    assert results[0].image_url == "https://shop.example/image.jpg"


def test_generic_company_homepage_is_not_product_evidence(monkeypatch):
    monkeypatch.setattr(
        "backend.assistant.search_provider.requests.get",
        lambda *_args, **_kwargs: fake_response(
            {
                "results": [
                    {
                        "title": "Microsoft - AI, Cloud, Productivity, Computing, Gaming & Apps",
                        "url": "https://www.microsoft.com/",
                        "content": "Explore Microsoft products and services for your home or business.",
                    }
                ]
            }
        ),
    )

    assert EndlessSearchProvider(api_key="configured").search("microsoft") == []


def test_forum_thread_is_not_product_evidence(monkeypatch):
    """A Discourse thread URL must never be treated as a product page.

    ``forum.hifiguides.com/t/<slug>/<id>`` carries a price in the raw result and
    uses a ``/t/`` path segment, but it is discussion content, not a shop offer.
    """
    monkeypatch.setattr(
        "backend.assistant.search_provider.requests.get",
        lambda *_args, **_kwargs: fake_response(
            {
                "results": [
                    {
                        "title": "Headphone Recommendation <$200 USD - Headphone Discussion",
                        "url": "https://forum.hifiguides.com/t/headphone-recommendation-under-200/12345",
                        "content": "Looking for headphones under $200. The HD 6XX is $199.",
                        "price": 199.0,
                    }
                ]
            }
        ),
    )

    assert EndlessSearchProvider(api_key="configured").search("headphones under 200") == []


def test_source_search_price_is_never_marked_verified(monkeypatch):
    """A price supplied by a raw search result is unverified until the page is fetched."""
    monkeypatch.setattr(
        "backend.assistant.search_provider.requests.get",
        lambda *_args, **_kwargs: fake_response(
            {
                "results": [
                    {
                        "title": "Live headphones",
                        "url": "https://shop.example/products/headphones",
                        "content": "Buy now",
                        "price": 199.0,
                    }
                ]
            }
        ),
    )

    result = EndlessSearchProvider(api_key="configured").search("headphones")[0]

    assert result.price == 199.0
    assert result.price_verified is False
    assert result.price_unverified_reason
