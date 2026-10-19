import test from 'node:test'
import assert from 'node:assert/strict'
import { decisionOf, filterRows, riskLevelOf, summarizeRisk, toRiskRow } from './risk.js'

test('decisionOf prefers the final decision and normalizes case', () => {
  assert.equal(decisionOf({ final_decision: 'block' }), 'BLOCK')
  assert.equal(decisionOf({ decision: 'review' }), 'REVIEW')
  assert.equal(decisionOf({ final_decision: 'ALLOW', decision: 'BLOCK' }), 'ALLOW')
  assert.equal(decisionOf({}), 'UNKNOWN')
  assert.equal(decisionOf(null), 'UNKNOWN')
})

test('riskLevelOf normalizes the risk level', () => {
  assert.equal(riskLevelOf({ risk_level: 'high' }), 'HIGH')
  assert.equal(riskLevelOf({}), 'UNKNOWN')
})

test('summarizeRisk counts decisions and levels from real records only', () => {
  const summary = summarizeRisk([
    { final_decision: 'ALLOW', risk_level: 'LOW', risk_score: 12 },
    { final_decision: 'REVIEW', risk_level: 'HIGH', risk_score: 88 },
    { final_decision: 'BLOCK', risk_level: 'MEDIUM', risk_score: 55 },
    { final_decision: 'REVIEW', risk_level: 'HIGH', risk_score: 71 },
  ])
  assert.equal(summary.total, 4)
  assert.deepEqual(summary.decisions, { ALLOW: 1, REVIEW: 2, BLOCK: 1, UNKNOWN: 0 })
  assert.deepEqual(summary.riskLevels, { LOW: 1, MEDIUM: 1, HIGH: 2, UNKNOWN: 0 })
  assert.equal(summary.nonAllow, 3)
})

test('summarizeRisk is empty-safe', () => {
  const summary = summarizeRisk(null)
  assert.equal(summary.total, 0)
  assert.equal(summary.nonAllow, 0)
})

test('toRiskRow never fabricates fields that are missing', () => {
  const row = toRiskRow({ transaction_id: 'txn_1', final_decision: 'REVIEW', amount: '12.50' }, 0)
  assert.equal(row.transactionId, 'txn_1')
  assert.equal(row.decision, 'REVIEW')
  assert.equal(row.currency, 'USD')
  assert.equal(row.riskScore, null)
  assert.equal(row.evidenceStatus, '')
  assert.equal(row.merchant, '')
  assert.equal(row.reason, '')
})

test('toRiskRow parses a numeric string risk score', () => {
  const row = toRiskRow({ risk_score: '82' })
  assert.equal(row.riskScore, 82)
})

test('filterRows matches id, merchant, decision and risk level', () => {
  const rows = [
    toRiskRow({ transaction_id: 'txn_alpha', merchant: 'Acme', final_decision: 'BLOCK', risk_level: 'HIGH' }),
    toRiskRow({ transaction_id: 'txn_beta', merchant: 'Beta Store', final_decision: 'ALLOW', risk_level: 'LOW' }),
  ]
  assert.equal(filterRows(rows, 'alpha').length, 1)
  assert.equal(filterRows(rows, 'beta store').length, 1)
  assert.equal(filterRows(rows, 'block').length, 1)
  assert.equal(filterRows(rows, 'low').length, 1)
  assert.equal(filterRows(rows, '').length, 2)
})
