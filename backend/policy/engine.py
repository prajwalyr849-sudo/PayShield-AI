class FinancialConstitution:

    def __init__(self, max_auto_payment, approval_limit, blocked_categories=None):
        self.max_auto_payment = max_auto_payment
        self.approval_limit = approval_limit
        self.blocked_categories = blocked_categories or []

    def check_payment(self, amount, category):

        if amount <= 0:
            return {
                "decision": "BLOCK",
                "reason": "Invalid payment amount"
            }

        if category.lower() in self.blocked_categories:
            return {
                "decision": "BLOCK",
                "reason": "This category is blocked"
            }

        if amount <= self.max_auto_payment:
            return {
                "decision": "ALLOW",
                "reason": "Payment is within the automatic limit"
            }

        if amount <= self.approval_limit:
            return {
                "decision": "REVIEW",
                "reason": "Human approval is required"
            }

        return {
            "decision": "BLOCK",
            "reason": "Payment exceeds the allowed limit"
        }


# Canonical, shared policy configuration used by every purchase and capture
# code path.  All components must import this single instance so that policy
# limits (max_auto_payment, approval_limit, blocked_categories) are identical
# across the evaluation, integration, and capture flows.
DEFAULT_CONSTITUTION = FinancialConstitution(
    max_auto_payment=10000,
    approval_limit=60000,
    blocked_categories=["gift_cards"],
)