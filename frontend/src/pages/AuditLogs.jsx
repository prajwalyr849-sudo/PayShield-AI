import { useCallback, useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import Icon from '../components/Icon'
import { getAuditHistory } from '../services/api'

const EVENT_LABELS = {
  purchase_integration: 'Purchase integration',
  capture: 'PayPal capture',
  guard_buy_decision: 'Guard Buy decision',
  guard_buy_checkout: 'Guard Buy checkout',
  auth_login: 'Authentication login',
  auth_logout: 'Authentication logout',
}

const DECISION_TONE = {
  ALLOW: 'allow',
  REVIEW: 'review',
  BLOCK: 'block',
}

function eventTypeLabel(source) {
  return EVENT_LABELS[String(source || '').toLowerCase()] || String(source || 'Unknown event')
}

function formatDate(value) {
  if (!value) return 'Not available'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString()
}

function decisionTone(decision) {
  return DECISION_TONE[String(decision || '').toUpperCase()] || 'review'
}

function AuditLogs() {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')

  const runFetch = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getAuditHistory(500)
      setRecords(response.records || [])
    } catch (requestError) {
      setError(requestError.message || 'Unable to load audit log.')
      setRecords([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    runFetch()
  }, [runFetch])

  const load = () => {
    setLoading(true)
    setError('')
    runFetch()
  }

  const filtered = useMemo(() => {
    const term = String(query || '').trim().toLowerCase()
    if (!term) return records
    return records.filter((record) => {
      const fields = [
        record.transaction_id || '',
        record.external_order_id || '',
        record.user_id || '',
        record.merchant || '',
        record.policy_decision || '',
        record.final_decision || record.decision || '',
        record.decision_reason || '',
        record.event_type || record.source || '',
      ]
      return fields.some((f) => String(f).toLowerCase().includes(term))
    })
  }, [records, query])

  return (
    <>
      <PageHeader
        eyebrow="Audit trail"
        title="Audit Logs"
        description="Tamper-evident, server-recorded history of PayShield decisions and security events."
        action={(
          <button type="button" className="outline-button small-button" onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        )}
      />
      {error && <p className="api-error" role="alert">{error}</p>}
      <section className="page-panel panel" aria-label="Audit log entries">
        <div className="table-heading">
          <div>
            <h2>Audit events</h2>
            <span>{filtered.length} of {records.length} records</span>
          </div>
          <label className="ri-search">
            <Icon name="search" size={14} />
            <input
              type="search"
              value={query}
              placeholder="Search transaction, merchant, decision, event…"
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search audit log"
            />
          </label>
        </div>

        {loading && records.length === 0 ? (
          <p className="muted-text">Loading audit records…</p>
        ) : filtered.length === 0 ? (
          <p className="muted-text">
            {records.length === 0
              ? 'No audit events recorded yet.'
              : 'No audit records match your search.'}
          </p>
        ) : (
          <div className="ri-table-wrap">
            <table className="ri-table">
              <thead>
                <tr>
                  <th scope="col">Timestamp</th>
                  <th scope="col">Event / action</th>
                  <th scope="col">Actor / service</th>
                  <th scope="col">Transaction / order</th>
                  <th scope="col">Decision</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((record, index) => (
                  <tr key={`${record.timestamp}-${record.transaction_id || record.external_order_id || ''}-${index}`}>
                    <td>{formatDate(record.timestamp)}</td>
                    <td>{eventTypeLabel(record.event_type || record.source)}</td>
                    <td>{record.user_id || 'system'}</td>
                    <td className="ri-mono">{record.transaction_id || record.external_order_id || '—'}</td>
                    <td>
                      <span className={`ri-badge ${decisionTone(record.final_decision || record.decision)}`}>
                        {record.final_decision || record.decision || '—'}
                      </span>
                    </td>
                    <td>{record.decision_reason || '—'}</td>
                    <td>{record.status || 'recorded'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}

export default AuditLogs
