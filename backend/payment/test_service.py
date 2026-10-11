from backend.agents.managers import Agent
from backend.payment.service import PaymentAuthorizationService
from backend.policy.engine import FinancialConstitution


def create_service(
    *,
    allowed_categories=None,
    spending_limit=60000,
    active=True,
    blocked_categories=None,
):
    agent = Agent(
        agent_id="agent-001",
        name="Payment Agent",
        allowed_categories=allowed_categories or ["groceries"],
        spending_limit=spending_limit,
        active=active,
    )
    constitution = FinancialConstitution(
        max_auto_payment=10000,
        approval_limit=60000,
        blocked_categories=blocked_categories or [],
    )
    return PaymentAuthorizationService({"agent-001": agent}, constitution)


def test_valid_payment_is_allowed():
    service = create_service()

    result = service.check_payment("agent-001", 2500, "groceries")

    assert result == {
        "decision": "ALLOW",
        "reason": "Payment is within the automatic limit",
    }


def test_unauthorized_category_is_blocked():
    service = create_service(allowed_categories=["groceries"])

    result = service.check_payment("agent-001", 2500, "travel")

    assert result == {
        "decision": "BLOCK",
        "reason": "Category is not allowed",
    }


def test_agent_spending_limit_is_enforced():
    service = create_service(spending_limit=5000)

    result = service.check_payment("agent-001", 7500, "groceries")

    assert result == {
        "decision": "BLOCK",
        "reason": "Payment exceeds spending limit",
    }


def test_financial_constitution_blocked_category_is_blocked():
    service = create_service(
        allowed_categories=["gift_cards"],
        blocked_categories=["gift_cards"],
    )

    result = service.check_payment("agent-001", 2500, "gift_cards")

    assert result == {
        "decision": "BLOCK",
        "reason": "This category is blocked",
    }


def test_payment_requiring_approval_is_reviewed():
    service = create_service(spending_limit=60000)

    result = service.check_payment("agent-001", 25000, "groceries")

    assert result == {
        "decision": "REVIEW",
        "reason": "Human approval is required",
    }


def test_inactive_agent_is_blocked():
    service = create_service(active=False)

    result = service.check_payment("agent-001", 2500, "groceries")

    assert result == {
        "decision": "BLOCK",
        "reason": "Agent is inactive",
    }
