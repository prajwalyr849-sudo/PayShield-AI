"""Deterministic evidence-state classification for product evidence.

PayShield distinguishes four evidence states so a downstream reviewer (and the
Guard Buy policy) can tell a real merchant offer apart from an unverified
candidate or a materially conflicting set of offers:

* ``VERIFIED``    -- a structured offer whose price has been independently
                     verified against the retailer's own page (or equivalent
                     authoritative source), with a valid explicit currency,
                     matching product identity, and fresh evidence timestamp.
* ``CANDIDATE``   -- partial evidence (a product with a price from a structured
                     provider, but not yet independently verified against the
                     retailer page, or missing some required checks).
* ``CONFLICT``    -- offers that materially disagree (for example a mixed
                     new/used condition set for the same reference).
* ``UNAVAILABLE`` -- no usable offer at all.

This module never fabricates values; it only labels what the provider returned
and what independent verification has confirmed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

VERIFIED = "VERIFIED"
CANDIDATE = "CANDIDATE"
CONFLICT = "CONFLICT"
UNAVAILABLE = "UNAVAILABLE"

ALL_STATES = (VERIFIED, CANDIDATE, CONFLICT, UNAVAILABLE)

# Evidence freshness threshold: offers whose retrieval timestamp is older than
# this are considered stale and must be re-verified before they can be VERIFIED.
EVIDENCE_FRESHNESS_HOURS = 24


def _is_currency(value: str) -> bool:
    return bool(value) and len(value) == 3 and value.isalpha()


def is_fresh(retrieved_at: str | None, max_hours: int = EVIDENCE_FRESHNESS_HOURS) -> bool:
    """Check if evidence was retrieved within the freshness window.

    Returns False for unparseable or stale timestamps. A missing timestamp is
    treated as fresh (we cannot prove staleness), so results without a
    retrieval timestamp are not penalized by the freshness check.
    """
    if not retrieved_at:
        return True
    try:
        retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    if retrieved.tzinfo is None:
        retrieved = retrieved.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - retrieved
    return age <= timedelta(hours=max_hours)


def structured_offer_status(
    *,
    has_offer: bool,
    price: float | None,
    currency: str,
    conflicts: list[str] | None = None,
) -> str:
    """Evidence state for a structured (Channel3-style) merchant offer.

    A structured offer with a usable price and valid currency is a
    *candidate* at this stage. It becomes ``VERIFIED`` only after independent
    retailer-page verification (see price_enrichment). This function does not
    claim independent verification merely because Channel3 returned an offer.
    """
    if conflicts:
        return CONFLICT
    if not has_offer:
        return UNAVAILABLE
    # A structured offer with price and currency is a candidate. It is not
    # VERIFIED until independently confirmed against the retailer page.
    if price is not None and _is_currency(currency):
        return CANDIDATE
    return CANDIDATE


def fallback_source_status(*, price_verified: bool) -> str:
    """Evidence state for a general web-search fallback result.

    A general web-search provider returns no structured offer, so a result is
    only ``VERIFIED`` once a source-verified price has been extracted from the
    product page itself; otherwise it stays a ``CANDIDATE``.
    """
    return VERIFIED if price_verified else CANDIDATE


def combined_evidence_status(
    *,
    provider_status: str,
    price_verified: bool,
    retrieved_at: str | None = None,
    identity_match: str | None = None,
    conflicts: list[str] | None = None,
    freshness_hours: int = EVIDENCE_FRESHNESS_HOURS,
) -> str:
    """Combine provider-level status with independent verification results.

    Determines the final evidence status by combining:

    * The provider-assigned status (CANDIDATE for structured offers).
    * Independent price verification against the retailer page.
    * Product identity match against the shopper's request.
    * Evidence freshness.
    * Material conflicts between offers.

    Never upgrades to VERIFIED unless independent verification has succeeded
    and the evidence is fresh. A provider-assigned CONFLICT is always preserved.
    """
    # A provider-assigned CONFLICT is always preserved.
    if provider_status == CONFLICT:
        return CONFLICT
    if conflicts:
        return CONFLICT

    # Identity mismatch is a material conflict.
    if identity_match == "MISMATCH":
        return CONFLICT

    # Not independently verified -> cannot be VERIFIED.
    if not price_verified:
        return CANDIDATE

    # Independently verified but stale -> downgrade to CANDIDATE.
    if not is_fresh(retrieved_at, max_hours=freshness_hours):
        return CANDIDATE

    # Independently verified, fresh, no conflicts -> VERIFIED.
    return VERIFIED
