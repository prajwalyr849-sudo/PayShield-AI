import test from 'node:test'
import assert from 'node:assert/strict'
import { countAlerts, deriveAlerts, isAlertRecord, severityForRecord } from './alerts.js'

test('isAlertRecord flags non-ALLOW decisions bound to a transaction', () => {
  assert.equal(isAlertRecord({ transaction_id: 'txn_1', final_decision: 'REVIEW' }), true)
  assert.equal(isAlertRecord({ transaction_id: 'txn_2', final_decision: 'BLOCK' }), true)
  assert.equal(isAlertRecord({ transaction_id: 'txn_3', final_decision: 'ALLOW' }), false)
  assert.equal(isAlertRecord({ final_decision: 'BLOCK' }), false)
  assert.equal(isAlertRecord(null), false)
})

test('severityForRecord maps risk score to High at or above 70', () => {
  assert.equal(severityForRecord({ risk_score: 70 }), 'High')
  assert.equal(severityForRecord({ risk_score: 69 }), 'Medium')
  assert.equal(severityForRecord({}), 'Medium')
})

test('deriveAlerts drops ALLOW records and keeps non-ALLOW ones', () => {
  const records = [
    { transaction_id: 'txn_allow', final_decision: 'ALLOW', risk_score: 10 },
    { transaction_id: 'txn_review', final_decision: 'REVIEW', risk_score: 82, decision_reason: 'Manual review' },
    { transaction_id: 'txn_block', final_decision: 'BLOCK', risk_score: 40 },
  ]
  const alerts = deriveAlerts(records)
  assert.equal(alerts.length, 2)
  assert.deepEqual(alerts.map((alert) => alert.id), ['txn_review', 'txn_block'])
  assert.equal(alerts[0].severity, 'High')
  assert.equal(alerts[1].severity, 'Medium')
  assert.equal(alerts[0].description, 'Manual review')
  assert.equal(alerts[1].description, 'Explanation unavailable')
})

test('deriveAlerts never invents alerts from an empty or invalid list', () => {
  assert.deepEqual(deriveAlerts([]), [])
  assert.deepEqual(deriveAlerts(null), [])
})

test('countAlerts agrees with the derived alert list', () => {
  const alerts = deriveAlerts([
    { transaction_id: 'a', final_decision: 'REVIEW', risk_score: 90 },
    { transaction_id: 'b', final_decision: 'BLOCK', risk_score: 20 },
    { transaction_id: 'c', final_decision: 'REVIEW', risk_score: 75 },
  ])
  assert.deepEqual(countAlerts(alerts), { total: 3, High: 2, Medium: 1 })
  assert.deepEqual(countAlerts([]), { total: 0, High: 0, Medium: 0 })
})

test('duplicate callback events for one attempt collapse to a single alert', () => {
  const alerts = deriveAlerts([
    { transaction_id: 'txn_dup', final_decision: 'REVIEW', risk_score: 80, timestamp: '2026-01-01T10:00:00Z', decision_reason: 'first pass' },
    { transaction_id: 'txn_dup', final_decision: 'BLOCK', risk_score: 40, timestamp: '2026-01-01T10:05:00Z', decision_reason: 'authoritative' },
  ])
  assert.equal(alerts.length, 1)
  assert.equal(alerts[0].decision, 'BLOCK')
  assert.equal(alerts[0].severity, 'Medium')
  assert.equal(alerts[0].description, 'authoritative')
})

test('an attempt whose newest decision is ALLOW is not an alert', () => {
  const alerts = deriveAlerts([
    { transaction_id: 'txn_resolved', final_decision: 'REVIEW', risk_score: 80, timestamp: '2026-01-01T10:00:00Z' },
    { transaction_id: 'txn_resolved', final_decision: 'ALLOW', risk_score: 20, timestamp: '2026-01-01T10:05:00Z' },
  ])
  assert.deepEqual(alerts, [])
})
