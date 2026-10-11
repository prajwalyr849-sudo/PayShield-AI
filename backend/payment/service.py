from typing import Mapping

from backend.agents.managers import Agent
from backend.policy.engine import FinancialConstitution


class PaymentAuthorizationService:
    """Coordinates agent authorization and financial policy checks."""

    def __init__(
        self,
        agents: Mapping[str, Agent],
        constitution: FinancialConstitution,
    ) -> None:
        self.agents = agents
        self.constitution = constitution

    def check_payment(
        self,
        agent_id: str,
        amount: float,
        category: str,
    ) -> dict[str, str]:
        agent = self.agents.get(agent_id)
        if agent is None:
            return {
                "decision": "BLOCK",
                "reason": "Agent not found",
            }

        authorization = agent.can_make_payment(amount, category)
        if not authorization.authorized:
            return {
                "decision": "BLOCK",
                "reason": authorization.reason,
            }

        return self.constitution.check_payment(amount, category)
