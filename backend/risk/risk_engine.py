from backend.payment.models import Transaction

def is_amount_is_normal(amount,previous_spend):
    if amount<=previous_spend:
        return 0
    elif amount<= previous_spend * 2:
        return 30
    else:
        return 60

def is_recipient_known(recipient,previous_recipients):
    if recipient in previous_recipients:
        return 0
    else:
        return 1

def calculate_risk_score(amount_risk,recipent_risk):
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
        return "BOCK"
    elif risk_level == "MEDIUM":
            return "REVIEW"
    else:
        return "ALLOW" 

def get_amount_risk(amount,previous_spend):
    if amount <= previous_spend:
        return 0
    elif amount <= previous_spend*2:
        return 20
    elif amount<= previous_spend*5:
        return 40
    else:
        return 60

def get_risk_bar(score):
    filled = score // 5
    empty = 20 - filled

    return "[" + "█" * filled + "░" * empty + "]"


def evaluate_transaction(transaction:Transaction,previous_spend:float=0):
    amount_risk = get_amount_risk(transaction.amount,previous_spend)
    recipient_risk = is_recipient_known(transaction.merchant_name,[])

    score = calculate_risk_score(amount_risk,recipient_risk)

    risk_level = get_risk_level(score)
    decision = get_decision(risk_level)
    return{
        "transaction_id":transaction.transaction_id,
        "risk_score": score,
        "risk_level":risk_level,
        "decision":decision,
    }

