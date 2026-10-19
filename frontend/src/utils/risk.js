// Derivation helpers for the Risk Intelligence console.
//
// Everything here is computed from the real audit records returned by the
// backend. Nothing is fabricated: missing fields stay empty and are rendered as
// "unavailable" by the UI.

export function decisionOf(record) {
  if (!record || typeof record !== 'object') return 'UNKNOWN'
  return String(record.final_decision || record.decision || 'UNKNOWN').toUpperCase()
}

export function riskLevelOf(record) {
  if (!record || typeof record !== 'object') return 'UNKNOWN'
  return String(record.risk_level || 'UNKNOWN').toUpperCase()
}

function numericScore(value) {
  const score = Number(value)
  return Number.isFinite(score) ? score : null
}

export function summarizeRisk(records) {
  const summary = {
    total: 0,
    decisions: { ALLOW: 0, REVIEW: 0, BLOCK: 0, UNKNOWN: 0 },
    riskLevels: { LOW: 0, MEDIUM: 0, HIGH: 0, UNKNOWN: 0 },
    nonAllow: 0,
  }
  if (!Array.isArray(records)) return summary

  for (const record of records) {
    if (!record || typeof record !== 'object') continue
    summary.total += 1
    const decision = decisionOf(record)
    summary.decisions[decision] = (summary.decisions[decision] || 0) + 1
    const level = riskLevelOf(record)
    summary.riskLevels[level] = (summary.riskLevels[level] || 0) + 1
    if (decision !== 'ALLOW') summary.nonAllow += 1
  }
  return summary
}

export function toRiskRow(record, index = 0) {
  const safe = record && typeof record === 'object' ? record : {}
  return {
    key: safe.record_hash || safe.transaction_id || `row-${index}`,
    transactionId: safe.transaction_id || '',
    merchant: safe.merchant || '',
    amount: safe.amount,
    currency: safe.currency || 'USD',
    decision: decisionOf(safe),
    policyDecision: safe.policy_decision || '',
    riskScore: numericScore(safe.risk_score),
    riskLevel: safe.risk_level || '',
    reason: safe.decision_reason || '',
    timestamp: safe.timestamp || '',
    evidenceStatus: safe.evidence_status || '',
    orderReference: safe.order_id || safe.external_order_id || '',
    paymentStatus: safe.payment_status || '',
    raw: safe,
  }
}

export function filterRows(rows, query) {
  const term = String(query || '').trim().toLowerCase()
  if (!term) return rows
  return rows.filter((row) => (
    row.transactionId.toLowerCase().includes(term)
    || row.merchant.toLowerCase().includes(term)
    || row.decision.toLowerCase().includes(term)
    || row.riskLevel.toLowerCase().includes(term)
  ))
}
