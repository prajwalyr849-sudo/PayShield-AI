"""PayShield AI Explanation and Reason Engine.

Generates human-readable, structured explanations for transaction risk scores,
policy evaluations, and final authorization decisions.
"""

from typing import Any, Dict, List


def explain_decision(
    *,
    decision: str,
    risk_score: int,
    risk_level: str,
    policy_result: Dict[str, Any],
    amount: float = 0.0,
    merchant_name: str = "",
    currency: str = "USD",
) -> Dict[str, Any]:
    """Generate structured explanations for a payment governance decision."""
    signals: List[Dict[str, str]] = []
    policy_reason = policy_result.get("reason", "")
    policy_decision = policy_result.get("decision", "ALLOW")

    # Policy factors
    if policy_decision == "BLOCK":
        signals.append({
            "category": "POLICY",
            "severity": "CRITICAL",
            "signal": f"Financial Constitution violation: {policy_reason}",
        })
    elif policy_decision == "REVIEW":
        signals.append({
            "category": "POLICY",
            "severity": "MEDIUM",
            "signal": f"Constitution threshold exceeded: {policy_reason}",
        })
    else:
        signals.append({
            "category": "POLICY",
            "severity": "LOW",
            "signal": "Transaction adheres to configured policy limits.",
        })

    # Risk signals
    if risk_score >= 80:
        signals.append({
            "category": "RISK",
            "severity": "CRITICAL",
            "signal": f"High anomaly score ({risk_score}/100) indicates significant variance from baseline spending.",
        })
    elif risk_score >= 50:
        signals.append({
            "category": "RISK",
            "severity": "MEDIUM",
            "signal": f"Moderate risk score ({risk_score}/100) detected due to elevated spend or unfamiliar merchant.",
        })
    else:
        signals.append({
            "category": "RISK",
            "severity": "LOW",
            "signal": f"Low risk score ({risk_score}/100) consistent with normal purchasing patterns.",
        })

    # Summary synthesis
    if decision == "BLOCK":
        summary = (
            f"Payment of {currency} {amount:.2f} to {merchant_name or 'merchant'} was BLOCKED. "
            f"{policy_reason if policy_decision == 'BLOCK' else 'Risk score exceeded safety limit.'}"
        )
        recommended_action = "REJECT_TRANSACTION"
    elif decision == "REVIEW":
        summary = (
            f"Payment of {currency} {amount:.2f} requires HUMAN REVIEW. "
            f"{policy_reason or 'Risk signals require supervisor approval before capture.'}"
        )
        recommended_action = "AWAIT_SUPERVISOR_APPROVAL"
    else:
        summary = (
            f"Payment of {currency} {amount:.2f} to {merchant_name or 'merchant'} was APPROVED. "
            "All risk evaluations and financial constitution checks passed."
        )
        recommended_action = "PROCEED_TO_CAPTURE"

    return {
        "decision": decision,
        "summary": summary,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "signals": signals,
        "policy_decision": policy_decision,
        "recommended_action": recommended_action,
    }

