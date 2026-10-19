// Shared metric definitions so every surface describes the same dataset.
//
// PayShield records audit events as JSONL lines. One payment attempt can
// produce several events (a decision-time evaluation plus a capture-time
// re-evaluation), so two distinct metrics exist:
//
//   * authorization attempts  — unique transaction references, grouped by
//     transaction_id with the newest event as the current state. One attempt
//     per transaction reference, regardless of how many audit events it
//     emitted.
//   * audit decision records  — every raw audit line, including duplicate
//     events for the same transaction. One record per JSONL entry.
//
// Never substitute one dataset for the other. Always label which metric is
// being shown and the time range / user scope it covers.

import { groupAttempts } from './transactions.js'

export const METRIC_DEFINITIONS = {
  authorizationAttempts: {
    label: 'Authorization attempts',
    description: 'Unique transaction references in the selected period.',
  },
  auditDecisionRecords: {
    label: 'Audit decision records',
    description: 'Every raw audit event line, including duplicates per attempt.',
  },
  uniqueTransactionReferences: {
    label: 'Unique transaction references',
    description: 'Distinct transaction IDs in the selected period.',
  },
  confirmedPayPalCaptures: {
    label: 'Confirmed PayPal captures',
    description: 'Server-verified COMPLETED captures from receipts.',
  },
}

// Group raw audit records into authorization attempts (deduplicated by
// transaction_id), then summarize decisions.
export function summarizeAuthorizationAttempts(records) {
  const attempts = groupAttempts(records || [])
  const summary = {
    total: 0,
    ALLOW: 0,
    REVIEW: 0,
    BLOCK: 0,
    UNKNOWN: 0,
    nonAllow: 0,
  }
  for (const attempt of attempts) {
    summary.total += 1
    summary[attempt.decision] = (summary[attempt.decision] || 0) + 1
    if (attempt.decision !== 'ALLOW') summary.nonAllow += 1
  }
  return { ...summary, attempts }
}

// Count raw audit decision records without deduplication.
export function summarizeAuditDecisionRecords(records) {
  const summary = {
    total: 0,
    ALLOW: 0,
    REVIEW: 0,
    BLOCK: 0,
    UNKNOWN: 0,
    nonAllow: 0,
  }
  for (const record of records || []) {
    if (!record || typeof record !== 'object') continue
    const decision = String(record.final_decision || record.decision || 'UNKNOWN').toUpperCase()
    summary.total += 1
    summary[decision] = (summary[decision] || 0) + 1
    if (decision !== 'ALLOW') summary.nonAllow += 1
  }
  return summary
}
