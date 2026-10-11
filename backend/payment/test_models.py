from backend.payment.models import Transaction, TransactionItem


def test_transaction_creation():
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

    assert transaction.amount == 25000
    assert transaction.currency == "INR"
    assert transaction.agent_name == "ShoppingAgent"