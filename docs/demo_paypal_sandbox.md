# PayShield three-scenario PayPal Sandbox demo

## Setup

1. Run backend with `uvicorn backend.main:app --reload`.
2. Run frontend with `npm run dev`.
3. Configure Sandbox credentials only. Never use live PayPal credentials.

## Scenario A - legitimate purchase

1. Search a verified product in Product Search.
2. Run Guard Buy for a verified USD offer.
3. Expected: `ALLOW`, amount and currency match the server-derived evidence.
4. Buyer approval and server-side PayPal order retrieval succeed.
5. Expected capture result: `success=true`, `decision=ALLOW`, capture status `COMPLETED`.

## Scenario B - suspicious purchase

1. Use an unverified or conflicting evidence result.
2. Expected: `REVIEW`, `checkout_available=false`.
3. No PayPal order is created and no capture occurs.
4. UI explains the risk signal and missing evidence.

## Scenario C - tampered checkout

1. Create an approved purchase context / registered checkout order.
2. In a controlled test, change amount, currency, product, or context before capture.
3. Backend detects mismatch during PayPal order verification or context comparison.
4. Expected: capture rejected, reason contains `verification failed` or `does not match`.
5. Receipt and transaction history retain the original attempt, decision, and payment state.
"""