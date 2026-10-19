"""Tests for PayShield Financial Constitution policy engine."""

import pytest
from backend.policy.decision_engine import make_decision
from backend.policy.engine import FinancialConstitution
from backend.risk.risk_engine import (
    calculate_risk_score,
    get_amount_risk,
    get_decision,
    get_risk_bar,
    get_risk_level,
    is_amount_is_normal,
    is_recipient_known,
)


@pytest.fixture
def constitution():
    return FinancialConstitution(
        max_auto_payment=10000,
        approval_limit=60000,
        blocked_categories=["gift_cards"],
    )


def test_payment_under_auto_limit_is_allowed(constitution):
    result = constitution.check_payment(5000, "electronics")
    assert result["decision"] == "ALLOW"
    assert "automatic limit" in result["reason"]


def test_payment_between_auto_and_approval_limit_requires_review(constitution):
    result = constitution.check_payment(25000, "electronics")
    assert result["decision"] == "REVIEW"
    assert "Human approval" in result["reason"]


def test_payment_exceeding_approval_limit_is_blocked(constitution):
    result = constitution.check_payment(75000, "electronics")
    assert result["decision"] == "BLOCK"
    assert "exceeds" in result["reason"]


def test_blocked_category_is_blocked(constitution):
    result = constitution.check_payment(5000, "gift_cards")
    assert result["decision"] == "BLOCK"
    assert "blocked" in result["reason"]


def test_zero_or_negative_amount_is_blocked(constitution):
    result = constitution.check_payment(0, "electronics")
    assert result["decision"] == "BLOCK"

    result_neg = constitution.check_payment(-50, "electronics")
    assert result_neg["decision"] == "BLOCK"


def test_policy_block_wins_over_low_risk():
    decision, risk_score, risk_level, policy_result = make_decision(
        5000, "gift_cards", 10000, "friend", ["friend", "shop"]
    )
    assert risk_level == "LOW"
    assert risk_score == 0
    assert policy_result["decision"] == "BLOCK"
    assert decision == "BLOCK"


def test_low_risk_allowed_category_is_allowed():
    decision, risk_score, risk_level, _ = make_decision(
        5000, "electronics", 10000, "friend", ["friend", "shop"]
    )
    assert risk_level == "LOW"
    assert risk_score == 0
    assert decision == "ALLOW"


def test_high_risk_blocks_even_when_policy_allows():
    decision, risk_score, risk_level, policy_result = make_decision(
        9000, "electronics", 1000, "new_user", ["friend", "shop"]
    )
    assert risk_level == "HIGH"
    assert policy_result["decision"] == "ALLOW"
    assert decision == "BLOCK"


def test_risk_engine_helpers():
    assert is_amount_is_normal(500, 1000) == 0
    assert is_amount_is_normal(1500, 1000) == 30
    assert is_amount_is_normal(3000, 1000) == 60

    assert is_recipient_known("Amazon", ["Amazon", "Flipkart"]) == 0
    assert is_recipient_known("Unknown", ["Amazon", "Flipkart"]) == 1

    score = calculate_risk_score(get_amount_risk(5000, 1000), 1)
    assert score > 0

    level = get_risk_level(score)
    assert level in {"LOW", "MEDIUM", "HIGH"}
    assert get_decision(level) in {"ALLOW", "REVIEW", "BLOCK"}

    bar = get_risk_bar(score)
    assert bar.startswith("[") and bar.endswith("]")


def test_missing_mandatory_evidence_never_allows_even_with_low_risk():
    decision, risk_score, risk_level, policy_result = make_decision(
        5000,
        "electronics",
        10000,
        "friend",
        ["friend", "shop"],
        mandatory_evidence_verified=False,
        evidence_status="CANDIDATE",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    # Low risk and an ALLOW policy must not override missing mandatory evidence.
    assert risk_score == 0
    assert risk_level == "LOW"
    assert policy_result["decision"] == "ALLOW"
    assert decision != "ALLOW"
    assert decision in {"REVIEW", "BLOCK"}


def test_verified_offer_false_never_allows():
    decision, _, _, _ = make_decision(
        5000,
        "electronics",
        10000,
        "friend",
        ["friend", "shop"],
        verified_offer=False,
        evidence_status="UNAVAILABLE",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert decision != "ALLOW"


def test_verified_merchant_offer_false_never_allows():
    decision, _, _, _ = make_decision(
        5000,
        "electronics",
        10000,
        "friend",
        ["friend", "shop"],
        verified_merchant_offer=False,
        evidence_status="UNAVAILABLE",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert decision != "ALLOW"


def test_policy_allow_and_low_risk_never_blocks():
    # The Checkout screenshot showed decision BLOCK with risk 40/LOW and policy
    # ALLOW. No single server-side make_decision call can produce that
    # combination: a LOW risk with an ALLOW policy (and verified evidence) must
    # always yield ALLOW. Policy ALLOW is not equivalent to final ALLOW, but a
    # LOW risk + ALLOW policy must not synthesize a spurious BLOCK.
    decision, risk_score, risk_level, policy_result = make_decision(
        1000,
        "electronics",
        10000,
        "stranger",
        ["friend", "shop"],
        mandatory_evidence_verified=True,
        evidence_status="VERIFIED",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert risk_score == 40
    assert risk_level == "LOW"
    assert policy_result["decision"] == "ALLOW"
    assert decision == "ALLOW"


def test_risk_score_100_high_blocks_even_when_policy_allows():
    decision, risk_score, risk_level, policy_result = make_decision(
        60000,
        "electronics",
        1000,
        "new_user",
        ["friend", "shop"],
        mandatory_evidence_verified=True,
        evidence_status="VERIFIED",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert risk_score == 100
    assert risk_level == "HIGH"
    assert policy_result["decision"] == "ALLOW"
    assert decision == "BLOCK"


def test_policy_allow_is_not_final_authorization():
    # Policy ALLOW with missing mandatory evidence must not become ALLOW.
    decision, _, _, policy_result = make_decision(
        5000,
        "electronics",
        10000,
        "friend",
        ["friend", "shop"],
        mandatory_evidence_verified=False,
        evidence_status="UNAVAILABLE",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert policy_result["decision"] == "ALLOW"
    assert decision != "ALLOW"
    assert decision in {"REVIEW", "BLOCK"}
