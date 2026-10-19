"""Tests for PayShield AI Reason and Explainability Engine."""

import pytest
from backend.explanation.reason_engine import explain_decision


def test_allowed_decision_explanation():
    result = explain_decision(
        decision="ALLOW",
        risk_score=10,
        risk_level="LOW",
        policy_result={"decision": "ALLOW", "reason": "Payment within limit"},
        amount=150.0,
        merchant_name="Dell",
        currency="USD",
    )

    assert result["decision"] == "ALLOW"
    assert result["risk_level"] == "LOW"
    assert result["recommended_action"] == "PROCEED_TO_CAPTURE"
    assert "APPROVED" in result["summary"]
    assert any(s["category"] == "POLICY" for s in result["signals"])
    assert any(s["category"] == "RISK" for s in result["signals"])


def test_blocked_due_to_policy_explanation():
    result = explain_decision(
        decision="BLOCK",
        risk_score=20,
        risk_level="LOW",
        policy_result={"decision": "BLOCK", "reason": "Category gift_cards is blocked"},
        amount=50.0,
        merchant_name="GiftStore",
        currency="USD",
    )

    assert result["decision"] == "BLOCK"
    assert result["recommended_action"] == "REJECT_TRANSACTION"
    assert "BLOCKED" in result["summary"]
    assert any(s["severity"] == "CRITICAL" for s in result["signals"])


def test_review_required_explanation():
    result = explain_decision(
        decision="REVIEW",
        risk_score=55,
        risk_level="MEDIUM",
        policy_result={"decision": "REVIEW", "reason": "Requires supervisor sign-off"},
        amount=2500.0,
        merchant_name="NewTech",
        currency="USD",
    )

    assert result["decision"] == "REVIEW"
    assert result["recommended_action"] == "AWAIT_SUPERVISOR_APPROVAL"
    assert "HUMAN REVIEW" in result["summary"]

