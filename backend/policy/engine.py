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