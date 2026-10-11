from backend.payment.models import Transaction, TransactionItem
from backend.payshield.service import evaluate_transaction


def test_payshield_transaction_flow():

    transaction = Transaction(
        transaction_id="TXN-001",
        user_id="USER-001",
        merchant_name="Amazon",
        merchant_category="electronics",
        amount=5000,
        currency="INR",
        payment_method="paypal",
        items=[
            TransactionItem(
                name="Keyboard",
                quantity=1,
                price=5000
            )
        ],
        agent_name="ShoppingAgent",
        agent_confidence=0.94
    )

    result = evaluate_transaction(
        transaction,
        previous_spend=10000,
        previous_recipients=["Amazon"]
    )

    assert result["transaction_id"] == "TXN-001"
    assert result["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
    assert result["final_decision"] in ["ALLOW", "REVIEW", "BLOCK"]
    assert "policy_decision" in result