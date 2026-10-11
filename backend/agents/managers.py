"""Agent identity and payment authorization helpers."""

from dataclasses import dataclass
from typing import Iterable, FrozenSet


@dataclass(frozen=True)
class AuthorizationResult:
	"""The result of an agent authorization check."""

	authorized: bool
	reason: str


@dataclass
class Agent:
	"""An agent and the payment permissions assigned to it."""

	agent_id: str
	name: str
	allowed_categories: FrozenSet[str]
	spending_limit: float
	active: bool = True

	def __init__(
		self,
		agent_id: str,
		name: str,
		allowed_categories: Iterable[str],
		spending_limit: float,
		active: bool = True,
	) -> None:
		self.agent_id = agent_id
		self.name = name
		self.allowed_categories = frozenset(allowed_categories)
		self.spending_limit = spending_limit
		self.active = active

	def is_active(self) -> bool:
		"""Return whether the agent can authorize payments."""
		return self.active

	def is_category_allowed(self, category: str) -> bool:
		"""Return whether the agent may pay for the given category."""
		return category in self.allowed_categories

	def is_within_spending_limit(self, amount: float) -> bool:
		"""Return whether an amount is within the agent's limit."""
		return amount >= 0 and amount <= self.spending_limit

	def authorize(self, category: str, amount: float) -> AuthorizationResult:
		"""Check the agent's identity permissions for one payment."""
		if not self.is_active():
			return AuthorizationResult(False, "Agent is inactive")
		if not self.is_category_allowed(category):
			return AuthorizationResult(False, "Category is not allowed")
		if not self.is_within_spending_limit(amount):
			return AuthorizationResult(False, "Payment exceeds spending limit")
		return AuthorizationResult(True, "Payment authorized")

	def can_make_payment(self, amount: float, category: str) -> AuthorizationResult:
		"""Check whether the agent can make a payment."""
		return self.authorize(category, amount)
