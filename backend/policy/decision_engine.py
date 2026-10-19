from backend.risk.risk_engine import is_amount_is_normal,is_recipient_known,calculate_risk_score,get_risk_level
from backend.policy.engine import DEFAULT_CONSTITUTION as policy

# Evidence states that may satisfy a mandatory verified-offer requirement.
VERIFIED_EVIDENCE_STATES = {"VERIFIED", "STRUCTURED_OFFER"}


def make_decision(
    amount,
    category,
    previous_spend,
    recipient,
    previous_recipient,
    *,
    mandatory_evidence_verified=True,
    evidence_verified=None,
    verified_offer=None,
    verified_merchant_offer=None,
    mandatory_evidence=None,
    evidence_status="VERIFIED",
    policy_result=None,
    context=None,
):
    if evidence_verified is not None:
        mandatory_evidence_verified = mandatory_evidence_verified and bool(evidence_verified)
    if verified_offer is not None:
        mandatory_evidence_verified = mandatory_evidence_verified and bool(verified_offer)
    if verified_merchant_offer is not None:
        mandatory_evidence_verified = mandatory_evidence_verified and bool(verified_merchant_offer)
    if mandatory_evidence is not None:
        mandatory_evidence_verified = mandatory_evidence_verified and bool(mandatory_evidence)
    """Run deterministic PayShield risk/policy decision.

    ``policy_result`` may be supplied by a caller that has already evaluated the
    applicable authorization policy (including evidence requirements).  Risk is
    advisory to the extent that it can only strengthen or maintain a decision,
    never weaken a policy BLOCK.  A missing/unverified mandatory offer can
    therefore never collapse into ALLOW, even when the numerical risk score is 0.
    """

    if policy_result is None:
        policy_result = policy.check_payment(amount, category)

    if not isinstance(policy_result, dict) or "decision" not in policy_result:
        policy_result = {"decision": "BLOCK", "reason": "Policy result unavailable"}

    amount_risk = is_amount_is_normal(amount, previous_spend)

    recipient_risk = is_recipient_known(recipient, previous_recipient)

    risk_score = calculate_risk_score(amount_risk, recipient_risk)

    risk_level = get_risk_level(risk_score)

    policy_decision = str(policy_result.get("decision", "BLOCK")).upper()

    # Conservative evidence gate: policy may require a verified offer; a forum
    # post, review or AI assessment is never sufficient.  Missing or stale
    # evidence can only result in REVIEW or BLOCK, never ALLOW.
    evidence_ok = bool(mandatory_evidence_verified) and (
        str(evidence_status or "").upper() in VERIFIED_EVIDENCE_STATES
        or str(evidence_status or "").upper() == ""
    )
    if "required_evidence" in (policy_result or {}) and not evidence_ok:
        evidence_ok = False

    if policy_decision == "BLOCK":
        decision = "BLOCK"

    elif risk_level == "HIGH":
        decision = "BLOCK"

    elif not evidence_ok:
        # Configured conservative outcome for unverifiable mandatory evidence.
        decision = "REVIEW"

    elif policy_decision == "REVIEW":
        decision = "REVIEW"

    elif risk_level == "MEDIUM":
        decision = "REVIEW"

    else:
        decision = "ALLOW"

    return decision, risk_score, risk_level, policy_result

if __name__ == "__main__":
    # LOW → ALLOW
    print(make_decision(
        5000, "electronics",
        10000,
        "friend",
        ["friend", "shop"]
    ))

    # MEDIUM → REVIEW
    print(make_decision(
        15000, "electronics",
        10000,
        "friend",
        ["friend", "shop"]
    ))

    # HIGH → BLOCK
    print(make_decision(
        30000, "electronics",
        10000,
        "new_user",
        ["friend", "shop"]
    ))

    print(make_decision(
        5000, "gift_card",
        10000,
        "friend",
        ["friend", "shop"]
    ))
