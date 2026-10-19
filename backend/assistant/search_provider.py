"""Server-side live product search backed by Endless Search.

The configured provider (``search.endless.sbs``) is a *general web-search* API
(SearXNG-style). It does not expose a shopping product feed: individual results
carry no price, availability, or structured product fields. Individual retailer
product pages therefore have to be recovered by classifying raw web/image
results by their URL structure.

This module keeps that reality explicit:

* it reports structured :class:`SearchDiagnostics` instead of pretending there
  is a product catalog;
* it never invents prices, availability, or products;
* it defines a small :class:`ProductSearchProvider` interface so a genuine
  product-data source can be plugged in later without touching callers.
"""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from backend.assistant.models import ProductSearchResult, SearchDiagnostics


load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)


class ProductSearchError(RuntimeError):
    """Safe error raised when live search cannot return usable results."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SearchOutcome:
    """The results of one search plus the diagnostics that produced them."""

    results: list[ProductSearchResult]
    diagnostics: SearchDiagnostics


class ProductSearchProvider(Protocol):
    """Interface for a live product search source.

    A future provider that exposes a real shopping product feed (prices,
    availability, images) can implement this interface; callers only depend on
    ``search_with_diagnostics`` and ``configured``.
    """

    provider_name: str

    @property
    def configured(self) -> bool:  # pragma: no cover - protocol definition
        ...

    def search_with_diagnostics(
        self,
        query: str,
        *,
        budget: float | None = None,
        currency: str = "USD",
        category: str | None = None,
        country: str = "US",
        max_results: int = 12,
    ) -> SearchOutcome:  # pragma: no cover - protocol definition
        ...


# --------------------------------------------------------------------------- #
# Classification vocabularies
# --------------------------------------------------------------------------- #

# Hosts that never represent a shoppable product page.
_CODE_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "sourceforge.net", "codeberg.org")
_SOCIAL_HOSTS = (
    "ycombinator.com", "reddit.com", "twitter.com", "x.com", "facebook.com",
    "linkedin.com", "quora.com", "pinterest.com", "discord.com", "instagram.com",
    "t.me", "mastodon.social",
)
_MEDIA_HOSTS = (
    "artic.edu", "flickr.com", "wikimedia.org", "wikipedia.org", "wikinews.org",
    "pngtree.com", "quotefancy.com", "fity.club", "animalia-life.club", "alamy.com",
    "shutterstock.com", "gettyimages.com", "istockphoto.com", "pinimg.com",
    "ytimg.com", "blogspot.com", "wordpress.com", "medium.com",
    "compute.amazonaws.com",
)
_EDITORIAL_HOSTS = (
    "forbes.com", "bhg.com", "consumerreports.org", "wired.com", "cnet.com",
    "pcmag.com", "rtings.com", "nytimes.com", "nymag.com", "runnersworld.com",
    "menshealth.com", "vogue.com", "esquire.com", "architecturaldigest.com",
    "popularmechanics.com", "techrepublic.com", "xda-developers.com", "mashable.com",
    "gsmarena.com", "ndtv.com", "bloomberg.com", "theverge.com", "engadget.com",
    "digitaltrends.com", "tomsguide.com", "techradar.com", "androidauthority.com",
    "msn.com", "wikihow.com", "substack.com", "soundguys.com",
)

# URL path fragments that identify an individual product detail page. These are
# generic across retailers, not per-brand special cases.
# NOTE: a bare "/t/" is deliberately excluded. Discourse-style forums expose
# threads at "/t/<slug>/<id>", which would otherwise be mistaken for a product
# detail page.
_PRODUCT_PATH_MARKERS = (
    "/dp/", "/gp/product/", "/ip/", "/pd/", "/pdp/", "/product/", "/products/",
    "/item", "/itm/", "/p/", "/prod/", "/buy-", "/buy/", "/shop/product",
    "/d/", "/sku/", "/model/",
)

# Path fragments that identify a listing/search/index page (never a product).
_LISTING_PATH_MARKERS = (
    "/search", "/category", "/categories", "/collections", "/collection",
    "/browse", "/clp/", "/cat_", "/cat/", "/c/", "/s?", "/s/", "/b?", "/b/",
    "/scr/", "/deals", "/deal", "/results", "/listing", "/catalog", "/catalogue",
    "/gallery", "/shop/", "/store/browse", "/all-", "/sb0/", "/w/", "/page", "node=", "pcmcat",
    "abcat", ".c?",
)

# Domain labels that identify discussion forums rather than shops. Discourse and
# similar platforms host threads under "/t/<slug>/<id>", so the host itself must
# be rejected before URL-path heuristics are applied.
_FORUM_HOST_TOKENS = (
    "forum", "forums", "discourse", "discuss", "discussion", "community", "boards",
)

# Path fragments that identify articles, guides, reviews, help/QA, or news.
_ARTICLE_PATH_MARKERS = (
    "/wiki/", "/article", "/story", "/stories", "/news", "/blog", "/reviews",
    "/review/", "/guide", "/explorer/", "/questions", "/forum", "/community",
    "/support/", "/help/", "/faq", "/wirecutter", "/strategist", "/picks",
    "/how-to", "/a/", "-review",
)

# Domain tokens that indicate a retailer or manufacturer that publishes real
# product detail pages. Used together with a product-looking URL slug.
_RETAIL_BRAND_TOKENS = {
    "amazon", "bestbuy", "walmart", "target", "costco", "homedepot", "lowes",
    "newegg", "bhphotovideo", "adorama", "staples", "officedepot", "wayfair",
    "ikea", "uline", "westelm", "potterybarn", "birchlane", "apple", "samsung",
    "sony", "dell", "hp", "lenovo", "microsoft", "asus", "acer", "nike", "adidas",
    "asics", "newbalance", "nordstrom", "macys", "zappos", "sportchek", "currys",
    "johnlewis", "desertcart", "cleanairoptima", "keysme", "yunzii",
    "huskyseating", "shop", "store", "buy",
}

_PURCHASE_TERMS = ("add to cart", "add to bag", "buy now", "in stock", "ships from", "sold by")

_PROVIDER_LIMITATION = (
    "The configured provider is a general web-search API, not a product feed. "
    "Product pages are matched by URL structure, so some queries legitimately "
    "return no individual retailer product pages."
)


class EndlessSearchProvider:
    """General web-search provider that recovers product pages from raw results."""

    endpoint = "https://search.endless.sbs/api/v1/search"
    provider_name = "endless-search"

    def __init__(self, api_key: str | None = None, timeout: int = 10):
        self.api_key = (api_key if api_key is not None else os.getenv("ENDLESS_SEARCH_KEY", "")).strip()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        *,
        budget: float | None = None,
        currency: str = "USD",
        category: str | None = None,
        country: str = "US",
        max_results: int = 12,
    ) -> list[ProductSearchResult]:
        """Backwards-compatible convenience wrapper returning only results."""
        return self.search_with_diagnostics(
            query,
            budget=budget,
            currency=currency,
            category=category,
            country=country,
            max_results=max_results,
        ).results

    def search_with_diagnostics(
        self,
        query: str,
        *,
        budget: float | None = None,
        currency: str = "USD",
        category: str | None = None,
        country: str = "US",
        max_results: int = 12,
    ) -> SearchOutcome:
        if not self.configured:
            raise ProductSearchError(
                "Live product search is not configured. Set ENDLESS_SEARCH_KEY on the backend.",
                503,
            )

        base_query = (query or "").strip()
        primary_query = self._compose_query(base_query, category=category, budget=budget, currency=currency)

        # Bounded strategy plan: bias toward product pages without unbounded,
        # spammy query rewriting. Web first, then a pristine-query fallback,
        # then image search (which surfaces product detail pages + images).
        plan: list[tuple[str, str]] = [("web", primary_query)]
        if primary_query != base_query:
            plan.append(("web", base_query))
        plan.append(("images", base_query))

        diagnostics = SearchDiagnostics(
            provider=self.provider_name,
            configured=True,
            query=base_query,
        )
        notes: list[str] = [_PROVIDER_LIMITATION]
        rejection_counts: Counter[str] = Counter()
        provider_result_count = 0

        accepted: dict[str, ProductSearchResult] = {}
        for index, (search_type, search_query) in enumerate(plan):
            try:
                payload = self._request(
                    search_query,
                    search_type=search_type,
                    currency=currency,
                    country=country,
                )
            except ProductSearchError:
                # The primary call is authoritative; secondary strategies are
                # best-effort enrichments.
                if index == 0:
                    raise
                notes.append(f"Skipped the '{search_type}' strategy after a provider error.")
                continue

            diagnostics.attempts += 1
            diagnostics.strategies.append(f"{search_type}:{search_query}")

            for item in payload.get("results", []):
                provider_result_count += 1
                result, reason = self._build_result(item, currency=currency)
                if reason is not None:
                    rejection_counts[reason] += 1
                    continue
                assert result is not None
                canonical = self._canonical_url(result.source_url)
                existing = accepted.get(canonical)
                if existing is not None:
                    if not existing.image_url and result.image_url:
                        existing.image_url = result.image_url
                    if existing.price is None and result.price is not None:
                        existing.price = result.price
                    continue
                accepted[canonical] = result

            if len(accepted) >= max_results:
                break

        results = list(accepted.values())[:max_results]

        diagnostics.provider_result_count = provider_result_count
        diagnostics.accepted_count = len(results)
        diagnostics.rejected_count = sum(rejection_counts.values())
        diagnostics.rejection_reasons = dict(rejection_counts.most_common())
        diagnostics.notes = notes
        return SearchOutcome(results=results, diagnostics=diagnostics)

    # ------------------------------------------------------------------ #
    # Provider transport
    # ------------------------------------------------------------------ #
    def _compose_query(
        self,
        base_query: str,
        *,
        category: str | None,
        budget: float | None,
        currency: str,
    ) -> str:
        search_query = base_query
        if category:
            search_query = f"{search_query} {category.strip()}"
        if budget is not None:
            search_query = f"{search_query} under {budget:g} {currency.upper()}"
        return search_query

    def _request(
        self,
        search_query: str,
        *,
        currency: str,
        country: str,
        search_type: str = "web",
    ) -> dict[str, Any]:
        try:
            response = requests.get(
                self.endpoint,
                headers={"X-API-Key": self.api_key},
                params={
                    "q": search_query,
                    "type": search_type,
                    "currency": currency.upper(),
                    "country": country.upper(),
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ProductSearchError("The live search provider could not be reached.", 503) from exc

        if response.status_code in {401, 403}:
            raise ProductSearchError("Live search authentication failed.", 502)
        if response.status_code == 429:
            raise ProductSearchError("Live search rate limit reached. Try again later.", 429)
        if response.status_code >= 500:
            raise ProductSearchError("The live search provider is temporarily unavailable.", 503)
        if not 200 <= response.status_code < 300:
            raise ProductSearchError("Live search returned an unexpected response.", 502)

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise ProductSearchError("Live search returned invalid data.", 502) from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ProductSearchError("Live search returned an invalid result shape.", 502)
        return payload

    # ------------------------------------------------------------------ #
    # Parsing + classification
    # ------------------------------------------------------------------ #
    def _build_result(
        self, item: Any, *, currency: str
    ) -> tuple[ProductSearchResult | None, str | None]:
        """Return ``(result, None)`` for a product page or ``(None, reason)``."""
        if not isinstance(item, dict):
            return None, "invalid"

        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or item.get("link") or "").strip()
        if not title or not url or not url.startswith(("http://", "https://")):
            return None, "invalid"

        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.") or "unknown source"
        snippet = str(item.get("content") or item.get("snippet") or "").strip()

        reason = self._classify(domain, parsed.path.lower(), parsed.query.lower(), title, snippet)
        if reason is not None:
            return None, reason

        retailer = str(item.get("retailer") or item.get("merchant") or item.get("source") or "").strip()
        image_url = self._normalize_image(
            item.get("img_src") or item.get("thumbnail") or item.get("image_url") or item.get("image")
        )
        price = self._source_price(item)
        reference = self._stable_reference(url)

        return (
            ProductSearchResult(
                id=reference,
                product_reference=reference,
                title=title,
                source_url=url,
                source_domain=domain,
                snippet=snippet[:1000],
                retailer=retailer or domain,
                image_url=image_url,
                price=price,
                # A raw web-search result is never authoritative. A price shown
                # here stays unverified until the product page itself is fetched
                # and a structured price is extracted (see price_enrichment).
                price_verified=False,
                price_unverified_reason=(
                    "the search result supplied a price that has not been "
                    "verified against the product page"
                    if price is not None
                    else ""
                ),
                availability=str(item.get("availability") or "Unknown"),
                result_type="product",
                currency=currency.upper(),
                search_timestamp=datetime.now(timezone.utc).isoformat(),
                provider=self.provider_name,
                # A raw web-search result is only a candidate until the product
                # page itself provides a source-verified price.
                evidence_status="CANDIDATE",
            ),
            None,
        )

    def _classify(self, domain: str, path: str, query: str, title: str, snippet: str) -> str | None:
        """Return a rejection reason, or ``None`` if the candidate is a product page."""
        if self._host_matches(domain, _CODE_HOSTS):
            return "code_host"
        if self._host_matches(domain, _SOCIAL_HOSTS):
            return "social"
        if self._host_matches(domain, _MEDIA_HOSTS):
            return "media"
        if self._host_matches(domain, _EDITORIAL_HOSTS):
            return "editorial"
        if self._is_forum_host(domain):
            return "forum"

        haystack = f"{path}?{query}"
        if any(marker in haystack for marker in _ARTICLE_PATH_MARKERS):
            return "editorial"

        if not path or path == "/":
            return "homepage"

        if any(marker in path for marker in _LISTING_PATH_MARKERS):
            return "listing"

        if any(marker in path for marker in _PRODUCT_PATH_MARKERS):
            return None

        # Retailer/brand domain with a product-looking, non-root slug.
        if self._is_retail_brand(domain) and self._looks_like_slug(path):
            return None

        text = f"{title} {snippet}".lower()
        if any(term in text for term in _PURCHASE_TERMS) and self._looks_like_slug(path):
            return None

        return "no_product_signal"

    @staticmethod
    def _host_matches(domain: str, hosts: tuple[str, ...]) -> bool:
        return any(domain == host or domain.endswith(f".{host}") for host in hosts)

    @staticmethod
    def _is_forum_host(domain: str) -> bool:
        return any(token in domain.split(".") for token in _FORUM_HOST_TOKENS)

    @staticmethod
    def _is_retail_brand(domain: str) -> bool:
        tokens = set(domain.split("."))
        return bool(tokens & _RETAIL_BRAND_TOKENS)

    @staticmethod
    def _looks_like_slug(path: str) -> bool:
        """A specific product slug: non-root, hyphenated/long, or model-like."""
        segments = [segment for segment in path.strip("/").split("/") if segment]
        if not segments:
            return False
        last = segments[-1]
        if any(char.isdigit() for char in last):
            return True
        if len(segments) >= 2 and len(last) >= 12 and "-" in last:
            return True
        return len(last) >= 20

    @staticmethod
    def _normalize_image(value: Any) -> str:
        if not value:
            return ""
        url = str(value).strip()
        if url.startswith("//"):
            url = f"https:{url}"
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.netloc:
            return url
        return ""

    @staticmethod
    def _source_price(item: dict[str, Any]) -> float | None:
        value = item.get("price")
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
        return None

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #
    @staticmethod
    def _canonical_url(url: str) -> str:
        """Normalized URL used for de-duplication (tracking params stripped)."""
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.rstrip("/").lower()
        return f"{parsed.scheme}://{host}{path}"

    @classmethod
    def _stable_reference(cls, url: str) -> str:
        """Deterministic, stable product reference derived from the source URL."""
        normalized = cls._canonical_url(url)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"prod_{digest[:24]}"
