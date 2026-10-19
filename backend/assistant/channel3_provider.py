"""Server-side live product search backed by the Channel3 product API.

Channel3 (trychannel3.com) exposes a *structured product and offer feed*, not a
general web search. Each returned ``Product`` carries merchant ``Offer`` objects
with an explicit price, currency, availability, and domain, so this provider can
treat them as evidence rather than guessing a product page from a URL slug.

Verified against the official API reference
(https://docs.trychannel3.com/api-reference/v1/search):

* ``POST https://api.trychannel3.com/v1/search`` with ``x-api-key`` auth.
* Request ``SearchRequest`` (``additionalProperties: false``): ``query``,
  ``limit`` (1-30, default 20), ``filters`` (``SearchFilters``), ``config``
  (``SearchConfig``: ``language``, ``country``, ``currency``, ...).
* Response ``SearchResponse``: ``{"products": [Product], "next_page_token": ...}``.
* ``ProductOffer`` (required ``url``, ``domain``, ``price``, ``availability``).

This module never invents prices, availability, merchants, or API responses; it
maps only the fields the provider actually returned.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from backend.assistant.evidence_status import structured_offer_status
from backend.assistant.models import ProductSearchResult, SearchDiagnostics


class Channel3ProviderError(RuntimeError):
    """Safe error raised when Channel3 search cannot return usable results."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SearchOutcome:
    """Results plus diagnostics from a search."""

    results: list[ProductSearchResult]
    diagnostics: SearchDiagnostics


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _normalize_url(url: Optional[str]) -> str:
    if not url or not str(url).strip():
        return ""
    value = str(url).strip()
    if value.startswith("//"):
        value = f"https:{value}"
    if not value.startswith(("http://", "https://")):
        return ""
    return value


def _extract_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _coerce_price(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
    return None


def _stable_reference(*basis: str) -> str:
    seed = "|".join(part for part in basis if part) or "product"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"c3_{digest[:24]}"


_AVAILABILITY_LABELS = {
    "instock": "In stock",
    "outofstock": "Out of stock",
    "preorder": "Pre-order",
    "backorder": "Back order",
    "limitedavailability": "Limited availability",
    "soldout": "Sold out",
    "discontinued": "Discontinued",
}


def _normalize_availability(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Unknown"
    key = raw.lower().rstrip("/")
    if key in _AVAILABILITY_LABELS:
        return _AVAILABILITY_LABELS[key]
    if key.startswith(("https://schema.org/", "http://schema.org/")):
        term = key.rsplit("/", 1)[-1]
        return term[:60] or "Unknown"
    return raw[:60]


def _first_brand_name(brands: Any) -> str:
    if isinstance(brands, list):
        for brand in brands:
            if isinstance(brand, dict) and brand.get("name"):
                return str(brand["name"]).strip()
    return ""


def _select_image(images: Any) -> str:
    if not isinstance(images, list):
        return ""
    main = None
    first = None
    for image in images:
        if not isinstance(image, dict):
            continue
        url = _normalize_url(image.get("url") or image.get("cleaned_url"))
        if not url:
            continue
        if first is None:
            first = url
        if image.get("is_main_image") and main is None:
            main = url
    return main or first or ""


def _summarize_variant(variants: Any) -> str:
    if not isinstance(variants, dict):
        return ""
    selected = variants.get("selected")
    if isinstance(selected, dict):
        parts = [f"{key}: {value}" for key, value in selected.items() if value not in (None, "")]
        return ", ".join(parts)[:200]
    if isinstance(selected, list):
        return ", ".join(str(item) for item in selected if item)[:200]
    return str(selected).strip()[:200] if selected else ""


def _offer_price(offer: Dict[str, Any]) -> Optional[float]:
    price_obj = offer.get("price")
    if isinstance(price_obj, dict):
        return _coerce_price(price_obj.get("price"))
    return _coerce_price(price_obj)


def _select_offer(offers: List[Any]) -> tuple[Optional[Dict[str, Any]], List[str]]:
    """Choose the representative offer and detect condition conflicts.

    A product can carry several merchant offers. PayShield never averages them
    into a single number; it selects the cheapest in-stock offer (preferring new
    condition) and keeps that offer's own price, condition, and domain. A set of
    offers that mixes new and used conditions is reported as a conflict.
    """
    valid: List[Dict[str, Any]] = []
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        if _offer_price(offer) is None:
            continue
        if not _normalize_url(offer.get("url")):
            continue
        valid.append(offer)

    if not valid:
        return None, ["no merchant offer with both a URL and a numeric price was returned"]

    conditions = {
        str(offer.get("condition")).lower()
        for offer in valid
        if offer.get("condition")
    }
    conflicts: List[str] = []
    if {"new", "used"} <= conditions:
        conflicts.append("merchant offers mix new and used condition")

    def rank(offer: Dict[str, Any]):
        availability = str(offer.get("availability") or "").lower()
        in_stock = 0 if availability == "instock" else 1
        condition = str(offer.get("condition") or "").lower()
        condition_rank = 0 if condition in ("", "new") else 1
        price = _offer_price(offer)
        return (in_stock, condition_rank, price if price is not None else float("inf"))

    return min(valid, key=rank), conflicts


class Channel3SearchProvider:
    """Structured product search provider via the Channel3 API."""

    endpoint = "https://api.trychannel3.com/v1/search"
    provider_name = "channel3"

    # Channel3 documents a hard maximum of 30 for ``limit``.
    MAX_LIMIT = 30

    def __init__(self, api_key: str | None = None, timeout: int = 10):
        self.api_key = (
            api_key if api_key is not None else os.getenv("CHANNEL3_API_KEY", "")
        ).strip()
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
            raise Channel3ProviderError(
                "Channel3 API key is not configured. Set CHANNEL3_API_KEY in the environment.",
                status_code=503,
            )

        limit = max(1, min(int(max_results), self.MAX_LIMIT))
        payload = self._build_request(
            query, budget=budget, currency=currency, category=category,
            country=country, limit=limit,
        )

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except requests.Timeout:
            raise Channel3ProviderError(
                "Channel3 search request timed out.", status_code=503
            ) from None
        except requests.RequestException:
            raise Channel3ProviderError(
                "Channel3 search request failed to reach the provider.", status_code=503
            ) from None

        self._raise_for_status(response)

        try:
            data = response.json()
        except ValueError:
            raise Channel3ProviderError(
                "Channel3 provider returned malformed JSON.", status_code=502
            ) from None

        if not isinstance(data, dict) or not isinstance(data.get("products"), list):
            raise Channel3ProviderError(
                "Channel3 provider returned an unexpected result shape.", status_code=502
            )

        products = data["products"]
        results: list[ProductSearchResult] = []
        rejection_counts: Dict[str, int] = {}
        for product in products:
            result, reason = self._normalize_product(
                product, default_currency=currency.upper()
            )
            if reason is not None:
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                continue
            assert result is not None
            results.append(result)

        notes = [
            "Channel3 returned structured products; each result carries the "
            "cheapest in-stock merchant offer."
        ]
        diagnostics = SearchDiagnostics(
            provider=self.provider_name,
            primary_provider=self.provider_name,
            configured=True,
            query=query,
            provider_result_count=len(products),
            accepted_count=len(results),
            rejected_count=sum(rejection_counts.values()),
            rejection_reasons=rejection_counts,
            notes=notes,
        )
        return SearchOutcome(results=results, diagnostics=diagnostics)

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #
    def _build_request(
        self,
        query: str,
        *,
        budget: float | None,
        currency: str,
        category: str | None,
        country: str,
        limit: int,
    ) -> Dict[str, Any]:
        text = (query or "").strip()
        # ``filters.category_ids`` expects Channel3 category slugs, not a
        # free-text hint, so the hint is folded into the query instead of being
        # sent as a (rejected) top-level field.
        if category and category.strip():
            text = f"{text} {category.strip()}".strip()

        payload: Dict[str, Any] = {"query": text, "limit": limit}

        if budget is not None:
            try:
                payload["filters"] = {"price": {"max_price": float(budget)}}
            except (TypeError, ValueError):
                pass

        config: Dict[str, Any] = {}
        if country:
            config["country"] = country.upper()
        if currency:
            config["currency"] = currency.upper()
        if config:
            payload["config"] = config
        return payload

    def _raise_for_status(self, response) -> None:
        status = response.status_code
        if status in (401, 403):
            raise Channel3ProviderError(
                "Channel3 authentication failed. Verify the API key is valid.",
                status_code=502,
            )
        if status == 429:
            raise Channel3ProviderError(
                "Channel3 rate limit exceeded. Try again later.", status_code=429
            )
        if status >= 500:
            raise Channel3ProviderError(
                f"Channel3 provider returned a server error (HTTP {status}).",
                status_code=503,
            )
        if status != 200:
            raise Channel3ProviderError(
                f"Channel3 provider returned HTTP {status}.", status_code=502
            )

    # ------------------------------------------------------------------ #
    # Normalization
    # ------------------------------------------------------------------ #
    def _normalize_product(
        self, product: Any, *, default_currency: str
    ) -> tuple[Optional[ProductSearchResult], Optional[str]]:
        if not isinstance(product, dict):
            return None, "invalid_product"

        title = str(product.get("title") or "").strip()
        if not title:
            return None, "missing_title"

        offers = product.get("offers")
        if not isinstance(offers, list) or not offers:
            return None, "no_offers"

        best, conflicts = _select_offer(offers)
        if best is None:
            return None, "no_usable_offer"

        source_url = _normalize_url(best.get("url"))
        if not source_url:
            return None, "no_usable_offer"

        price = _offer_price(best)
        price_obj = best.get("price") if isinstance(best.get("price"), dict) else {}
        offer_currency_raw = price_obj.get("currency") if isinstance(price_obj, dict) else None
        # Never silently relabel one currency as another. If the offer does not
        # carry an explicit currency, the price is unverified and the result
        # stays CANDIDATE until enrichment can confirm it against the retailer
        # page.
        offer_currency = str(offer_currency_raw).strip().upper() if offer_currency_raw else ""
        currency = offer_currency or default_currency
        offer_currency_explicit = bool(offer_currency)
        compare_at = (
            _coerce_price(price_obj.get("compare_at_price"))
            if isinstance(price_obj, dict)
            else None
        )

        domain = str(best.get("domain") or "").strip().lower().removeprefix("www.")
        if not domain:
            domain = _extract_domain(source_url)

        availability = _normalize_availability(best.get("availability"))
        condition = str(best.get("condition") or "").strip().lower() or "unknown"

        brand = _first_brand_name(product.get("brands"))
        image_url = _select_image(product.get("images"))
        description = str(product.get("description") or "").strip()
        variant = _summarize_variant(product.get("variants"))
        seller = domain or brand
        offer_count = len([offer for offer in offers if isinstance(offer, dict)])

        product_id = str(product.get("id") or "").strip()
        reference = _stable_reference(product_id, source_url)

        # A Channel3 structured offer is a *candidate* at this stage. It carries
        # a price from the provider but has not been independently verified
        # against the retailer page. It becomes VERIFIED only after price
        # enrichment fetches the retailer page and confirms the price, currency,
        # and product identity. Material conflicts (e.g. new vs used condition
        # for the same reference) make it CONFLICT immediately.
        price_verified = False
        price_confidence = "medium" if price is not None else "none"
        if conflicts:
            evidence_status = "CONFLICT"
            unverified_reason = "; ".join(conflicts)
        elif price is not None and offer_currency_explicit and source_url:
            evidence_status = "CANDIDATE"
            unverified_reason = (
                "Channel3 structured offer has not been independently verified "
                "against the retailer page."
            )
            if not offer_currency_explicit:
                unverified_reason = (
                    "Channel3 offer did not include an explicit currency; "
                    "price cannot be verified without currency confirmation."
                )
        else:
            evidence_status = "CANDIDATE"
            unverified_reason = (
                "Channel3 offer did not include a usable numeric price, "
                "currency, or source URL."
            )
            if not offer_currency_explicit:
                unverified_reason += " The offer did not specify a currency."
            if price is None:
                unverified_reason = (
                    "Channel3 offer did not include a usable numeric price."
                )
            if not source_url:
                unverified_reason = (
                    "Channel3 offer did not include a usable source URL."
                )

        reasons = [f"Channel3 structured offer from {domain or 'an unknown merchant'}"]
        if offer_count > 1:
            reasons.append(
                f"{offer_count} merchant offers were returned; the cheapest in-stock "
                "offer is shown"
            )
        if compare_at is not None and price is not None and compare_at > price:
            reasons.append(f"listed at {compare_at:.2f} {currency} before discount")
        if brand:
            reasons.append(f"brand: {brand}")
        if not offer_currency_explicit:
            reasons.append(
                f"Currency defaulted to {currency}; offer did not specify currency."
            )

        now = _utcnow()
        result = ProductSearchResult(
            id=reference,
            product_reference=reference,
            title=title,
            source_url=source_url,
            source_domain=domain,
            snippet=description[:1000],
            retailer=seller or domain,
            seller=seller,
            image_url=image_url,
            price=price,
            price_verified=price_verified,
            price_currency=currency if price is not None else "",
            price_type="selling_price" if price is not None else "",
            price_method="channel3_structured" if price is not None else "",
            price_confidence=price_confidence,
            price_source_url=source_url,
            price_retrieved_at=now,
            price_unverified_reason=unverified_reason,
            availability=availability,
            result_type="product",
            currency=currency,
            search_timestamp=now,
            retrieval_status="retrieved",
            retrieval_reason="",
            retrieval_http_status=None,
            provider=self.provider_name,
            is_fallback=False,
            evidence_status=evidence_status,
            condition=condition,
            variant=variant,
            offer_count=offer_count,
            evidence_reasons=reasons,
            conflicts=conflicts,
        )
        return result, None
