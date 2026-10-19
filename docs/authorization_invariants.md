# PayShield AI authorization invariants

1. **Risk is not authorization.** A low numerical risk score, including `0`, never
   authorizes a payment by itself. The risk score can only make a decision more
   restrictive.

2. **ALLOW requires every mandatory gate.** A final `ALLOW` requires agent
   authorization, financial policy authorization, required product/evidence
   checks, immutable purchase-context checks, PayPal order verification, and the
   current deterministic PayShield decision to pass.

3. **Evidence requirements come from policy.** The applicable policy determines
   which evidence is mandatory. A forum post, review, or AI-generated answer can
   never satisfy a verified merchant-offer requirement. Only structured,
   source-attributed offer evidence may do so.

4. **Missing or unsafe evidence is conservative.** Missing, stale, conflicting,
   or unverifiable mandatory evidence produces `REVIEW` or `BLOCK`, never
   `ALLOW`.

5. **AI is advisory.** Ollama or browser-supplied assessments can explain or
   annotate a result but cannot override deterministic risk, policy, evidence,
   or payment guards.

6. **Decisions are attempt-scoped.** Each risk/policy/decision result, evidence
   references, and purchase-context version are persisted for the exact payment
   attempt.

7. **Authorization is re-evaluated before capture.** If material transaction data
   or evidence changes before capture, PayShield re-runs authorization. A capture
   is rejected if authorization is no longer valid.

8. **Tampered context fails closed.** Product, variant, merchant, quantity, unit
   price, total, currency, shipping, evidence, user intent, PayPal order ID, or
   payment attempt changes to protected fields invalidate authorization.

9. **Blocked outcomes are terminal per attempt.** A retry or repeated callback
   cannot convert a settled `BLOCK` or `REVIEW` into `ALLOW`.

10. **Receipts correspond to attempts.** Receipt decisions and payment states are
   keyed to the exact PayPal order and payment attempt that produced them.
"""