import { useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { getAuditHistory } from '../services/api'

function Dashboard() {
  const [records, setRecords] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    getAuditHistory(100)
      .then((response) => setRecords(response.records || []))
      .catch((requestError) => setError(requestError.message))
  }, [])

  const summary = useMemo(() => records.reduce((result, record) => {
    const decision = record.final_decision || record.decision || 'UNKNOWN'
    result.total += 1
    result[decision] = (result[decision] || 0) + 1
    if (decision === 'ALLOW' && record.currency === 'USD') {
      result.volume += Number(record.amount) || 0
    }
    return result
  }, { total: 0, volume: 0, ALLOW: 0, REVIEW: 0, BLOCK: 0 }), [records])

  return (
    <>
      <PageHeader
        eyebrow="Payment operations"
        title="PayShield overview"
        description="Live decisions and completed USD payment activity from the backend audit stream."
      />
      {error && <p className="api-error" role="alert">{error}</p>}
      <section className="metrics-grid" aria-label="Transaction overview">
        {[
          ['Evaluated', summary.total],
          ['Allowed', summary.ALLOW],
          ['Review', summary.REVIEW],
          ['Blocked', summary.BLOCK],
          ['Allowed USD volume', `$${summary.volume.toFixed(2)}`],
        ].map(([label, value]) => (
          <article className="metric-card panel" key={label}>
            <span className="overline">{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>
      <section className="page-panel panel">
        <div className="table-heading">
          <div><h2>Recent activity</h2><span>{records.length} audit records</span></div>
        </div>
        {records.length === 0 ? (
          <p className="muted-text">No transactions yet.</p>
        ) : (
          <div className="audit-list">
            {records.slice(0, 10).map((record, index) => (
              <article className="audit-row" key={`${record.transaction_id || 'record'}-${record.timestamp || index}`}>
                <div><strong>{record.transaction_id || 'Unknown transaction'}</strong><span>{record.merchant || 'Unknown merchant'}</span></div>
                <div><strong>{record.currency || 'USD'} {Number(record.amount || 0).toFixed(2)}</strong><span>{record.timestamp || 'Unknown time'}</span></div>
                <b>{record.final_decision || record.decision || 'UNKNOWN'}</b>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

export default Dashboard
