import { useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { getAuditHistory } from '../services/api'

function RiskIntelligence() {
  const [records, setRecords] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    getAuditHistory(500)
      .then((response) => setRecords(response.records || []))
      .catch((requestError) => setError(requestError.message))
  }, [])

  const distribution = useMemo(() => records.reduce((result, record) => {
    const decision = record.final_decision || record.decision || 'UNKNOWN'
    result[decision] = (result[decision] || 0) + 1
    return result
  }, {}), [records])

  return (
    <>
      <PageHeader
        eyebrow="AI explainability"
        title="Risk intelligence"
        description="Inspect the actual risk and policy outcomes produced by PayShield."
      />
      {error && <p className="api-error" role="alert">{error}</p>}
      <section className="metrics-grid" aria-label="Risk decisions">
        {['ALLOW', 'REVIEW', 'BLOCK'].map((decision) => (
          <article className="metric-card panel" key={decision}>
            <span className="overline">{decision}</span>
            <strong>{distribution[decision] || 0}</strong>
          </article>
        ))}
      </section>
      <section className="page-panel panel">
        <div className="table-heading"><div><h2>Decision explanations</h2><span>{records.length} records</span></div></div>
        {records.length === 0 ? <p className="muted-text">No risk evaluations yet.</p> : (
          <div className="audit-list">
            {records.slice(0, 25).map((record, index) => (
              <article className="audit-row" key={`${record.transaction_id || 'record'}-${record.timestamp || index}`}>
                <div><strong>{record.transaction_id || 'Unknown transaction'}</strong><span>{record.merchant || 'Unknown merchant'}</span></div>
                <div><strong>Risk {record.risk_score ?? 'n/a'}</strong><span>{record.decision_reason || 'No explanation recorded'}</span></div>
                <b>{record.final_decision || record.decision || 'UNKNOWN'}</b>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

export default RiskIntelligence
