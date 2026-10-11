from backend.policy.engine import FinancialConstitution

from backend.risk.risk_engine import is_amount_is_normal,is_recipient_known,calculate_risk_score,get_risk_level,get_decision,get_amount_risk,get_risk_bar


constitution = FinancialConstitution(
    max_auto_payment=10000,
    approval_limit=60000,
    blocked_categories=["gift_cards"]
)


print("₹5,000 laptop:")
print(constitution.check_payment(5000, "electronics"))

print("\n₹25,000 laptop:")
print(constitution.check_payment(25000, "electronics"))

print("\n₹75,000 laptop:")
print(constitution.check_payment(75000, "electronics"))

print("\n₹5,000 gift card:")
print(constitution.check_payment(5000, "gift_cards"))

print("Amount test:",is_amount_is_normal(500,1000))

print("Known recipient:",is_recipient_known("Amazon",["Amazon","Flipkart","Swiggy"]))
print("New recipient:",is_recipient_known("Unknown",["Amazon","Flipkart","Swiggy"]))

amount_risk = get_amount_risk(5000,1000)
recipient_risk = is_recipient_known("Unknown",["Amazon","Flipkart"])

risk_score = calculate_risk_score(amount_risk,recipient_risk)

print("Amount risk:",amount_risk)
print("Recipient risk:",recipient_risk)
print("Risk score:",risk_score)

risk_level = get_risk_level(risk_score)

print("Risk level:",risk_level)
print("Decision:",get_decision(risk_level))
risk_bar = get_risk_bar(risk_score)
print(risk_bar)

