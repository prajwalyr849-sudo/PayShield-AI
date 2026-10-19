import test from 'node:test'
import assert from 'node:assert/strict'
import {
  decisionOf,
  filterAttempts,
  groupAttempts,
  isPaymentAttempt,
  summarizeAttempts,
} from './transactions.js'

const ATTEMPT_A = {
  transaction_id: 'txn_a',
  merchant: 'Acme',
  amount: 10,
  currency: 'USD',
  final_decision: 'ALLOW',
  policy_decision: 'ALLOW',
  risk_score: 12,
  risk_level: 'LOW',
  timestamp: '2026-01-01T10:00:00Z',
}
const ATTEMPT_A_LATER = {
  transaction_id: 'txn_a',
  merchant: 'Acme',
  final_decision: 'REVIEW',
  risk_level: 'MEDIUM',
  risk_score: 60,
  timestamp: '2026-01-01T10:05:00Z',
}
const ATTEMPT_B = {
  transaction_id: 'txn_b',
  merchant: 'Beta',
  final_decision: 'BLOCK',
  risk_level: 'HIGH',
  timestamp: '2026-01-02T00:00:00Z',
}
const AUTH_EVENT = { event_type: 'AUTH_LOGIN_SUCCESS', user_id: 'u1' }

test('isPaymentAttempt requires a transaction id and a decision', () => {
  assert.equal(isPaymentAttempt(ATTEMPT_A), true)
  assert.equal(isPaymentAttempt(AUTH_EVENT), false)
  assert.equal(isPaymentAttempt({ transaction_id: 'x' }), false)
  assert.equal(isPaymentAttempt(null), false)
})

test('groupAttempts ignores auth events and collapses duplicate events per attempt', () => {
  const attempts = groupAttempts([ATTEMPT_A, AUTH_EVENT, ATTEMPT_A_LATER, ATTEMPT_B])
  assert.equal(attempts.length, 2)
  const txnA = attempts.find((a) => a.transactionId === 'txn_a')
  assert.equal(txnA.eventCount, 2)
  assert.equal(txnA.decision, 'REVIEW')
  assert.equal(txnA.riskLevel, 'MEDIUM')
  assert.equal(txnA.hasMultipleEvents, true)
})

test('groupAttempts returns newest first when timestamps exist', () => {
  const attempts = groupAttempts([ATTEMPT_A, ATTEMPT_B])
  assert.deepEqual(attempts.map((a) => a.transactionId), ['txn_b', 'txn_a'])
})

test('groupAttempts preserves API order when timestamps are missing', () => {
  const first = { transaction_id: 'first', final_decision: 'ALLOW' }
  const second = { transaction_id: 'second', final_decision: 'BLOCK' }
  const attempts = groupAttempts([first, second])
  assert.deepEqual(attempts.map((a) => a.transactionId), ['first', 'second'])
})

test('groupAttempts is empty-safe', () => {
  assert.deepEqual(groupAttempts(null), [])
  assert.deepEqual(groupAttempts([]), [])
})

test('summarizeAttempts counts unique attempts, not audit events', () => {
  const attempts = groupAttempts([ATTEMPT_A, ATTEMPT_A_LATER, ATTEMPT_B, AUTH_EVENT])
  const summary = summarizeAttempts(attempts)
  assert.equal(summary.total, 2)
  assert.equal(summary.REVIEW, 1)
  assert.equal(summary.BLOCK, 1)
  assert.equal(summary.nonAllow, 2)
  assert.equal(summary.riskLevels.HIGH, 1)
  assert.equal(summary.riskLevels.MEDIUM, 1)
})

test('filterAttempts matches id, merchant, decision and risk level', () => {
  const attempts = groupAttempts([ATTEMPT_A, ATTEMPT_B])
  assert.equal(filterAttempts(attempts, { query: 'beta' }).length, 1)
  assert.equal(filterAttempts(attempts, { decision: 'ALLOW' }).length, 1)
  assert.equal(filterAttempts(attempts, { riskLevel: 'HIGH' }).length, 1)
  assert.equal(filterAttempts(attempts, {}).length, 2)
})

test('decisionOf normalizes and defaults to UNKNOWN', () => {
  assert.equal(decisionOf({ final_decision: 'block' }), 'BLOCK')
  assert.equal(decisionOf({}), 'UNKNOWN')
})
