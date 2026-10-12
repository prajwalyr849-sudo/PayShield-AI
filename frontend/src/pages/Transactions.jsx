import { useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { getAuditHistory } from '../services/api'

function Transactions() {
  const [records, setRecords] = useState([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    getAuditHistory(500)
      .then((response) => setRecords(response.records || []))
      .catch((requestError) => setError(requestError.message))
  }, [])

  const filtered = useMemo(() => records.filter((record) => (
    `${record.transaction_id || ''} ${record.merchant || ''}`.toLowerCase().includes(query.toLowerCase())
  )), [records, query])

  return (
    <>
      <PageHeader eyebrow="Activity monitor" title="Transactions" description="Review actual PayShield decisions recorded by the backend." />
      {error && <p className="api-error" role="alert">{error}</p>}
      <section className="page-panel panel">
        <label className="search-field">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search transaction or merchant" aria-label="Search transactions" />
        </label>
        <div className="table-heading"><div><h2>Audit transactions</h2><span>{filtered.length} records</span></div></div>
        {filtered.length === 0 ? <p className="muted-text">No transactions match this search.</p> : (
          <div className="audit-list">
            {filtered.map((record, index) => (
              <article className="audit-row" key={`${record.transaction_id || 'record'}-${record.timestamp || index}`}>
                <div><strong>{record.transaction_id || 'Unknown transaction'}</strong><span>{record.merchant || 'Unknown merchant'}</span></div>
                <div><strong>{record.currency || 'USD'} {Number(record.amount || 0).toFixed(2)}</strong><span>{record.decision_reason || 'No reason recorded'}</span></div>
                <b>{record.final_decision || record.decision || 'UNKNOWN'}</b>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )
}

export default Transactions
