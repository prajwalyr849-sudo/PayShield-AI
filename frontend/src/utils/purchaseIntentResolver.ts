/** Canonical purchase-intent resolution for Assistant Chat.
 *
 * Purchase utterances must resolve against trusted offer records already in
 * the user's context (staged/dispatched search results) — never against
 * free-form LLM text or a fresh provider search. The canonical offer
 * identity is the backend product reference (`ProductOffer.id`, e.g.
 * `c3_…`), which the guard-buy endpoint re-validates server-side.
 *
 * This module is pure: no React, no network, no storage.
 */

import { ProductOffer } from '../types';

export interface ResolvableOfferContext {
  /** Offers explicitly staged/dispatched in this conversation, oldest first. */
  stagedOffers: ProductOffer[];
  /** Product-type scope tokens (from the user's last search query, e.g.
   *  "iphone 17" -> ["iphone", "17"]) applied to cheapest-selection. */
  scopeTokens: string[];
  /** Full result set of the latest search, when available. */
  latestResults: ProductOffer[];
}

export type PurchaseCommand = { kind: 'this' } | { kind: 'cheapest' } | null;

/** Recognize imperative purchase commands that reference context offers.
 *  Questions ("should I buy this?") and product-naming sentences are NOT
 *  commands and return null so they still reach the normal chat path. */
export function parsePurchaseCommand(raw: string): PurchaseCommand {
  const text = (raw || '').trim().toLowerCase().replace(/[.!]+$/, '');
  const m = text.match(
    /^(?:please\s+)?(?:go\s+ahead\s+(?:and\s+)?)?(?:i\s+(?:want|would\s+like|'d\s+like)\s+to\s+)?(?:buy|purchase|order|get)\s+(?:the\s+)?(cheapest|lowest-priced|this|that|it)(?:\s+one)?(?:\s+(?:offer|product|item|deal))?(?:\s+(?:now|please))?$/
  );
  if (!m) return null;
  if (m[1] === 'cheapest' || m[1] === 'lowest-priced') return { kind: 'cheapest' };
  return { kind: 'this' };
}

export type SelectionResolution =
  | { status: 'resolved'; offer: ProductOffer; reason: string }
  | { status: 'ambiguous'; offers: ProductOffer[]; message: string }
  | { status: 'none'; message: string };

/** Resolve "buy this/that/it (one)": explicit selection wins, then a single
 *  staged offer, then ask. Never guesses between staged offers. */
export function resolveSelectedOffer(
  context: ResolvableOfferContext,
  selectedOfferId: string | null
): SelectionResolution {
  if (selectedOfferId) {
    const selected = context.stagedOffers.find((o) => o.id === selectedOfferId);
    if (selected) {
      return {
        status: 'resolved',
        offer: selected,
        reason: 'your explicitly selected search entry',
      };
    }
  }
  if (context.stagedOffers.length === 1) {
    return {
      status: 'resolved',
      offer: context.stagedOffers[0],
      reason: 'the only product staged in this conversation',
    };
  }
  if (context.stagedOffers.length > 1) {
    const list = context.stagedOffers
      .map((o) => `• ${o.title} — ${o.merchantName} — ${describePrice(o)}`)
      .join('\n');
    return {
      status: 'ambiguous',
      offers: context.stagedOffers,
      message:
        'Several offers are staged, so I will not guess which one you mean. ' +
        'Click one under "Product Searches" to select it (or stage just one), then repeat. Staged offers:\n' +
        list,
    };
  }
  return {
    status: 'none',
    message:
      'No offer is staged in this conversation yet. Stage one in Product Search and dispatch it to me first; then say "buy this".',
  };
}

export type CheapestResolution =
  | { status: 'resolved'; offer: ProductOffer; reason: string }
  | { status: 'refused'; message: string };

function describePrice(o: ProductOffer): string {
  const currency = (o.currency || 'USD').toUpperCase();
  const amount = typeof o.price === 'number' && Number.isFinite(o.price) ? o.price.toFixed(2) : 'n/a';
  return `${currency} ${amount}`;
}

/** Product-type tokens that identify a device (as opposed to an accessory). */
const _DEVICE_TOKENS = [
  'iphone', 'samsung', 'galaxy', 'pixel', 'ipad', 'macbook', 'phone',
  'smartphone', 'laptop', 'notebook',
];

/** Obvious accessory/attachments words. An offer matching a device query but
 *  carrying one of these words is an accessory, not the device itself. */
const _ACCESSORY_WORDS = [
  'case', 'cover', 'charger', 'charging', 'cable', 'screen protector',
  'protector', 'earbud', 'airpod', 'adapter', 'battery', 'strap', 'band',
  'dock', 'stand',
];

function isObviousAccessory(title: string, deviceTokens: string[]): boolean {
  const lower = (title || '').toLowerCase();
  const namesDevice = deviceTokens.some((t) => lower.includes(t));
  if (!namesDevice) return false;
  return _ACCESSORY_WORDS.some((w) => lower.includes(w));
}

/** Eligible, price-comparable offers for cheapest selection, in ascending
 *  price order, plus a refusal when no defensible comparison exists.
 *
 *  Every scope token must appear in the title so an unrelated cheaper product
 *  can never win. When the query names a device, obvious accessories are
 *  excluded so a cheaper accessory can never stand in for the device. Prices
 *  are only compared within a single currency, and unverified prices are still
 *  eligible here — the caller decides how to treat verification.
 */
function cheapestEligible(context: ResolvableOfferContext): {
  eligible: ProductOffer[];
  tokens: string[];
  refusal: CheapestNResolution | null;
} {
  const scope = context.latestResults.length > 0 ? context.latestResults : context.stagedOffers;
  if (scope.length === 0) {
    return {
      eligible: [],
      tokens: [],
      refusal: {
        status: 'refused',
        message:
          'I have no search results in this conversation to choose from. Run a Product Search and dispatch it to me first; then ask for the cheapest again.',
      },
    };
  }

  const tokens = context.scopeTokens.filter((t) => t.length >= 2);
  const deviceTokens = tokens.filter((t) => _DEVICE_TOKENS.includes(t));
  let typeMatched = tokens.length
    ? scope.filter((o) => {
        const title = (o.title || '').toLowerCase();
        return tokens.every((t) => title.includes(t));
      })
    : scope;

  if (deviceTokens.length > 0) {
    typeMatched = typeMatched.filter((o) => !isObviousAccessory(o.title, deviceTokens));
  }
  if (typeMatched.length === 0) {
    return {
      eligible: [],
      tokens,
      refusal: {
        status: 'refused',
        message:
          `None of the offers in your latest search match "${tokens.join(' ')}", ` +
          'so I cannot pick a cheapest one. I will not substitute a different product — run a narrower search or stage a specific offer.',
      },
    };
  }

  const currencies = new Set(typeMatched.map((o) => (o.currency || 'USD').toUpperCase()));
  if (currencies.size > 1) {
    return {
      eligible: [],
      tokens,
      refusal: {
        status: 'refused',
        message:
          `The matching offers are priced in multiple currencies (${Array.from(currencies).join(', ')}), so a direct price comparison would be misleading.`,
      },
    };
  }

  const priced = typeMatched.filter(
    (o) => typeof o.price === 'number' && Number.isFinite(o.price) && o.price > 0
  );
  if (priced.length === 0) {
    return {
      eligible: [],
      tokens,
      refusal: {
        status: 'refused',
        message:
          'No matching offer has a usable price. I will not guess — stage a specific offer with a verified price instead.',
      },
    };
  }

  return { eligible: [...priced].sort((a, b) => a.price - b.price), tokens, refusal: null };
}

/** Resolve "buy the cheapest one" against the latest search's trusted
 *  results, constrained to the searched product type. Refuses rather than
 *  substituting when no eligible offer can be established. */
export function resolveCheapestOffer(context: ResolvableOfferContext): CheapestResolution {
  const { eligible, tokens, refusal } = cheapestEligible(context);
  if (refusal) return refusal as CheapestResolution;
  const cheapest = eligible[0];
  const verified = cheapest.verification === 'VERIFIED_MERCHANT';
  return {
    status: 'resolved',
    offer: cheapest,
    reason:
      `the cheapest ${tokens.length ? `"${tokens.join(' ')}" ` : ''}offer in your latest search` +
      (verified ? ' (price verified from the retailer page)' : ' (price NOT yet verified — PayShield will require verified evidence before authorizing payment)'),
  };
}

/* ------------------------------------------------------------------ */
/* Shopping-copilot intent parsing (deterministic, context-driven)     */
/* ------------------------------------------------------------------ */

export type CopilotIntent =
  | { kind: 'purchase'; command: 'this' | 'cheapest' }
  | { kind: 'search'; query: string }
  | { kind: 'refine'; tokens: string[] }
  | { kind: 'cheapest_n'; count: number; compareOnly: boolean }
  | { kind: 'select_index'; index: number }
  | { kind: 'stage' }
  | { kind: 'explain' }
  | { kind: 'explain_index'; index: number }
  | { kind: 'lowest_verified' }
  | { kind: 'total' }
  | { kind: 'payment_status' }
  | { kind: 'show_receipt' }
  | null;

const ORDINALS: Record<string, number> = {
  first: 1, second: 2, third: 3, fourth: 4, fifth: 5,
  '1st': 1, '2nd': 2, '3rd': 3, '4th': 4, '5th': 5,
};

/** Classify a chat utterance into a deterministic copilot intent. Security-
 *  sensitive actions (purchase/selection/staging) are resolved only here and
 *  against structured state — the LLM never decides offer identity. */
export function parseCopilotIntent(raw: string): CopilotIntent {
  const text = (raw || '').trim().toLowerCase().replace(/[.!]+$/, '');
  if (!text) return null;

  const purchase = parsePurchaseCommand(text);
  if (purchase) return { kind: 'purchase', command: purchase.kind };

  // "stage this one" / "stage this"
  if (/^(?:please\s+)?stage\s+(?:this|that|it)(?:\s+one)?$/.test(text)) {
    return { kind: 'stage' };
  }

  // "tell me more about the first product" / "tell me more about the second one"
  const explainIdx =
    text.match(
      /^(?:tell me more about|explain|describe|more info on)\s+(?:the\s+)?(\d+)(?:st|nd|rd|th)?\s+(?:one|offer|product|result|item)$/
    ) ||
    text.match(
      /^(?:tell me more about|explain|describe|more info on)\s+(?:the\s+)?(first|second|third|fourth|fifth)\s+(?:one|offer|product|result|item)$/
    );
  if (explainIdx) {
    const idx = /^\d+$/.test(explainIdx[1]) ? parseInt(explainIdx[1], 10) : ORDINALS[explainIdx[1]];
    if (idx >= 1 && idx <= 5) return { kind: 'explain_index', index: idx };
  }

  // "tell me more about this offer" / "explain this one"
  if (
    /^(?:tell me more about|explain|describe|more info on)\s+(?:this|that|the)?\s*(?:one|offer|product|it)?$/.test(text) ||
    /^what\s+(?:is|about)\s+(?:this|that)\s*(?:one|offer|product)?$/.test(text)
  ) {
    return { kind: 'explain' };
  }

  // "what is the total?" / "what's the total?" / "how much is the total?"
  if (
    /^(?:what(?:'s|\s+is)|\s*how\s+much\s+is)\s+(?:the\s+)?(?:total|order\s+total|price)(?:\s+for\s+this)?\??$/.test(text)
  ) {
    return { kind: 'total' };
  }

  // "has my payment completed?" / "is my payment complete?" / "did my payment go through?" / "check payment status"
  if (
    /^(?:has|is|did)\s+(?:my\s+)?payment\s+(?:completed?|gone\s+through|finished|succeeded?)\??$/.test(text) ||
    /^(?:check\s+)?payment\s+status\??$/.test(text)
  ) {
    return { kind: 'payment_status' };
  }

  // "show my receipt." / "show receipt" / "view my receipt"
  if (/^(?:show|view|get|open|display)\s+(?:my\s+)?(?:receipt|latest\s+receipt)\??$/.test(text)) {
    return { kind: 'show_receipt' };
  }

  // "which has the lowest verified price?"
  if (/^(?:which|what)\s+(?:one\s+)?(?:has\s+)?the\s+lowest\s+(?:verified\s+)?price\??$/.test(text)) {
    return { kind: 'lowest_verified' };
  }

  // "select/pick/choose the second one"
  const sel = text.match(/^(?:please\s+)?(?:select|pick|choose)\s+(?:the\s+)?(\d+)(?:st|nd|rd|th)\s+(?:one|offer|product|result)$/) ||
    text.match(/^(?:please\s+)?(?:select|pick|choose)\s+(?:the\s+)?(first|second|third|fourth|fifth)\s+(?:one|offer|product|result)$/);
  if (sel) {
    const idx = /^\d+$/.test(sel[1]) ? parseInt(sel[1], 10) : ORDINALS[sel[1]];
    if (idx >= 1 && idx <= 5) return { kind: 'select_index', index: idx };
    return null;
  }

  // "show me the cheapest three" / "compare the cheapest two" / "find the cheapest one"
  const cheapN = text.match(
    /^(?:(?:show|list|find|get)\s+(?:me\s+)?(?:the\s+)?|(?:compare\s+))?(?:the\s+)?cheapest\s+(one|two|three|four|five|\d+)(?:\s+(?:offers?|products?|results?|options?|models?))?$/
  ) || text.match(
    /^(?:compare|show|list)\s+(?:the\s+)?(?:cheapest\s+)?(two|three|four|five|\d+)\s+(?:cheapest\s+)?(?:offers?|options?|results?|products?|models?)$/
  );
  if (cheapN) {
    const wordMap: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5 };
    const n = /^\d+$/.test(cheapN[1]) ? parseInt(cheapN[1], 10) : wordMap[cheapN[1]];
    if (n >= 1 && n <= 5) {
      const compareOnly = /^(?:compare|what about)\b/.test(text) || /compare/.test(text);
      return { kind: 'cheapest_n', count: n, compareOnly };
    }
    return null;
  }

  // "only 256 gb" / "only 256gb models" / "just unlocked models"
  const refine = text.match(/^(?:only|just|filter to|refine to)\s+(?:show\s+)?(.+?)(?:\s+(?:models?|options?|offers?|results?|versions?|variants?))?$/);
  if (refine && refine[1] && refine[1].length >= 2) {
    const tokens = refine[1].split(/[^a-z0-9.]+/).filter((t) => t.length >= 2);
    if (tokens.length > 0) return { kind: 'refine', tokens };
  }

  // "find iphone 17" / "search for wireless headphones" / "show me iphones"
  const search = text.match(
    /^(?:(?:find|search for|look for|show me|search)\s+)(.+)$/
  );
  if (search && search[1] && search[1].split(/\s+/).length <= 8 && !/\?$/.test(text)) {
    return { kind: 'search', query: search[1].trim() };
  }

  return null;
}

export interface ActiveSearchState {
  query: string;
  /** Product-type constraint tokens accumulated from the query and refines. */
  constraintTokens: string[];
  /** Ordered offers exactly as shown to the user, de-duplicated by canonical id. */
  offers: ProductOffer[];
  /** Explicitly selected canonical offer id (c3_…). */
  selectedOfferId: string | null;
  /** Explicitly staged canonical offer id (a purchase-intent candidate). */
  stagedOfferId: string | null;
  /** The provider's real next-page cursor, or null when no further page exists. */
  pageToken: string | null;
  hasMore: boolean;
}

/** Split a query into product-type constraint tokens (model, storage, etc.). */
function tokenizeQuery(query: string): string[] {
  return (query || '')
    .toLowerCase()
    .split(/[^a-z0-9.]+/)
    .filter((t) => t.length >= 2);
}

/** De-duplicate offers by canonical id while preserving first-seen order. */
function dedupeOffers(offers: ProductOffer[]): ProductOffer[] {
  const seen = new Set<string>();
  const out: ProductOffer[] = [];
  for (const offer of offers) {
    if (!offer || !offer.id) continue;
    if (seen.has(offer.id)) continue;
    seen.add(offer.id);
    out.push(offer);
  }
  return out;
}

/** Start a new active search from a provider response. The new query replaces
 *  the previous context deliberately: constraints, selection and staging are
 *  reset so an old query's constraints or a stale staged offer can never leak
 *  into the new search. */
export function startSearch(
  query: string,
  offers: ProductOffer[],
  pageToken: string | null,
  hasMore: boolean
): ActiveSearchState {
  return {
    query: (query || '').trim(),
    constraintTokens: tokenizeQuery(query),
    offers: dedupeOffers(offers),
    selectedOfferId: null,
    stagedOfferId: null,
    pageToken: pageToken ? String(pageToken) : null,
    hasMore: !!hasMore,
  };
}

/** Apply a refine turn ("only 256 gb") to the active search: filter the
 *  ordered offers in place, preserving order, and accumulate the constraint
 *  tokens. Clears selection/staging if they no longer match the refined set.
 *  Returns the new state. */
export function refineSearch(state: ActiveSearchState, tokens: string[]): ActiveSearchState {
  const usable = tokenizeQuery(tokens.join(' '));
  const filtered =
    usable.length === 0
      ? state.offers
      : state.offers.filter((o) => usable.every((t) => (o.title || '').toLowerCase().includes(t)));
  const next: ActiveSearchState = {
    ...state,
    constraintTokens: [...state.constraintTokens, ...usable],
    offers: dedupeOffers(filtered),
  };
  if (next.selectedOfferId && !next.offers.some((o) => o.id === next.selectedOfferId)) {
    next.selectedOfferId = null;
  }
  if (next.stagedOfferId && !next.offers.some((o) => o.id === next.stagedOfferId)) {
    next.stagedOfferId = null;
  }
  return next;
}

/** Keep `applyRefine` for callers that only need the filtered offer list. */
export function applyRefine(state: ActiveSearchState, tokens: string[]): ProductOffer[] {
  const usable = tokens.filter((t) => t.length >= 2);
  if (usable.length === 0) return state.offers;
  return state.offers.filter((o) => {
    const title = (o.title || '').toLowerCase();
    return usable.every((t) => title.includes(t));
  });
}

/** Resolve the offer with the exact canonical id from the currently displayed,
 *  ordered offers. Never substitutes a different offer. */
export function selectOfferById(
  state: ActiveSearchState,
  offerId: string | null
): SelectionResolution {
  if (!offerId) {
    return { status: 'none', message: 'No offer was specified.' };
  }
  const offer = state.offers.find((o) => o.id === offerId);
  if (!offer) {
    return {
      status: 'none',
      message:
        'That offer is no longer in the displayed results. Run the search again and select it.',
    };
  }
  return { status: 'resolved', offer, reason: 'your selected search entry' };
}

/** Resolve an ordinal ("the second one") against the actual currently
 *  displayed, ordered result ids — never against a stale list or history UUID. */
export function selectIndex(state: ActiveSearchState, index: number): SelectionResolution {
  if (!Number.isFinite(index) || index < 1 || Math.floor(index) !== index) {
    return {
      status: 'none',
      message: 'Please specify a valid position in the current results.',
    };
  }
  const offer = state.offers[index - 1];
  if (!offer) {
    return {
      status: 'none',
      message: `There is no offer at position ${index} in the current results.`,
    };
  }
  return { status: 'resolved', offer, reason: `offer #${index} in the current results` };
}

/** Stage the currently selected offer as a purchase-intent candidate. Staging
 *  is local context only — it never authorizes or initiates a payment. */
export type StageResolution =
  | { status: 'resolved'; offer: ProductOffer; reason: string }
  | { status: 'refused'; message: string };

export function stageSelected(state: ActiveSearchState): StageResolution {
  if (!state.selectedOfferId) {
    return {
      status: 'refused',
      message:
        'No offer is selected in the current results. Select an offer first, then say "stage this one".',
    };
  }
  const offer = state.offers.find((o) => o.id === state.selectedOfferId);
  if (!offer) {
    return {
      status: 'refused',
      message:
        'The selected offer is no longer in the current results. Re-select it, then stage.',
    };
  }
  return { status: 'resolved', offer, reason: 'staged from your selected search entry' };
}

/** Build an evidence-based explanation for the currently selected offer.
 *  Offer identity comes from structured state only; the LLM is not needed to
 *  establish which offer is being explained. */
export function explainOffer(state: ActiveSearchState): {
  status: 'resolved';
  text: string;
} | { status: 'refused'; message: string } {
  const offer = state.selectedOfferId ? state.offers.find((o) => o.id === state.selectedOfferId) : null;
  if (!offer) {
    return {
      status: 'refused',
      message:
        'No offer is selected. Select an offer, then ask me to explain it.',
    };
  }
  const verified = offer.verification === 'VERIFIED_MERCHANT';
  const parts: string[] = [
    `"${offer.title}" from ${offer.merchantName} (${offer.merchantDomain || 'domain not reported'}).`,
    `Price: ${(offer.currency || 'USD').toUpperCase()} ${offer.price.toFixed(2)} — ` +
      (verified
        ? 'price verified from the retailer page.'
        : 'price NOT yet independently verified — treat as a candidate.'),
  ];
  if (offer.condition && offer.condition !== 'unknown') parts.push(`Condition: ${offer.condition}.`);
  if (offer.variant) parts.push(`Variant: ${offer.variant}.`);
  if (offer.availability) parts.push(`Availability: ${offer.availability}.`);
  return { status: 'resolved', text: parts.join(' ') };
}

/** Resolve the cheapest eligible offers (top N), constrained to the searched
 *  product type and limited to a single currency so prices are comparable.
 *  Never substitutes an out-of-scope product. */
export type CheapestNResolution =
  | { status: 'resolved'; offers: ProductOffer[]; reason: string }
  | { status: 'refused'; message: string };

export function resolveCheapestN(
  context: ResolvableOfferContext,
  n: number
): CheapestNResolution {
  if (!Number.isFinite(n) || n < 1 || Math.floor(n) !== n) {
    return {
      status: 'refused',
      message: 'Please specify a valid number of offers to compare.',
    };
  }
  const { eligible, tokens, refusal } = cheapestEligible(context);
  if (refusal) return refusal;
  const picks = eligible.slice(0, Math.min(n, eligible.length));
  const verifiedCount = picks.filter((o) => o.verification === 'VERIFIED_MERCHANT').length;
  const priceWord = picks.length === 1 ? 'offer' : 'offers';
  let verificationNote = '';
  if (verifiedCount === picks.length) verificationNote = ' — all price-verified';
  else if (verifiedCount === 0) verificationNote = ' — none price-verified yet';
  else verificationNote = ` — ${verifiedCount} of ${picks.length} price-verified`;

  return {
    status: 'resolved',
    offers: picks,
    reason:
      `the ${picks.length} cheapest ${priceWord} matching "${tokens.join(' ')}" in your latest search` +
      verificationNote,
  };
}

/** Resolve the lowest-priced offer that carries a verified price. Refuses
 *  rather than falling back to an unverified candidate. */
export function resolveLowestVerified(context: ResolvableOfferContext): CheapestResolution {
  const scope = context.latestResults.length > 0 ? context.latestResults : context.stagedOffers;
  const verified = scope.filter(
    (o) =>
      o.verification === 'VERIFIED_MERCHANT' &&
      typeof o.price === 'number' &&
      Number.isFinite(o.price) &&
      o.price > 0
  );
  if (verified.length === 0) {
    return {
      status: 'refused',
      message:
        'No price-verified offer is available in your latest search. I will not treat an unverified price as verified.',
    };
  }
  const cheapest = verified.reduce((a, b) => (b.price < a.price ? b : a));
  return {
    status: 'resolved',
    offer: cheapest,
    reason: `the lowest price-verified offer matching "${context.scopeTokens.join(' ')}" in your latest search`,
  };
}
