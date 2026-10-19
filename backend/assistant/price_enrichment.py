"""Enrich discovered products with a source-verified retail price.

The search provider deliberately returns *candidates* without trusting any price
shown in a search snippet. This service retrieves each candidate's original
source page server-side and runs :mod:`backend.assistant.price_extractor` so the
stored evidence carries a real amount, currency, price type, extraction method,
and provenance -- or an explicit reason explaining why the price stays
unverified.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable, Optional

from backend.assistant.price_extractor import (
    PriceEvidence,
    ProductPageFetcher,
    extract_from_snippet,
    extract_price_from_html,
)

_TRUTHY = {"1", "true", "yes", "on"}

# schema.org availability URLs -> short, human-safe labels. Availability is only
# ever taken from explicit structured evidence, never inferred from a title.
_AVAILABILITY_LABELS = {
    "https://schema.org/instock": "In stock",
    "https://schema.org/outofstock": "Out of stock",
    "https://schema.org/preorder": "Pre-order",
    "https://schema.org/backorder": "Back order",
    "https://schema.org/limitedavailability": "Limited availability",
    "https://schema.org/instoreonly": "In store only",
    "https://schema.org/onlineonly": "Online only",
    "https://schema.org/soldout": "Sold out",
    "https://schema.org/discontinued": "Discontinued",
    "instock": "In stock",
    "outofstock": "Out of stock",
    "preorder": "Pre-order",
    "backorder": "Back order",
    "limitedavailability": "Limited availability",
    "soldout": "Sold out",
    "discontinued": "Discontinued",
}


def _normalize_availability(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    key = raw.lower().rstrip("/")
    if key in _AVAILABILITY_LABELS:
        return _AVAILABILITY_LABELS[key]
    if key.startswith("https://schema.org/") or key.startswith("http://schema.org/"):
        # An unrecognised schema.org term: keep just the term, never the URL.
        term = key.rsplit("/", 1)[-1]
        return term[:60] or ""
    return raw[:60]


def _apply(result, evidence: PriceEvidence) -> None:
    try:
        result.price = evidence.amount
        result.price_verified = evidence.verified
        result.price_currency = evidence.currency or ""
        result.price_type = evidence.price_type if evidence.price_type != "none" else ""
        result.price_method = evidence.method
        result.price_confidence = evidence.confidence
        result.price_source_url = evidence.source_url
        # Preserve the original retrieval timestamp from the provider. Enrichment
        # verifies the price against the retailer page but does not re-retrieve
        # the original offer timestamp.
        if not result.price_retrieved_at:
            result.price_retrieved_at = evidence.retrieved_at
        result.price_unverified_reason = "" if evidence.verified else evidence.reason
        availability = _normalize_availability(getattr(evidence, "availability", ""))
        if availability:
            result.availability = availability
    except Exception:  # pragma: no cover - defensive: never break a search on UI data
        pass


class PriceEnrichmentService:
    """Bounded, concurrent, fail-safe price enrichment for search results."""

    def __init__(
        self,
        *,
        fetcher=None,
        extractor: Callable = extract_price_from_html,
        snippet_extractor: Callable = extract_from_snippet,
        max_products: int = 8,
        max_workers: int = 4,
        enabled: Optional[bool] = None,
    ):
        self.fetcher = fetcher or ProductPageFetcher()
        self.extractor = extractor
        self.snippet_extractor = snippet_extractor
        self.max_products = max_products
        self.max_workers = max_workers
        if enabled is None:
            enabled = os.getenv("PAYSHIELD_FETCH_PRODUCT_PAGES", "1").lower() in _TRUTHY
        self.enabled = enabled

    def enrich(
        self,
        results: Iterable,
        *,
        expected_currency: str = "USD",
    ) -> list:
        results = list(results)
        if not self.enabled:
            return results

        products = [r for r in results if getattr(r, "result_type", "") == "product"]
        targets = products[: self.max_products]
        target_ids = {id(r) for r in targets}
        for result in results:
            if id(result) not in target_ids:
                self._mark_skipped(result)

        if not targets:
            return results

        workers = max(1, min(self.max_workers, len(targets)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._enrich_one, result, expected_currency): result
                for result in targets
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:  # pragma: no cover - defensive
                    self._mark_skipped(futures[future])
        return results

    def _mark_skipped(self, result) -> None:
        if getattr(result, "result_type", "") != "product":
            return
        if getattr(result, "price_unverified_reason", ""):
            return
        try:
            result.price_unverified_reason = (
                "price verification was skipped for this result"
            )
        except Exception:  # pragma: no cover
            pass

    def _retrieve(self, url: str):
        """Return ``(html, outcome)`` using the structured fetcher when present."""
        if hasattr(self.fetcher, "fetch_outcome"):
            outcome = self.fetcher.fetch_outcome(url)
            return outcome.html, outcome
        return self.fetcher.fetch(url), None

    def _record_retrieval(self, result, outcome) -> None:
        if outcome is None:
            return
        try:
            result.retrieval_status = outcome.status
            result.retrieval_reason = outcome.reason
            result.retrieval_http_status = outcome.http_status
        except Exception:  # pragma: no cover - defensive
            pass

    def _enrich_one(self, result, expected_currency: str) -> None:
        url = getattr(result, "source_url", "")
        title = getattr(result, "title", "")
        html = None
        outcome = None
        if url:
            html, outcome = self._retrieve(url)
            self._record_retrieval(result, outcome)

        if html:
            evidence = self.extractor(
                html,
                url,
                product_title=title,
                expected_currency=expected_currency,
            )
        else:
            evidence = self.snippet_extractor(
                getattr(result, "snippet", ""),
                url,
                expected_currency=expected_currency,
            )
            failure = (outcome.reason if outcome is not None else "") or (
                "the source page could not be retrieved"
            )
            evidence.reason = f"source page could not be retrieved: {failure}; " + (
                evidence.reason or ""
            )
        original_currency = getattr(result, "price_currency", "")
        _apply(result, evidence)

        # Currency mismatch: original offer currency differs from the verified
        # page currency. The browser-supplied price from Channel3 must not be
        # silently relabeled to match the retailer page.
        if (
            result.price_verified
            and evidence.currency
            and original_currency
            and original_currency != evidence.currency
        ):
            result.price_verified = False
            result.price_unverified_reason = (
                f"Currency mismatch: source page lists {evidence.currency}, "
                f"original offer was in {original_currency}."
            )

        # Re-derive evidence status after enrichment using the combined
        # verification rules: independent price verification, freshness,
        # identity match, and conflicts. A Channel3 structured offer starts
        # as CANDIDATE and only becomes VERIFIED after successful enrichment.
        from backend.assistant.evidence_status import combined_evidence_status

        result.evidence_status = combined_evidence_status(
            provider_status=result.evidence_status,
            price_verified=bool(result.price_verified),
            retrieved_at=result.price_retrieved_at,
            identity_match=getattr(result, "identity_match", ""),
            conflicts=list(getattr(result, "conflicts", []) or []),
        )
