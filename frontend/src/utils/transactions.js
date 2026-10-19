// Derivation helpers for the Transactions console.
//
// The backend audit history interleaves payment-decision events (which carry a
// transaction_id and a final_decision) with unrelated auth events (event_type
// only). One payment attempt can produce several audit events (for example a
// decision-time evaluation and a capture-time re-evaluation), so the console
// groups events by transaction_id and keeps the newest event as the attempt's
// current state. Nothing is fabricated: fields that the audit record does not
// contain are left empty and rendered as "Unavailable".

export const ATTEMPT_PAGE_SIZE = 25

export function decisionOf(record) {
  if (!record || typeof record !== 'object') return 'UNKNOWN'
  return String(record.final_decision || record.decision || 'UNKNOWN').toUpperCase()
}

export function isPaymentAttempt(record) {
  if (!record || typeof record !== 'object') return false
  if (!record.transaction_id) return false
  const decision = record.final_decision || record.decision
  return Boolean(decision)
}

function timestampValue(value) {
  const parsed = Date.parse(value || '')
  return Number.isFinite(parsed) ? parsed : null
}

function numericScore(value) {
  const score = Number(value)
  return Number.isFinite(score) ? score : null
}

function toAttempt(transactionId, latest, events, index) {
  const latestTs = timestampValue(latest.timestamp)
  return {
    key: transactionId,
    transactionId,
    merchant: latest.merchant || '',
    amount: latest.amount,
    currency: latest.currency || 'USD',
    decision: decisionOf(latest),
    policyDecision: latest.policy_decision || '',
    riskScore: numericScore(latest.risk_score),
    riskLevel: String(latest.risk_level || '').toUpperCase(),
    reason: latest.decision_reason || '',
    timestamp: latest.timestamp || '',
    eventCount: events.length,
    hasMultipleEvents: events.length > 1,
    // Payment/capture state is not part of the audit stream; it lives on the
    // receipt. Expose it as unavailable rather than guessing.
    paymentState: '',
    latestTs,
    index,
    events,
  }
}

export function groupAttempts(records) {
  if (!Array.isArray(records)) return []
  const groups = new Map()
  records.forEach((record, index) => {
    if (!isPaymentAttempt(record)) return
    const id = record.transaction_id
    if (!groups.has(id)) groups.set(id, [])
    groups.get(id).push({ record, index })
  })

  const attempts = []
  for (const [transactionId, entries] of groups) {
    const sorted = [...entries].sort((a, b) => {
      const aTs = timestampValue(a.record.timestamp)
      const bTs = timestampValue(b.record.timestamp)
      if (aTs !== null && bTs !== null) return bTs - aTs
      if (aTs !== null) return -1
      if (bTs !== null) return 1
      return a.index - b.index
    })
    const latestEntry = sorted[0]
    attempts.push(toAttempt(
      transactionId,
      latestEntry.record,
      sorted.map((entry) => entry.record),
      latestEntry.index,
    ))
  }

  attempts.sort((a, b) => {
    if (a.latestTs !== null && b.latestTs !== null) return b.latestTs - a.latestTs
    if (a.latestTs !== null) return -1
    if (b.latestTs !== null) return 1
    return a.index - b.index
  })
  return attempts
}

export function summarizeAttempts(attempts) {
  const summary = {
    total: 0,
    ALLOW: 0,
    REVIEW: 0,
    BLOCK: 0,
    UNKNOWN: 0,
    nonAllow: 0,
    riskLevels: { LOW: 0, MEDIUM: 0, HIGH: 0, UNKNOWN: 0 },
  }
  if (!Array.isArray(attempts)) return summary
  for (const attempt of attempts) {
    summary.total += 1
    summary[attempt.decision] = (summary[attempt.decision] || 0) + 1
    if (attempt.decision !== 'ALLOW') summary.nonAllow += 1
    const level = attempt.riskLevel in summary.riskLevels ? attempt.riskLevel : 'UNKNOWN'
    summary.riskLevels[level] += 1
  }
  return summary
}

export function filterAttempts(attempts, { query = '', decision = 'ALL', riskLevel = 'ALL' } = {}) {
  const term = String(query || '').trim().toLowerCase()
  return (Array.isArray(attempts) ? attempts : []).filter((attempt) => {
    if (decision !== 'ALL' && attempt.decision !== decision) return false
    if (riskLevel !== 'ALL' && attempt.riskLevel !== riskLevel) return false
    if (!term) return true
    return (
      attempt.transactionId.toLowerCase().includes(term)
      || attempt.merchant.toLowerCase().includes(term)
      || attempt.decision.toLowerCase().includes(term)
      || attempt.policyDecision.toLowerCase().includes(term)
    )
  })
}
