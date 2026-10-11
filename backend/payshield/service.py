from backend.payment.models import Transaction
from backend.policy.decision_engine import make_decision

def evaluate_transaction(
        transaction: Transaction,
        previous_spend: float =0,
        previous_recipients:list = None
):
    if previous_recipients is None:
        previous_recipients = []

    decision,risk_score,risk_level,policy_result= make_decision(
        transaction.amount,
        transaction.merchant_category,
        previous_spend,
        transaction.merchant_name,
        previous_recipients
        

    )

    return{
        "transaction_id":transaction.transaction_id,
        "user_id":transaction.user_id,
        "merchant":transaction.merchant_name,
        "amount":transaction.amount,
        "currency":transaction.currency,
        "risk_score":risk_score,
        "risk_level":risk_level,
        "policy_decision":policy_result["decision"],
        "final_decision":decision,
    }