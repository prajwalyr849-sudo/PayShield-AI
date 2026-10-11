from backend.payment.models import Transaction, TransactionItem
from backend.risk.risk_engine import evaluate_transaction


def test_transaction_risk_evaluation():

    transaction = Transaction(
        transaction_id="TXN-001",
        user_id="USER-001",
        merchant_name="Amazon",
        merchant_category="electronics",
        amount=25000,
        currency="INR",
        payment_method="paypal",
        items=[
            TransactionItem(
                name="Laptop",
                quantity=1,
                price=25000
            )
        ],
        agent_name="ShoppingAgent",
        agent_confidence=0.94
    )

    result = evaluate_transaction(
        transaction,
        previous_spend=5000
    )

    assert result["transaction_id"] == "TXN-001"
    assert "risk_score" in result
    assert "risk_level" in result
    assert "decision" in result