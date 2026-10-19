import test from 'node:test'
import assert from 'node:assert/strict'
import {
  summarizeAuthorizationAttempts,
  summarizeAuditDecisionRecords,
  METRIC_DEFINITIONS,
} from './metrics.js'

const RECORD_A = {
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
const RECORD_A_LATER = {
  transaction_id: 'txn_a',
  merchant: 'Acme',
  final_decision: 'REVIEW',
  risk_level: 'MEDIUM',
  risk_score: 60,
  timestamp: '2026-01-01T10:05:00Z',
}
const RECORD_B = {
  transaction_id: 'txn_b',
  merchant: 'Beta',
  final_decision: 'BLOCK',
  risk_level: 'HIGH',
  timestamp: '2026-01-02T00:00:00Z',
}
const AUTH_EVENT = { event_type: 'AUTH_LOGIN_SUCCESS', user_id: 'u1' }

test('METRIC_DEFINITIONS documents each metric clearly', () => {
  assert.equal(METRIC_DEFINITIONS.authorizationAttempts.label, 'Authorization attempts')
  assert.equal(
    METRIC_DEFINITIONS.authorizationAttempts.description,
    'Unique transaction references in the selected period.',
  )
  assert.equal(METRIC_DEFINITIONS.auditDecisionRecords.label, 'Audit decision records')
  assert.equal(
    METRIC_DEFINITIONS.auditDecisionRecords.description,
    'Every raw audit event line, including duplicates per attempt.',
  )
})

test('summarizeAuthorizationAttempts counts unique attempts, not audit events', () => {
  const summary = summarizeAuthorizationAttempts([
    RECORD_A,
    AUTH_EVENT,
    RECORD_A_LATER,
    RECORD_B,
  ])
  // Two unique transaction references (txn_a, txn_b), not four audit lines.
  // txn_a's latest event is RECORD_A_LATER (REVIEW), not RECORD_A (ALLOW).
  assert.equal(summary.total, 2)
  assert.equal(summary.REVIEW, 1)
  assert.equal(summary.BLOCK, 1)
  assert.equal(summary.nonAllow, 2)
})

test('summarizeAuthorizationAttempts includes attempts array', () => {
  const result = summarizeAuthorizationAttempts([RECORD_A, RECORD_B])
  assert.equal(result.attempts.length, 2)
  assert.equal(result.attempts[0].transactionId, 'txn_b') // newest first
  assert.equal(result.attempts[1].transactionId, 'txn_a')
})

test('summarizeAuthorizationAttempts empty attempts array', () => {
  const result = summarizeAuthorizationAttempts([])
  assert.equal(result.attempts.length, 0)
})

test('summarizeAuthorizationAttempts is empty-safe', () => {
  const summary = summarizeAuthorizationAttempts(null)
  assert.equal(summary.total, 0)
  assert.equal(summary.ALLOW, 0)
  assert.equal(summary.REVIEW, 0)
  assert.equal(summary.BLOCK, 0)
})

test('summarizeAuditDecisionRecords counts every raw audit line', () => {
  const summary = summarizeAuditDecisionRecords([
    RECORD_A,
    AUTH_EVENT,
    RECORD_A_LATER,
    RECORD_B,
  ])
  // All four lines counted, including the auth event (no decision → UNKNOWN)
  assert.equal(summary.total, 4)
  assert.equal(summary.ALLOW, 1)
  assert.equal(summary.REVIEW, 1)
  assert.equal(summary.BLOCK, 1)
  assert.equal(summary.UNKNOWN, 1) // AUTH_EVENT has no decision
  assert.equal(summary.nonAllow, 3)
})

test('summarizeAuditDecisionRecords is empty-safe', () => {
  const summary = summarizeAuditDecisionRecords(null)
  assert.equal(summary.total, 0)
  assert.equal(summary.ALLOW, 0)
  assert.equal(summary.REVIEW, 0)
  assert.equal(summary.BLOCK, 0)
  assert.equal(summary.UNKNOWN, 0)
})

test('authorization attempts and audit records produce different counts', () => {
  const records = [RECORD_A, RECORD_A_LATER, RECORD_B]
  const attemptSummary = summarizeAuthorizationAttempts(records)
  const recordSummary = summarizeAuditDecisionRecords(records)
  // 2 unique attempts vs 3 raw records
  assert.equal(attemptSummary.total, 2)
  assert.equal(recordSummary.total, 3)
  assert.notEqual(attemptSummary.total, recordSummary.total)
})
