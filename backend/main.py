from fastapi import FastAPI
from pydantic import BaseModel

from backend.agents.managers import Agent
from backend.payment.service import PaymentAuthorizationService
from backend.policy.engine import FinancialConstitution


app = FastAPI(
    title="PayShield AI",
    description="Trust and governance layer for agentic commerce",
    version="0.1.0"
)


constitution = FinancialConstitution(
    max_auto_payment=10000,
    approval_limit=60000,
    blocked_categories=["gift_cards"]
)

agents = {
    "agent-001": Agent(
        agent_id="agent-001",
        name="Payment Agent",
        allowed_categories=["food", "groceries", "office", "services", "software", "travel"],
        spending_limit=10000,
    )
}

payment_service = PaymentAuthorizationService(agents, constitution)


class PaymentRequest(BaseModel):
    agent_id: str
    amount: float
    category: str


@app.get("/")
def root():
    return {
        "name": "PayShield AI",
        "status": "online"
    }


@app.post("/check-payment")
def check_payment(payment: PaymentRequest):
    return payment_service.check_payment(
        payment.agent_id,
        payment.amount,
        payment.category,
    )