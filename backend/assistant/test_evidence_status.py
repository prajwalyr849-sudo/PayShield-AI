"""Tests for evidence-status classification and combined verification logic."""

from datetime import datetime, timezone

import pytest

from backend.assistant.evidence_status import (
    CANDIDATE,
    CONFLICT,
    UNAVAILABLE,
    VERIFIED,
    combined_evidence_status,
    is_fresh,
    structured_offer_status,
)


def _fresh_timestamp() -> str:
    """Retrieval timestamp that is always inside the freshness window."""
    return datetime.now(timezone.utc).isoformat()


def test_structured_offer_with_price_and_currency_is_candidate():
    """A structured offer with price + currency is CANDIDATE, not VERIFIED,
    until independently verified against the retailer page."""
    status = structured_offer_status(
        has_offer=True, price=349.99, currency="USD", conflicts=None
    )
    assert status == CANDIDATE


def test_structured_offer_without_price_is_candidate():
    """A structured offer without a price is CANDIDATE."""
    status = structured_offer_status(
        has_offer=True, price=None, currency="USD", conflicts=None
    )
    assert status == CANDIDATE


def test_structured_offer_without_currency_is_candidate():
    """A structured offer without currency is CANDIDATE."""
    status = structured_offer_status(
        has_offer=True, price=349.99, currency="", conflicts=None
    )
    assert status == CANDIDATE


def test_structured_offer_without_offer_is_unavailable():
    """No offer means UNAVAILABLE."""
    status = structured_offer_status(
        has_offer=False, price=None, currency="USD", conflicts=None
    )
    assert status == UNAVAILABLE


def test_structured_offer_with_conflicts_is_conflict():
    """Material conflicts between offers make it CONFLICT."""
    status = structured_offer_status(
        has_offer=True,
        price=349.99,
        currency="USD",
        conflicts=["merchant offers mix new and used condition"],
    )
    assert status == CONFLICT


def test_structured_offer_with_conflicts_is_conflict_even_with_price():
    """Even with a valid price, conflicts make it CONFLICT."""
    status = structured_offer_status(
        has_offer=True,
        price=349.99,
        currency="USD",
        conflicts=["merchant offers mix new and used condition"],
    )
    assert status == CONFLICT


def test_is_fresh_with_recent_timestamp():
    """A recent timestamp is fresh."""
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    assert is_fresh(recent, max_hours=24) is True


def test_is_fresh_with_stale_timestamp():
    """A stale timestamp is not fresh."""
    assert is_fresh("2020-01-01T00:00:00Z", max_hours=24) is False


def test_is_fresh_with_missing_timestamp():
    """A missing timestamp is treated as fresh (cannot prove staleness)."""
    assert is_fresh(None, max_hours=24) is True
    assert is_fresh("", max_hours=24) is True


def test_is_fresh_with_unparseable_timestamp():
    """An unparseable timestamp is not fresh."""
    assert is_fresh("not-a-date", max_hours=24) is False


def test_combined_evidence_status_provider_verified_fresh():
    """Provider-verified + fresh -> VERIFIED."""
    status = combined_evidence_status(
        provider_status=VERIFIED,
        price_verified=True,
        retrieved_at=_fresh_timestamp(),
        identity_match="MATCH",
        conflicts=None,
    )
    assert status == VERIFIED


def test_combined_evidence_status_provider_candidate_not_verified():
    """Provider CANDIDATE + price not verified -> CANDIDATE."""
    status = combined_evidence_status(
        provider_status=CANDIDATE,
        price_verified=False,
        retrieved_at="2026-10-16T00:00:00Z",
        identity_match="MATCH",
        conflicts=None,
    )
    assert status == CANDIDATE


def test_combined_evidence_status_conflict_is_always_conflict():
    """Provider CONFLICT is always preserved."""
    status = combined_evidence_status(
        provider_status=CONFLICT,
        price_verified=True,
        retrieved_at="2026-10-16T00:00:00Z",
        identity_match="MATCH",
        conflicts=["mixed conditions"],
    )
    assert status == CONFLICT


def test_combined_evidence_status_identity_mismatch_is_conflict():
    """Identity MISMATCH is a material conflict."""
    status = combined_evidence_status(
        provider_status=CANDIDATE,
        price_verified=True,
        retrieved_at="2026-10-16T00:00:00Z",
        identity_match="MISMATCH",
        conflicts=None,
    )
    assert status == CONFLICT


def test_combined_evidence_status_stale_evidence_downgrades():
    """Verified but stale -> CANDIDATE."""
    status = combined_evidence_status(
        provider_status=VERIFIED,
        price_verified=True,
        retrieved_at="2020-01-01T00:00:00Z",
        identity_match="MATCH",
        conflicts=None,
    )
    assert status == CANDIDATE


def test_combined_evidence_status_verified_and_fresh():
    """Full chain: provider VERIFIED + price verified + fresh + match -> VERIFIED."""
    status = combined_evidence_status(
        provider_status=VERIFIED,
        price_verified=True,
        retrieved_at=_fresh_timestamp(),
        identity_match="MATCH",
        conflicts=None,
    )
    assert status == VERIFIED
