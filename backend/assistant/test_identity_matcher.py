"""Tests for deterministic product identity matching."""

import pytest

from backend.assistant.identity_matcher import (
    MATCH,
    MISMATCH,
    PARTIAL_MATCH,
    UNKNOWN,
    match_identity,
    parse_identity,
)


def test_exact_model_match():
    result = match_identity("iPhone 17", "Apple iPhone 17 128GB")
    assert result.outcome == MATCH
    assert any("family=iphone" in item for item in result.matched)


def test_iphone_14_pro_max_is_not_an_iphone_17():
    result = match_identity("iPhone 17", "Restored iPhone 14 Pro Max 256GB")
    assert result.outcome == MISMATCH
    assert any("model/generation" in conflict for conflict in result.conflicts)


def test_new_device_is_not_satisfied_by_refurbished():
    result = match_identity("new iPhone 17", "Refurbished iPhone 17 128GB")
    assert result.outcome == MISMATCH
    assert any("condition" in conflict for conflict in result.conflicts)


def test_refurbished_candidate_for_silent_request_is_partial_not_match():
    result = match_identity("iPhone 17", "Refurbished iPhone 17 128GB")
    assert result.outcome == PARTIAL_MATCH
    assert any("refurbished" in reason for reason in result.reasons)


def test_storage_difference_is_partial_match():
    result = match_identity("iPhone 17 256GB", "iPhone 17 128GB")
    assert result.outcome == PARTIAL_MATCH
    assert any("storage" in conflict for conflict in result.conflicts)


def test_variant_difference_is_partial_match():
    result = match_identity("iPhone 17 Pro", "iPhone 17")
    assert result.outcome == PARTIAL_MATCH


def test_different_brand_and_family_is_mismatch():
    result = match_identity("iPhone 17", "Samsung Galaxy S24")
    assert result.outcome == MISMATCH


def test_model_number_is_compared_for_non_numeric_families():
    assert match_identity("Sony WH-1000XM5", "Sony WH1000XM5 Headphones").outcome == MATCH
    assert match_identity("Sony WH-1000XM5", "Sony WH-1000XM4 Headphones").outcome == MISMATCH


def test_informational_query_without_identity_is_unknown():
    result = match_identity(
        "noise cancelling headphones under 250 USD", "Sony WH-1000XM5"
    )
    assert result.outcome == UNKNOWN


def test_budget_number_is_not_treated_as_a_model():
    identity = parse_identity("headphones under 250 USD")
    assert "250" not in identity.model_tokens


def test_parse_identity_extracts_explicit_attributes():
    identity = parse_identity("Refurbished iPhone 17 Pro Max 256GB dual sim")
    assert identity.family == "iphone"
    assert identity.condition == "refurbished"
    assert identity.storage == "256gb"
    assert identity.variant == "pro max"
    assert "17" in identity.model_tokens


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_text_is_unknown(text):
    result = match_identity(text or "", "")
    assert result.outcome == UNKNOWN


def test_match_as_dict_shape():
    payload = match_identity("iPhone 17", "iPhone 14").as_dict()
    assert payload["identity_match"] == MISMATCH
    assert isinstance(payload["identity_reasons"], list)
    assert isinstance(payload["identity_conflicts"], list)
