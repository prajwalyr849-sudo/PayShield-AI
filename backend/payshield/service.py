from backend.payment.models import Transaction
from backend.policy.decision_engine import make_decision
from backend.payshield.order_integrity import approve_order
from backend.audit.audit_logger import AuditLogger

def evaluate_transaction(
        transaction: Transaction,
        previous_spend: float =0,
        previous_recipients:list = None
        

):
    if transaction.amount <= 0:
         raise ValueError("Transaction amount must be positive")
    if not transaction.transaction_id:
        raise ValueError("Transaction ID is required")
    if not transaction.user_id:
        raise ValueError("User ID is required")
    if not transaction.merchant_name:
        raise ValueError("Merchant name is required")
    
    if previous_recipients is None:
        previous_recipients = []

    decision,risk_score,risk_level,policy_result= make_decision(
        transaction.amount,
        transaction.merchant_category,
        previous_spend,
        transaction.merchant_name,
        previous_recipients
    )

    approved_order = approve_order(
        transaction_id = transaction.transaction_id,
        amount=str(transaction.amount),
        currency = transaction.currency,
        decision=decision,
    )    

    audit_logger = AuditLogger()

    audit_logger.log_decision({
        "transaction_id": transaction.transaction_id,
        "user_id": transaction.user_id,
        "merchant": transaction.merchant_name,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "policy_decision": policy_result["decision"],
        "final_decision": decision,
        "decision_reason": policy_result.get("reason", ""),
    })
    

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
        "decision_reason": policy_result.get("reason", ""),
        "requires_approval": decision == "REVIEW",
        "payment_authorized": decision == "ALLOW",
        "decision": decision,
        "risk_assessment": {
        "score": risk_score,
        "level": risk_level,
        },
        "policy_result": policy_result,
        "order_fingerprint":approved_order.fingerprint,
    }