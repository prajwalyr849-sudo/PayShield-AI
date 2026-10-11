
from backend.agents.managers import Agent


def test_payment_with_allowed_category_and_spending_limit_is_authorized():
    agent = Agent(
        agent_id="agent-001",
        name="Payment Agent",
        allowed_categories=["groceries"],
        spending_limit=10000,
    )

    result = agent.can_make_payment(2500, "groceries")

    assert result.authorized is True
    assert result.reason == "Payment authorized"


def test_payment_with_disallowed_category_is_rejected():
    agent = Agent(
        agent_id="agent-001",
        name="Payment Agent",
        allowed_categories=["groceries"],
        spending_limit=10000,
    )

    result = agent.can_make_payment(2500, "gift_cards")

    assert result.authorized is False
    assert result.reason == "Category is not allowed"


def test_payment_above_spending_limit_is_rejected():
    agent = Agent(
        agent_id="agent-001",
        name="Payment Agent",
        allowed_categories=["groceries"],
        spending_limit=10000,
    )

    result = agent.can_make_payment(12500, "groceries")

    assert result.authorized is False
    assert result.reason == "Payment exceeds spending limit"


def test_payment_from_inactive_agent_is_rejected():
    agent = Agent(
        agent_id="agent-001",
        name="Payment Agent",
        allowed_categories=["groceries"],
        spending_limit=10000,
        active=False,
    )

    result = agent.can_make_payment(2500, "groceries")

    assert result.authorized is False
    assert result.reason == "Agent is inactive"
