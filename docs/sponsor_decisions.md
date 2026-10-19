# Sponsor integration decisions

## Channel3

- Status: implemented and live-verified.
- Official API request used: `POST https://api.trychannel3.com/v1/search` with
  `x-api-key` authentication.
- Channel3 is the primary structured product provider when `CHANNEL3_API_KEY` is
  configured.
- Responses are normalized into `ProductSearchResult` with source attribution,
  retrieval time, price verification, offer/availability fields, and deterministic
  evidence state.
- Fallback is explicitly labelled and opt-in only (`PAYSHIELD_LIVE_SEARCH_FALLBACK`).
- Tests cover configured/unconfigured behavior and response normalization.

## APIMatic

- Decision: not added as a runtime dependency.
- Reason: APIMatic's available functionality is SDK/context-plugin and developer
  experience tooling, not a runtime PayPal validation layer. PayShield already uses
  direct server-side PayPal REST calls with explicit verification and idempotency.
- Its value is documentation/developer tooling, which does not justify a new
  dependency in the payment path.

## AG Grid

- Decision: not adopted.
- Reason: the existing transaction table is a lightweight, dependency-free
  component. Adding AG Grid would introduce a large frontend dependency for
  capabilities already provided in a dependency-free form or not required for
  the demonstrated authorization workflow.
"""