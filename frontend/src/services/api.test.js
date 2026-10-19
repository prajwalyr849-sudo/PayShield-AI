import test from 'node:test'
import assert from 'node:assert/strict'
import {
  parseResponse,
  rateAssistantProduct,
  guardBuy,
  approveGuardBuyReview,
  guardBuyCheckout,
  createPayPalOrder,
  capturePayPalOrder,
  getReceipt,
  getReceipts,
  getReceiptByOrderId,
  getSecurityControls,
  getAssistantRecommendations,
  sendAssistantChat,
} from './api.js'

function stubFetch(payload = { ok: true }, capture = {}) {
  return async (url, options = {}) => {
    capture.url = url
    capture.options = options
    capture.body = options.body ? JSON.parse(options.body) : null
    return {
      ok: payload.ok ?? true,
      status: payload.status ?? 200,
      text: async () => JSON.stringify(payload.body ?? {}),
    }
  }
}

test('parseResponse parses valid JSON response on 200 OK', async () => {
  const mockResponse = {
    ok: true,
    status: 200,
    text: async () => JSON.stringify({ status: 'online', name: 'PayShield AI' }),
  }

  const result = await parseResponse(mockResponse, 'Health check')
  assert.deepEqual(result, { status: 'online', name: 'PayShield AI' })
})

test('parseResponse throws on malformed JSON on 200 OK', async () => {
  const mockResponse = {
    ok: true,
    status: 200,
    text: async () => '<html>Not JSON</html>',
  }

  await assert.rejects(
    () => parseResponse(mockResponse, 'Payment test'),
    /returned malformed JSON/,
  )
})

test('parseResponse extracts detail string on 400 Bad Request', async () => {
  const mockResponse = {
    ok: false,
    status: 400,
    text: async () => JSON.stringify({ detail: 'Invalid payment amount' }),
  }

  await assert.rejects(
    () => parseResponse(mockResponse, 'Order check'),
    /Invalid payment amount/,
  )
})

test('parseResponse extracts error array on validation error', async () => {
  const mockResponse = {
    ok: false,
    status: 422,
    text: async () => JSON.stringify({
      detail: [{ msg: 'Field required: amount' }, { msg: 'Currency must be USD' }],
    }),
  }

  await assert.rejects(
    () => parseResponse(mockResponse, 'Validation check'),
    /Field required: amount, Currency must be USD/,
  )
})

test('parseResponse exposes structured error code and message', async () => {
  const mockResponse = {
    ok: false,
    status: 409,
    text: async () =>
      JSON.stringify({
        detail: {
          code: 'unverifiable_amount',
          message: 'This decision has no verified amount.',
        },
      }),
  }

  const error = await parseResponse(mockResponse, 'Sandbox checkout').then(
    () => null,
    (err) => err,
  )
  assert.ok(error instanceof Error)
  assert.equal(error.message, 'This decision has no verified amount.')
  assert.equal(error.code, 'unverifiable_amount')
  assert.equal(error.status, 409)
  assert.deepEqual(error.detail, {
    code: 'unverifiable_amount',
    message: 'This decision has no verified amount.',
  })
})


test('parseResponse handles assistant recommendation payload', async () => {
  const mockPayload = {
    query: 'Noise-cancelling headphones under $250',
    intent: { category: 'electronics', target_budget: 250 },
    recommendations: [
      { rank: 1, badge: 'Top Value Pick', product: { id: 'p1', title: 'Sony WH-1000XM5' } },
      { rank: 2, badge: 'Best Performance', product: { id: 'p2', title: 'Bose QC Ultra' } },
      { rank: 3, badge: 'Budget Champion', product: { id: 'p3', title: 'Anker Q30' } },
    ],
  }
  const mockResponse = {
    ok: true,
    status: 200,
    text: async () => JSON.stringify(mockPayload),
  }
  const result = await parseResponse(mockResponse, 'Shopping recommendations')
  assert.equal(result.recommendations.length, 3)
  assert.equal(result.recommendations[0].badge, 'Top Value Pick')
})

test('rateAssistantProduct posts the product reference with credentials', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { ai_score: 82 } }, capture)
  try {
    const result = await rateAssistantProduct({
      product_reference: 'prod_abc',
      query: 'headphones',
    })
    assert.equal(result.ai_score, 82)
    assert.ok(capture.url.endsWith('/assistant/rate'))
    assert.equal(capture.options.method, 'POST')
    assert.equal(capture.options.credentials, 'include')
    assert.deepEqual(capture.body, { product_reference: 'prod_abc', query: 'headphones' })
  } finally {
    globalThis.fetch = original
  }
})

test('guardBuy sends only the reference and quantity', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { decision: 'ALLOW' } }, capture)
  try {
    const result = await guardBuy({ product_reference: 'prod_abc', quantity: 2 })
    assert.equal(result.decision, 'ALLOW')
    assert.ok(capture.url.endsWith('/assistant/guard-buy'))
    assert.equal(capture.body.product_reference, 'prod_abc')
    assert.equal(capture.body.quantity, 2)
    assert.equal(capture.body.idempotency_key, undefined)
  } finally {
    globalThis.fetch = original
  }
})

test('approveGuardBuyReview posts the decision reference and approval', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { decision: 'ALLOW' } }, capture)
  try {
    await approveGuardBuyReview({ decision_reference: 'gb_1', approved: true })
    assert.ok(capture.url.endsWith('/assistant/guard-buy/review'))
    assert.deepEqual(capture.body, { decision_reference: 'gb_1', approved: true })
  } finally {
    globalThis.fetch = original
  }
})

test('guardBuyCheckout always supplies an idempotency key', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { decision: 'ALLOW', approval_url: 'https://sandbox' } }, capture)
  try {
    const result = await guardBuyCheckout({ decision_reference: 'gb_1' })
    assert.equal(result.approval_url, 'https://sandbox')
    assert.ok(capture.url.endsWith('/assistant/guard-buy/checkout'))
    assert.equal(capture.body.decision_reference, 'gb_1')
    assert.ok(capture.body.idempotency_key)
  } finally {
    globalThis.fetch = original
  }
})

test('createPayPalOrder posts the order with credentials', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { order_id: 'ORDER-1', approval_url: 'https://sandbox' } }, capture)
  try {
    const result = await createPayPalOrder({ amount: '25.00', currency: 'USD', category: 'services', merchant_name: 'Sandbox merchant' })
    assert.equal(result.order_id, 'ORDER-1')
    assert.ok(capture.url.endsWith('/paypal/orders'))
    assert.equal(capture.options.method, 'POST')
    assert.equal(capture.options.credentials, 'include')
    assert.equal(capture.body.amount, 25)
  } finally {
    globalThis.fetch = original
  }
})

test('capturePayPalOrder captures with credentials and returns the receipt id', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { success: true, decision: 'ALLOW', receipt_id: 'RCPT-ABC' } }, capture)
  try {
    const result = await capturePayPalOrder('ORDER 1/2')
    assert.equal(result.receipt_id, 'RCPT-ABC')
    assert.ok(capture.url.endsWith('/paypal/orders/ORDER%201%2F2/capture'))
    assert.equal(capture.options.method, 'POST')
    assert.equal(capture.options.credentials, 'include')
  } finally {
    globalThis.fetch = original
  }
})

test('getReceipt fetches a single receipt with credentials', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { receipt_id: 'RCPT-ABC', status: 'COMPLETED' } }, capture)
  try {
    const result = await getReceipt('RCPT-ABC')
    assert.equal(result.receipt_id, 'RCPT-ABC')
    assert.ok(capture.url.endsWith('/receipts/RCPT-ABC'))
    assert.equal(capture.options.credentials, 'include')
  } finally {
    globalThis.fetch = original
  }
})

test('getReceipt rejects a blank receipt id without a request', async () => {
  await assert.rejects(() => getReceipt('   '), /Receipt ID is required/)
})

test('getReceipts requests the receipt list with a limit and credentials', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { receipts: [], count: 0 } }, capture)
  try {
    const result = await getReceipts(25)
    assert.deepEqual(result.receipts, [])
    assert.ok(capture.url.endsWith('/receipts?limit=25'))
    assert.equal(capture.options.credentials, 'include')
  } finally {
    globalThis.fetch = original
  }
})

test('getReceiptByOrderId looks up the receipt for an order with credentials', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { receipt_id: 'RCPT-ABC', order_id: 'ORDER 1' } }, capture)
  try {
    const result = await getReceiptByOrderId('ORDER 1')
    assert.equal(result.order_id, 'ORDER 1')
    assert.ok(capture.url.endsWith('/receipts/order/ORDER%201'))
    assert.equal(capture.options.credentials, 'include')
  } finally {
    globalThis.fetch = original
  }
})

test('getReceiptByOrderId rejects a blank order id without a request', async () => {
  await assert.rejects(() => getReceiptByOrderId(''), /Order ID is required/)
})

test('Product Search and Assistant Chat call independent endpoints', async () => {
  const original = globalThis.fetch

  const searchCapture = {}
  globalThis.fetch = stubFetch({ body: { search_results: [] } }, searchCapture)
  await getAssistantRecommendations({ query: 'headphones', currency: 'USD', country: 'US' })
  assert.ok(searchCapture.url.endsWith('/assistant/recommendations'))
  assert.equal(searchCapture.options.method, 'POST')

  const chatCapture = {}
  globalThis.fetch = stubFetch({ body: { reply: 'hello', search_results: [] } }, chatCapture)
  await sendAssistantChat({ query: 'hello', messages: [] })
  assert.ok(chatCapture.url.endsWith('/assistant/chat'))
  assert.equal(chatCapture.options.method, 'POST')

  assert.notEqual(searchCapture.url, chatCapture.url)
  globalThis.fetch = original
})

test('getAssistantRecommendations tolerates an empty result list', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({ body: { search_results: [] } }, capture)
  try {
    const result = await getAssistantRecommendations({ query: 'nothing', currency: 'USD', country: 'US' })
    assert.deepEqual(result.search_results, [])
  } finally {
    globalThis.fetch = original
  }
})

test('getSecurityControls calls settings preferences endpoint with credentials', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch(
    { body: { preferences: {}, security_controls: [], editable_fields: [] } },
    capture,
  )
  try {
    const result = await getSecurityControls()
    assert.ok(capture.url.endsWith('/settings/preferences'))
    assert.equal(capture.options.credentials, 'include')
    assert.deepEqual(result.security_controls, [])
  } finally {
    globalThis.fetch = original
  }
})

test('getSecurityControls propagates errors', async () => {
  const original = globalThis.fetch
  globalThis.fetch = async () => ({
    ok: false,
    status: 500,
    text: async () => JSON.stringify({ detail: 'Internal server error' }),
  })
  try {
    await assert.rejects(() => getSecurityControls(), /Internal server error/)
  } finally {
    globalThis.fetch = original
  }
})

test('guardBuy with candidate evidence returns REVIEW decision', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({
    body: {
      decision: 'REVIEW',
      evidence_status: 'CANDIDATE',
      price_verified: false,
      price_unverified_reason:
        'Channel3 structured offer has not been independently verified against the retailer page.',
      amount: null,
      checkout_amount_verified: false,
      checkout_available: false,
      reason: 'The source price could not be verified, so PayShield cannot authorize an amount it cannot verify.',
    },
  }, capture)
  try {
    const result = await guardBuy({ product_reference: 'prod_abc', quantity: 1 })
    assert.equal(result.decision, 'REVIEW')
    assert.equal(result.evidence_status, 'CANDIDATE')
    assert.equal(result.price_verified, false)
    assert.equal(result.checkout_available, false)
    assert.ok(capture.url.endsWith('/assistant/guard-buy'))
    assert.equal(capture.body.product_reference, 'prod_abc')
    assert.equal(capture.body.quantity, 1)
  } finally {
    globalThis.fetch = original
  }
})

test('guardBuy with verified evidence returns ALLOW decision', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({
    body: {
      decision: 'ALLOW',
      evidence_status: 'VERIFIED',
      price_verified: true,
      price: 348.00,
      price_currency: 'USD',
      amount: 348.00,
      checkout_amount_verified: true,
      checkout_available: true,
      reason: 'PayShield authorized this purchase. Sandbox checkout is enabled.',
    },
  }, capture)
  try {
    const result = await guardBuy({ product_reference: 'prod_abc', quantity: 1 })
    assert.equal(result.decision, 'ALLOW')
    assert.equal(result.evidence_status, 'VERIFIED')
    assert.equal(result.price_verified, true)
    assert.equal(result.amount, 348.00)
    assert.equal(result.checkout_available, true)
    assert.ok(capture.url.endsWith('/assistant/guard-buy'))
  } finally {
    globalThis.fetch = original
  }
})

test('guardBuy with conflicting evidence returns REVIEW decision', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({
    body: {
      decision: 'REVIEW',
      evidence_status: 'CONFLICT',
      price_verified: false,
      amount: null,
      checkout_amount_verified: false,
      checkout_available: false,
      reason: 'Conflicting merchant offers prevent an automatic amount, so PayShield requires review before any payment.',
    },
  }, capture)
  try {
    const result = await guardBuy({ product_reference: 'prod_abc', quantity: 1 })
    assert.equal(result.decision, 'REVIEW')
    assert.equal(result.evidence_status, 'CONFLICT')
    assert.equal(result.checkout_available, false)
    assert.ok(capture.url.endsWith('/assistant/guard-buy'))
  } finally {
    globalThis.fetch = original
  }
})

test('guardBuy propagates provider errors', async () => {
  const original = globalThis.fetch
  globalThis.fetch = async () => ({
    ok: false,
    status: 503,
    text: async () => JSON.stringify({
      detail: { code: 'unknown_product', message: 'Unknown or expired product reference.' },
    }),
  })
  try {
    await assert.rejects(
      () => guardBuy({ product_reference: 'prod_missing', quantity: 1 }),
      /Unknown or expired product reference/
    )
  } finally {
    globalThis.fetch = original
  }
})

test('guardBuyCheckout with BLOCK decision does not create PayPal order', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({
    body: {
      decision: 'BLOCK',
      payment_status: 'NOT_CAPTURED',
      reason: 'PayShield did not authorize checkout for this decision.',
    },
  }, capture)
  try {
    const result = await guardBuyCheckout({ decision_reference: 'gb_blocked' })
    assert.equal(result.decision, 'BLOCK')
    assert.equal(result.payment_status, 'NOT_CAPTURED')
    assert.ok(capture.url.endsWith('/assistant/guard-buy/checkout'))
    assert.equal(capture.body.decision_reference, 'gb_blocked')
  } finally {
    globalThis.fetch = original
  }
})

test('guardBuyCheckout with ALLOW decision creates PayPal order', async () => {
  const capture = {}
  const original = globalThis.fetch
  globalThis.fetch = stubFetch({
    body: {
      decision: 'ALLOW',
      payment_status: 'AWAITING_BUYER_APPROVAL',
      order_id: 'ORDER-123',
      approval_url: 'https://sandbox.paypal.com/checkoutnow?token=ORDER-123',
      total_amount: 348.00,
      checkout_amount_verified: true,
      reason: 'PayShield authorized Sandbox checkout. Awaiting buyer approval.',
    },
  }, capture)
  try {
    const result = await guardBuyCheckout({ decision_reference: 'gb_allowed' })
    assert.equal(result.decision, 'ALLOW')
    assert.equal(result.order_id, 'ORDER-123')
    assert.equal(result.approval_url, 'https://sandbox.paypal.com/checkoutnow?token=ORDER-123')
    assert.equal(result.checkout_amount_verified, true)
    assert.ok(capture.url.endsWith('/assistant/guard-buy/checkout'))
  } finally {
    globalThis.fetch = original
  }
})


