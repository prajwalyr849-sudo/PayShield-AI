"""Primary/fallback product-provider selection with explicit provenance.

Channel3 is the primary structured product provider. The general web-search
provider (``EndlessSearchProvider``) is only ever used as an explicitly-enabled
fallback, and every result it produces is stamped ``is_fallback=True`` with the
provider that actually produced it. PayShield never silently substitutes one
provider for another, and never merges results from two providers into one
answer.
"""

from __future__ import annotations

import os
from typing import Any

from backend.assistant.channel3_provider import Channel3ProviderError
from backend.assistant.evidence_status import combined_evidence_status
from backend.assistant.models import SearchDiagnostics
from backend.assistant.search_provider import ProductSearchError, SearchOutcome

_TRUTHY = {"1", "true", "yes", "on"}


def fallback_enabled_from_env() -> bool:
    """The fallback is opt-in: set ``PAYSHIELD_LIVE_SEARCH_FALLBACK`` to enable it."""
    return os.getenv("PAYSHIELD_LIVE_SEARCH_FALLBACK", "").strip().lower() in _TRUTHY


def _stamp(results: Any, *, provider: str, is_fallback: bool) -> None:
    for result in results or []:
        try:
            result.provider = provider
            result.is_fallback = is_fallback
        except Exception:  # pragma: no cover - defensive
            pass


def finalize_evidence_status(results: Any) -> Any:
    """Re-derive the evidence state for all results after price enrichment.

    Called after price enrichment, because a result can only become
    ``VERIFIED`` once a source-verified price has been extracted from the
    retailer page. Applies the combined verification rules to every result
    regardless of provider: provider-sourced offers start as CANDIDATE and
    are promoted to VERIFIED only after independent verification succeeds.
    """
    for result in results or []:
        try:
            result.evidence_status = combined_evidence_status(
                provider_status=result.evidence_status,
                price_verified=bool(getattr(result, "price_verified", False)),
                retrieved_at=getattr(result, "price_retrieved_at", ""),
                identity_match=getattr(result, "identity_match", ""),
                conflicts=list(getattr(result, "conflicts", []) or []),
            )
        except Exception:  # pragma: no cover - defensive
            pass
    return results


class ProductProviderService:
    """Runs the primary provider and, when explicitly enabled, a fallback."""

    def __init__(self, primary: Any, fallback: Any = None, *, fallback_enabled: bool = False):
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled

    # ------------------------------------------------------------------ #
    # Introspection (used by status endpoint and callers)
    # ------------------------------------------------------------------ #
    @property
    def provider_name(self) -> str:
        return getattr(self.primary, "provider_name", "unknown")

    @property
    def primary_provider_name(self) -> str:
        return getattr(self.primary, "provider_name", "unknown")

    @property
    def fallback_provider_name(self) -> str:
        return getattr(self.fallback, "provider_name", "") if self.fallback else ""

    @property
    def configured(self) -> bool:
        if bool(getattr(self.primary, "configured", False)):
            return True
        return self._fallback_usable()

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
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
        kwargs = dict(
            budget=budget,
            currency=currency,
            category=category,
            country=country,
            max_results=max_results,
        )

        if bool(getattr(self.primary, "configured", False)):
            try:
                outcome = self._call(self.primary, query, **kwargs)
            except (ProductSearchError, Channel3ProviderError) as exc:
                if self._fallback_usable():
                    return self._run_fallback(
                        query,
                        reason=f"the primary provider ({self.provider_name}) failed: {exc}",
                        **kwargs,
                    )
                raise ProductSearchError(
                    f"Product search is unavailable: {exc}",
                    getattr(exc, "status_code", 503) or 503,
                ) from exc

            _stamp(outcome.results, provider=self.provider_name, is_fallback=False)
            diagnostics = outcome.diagnostics or SearchDiagnostics(query=query)
            diagnostics.provider = self.provider_name
            diagnostics.primary_provider = self.provider_name
            diagnostics.providers_attempted = [self.provider_name]
            diagnostics.fallback_used = False
            diagnostics.fallback_reason = ""
            outcome.diagnostics = diagnostics
            return outcome

        if self._fallback_usable():
            return self._run_fallback(
                query,
                reason=(
                    f"the primary provider ({self.provider_name}) is not configured"
                ),
                **kwargs,
            )

        raise ProductSearchError(
            "No product search provider is configured. Set CHANNEL3_API_KEY, or "
            "enable and configure the explicit fallback provider.",
            503,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _fallback_usable(self) -> bool:
        return bool(
            self.fallback is not None
            and self.fallback_enabled
            and bool(getattr(self.fallback, "configured", False))
        )

    @staticmethod
    def _call(provider: Any, query: str, **kwargs: Any) -> SearchOutcome:
        if hasattr(provider, "search_with_diagnostics"):
            return provider.search_with_diagnostics(query, **kwargs)
        results = provider.search(query, **kwargs)
        return SearchOutcome(
            results=results,
            diagnostics=SearchDiagnostics(
                provider=getattr(provider, "provider_name", "unknown"),
                configured=True,
                query=query,
            ),
        )

    def _run_fallback(self, query: str, *, reason: str, **kwargs: Any) -> SearchOutcome:
        try:
            outcome = self._call(self.fallback, query, **kwargs)
        except (ProductSearchError, Channel3ProviderError) as exc:
            raise ProductSearchError(
                f"Product search is unavailable: {reason}; the fallback provider "
                f"also failed: {exc}",
                503,
            ) from exc

        name = getattr(self.fallback, "provider_name", "fallback")
        _stamp(outcome.results, provider=name, is_fallback=True)
        for result in outcome.results or []:
            try:
                result.evidence_status = fallback_source_status(
                    price_verified=bool(getattr(result, "price_verified", False))
                )
            except Exception:  # pragma: no cover - defensive
                pass

        diagnostics = outcome.diagnostics or SearchDiagnostics(query=query)
        diagnostics.provider = name
        diagnostics.primary_provider = self.provider_name
        diagnostics.providers_attempted = [self.provider_name, name]
        diagnostics.fallback_used = True
        diagnostics.fallback_reason = reason
        diagnostics.notes = list(diagnostics.notes) + [
            f"Results came from the fallback provider: {reason}."
        ]
        outcome.diagnostics = diagnostics
        return outcome
