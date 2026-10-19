"""Phase 12 regression tests for authorization integrity invariants."""

import pytest

from backend.policy.decision_engine import make_decision
from backend.payshield.purchase_context import PurchaseContext


def test_low_risk_cannot_override_policy_block():
    decision, risk_score, risk_level, policy_result = make_decision(
        5000, "gift_cards", 10000, "friend", ["friend", "shop"]
    )
    assert risk_score == 0
    assert risk_level == "LOW"
    assert policy_result["decision"] == "BLOCK"
    assert decision == "BLOCK"


def test_missing_verified_offer_cannot_allow():
    decision, _, _, _ = make_decision(
        5000, "electronics", 10000, "friend", ["friend", "shop"],
        mandatory_evidence_verified=False,
    )
    assert decision != "ALLOW"
    assert decision in {"REVIEW", "BLOCK"}


def test_forum_evidence_cannot_satisfy_merchant_offer():
    decision, _, _, _ = make_decision(
        5000, "electronics", 10000, "friend", ["friend", "shop"],
        evidence_status="CANDIDATE",
        mandatory_evidence_verified=False,
    )
    assert decision != "ALLOW"


def test_protected_context_change_invalidates_authorization():
    original = PurchaseContext(
        product_reference="prod-1",
        merchant="merchant-a",
        quantity=1,
        unit_price="10.00",
        total_amount="10.00",
        currency="USD",
        payment_attempt="attempt-1",
        approved_intent=True,
    )
    tampered = PurchaseContext(
        product_reference="prod-1",
        merchant="merchant-a",
        quantity=1,
        unit_price="100.00",
        total_amount="100.00",
        currency="USD",
        payment_attempt="attempt-1",
        approved_intent=True,
    )
    ok, changed = original.matches(tampered)
    assert ok is False
    assert "unit_price" in changed
    assert "total_amount" in changed
    assert original.fingerprint != tampered.fingerprint
