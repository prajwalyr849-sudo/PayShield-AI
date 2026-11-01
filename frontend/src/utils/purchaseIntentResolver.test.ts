/** Focused regression tests for purchase-intent resolution.
 *
 * Run: npx tsx src/utils/purchaseIntentResolver.test.ts
 * Plain asserts — no test framework dependency.
 */

import {
  parseCopilotIntent,
  parsePurchaseCommand,
  resolveCheapestN,
  resolveCheapestOffer,
  resolveLowestVerified,
  resolveSelectedOffer,
  selectIndex,
  selectOfferById,
  stageSelected,
  startSearch,
  refineSearch,
  explainOffer,
  ActiveSearchState,
} from './purchaseIntentResolver';
import { ProductOffer } from '../types';

let failures = 0;
function check(name: string, condition: boolean) {
  if (condition) {
    console.log(`  ok - ${name}`);
  } else {
    failures += 1;
    console.error(`  FAIL - ${name}`);
  }
}

function offer(partial: Partial<ProductOffer>): ProductOffer {
  return {
    id: 'c3_unknown',
    title: 'Untitled',
    category: 'general',
    merchantName: 'Unknown merchant',
    merchantDomain: '',
    price: 0,
    currency: 'USD',
    verification: 'CANDIDATE_UNVERIFIED',
    dnssec: false,
    kycTrustmark: false,
    reputationScore: 0,
    withinCeiling: true,
    specifications: [],
    ...partial,
  };
}

const iPhoneBackmarket = offer({
  id: 'c3_backmarket', title: 'iPhone 17', merchantName: 'backmarket.com',
  price: 731, verification: 'VERIFIED_MERCHANT',
});
const iPhoneTotalWireless = offer({
  id: 'c3_totalwireless', title: 'Apple iPhone 17 256GB – White', merchantName: 'totalwireless.com',
  price: 699.99, verification: 'VERIFIED_MERCHANT',
});
const iPhoneBestBuy = offer({
  id: 'c3_bestbuy', title: 'Apple iPhone 17 256GB - White (Best Buy)', merchantName: 'bestbuy.com',
  price: 804.97, verification: 'CANDIDATE_UNVERIFIED',
});
const samsungDollarGeneral = offer({
  id: 'c3_samsung', title: 'Samsung Galaxy A03s', merchantName: 'dollargeneral.com',
  price: 10, verification: 'CANDIDATE_UNVERIFIED',
});

const iphoneSearch = [iPhoneBackmarket, iPhoneTotalWireless, iPhoneBestBuy, samsungDollarGeneral];

console.log('parsePurchaseCommand');
check('"buy this" is a this-command', parsePurchaseCommand('buy this')?.kind === 'this');
check('"buy this one" is a this-command', parsePurchaseCommand('buy this one')?.kind === 'this');
check('"Buy the cheapest one." is a cheapest-command', parsePurchaseCommand('Buy the cheapest one.')?.kind === 'cheapest');
check('"buy the cheapest" is a cheapest-command', parsePurchaseCommand('buy the cheapest')?.kind === 'cheapest');
check('"get that one" is a this-command', parsePurchaseCommand('get that one')?.kind === 'this');
check('"I want to purchase this one." is a this-command', parsePurchaseCommand('I want to purchase this one.')?.kind === 'this');
check('"i would like to buy this" is a this-command', parsePurchaseCommand('i would like to buy this')?.kind === 'this');
check('"should I buy this?" is not a command', parsePurchaseCommand('should I buy this?') === null);
check('"what is the cheapest phone?" is not a command', parsePurchaseCommand('what is the cheapest phone?') === null);
check('"buy the samsung" is not a context command', parsePurchaseCommand('buy the samsung') === null);

console.log('resolveCheapestOffer — iPhone scope with unrelated cheaper Samsung');
const cheapest = resolveCheapestOffer({
  stagedOffers: [iPhoneBackmarket, iPhoneTotalWireless],
  scopeTokens: ['iphone', '17'],
  latestResults: iphoneSearch,
});
check('resolves', cheapest.status === 'resolved');
if (cheapest.status === 'resolved') {
  check('picks the Total Wireless iPhone ($699.99), never the $10 Samsung', cheapest.offer.id === 'c3_totalwireless');
  check('reason mentions verification evidence', cheapest.reason.includes('verified'));
}

console.log('resolveCheapestOffer — safe refusals');
check(
  'no context -> refused with guidance',
  resolveCheapestOffer({ stagedOffers: [], scopeTokens: [], latestResults: [] }).status === 'refused'
);
check(
  'type tokens exclude everything -> refused (no substitution)',
  resolveCheapestOffer({ stagedOffers: [samsungDollarGeneral], scopeTokens: ['iphone'], latestResults: [samsungDollarGeneral] }).status === 'refused'
);
const mixedCurrency = resolveCheapestOffer({
  stagedOffers: [],
  scopeTokens: ['iphone'],
  latestResults: [iPhoneBackmarket, offer({ ...iPhoneBestBuy, currency: 'EUR', id: 'c3_eur' })],
});
check('mixed currencies -> refused', mixedCurrency.status === 'refused');
const noPrices = resolveCheapestOffer({
  stagedOffers: [],
  scopeTokens: ['iphone'],
  latestResults: [offer({ id: 'c3_free', title: 'iPhone 17 Free', price: 0 })],
});
check('zero/missing prices -> refused', noPrices.status === 'refused');

console.log('resolveSelectedOffer — two staged iPhone offers');
const both = { stagedOffers: [iPhoneBackmarket, iPhoneTotalWireless], scopeTokens: ['iphone', '17'], latestResults: iphoneSearch };
const ambiguous = resolveSelectedOffer(both, null);
check('no selection + two staged -> ambiguous (no guess)', ambiguous.status === 'ambiguous');
if (ambiguous.status === 'ambiguous') {
  check('ambiguity lists both offers with merchants and prices', ambiguous.message.includes('backmarket.com') && ambiguous.message.includes('totalwireless.com'));
}
const explicit = resolveSelectedOffer(both, 'c3_totalwireless');
check('explicit selection resolves the exact Total Wireless offer', explicit.status === 'resolved' && explicit.offer.id === 'c3_totalwireless');
const single = resolveSelectedOffer({ stagedOffers: [iPhoneBackmarket], scopeTokens: [], latestResults: [] }, null);
check('single staged offer resolves without selection', single.status === 'resolved' && single.offer.id === 'c3_backmarket');
const none = resolveSelectedOffer({ stagedOffers: [], scopeTokens: [], latestResults: [] }, null);
check('nothing staged -> honest guidance', none.status === 'none');
const staleSelection = resolveSelectedOffer(both, 'c3_gone');
check('stale selection id does not resolve to a substitute', staleSelection.status === 'ambiguous');

console.log('identity preservation');
const selection = resolveSelectedOffer(both, 'c3_totalwireless');
if (selection.status === 'resolved') {
  check(
    'resolved offer keeps canonical identity, price, currency, merchant',
    selection.offer.id === 'c3_totalwireless' &&
      selection.offer.price === 699.99 &&
      selection.offer.currency === 'USD' &&
      selection.offer.merchantName === 'totalwireless.com'
  );
}

console.log('parseCopilotIntent');
const copilotCases: Array<[string, any]> = [
  ['Find iPhone 17.', { kind: 'search', query: 'iphone 17' }],
  ['Only 256 GB.', { kind: 'refine', tokens: ['256', 'gb'] }],
  ['just 256gb models', { kind: 'refine', tokens: ['256gb'] }],
  ['Find the cheapest one.', { kind: 'cheapest_n', count: 1, compareOnly: false }],
  ['Compare the cheapest three.', { kind: 'cheapest_n', count: 3, compareOnly: true }],
  ['show me the cheapest two offers', { kind: 'cheapest_n', count: 2, compareOnly: false }],
  ['Select the second one.', { kind: 'select_index', index: 2 }],
  ['pick the third offer', { kind: 'select_index', index: 3 }],
  ['Stage this one.', { kind: 'stage' }],
  ['Explain this offer.', { kind: 'explain' }],
  ['tell me more about this one', { kind: 'explain' }],
  ['which has the lowest verified price?', { kind: 'lowest_verified' }],
  ['buy this one', { kind: 'purchase', command: 'this' }],
  ['buy the cheapest one', { kind: 'purchase', command: 'cheapest' }],
  ['should I buy this?', null],
  ['hello there', null],
  ['what is the weather?', null],
];
for (const [utterance, expected] of copilotCases) {
  check(`parses "${utterance}"`, JSON.stringify(parseCopilotIntent(utterance)) === JSON.stringify(expected));
}

console.log('startSearch');
const first = startSearch('iphone 17', [iPhoneBackmarket, iPhoneTotalWireless, iPhoneTotalWireless], 'tok_page2', true);
check('startSearch sets query and tokens', first.query === 'iphone 17' && first.constraintTokens.includes('iphone') && first.constraintTokens.includes('17'));
check('startSearch dedupes canonical ids', first.offers.length === 2 && first.offers[0].id === 'c3_backmarket' && first.offers[1].id === 'c3_totalwireless');
check('startSearch carries real next page token', first.pageToken === 'tok_page2' && first.hasMore === true);
check('startSearch resets selection and staging', first.selectedOfferId === null && first.stagedOfferId === null);
const emptyPage = startSearch('headphones', [], null, false);
check('empty page has no token and hasMore false', emptyPage.pageToken === null && emptyPage.hasMore === false && emptyPage.offers.length === 0);
// New search after a refine must not carry over the old constraint or staged offer.
const refined = refineSearch(first, ['256', 'gb']);
const restarted = startSearch('samsung galaxy', [samsungDollarGeneral], null, false);
check('new search resets constraints', restarted.constraintTokens.includes('samsung') && !restarted.constraintTokens.includes('256'));
check('new search clears staged offer', restarted.stagedOfferId === null);

console.log('refineSearch');
check('refine filters to 256gb offers preserving order', refined.offers.length === 1 && refined.offers[0].id === 'c3_totalwireless');
check('refine accumulates constraint tokens', refined.constraintTokens.includes('iphone') && refined.constraintTokens.includes('17') && refined.constraintTokens.includes('256') && refined.constraintTokens.includes('gb'));
check('refine clears selection that no longer matches', refined.selectedOfferId === null);
const noMatch = refineSearch(first, ['nonexistentxx']);
check('refine with no matches yields empty offers', noMatch.offers.length === 0);

console.log('selectOfferById / selectIndex');
check('selectOfferById resolves exact canonical id', selectOfferById(first, 'c3_totalwireless').status === 'resolved');
const resolvedSelection = selectOfferById(first, 'c3_totalwireless');
check('selectOfferById keeps price/merchant identity', resolvedSelection.status === 'resolved');
if (resolvedSelection.status === 'resolved') {
  check('resolved selection keeps identity', resolvedSelection.offer.merchantName === 'totalwireless.com' && resolvedSelection.offer.price === 699.99);
}
check('selectOfferById missing id is none (no substitute)', selectOfferById(first, 'c3_gone').status === 'none');
check('selectOfferById null id is none', selectOfferById(first, null).status === 'none');
const second = selectIndex(first, 2);
check('selectIndex second one resolves by position', second.status === 'resolved');
if (second.status === 'resolved') {
  check('selectIndex returns the second displayed offer', second.offer.id === 'c3_totalwireless');
}
check('selectIndex out of range is none', selectIndex(first, 9).status === 'none');
check('selectIndex zero is none', selectIndex(first, 0).status === 'none');

console.log('resolveCheapestN');
const cheapestThree = resolveCheapestN(
  { stagedOffers: [], scopeTokens: ['iphone', '17'], latestResults: iphoneSearch },
  3
);
check('cheapest three resolves three offers', cheapestThree.status === 'resolved' && cheapestThree.offers.length === 3);
if (cheapestThree.status === 'resolved') {
  check('cheapest three ordered ascending', cheapestThree.offers[0].price <= cheapestThree.offers[1].price && cheapestThree.offers[1].price <= cheapestThree.offers[2].price);
  check('cheapest three excludes $10 Samsung', cheapestThree.offers.every((o) => o.id !== 'c3_samsung'));
  check('cheapest three includes Total Wireless first', cheapestThree.offers[0].id === 'c3_totalwireless');
}
const cheapestOne = resolveCheapestN({ stagedOffers: [], scopeTokens: ['iphone', '17'], latestResults: iphoneSearch }, 1);
check('cheapest one returns single offer', cheapestOne.status === 'resolved' && cheapestOne.offers.length === 1 && cheapestOne.offers[0].id === 'c3_totalwireless');
const cheapestMixed = resolveCheapestN(
  { stagedOffers: [], scopeTokens: ['iphone'], latestResults: [iPhoneBackmarket, offer({ ...iPhoneBestBuy, currency: 'EUR', id: 'c3_eur' })] },
  2
);
check('cheapest N mixed currencies refused', cheapestMixed.status === 'refused');

const iPhoneCase = offer({ ...iPhoneBackmarket, title: 'iPhone 17 Case – Leather', id: 'c3_case', price: 19.99 });
const withAccessory = resolveCheapestN(
  { stagedOffers: [], scopeTokens: ['iphone', '17'], latestResults: [iPhoneBackmarket, iPhoneCase] },
  2
);
check('cheapest N excludes obvious accessory case', withAccessory.status === 'resolved' && withAccessory.offers.length === 1 && withAccessory.offers[0].id === 'c3_backmarket');

console.log('stageSelected');
check('stageSelected requires a selection', stageSelected(first).status === 'refused');
const withSelection = { ...first, selectedOfferId: 'c3_totalwireless' };
const staged = stageSelected(withSelection);
check('stageSelected resolves the selected offer', staged.status === 'resolved');
if (staged.status === 'resolved') {
  check('stageSelected resolves the selected offer identity', staged.offer.id === 'c3_totalwireless');
}
const stale = stageSelected({ ...withSelection, offers: [iPhoneBackmarket] });
check('stageSelected refuses when selected offer is stale', stale.status === 'refused');

console.log('explainOffer');
const explainedUnverified = explainOffer({ ...withSelection, selectedOfferId: 'c3_bestbuy', offers: [iPhoneBestBuy] });
check('explainOffer resolves with evidence text', explainedUnverified.status === 'resolved');
if (explainedUnverified.status === 'resolved') {
  check('explainOffer names merchant and price', explainedUnverified.text.includes('bestbuy.com') && explainedUnverified.text.includes('804.97'));
  check('explainOffer notes unverified price', explainedUnverified.text.includes('NOT yet independently verified'));
}
const explainedVerified = explainOffer({ ...withSelection, selectedOfferId: 'c3_backmarket', offers: [iPhoneBackmarket] });
check('explainOffer notes verified price', explainedVerified.status === 'resolved');
if (explainedVerified.status === 'resolved') {
  check('explainOffer notes price verified', explainedVerified.text.includes('price verified'));
}
check('explainOffer refused without selection', explainOffer(first).status === 'refused');

console.log('resolveLowestVerified');
const lowestVerified = resolveLowestVerified({ stagedOffers: [], scopeTokens: ['iphone', '17'], latestResults: iphoneSearch });
check('lowest verified picks verified cheapest', lowestVerified.status === 'resolved' && lowestVerified.offer.id === 'c3_totalwireless');
const noneVerified = resolveLowestVerified({ stagedOffers: [], scopeTokens: ['iphone'], latestResults: [offer({ ...iPhoneBestBuy, verification: 'CANDIDATE_UNVERIFIED' })] });
check('lowest verified refuses when none verified', noneVerified.status === 'refused');

if (failures > 0) {
  console.error(`\n${failures} test(s) FAILED`);
  process.exit(1);
}
console.log('\nall purchase-intent resolver tests passed');
