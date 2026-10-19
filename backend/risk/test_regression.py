"""Regression tests for PayShield risk intelligence (Priority 2).

Covers:
  * Low numerical risk can never override a policy BLOCK.
  * Missing mandatory evidence follows configured policy (REVIEW/BLOCK, never ALLOW).
  * Risk score is an explainable indicator, not a fraud probability.
  * Formula: risk_score = amount_risk + recipient_risk; amount_risk in {0,30,60};
    recipient_risk is 40 when merchant unknown else 0.
  * Thresholds: HIGH >= 80, MEDIUM >= 50, else LOW.
"""

from backend.policy.decision_engine import make_decision
from backend.risk.risk_engine import (
    calculate_risk_score,
    get_amount_risk,
    get_decision,
    get_risk_level,
    is_amount_is_normal,
    is_recipient_known,
)


def test_low_risk_cannot_override_block():
    """A risk score of 0/LOW must not override a policy/category BLOCK."""
    decision, score, level, policy = make_decision(
        5000, "gift_cards", 10000, "friend", ["friend", "shop"],
    )
    assert score == 0
    assert level == "LOW"
    assert policy["decision"] == "BLOCK"
    assert decision == "BLOCK"


def test_high_risk_blocks_even_when_policy_allows():
    """HIGH risk overrides a policy ALLOW (risk strengthens, never weakens)."""
    decision, score, level, policy = make_decision(
        60000, "electronics", 1000, "new_user", ["friend", "shop"],
        mandatory_evidence_verified=True, evidence_status="VERIFIED",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert score == 100
    assert level == "HIGH"
    assert policy["decision"] == "ALLOW"
    assert decision == "BLOCK"


def test_missing_mandatory_evidence_never_allows():
    """Missing/unverified mandatory evidence yields REVIEW/BLOCK, never ALLOW,
    even with LOW risk and an ALLOW policy."""
    decision, score, level, policy = make_decision(
        5000, "electronics", 10000, "friend", ["friend", "shop"],
        mandatory_evidence_verified=False, evidence_status="CANDIDATE",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert score == 0
    assert level == "LOW"
    assert policy["decision"] == "ALLOW"
    assert decision != "ALLOW"
    assert decision in {"REVIEW", "BLOCK"}


def test_verified_evidence_low_risk_allows():
    """Verified evidence + LOW risk + ALLOW policy = ALLOW."""
    decision, score, level, policy = make_decision(
        1000, "electronics", 10000, "stranger", ["friend", "shop"],
        mandatory_evidence_verified=True, evidence_status="VERIFIED",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert score == 40
    assert level == "LOW"
    assert policy["decision"] == "ALLOW"
    assert decision == "ALLOW"


def test_amount_risk_scale_is_authoritative():
    """Single authoritative amount scale: 0 / 30 / 60."""
    assert is_amount_is_normal(500, 1000) == 0
    assert is_amount_is_normal(1500, 1000) == 30
    assert is_amount_is_normal(3000, 1000) == 60
    # get_amount_risk is a legacy alias delegating to the same scale.
    assert get_amount_risk(500, 1000) == 0
    assert get_amount_risk(1500, 1000) == 30
    assert get_amount_risk(3000, 1000) == 60


def test_recipient_risk_scale():
    assert is_recipient_known("Amazon", ["Amazon", "Flipkart"]) == 0
    assert is_recipient_known("UnknownMerchant", ["Amazon", "Flipkart"]) == 1


def test_score_composition():
    """score = amount_risk + (40 if recipient unknown else 0)."""
    assert calculate_risk_score(0, 0) == 0
    assert calculate_risk_score(0, 1) == 40
    assert calculate_risk_score(30, 0) == 30
    assert calculate_risk_score(60, 1) == 100


def test_risk_level_thresholds():
    assert get_risk_level(0) == "LOW"
    assert get_risk_level(49) == "LOW"
    assert get_risk_level(50) == "MEDIUM"
    assert get_risk_level(79) == "MEDIUM"
    assert get_risk_level(80) == "HIGH"
    assert get_risk_level(100) == "HIGH"


def test_decision_from_level():
    assert get_decision("LOW") == "ALLOW"
    assert get_decision("MEDIUM") == "REVIEW"
    assert get_decision("HIGH") == "BLOCK"


def test_score_is_not_a_fraud_probability():
    """Score is an explainable indicator; a 100 score is not '100% fraud'."""
    assert get_risk_level(100) == "HIGH"
    # No probability language is returned anywhere in the decision result.
    decision, score, level, policy = make_decision(
        60000, "electronics", 1000, "new_user", ["friend", "shop"],
        mandatory_evidence_verified=True, evidence_status="VERIFIED",
        policy_result={"decision": "ALLOW", "reason": "within limit"},
    )
    assert score == 100
    assert decision == "BLOCK"
    assert "probab" not in str((decision, score, level, policy)).lower()
