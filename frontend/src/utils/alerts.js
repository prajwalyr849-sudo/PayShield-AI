// Single source of truth for the Alerts surface.
//
// The sidebar badge and the Alerts page must agree, so both derive alerts from
// the same audit records with the same rules. Nothing here is hard-coded or
// fabricated: an alert is one payment attempt whose authoritative (newest)
// decision was not ALLOW. Attempts are grouped by transaction reference so a
// repeated callback event for the same attempt cannot inflate the count.

import { groupAttempts } from './transactions.js'

export const ALERT_SEVERITIES = ['High', 'Medium']

export function recordDecision(record) {
  if (!record || typeof record !== 'object') return 'UNKNOWN'
  return String(record.final_decision || record.decision || 'UNKNOWN').toUpperCase()
}

// A record counts as an alert only when it is bound to a transaction and the
// final authorization decision was not ALLOW (REVIEW or BLOCK, or anything
// explicitly non-ALLOW). ALLOW decisions are never alerts.
export function isAlertRecord(record) {
  if (!record || typeof record !== 'object') return false
  if (!record.transaction_id) return false
  return recordDecision(record) !== 'ALLOW'
}

export function severityForScore(score) {
  const value = Number(score)
  return Number.isFinite(value) && value >= 70 ? 'High' : 'Medium'
}

export function severityForRecord(record) {
  return severityForScore(record?.risk_score)
}

export function deriveAlerts(records) {
  if (!Array.isArray(records)) return []
  return groupAttempts(records)
    .filter((attempt) => attempt.decision !== 'ALLOW')
    .map((attempt) => ({
      id: attempt.transactionId,
      decision: attempt.decision,
      severity: severityForScore(attempt.riskScore),
      title: `${attempt.decision} decision`,
      description: attempt.reason || 'Explanation unavailable',
      merchant: attempt.merchant || 'Merchant unavailable',
      time: attempt.timestamp || '',
      riskScore: attempt.riskScore,
      riskLevel: attempt.riskLevel,
      status: 'Open',
    }))
}

export function countAlerts(alerts) {
  const counts = { total: 0, High: 0, Medium: 0 }
  if (!Array.isArray(alerts)) return counts
  counts.total = alerts.length
  for (const alert of alerts) {
    if (counts[alert.severity] === undefined) counts[alert.severity] = 0
    counts[alert.severity] += 1
  }
  return counts
}
