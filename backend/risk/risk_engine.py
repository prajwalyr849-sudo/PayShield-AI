"""Deterministic risk scoring for PayShield.

The score is an explainable 0-100 risk indicator, NOT a calibrated fraud
probability. It must never be presented or treated as a probability of fraud.

Authoritative scoring formula (used by the policy/decision engine):

    amount_risk = is_amount_is_normal(amount, previous_spend)
        0   when amount <= previous_spend
        30  when previous_spend < amount <= previous_spend * 2
        60  when amount > previous_spend * 2

    recipient_risk = is_recipient_known(recipient, previous_recipients)
        0   when the recipient is a known previous recipient
        40  otherwise (implicitly added by calculate_risk_score)

    risk_score = amount_risk + recipient_risk        (range 0-100)

    risk_level = get_risk_level(risk_score)
        "HIGH" when score >= 80
        "MEDIUM" when 50 <= score < 80
        "LOW" when score < 50

Risk is advisory to the policy engine: a policy BLOCK, a blocked category, or a
failed integrity invariant can never be overridden by a low risk score. See
backend/policy/decision_engine.py for the authoritative decision ordering.

`get_amount_risk` is a legacy alias kept for backward compatibility; it now
delegates to `is_amount_is_normal` so there is a single authoritative amount
risk scale. The standalone `evaluate_transaction` below calls the engines with
an empty previous-recipient list, so it always scores the merchant as unknown
(recipient_risk = 40); callers that know the recipient history should use
`make_decision` / `calculate_risk_score` directly with the real recipient list.
"""

from backend.payment.models import Transaction


def is_amount_is_normal(amount, previous_spend):
    """Return the amount risk component (0, 30, or 60)."""
    if amount <= previous_spend:
        return 0
    elif amount <= previous_spend * 2:
        return 30
    else:
        return 60


def is_recipient_known(recipient, previous_recipients):
    """Return 0 when the recipient is known, 1 otherwise (unknown = 40 points)."""
    if recipient in previous_recipients:
        return 0
    else:
        return 1


def calculate_risk_score(amount_risk, recipent_risk):
    """Compose the risk score from amount and recipient components."""
    score = 0
    score += amount_risk
    if recipent_risk == 1:
        score += 40
    return score


def get_risk_level(score):
    if score >= 80:
        return "HIGH"
    elif score >= 50:
        return "MEDIUM"
    else:
        return "LOW"


def get_decision(risk_level):
    if risk_level == "HIGH":
        return "BLOCK"
    elif risk_level == "MEDIUM":
        return "REVIEW"
    else:
        return "ALLOW"


def get_amount_risk(amount, previous_spend):
    """Legacy alias for the authoritative amount risk scale."""
    return is_amount_is_normal(amount, previous_spend)


def get_risk_bar(score):
    filled = score // 5
    empty = 20 - filled
    return "[" + "█" * filled + "░" * empty + "]"


def evaluate_transaction(transaction: Transaction, previous_spend: float = 0):
    """Standalone risk evaluation (advisory only).

    Notes:
      * Uses the authoritative amount scale (is_amount_is_normal).
      * The merchant is scored as unknown because no recipient history is
        supplied here; pass real history to calculate_risk_score directly when
        available.
    """
    amount_risk = is_amount_is_normal(transaction.amount, previous_spend)
    recipient_risk = is_recipient_known(transaction.merchant_name, [])

    score = calculate_risk_score(amount_risk, recipient_risk)

    risk_level = get_risk_level(score)
    decision = get_decision(risk_level)
    return {
        "transaction_id": transaction.transaction_id,
        "risk_score": score,
        "risk_level": risk_level,
        "decision": decision,
    }
