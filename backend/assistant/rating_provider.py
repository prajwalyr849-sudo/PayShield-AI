"""Pluggable live product rating provider adapters.

PayShield never invents ratings, review counts, or provider credentials. A
rating provider is responsible only for returning what it actually observed
from its upstream source -- or reporting that nothing is available.

Two adapters exist:

* ``TrustpilotRatingProvider`` -- queries the Trustpilot Product Reviews API
  for a merchant's product review summary (``starsAverage`` +
  ``numberOfReviews``). Requires ``TRUSTPILOT_API_KEY`` and
  ``TRUSTPILOT_BUSINESS_UNIT_ID``. Degrades gracefully (returns unavailable)
  when either is missing.
* ``NullRatingProvider`` -- always reports that no live rating is available.
  Used when no provider is configured, so callers never have to special-case
  absence.

Both adapters implement the :class:`ProductRatingProvider` protocol.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional, Protocol
from urllib.parse import quote

import requests


class ProductRatingError(RuntimeError):
    """Safe, user-facing failure from a rating provider."""

    def __init__(self, message: str, status_code: int = 503, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class ProductRatingResult:
    """A single live product rating observation, with full provenance."""

    def __init__(
        self,
        *,
        provider: str,
        rating: Optional[float] = None,
        review_count: Optional[int] = None,
        source_url: Optional[str] = None,
        status: str = "unavailable",
        reason: str = "",
        retrieved_at: Optional[str] = None,
        ttl_seconds: int = 0,
    ):
        self.provider = provider
        self.rating = rating
        self.review_count = review_count
        self.source_url = source_url
        self.status = status
        self.reason = reason
        self.retrieved_at = retrieved_at or _utcnow()
        self.ttl_seconds = ttl_seconds

    @property
    def available(self) -> bool:
        return self.status == "available" and self.rating is not None

    def model_dump(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "rating": self.rating,
            "review_count": self.review_count,
            "source_url": self.source_url,
            "status": self.status,
            "reason": self.reason,
            "retrieved_at": self.retrieved_at,
            "ttl_seconds": self.ttl_seconds,
            "available": self.available,
        }


class ProductRatingProvider(Protocol):
    """Interface for a live product rating source.

    A future provider (for example another review aggregator) can implement
    this protocol; callers only depend on ``fetch_rating`` and ``configured``.
    """

    provider_name: str

    @property
    def configured(self) -> bool:  # pragma: no cover - protocol definition
        ...

    def fetch_rating(
        self,
        *,
        product_reference: str,
        source_url: str,
        sku: Optional[str] = None,
    ) -> ProductRatingResult:  # pragma: no cover - protocol definition
        ...


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Trustpilot adapter
# --------------------------------------------------------------------------- #

_TRUSTPILOT_SUMMARY_URL_TEMPLATE = (
    "https://api.trustpilot.com/v1/product-reviews/business-units/{business_unit_id}"
)


class TrustpilotRatingProvider:
    """Trustpilot Product Reviews API adapter.

    Fetches a merchant's public product review summary for one or more SKUs.
    The public endpoint uses ``apikey`` authentication (no OAuth flow) and
    returns ``starsAverage`` plus ``numberOfReviews``.

    Required environment variables (never sent to the browser):
    * ``TRUSTPILOT_API_KEY`` -- public Trustpilot API key
    * ``TRUSTPILOT_BUSINESS_UNIT_ID`` -- the merchant's Trustpilot business unit

    If either is missing the provider reports itself as unconfigured and
    ``fetch_rating`` returns an unavailable result rather than raising.
    """

    provider_name = "trustpilot"

    def __init__(
        self,
        api_key: Optional[str] = None,
        business_unit_id: Optional[str] = None,
        timeout: int = 10,
        ttl_seconds: int = 3600,
    ):
        self.api_key = (api_key or os.getenv("TRUSTPILOT_API_KEY", "")).strip()
        self.business_unit_id = (
            business_unit_id or os.getenv("TRUSTPILOT_BUSINESS_UNIT_ID", "")
        ).strip()
        self.timeout = timeout
        self.ttl_seconds = ttl_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.business_unit_id)

    def fetch_rating(
        self,
        *,
        product_reference: str,
        source_url: str,
        sku: Optional[str] = None,
    ) -> ProductRatingResult:
        if not self.configured:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason="Trustpilot provider is not configured. Set TRUSTPILOT_API_KEY and TRUSTPILOT_BUSINESS_UNIT_ID.",
                retrieved_at=_utcnow(),
                ttl_seconds=0,
            )

        target_sku = sku or product_reference
        params: list[str] = [f"sku={quote(str(target_sku), safe='')}"]

        url = _TRUSTPILOT_SUMMARY_URL_TEMPLATE.format(
            business_unit_id=quote(self.business_unit_id, safe="")
        )
        if params:
            url += "?" + "&".join(params)

        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
        except requests.Timeout:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason="Trustpilot request timed out.",
                retrieved_at=_utcnow(),
                ttl_seconds=self.ttl_seconds,
            )
        except requests.RequestException as exc:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason=f"Trustpilot request could not reach the provider: {exc}",
                retrieved_at=_utcnow(),
                ttl_seconds=self.ttl_seconds,
            )

        if response.status_code in {401, 403}:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason="Trustpilot authentication failed. Verify TRUSTPILOT_API_KEY.",
                retrieved_at=_utcnow(),
                ttl_seconds=0,
            )
        if response.status_code == 429:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason="Trustpilot rate limit reached. Try again later.",
                retrieved_at=_utcnow(),
                ttl_seconds=self.ttl_seconds,
            )
        if response.status_code >= 500:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason=f"Trustpilot returned a server error (HTTP {response.status_code}).",
                retrieved_at=_utcnow(),
                ttl_seconds=self.ttl_seconds,
            )
        if not 200 <= response.status_code < 300:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason=f"Trustpilot returned HTTP {response.status_code}.",
                retrieved_at=_utcnow(),
                ttl_seconds=self.ttl_seconds,
            )

        try:
            payload = response.json()
        except ValueError:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason="Trustpilot returned invalid data.",
                retrieved_at=_utcnow(),
                ttl_seconds=self.ttl_seconds,
            )

        if not isinstance(payload, dict):
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason="Trustpilot returned an unexpected response shape.",
                retrieved_at=_utcnow(),
                ttl_seconds=self.ttl_seconds,
            )

        stars_average = payload.get("starsAverage")
        number_of_reviews = payload.get("numberOfReviews") or {}
        total_reviews = (
            number_of_reviews.get("total")
            if isinstance(number_of_reviews, dict)
            else number_of_reviews
        )

        rating: Optional[float] = None
        if isinstance(stars_average, (int, float)) and not isinstance(stars_average, bool):
            rating = round(float(stars_average), 1)
        review_count: Optional[int] = None
        if isinstance(total_reviews, (int, float)) and not isinstance(total_reviews, bool):
            review_count = int(total_reviews)

        if rating is None and review_count is None:
            return ProductRatingResult(
                provider=self.provider_name,
                status="unavailable",
                reason="Trustpilot returned no review summary for this product.",
                retrieved_at=_utcnow(),
                ttl_seconds=self.ttl_seconds,
            )

        return ProductRatingResult(
            provider=self.provider_name,
            rating=rating,
            review_count=review_count,
            source_url=source_url,
            status="available",
            reason="",
            retrieved_at=_utcnow(),
            ttl_seconds=self.ttl_seconds,
        )


# --------------------------------------------------------------------------- #
# Null provider (no live rating available)
# --------------------------------------------------------------------------- #


class NullRatingProvider:
    """Always reports no live rating. Used when no provider is configured."""

    provider_name = "none"

    @property
    def configured(self) -> bool:
        return False

    def fetch_rating(
        self,
        *,
        product_reference: str,
        source_url: str,
        sku: Optional[str] = None,
    ) -> ProductRatingResult:
        return ProductRatingResult(
            provider=self.provider_name,
            status="unavailable",
            reason="No live product rating provider is configured.",
            retrieved_at=_utcnow(),
            ttl_seconds=0,
        )


def default_rating_provider() -> ProductRatingProvider:
    """Return the best-available configured rating provider, else a null provider."""
    trustpilot = TrustpilotRatingProvider()
    if trustpilot.configured:
        return trustpilot
    return NullRatingProvider()
