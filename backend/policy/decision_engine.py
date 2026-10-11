from backend.risk.risk_engine import is_amount_is_normal,is_recipient_known,calculate_risk_score,get_risk_level
from backend.policy.engine import FinancialConstitution

policy = FinancialConstitution(max_auto_payment=10000,approval_limit=50000,blocked_categories=["gift_card"])

def make_decision(amount,category,previous_spend,recipient,previous_recipient):

    policy_result = policy.check_payment(amount,category)

    amount_risk = is_amount_is_normal(amount,previous_spend)

    recipient_risk = is_recipient_known(recipient,previous_recipient)

    risk_score = calculate_risk_score(amount_risk,recipient_risk)

    risk_level = get_risk_level(risk_score)

    if policy_result["decision"] == "BLOCK":
        decision = "BLOCK"

    elif risk_level == "HIGH":
        decision = "BLOCK"

    elif policy_result["decision"]:
        decision = "REVIEW"

    elif risk_level == "MEDIUM":
        decision = "REVIEW"

    else:
        decision = "ALLOW"

    
       
    return decision,risk_score,risk_level,policy_result

# LOW → ALLOW
print(make_decision(
    5000,"electronics",
    10000,
    "friend",
    ["friend", "shop"]
))

# MEDIUM → REVIEW
print(make_decision(
    15000,"electronics",
    10000,
    "friend",
    ["friend", "shop"]
))

# HIGH → BLOCK
print(make_decision(
    30000,"electronics",
    10000,
    "new_user",
    ["friend", "shop"]
))

print(make_decision(
    5000,"gift_card",
    10000,
    "friend",
    ["friend", "shop"]

))

