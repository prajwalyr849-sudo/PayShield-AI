import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AgGridReact } from 'ag-grid-react'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-quartz.css'
import PageHeader from '../components/PageHeader'
import Icon from '../components/Icon'
import { getAuditHistory } from '../services/api'
import {
  ATTEMPT_PAGE_SIZE,
  filterAttempts,
  groupAttempts,
} from '../utils/transactions'
import {
  summarizeAuthorizationAttempts,
  METRIC_DEFINITIONS,
} from '../utils/metrics'

const DECISION_FILTERS = ['ALL', 'ALLOW', 'REVIEW', 'BLOCK']
const RISK_FILTERS = ['ALL', 'LOW', 'MEDIUM', 'HIGH']

function formatAmount(attempt) {
  if (attempt.amount == null || attempt.amount === '') return 'Unavailable'
  const value = Number(attempt.amount)
  if (!Number.isFinite(value)) return String(attempt.amount)
  return `${value.toFixed(2)} ${attempt.currency || 'USD'}`
}

function formatTime(value) {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

function AttemptsGridCellText({ _params, value }) {
  const val = value == null || value === '' ? 'Unavailable' : value
  return <span className="ri-cell-truncate" title={String(val)}>{val}</span>
}

const columnDefs = [
  { field: 'timestamp', headerName: 'Timestamp', sortable: true, filter: 'agTextColumnFilter', width: 170, valueFormatter: p => formatTime(p.value), sort: 'desc' },
  { field: 'transactionId', headerName: 'Attempt reference', sortable: true, filter: 'agTextColumnFilter', width: 180, cellClass: 'ri-mono' },
  { field: 'merchant', headerName: 'Merchant', sortable: true, filter: 'agTextColumnFilter', width: 150, cellRenderer: p => <AttemptsGridCellText {...p} value={p.value || 'Unavailable'} /> },
  { field: 'amount', headerName: 'Amount / currency', sortable: true, filter: 'agTextColumnFilter', width: 145, cellRenderer: p => <span className="ri-mono">{formatAmount(p.data)}</span> },
  { field: 'riskScore', headerName: 'Risk score', sortable: true, filter: 'agNumberColumnFilter', width: 100 },
  { field: 'riskLevel', headerName: 'Risk level', sortable: true, filter: 'agTextColumnFilter', width: 105 },
  { field: 'policyDecision', headerName: 'Policy', sortable: true, filter: 'agTextColumnFilter', width: 110, cellRenderer: p => <AttemptsGridCellText {...p} value={p.value || 'Unavailable'} /> },
  { field: 'decision', headerName: 'Authorization', sortable: true, filter: 'agTextColumnFilter', width: 125, cellRenderer: p => <span className={`ri-badge decision ${String(p.value || '').toLowerCase()}`}>{p.value || 'UNKNOWN'}</span> },
  { field: 'paymentState', headerName: 'Payment state', sortable: true, filter: 'agTextColumnFilter', width: 135, cellRenderer: p => <span className="tx-unavailable">{p.value || 'Unavailable'}</span> },
]

function AttemptDetails({ attempt, onClose }) {
  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="transaction-drawer"
        role="dialog"
        aria-label={`Transaction ${attempt.transactionId} details`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="drawer-head">
          <div>
            <p className="overline">Transaction attempt</p>
            <h2 className="ri-mono">{attempt.transactionId}</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close details">
            <Icon name="close" size={16} />
          </button>
        </div>

        <div className="drawer-amount">
          <span>Amount</span>
          <strong>{formatAmount(attempt)}</strong>
        </div>

        <dl className="drawer-details">
          <div><dt>Merchant</dt><dd>{attempt.merchant || 'Unavailable'}</dd></div>
          <div><dt>Product</dt><dd>Unavailable</dd></div>
          <div><dt>Authorization decision</dt><dd>{attempt.decision}</dd></div>
          <div><dt>Policy outcome</dt><dd>{attempt.policyDecision || 'Unavailable'}</dd></div>
          <div><dt>Risk</dt><dd>{attempt.riskScore == null ? 'Unavailable' : `${attempt.riskScore}/100 â€” ${attempt.riskLevel || 'n/a'}`}</dd></div>
          <div><dt>Payment state</dt><dd>Unavailable</dd></div>
          <div><dt>Latest event</dt><dd>{formatTime(attempt.timestamp)}</dd></div>
        </dl>

        {attempt.reason && <p className="drawer-reason">{attempt.reason}</p>}

        <section className="drawer-signals" aria-label="Audit events">
          <p className="overline">Audit events ({attempt.eventCount})</p>
          <ul className="drawer-event-list">
            {attempt.events.map((event, index) => (
              <li key={`${event.timestamp || 'event'}-${index}`}>
                <div>
                  <strong>{event.final_decision || event.decision || 'UNKNOWN'}</strong>
                  <span>{formatTime(event.timestamp)}</span>
                </div>
                <span className="drawer-event-meta">
                  policy {event.policy_decision || 'n/a'} â€” risk {event.risk_score ?? 'n/a'}
                </span>
                {event.decision_reason && <p>{event.decision_reason}</p>}
              </li>
            ))}
          </ul>
        </section>

        <p className="demo-note">
          Payment/capture verification is recorded on the receipt, not in the audit
          history. This attempt shows {attempt.eventCount} audit
          {attempt.eventCount === 1 ? ' event' : ' events'}; they are never merged across
          different transaction references.
        </p>
      </aside>
    </div>
  )
}

function Transactions() {
  const navigate = useNavigate()
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState(null)
  const [query, setQuery] = useState('')
  const [decision, setDecision] = useState('ALL')
  const [riskLevel, setRiskLevel] = useState('ALL')
  const [selectedId, setSelectedId] = useState('')
  const [tableApi, setTableApi] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getAuditHistory(500)
      setRecords(response.records || [])
      setUpdatedAt(new Date())
    } catch (requestError) {
      setError(requestError.message || 'Unable to load transactions.')
      setRecords([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const attempts = useMemo(() => groupAttempts(records), [records])
  const summary = useMemo(() => summarizeAuthorizationAttempts(records), [records])
  const filtered = useMemo(() => filterAttempts(attempts, { query, decision, riskLevel }), [attempts, query, decision, riskLevel])
  const selected = attempts.find((attempt) => attempt.transactionId === selectedId) || null

  const onQuickFilterChanged = useCallback((event) => {
    tableApi?.setQuickFilter?.(event.target.value)
    setQuery(event.target.value)
  }, [tableApi])

  const handleDecisionFilter = useCallback((value) => { setDecision(value) }, [])
  const handleRiskFilter = useCallback((value) => { setRiskLevel(value) }, [])

  const headerAction = (
    <div className="ri-header-actions">
      {updatedAt && <span className="ri-updated">Updated {updatedAt.toLocaleTimeString()}</span>}
      <button type="button" className="outline-button small-button" onClick={load} disabled={loading}>
        <Icon name="activity" size={14} /> {loading ? 'Refreshing...' : 'Refresh'}
      </button>
    </div>
  )

  return (
    <>
      <PageHeader
        eyebrow="Activity monitor"
        title="Transactions"
        description="Payment attempts recorded in the backend audit history, grouped by transaction reference."
        action={headerAction}
      />

      {error && <p className="api-error" role="alert">{error}</p>}

      <p className="metric-definition">
        <strong>{METRIC_DEFINITIONS.authorizationAttempts.label}:</strong>{' '}
        {METRIC_DEFINITIONS.authorizationAttempts.description} Counts unique
        transaction references, deduplicated by transaction ID — not raw audit
        lines. Compare with Risk Intelligence, which counts every audit
        decision record.
      </p>

      <section className="ri-summary" aria-label="Transaction summary">
        <article className="ri-card panel ri-card-total">
          <div className="ri-card-head">
            <span className="overline">Attempts</span>
            <span className="ri-card-icon"><Icon name="card" size={16} /></span>
          </div>
          <strong className="ri-card-value">{summary.total}</strong>
          <span className="ri-card-meta">Unique transaction references in audit history</span>
        </article>
        {['ALLOW', 'REVIEW', 'BLOCK'].map((item) => (
          <article className={`ri-card panel ri-card-${item.toLowerCase()}`} key={item}>
            <div className="ri-card-head">
              <span className="overline">{item}</span>
              <span className={`ri-card-icon ${item.toLowerCase()}`}>
                <Icon name={item === 'ALLOW' ? 'check' : item === 'REVIEW' ? 'alert' : 'close'} size={16} />
              </span>
            </div>
            <strong className="ri-card-value">{summary[item] || 0}</strong>
            <span className="ri-card-meta">{summary.total ? Math.round((summary[item] / summary.total) * 100) : 0}% of attempts</span>
          </article>
        ))}
      </section>

      <section className="page-panel panel" aria-label="Transaction table">
        <div className="table-heading tx-heading">
          <div>
            <h2>Payment attempts</h2>
            <span>{filtered.length} of {attempts.length} attempts â€” authorization decisions only</span>
          </div>
          <div className="tx-controls">
            <label className="ri-search">
              <Icon name="search" size={14} />
              <input type="search" value={query} placeholder="Search reference, merchantâ€¦" aria-label="Search transactions" onChange={onQuickFilterChanged} />
            </label>
            <select value={decision} onChange={(event) => handleDecisionFilter(event.target.value)} aria-label="Filter by decision">
              {DECISION_FILTERS.map((item) => <option key={item} value={item}>{item === 'ALL' ? 'All decisions' : item}</option>)}
            </select>
            <select value={riskLevel} onChange={(event) => handleRiskFilter(event.target.value)} aria-label="Filter by risk level">
              {RISK_FILTERS.map((item) => <option key={item} value={item}>{item === 'ALL' ? 'All risk levels' : item}</option>)}
            </select>
          </div>
        </div>

        {loading && attempts.length === 0 ? (
          <p className="muted-text">Loading transactionsâ€¦</p>
        ) : filtered.length === 0 ? (
          <p className="muted-text">
            {attempts.length === 0
              ? 'No payment attempts recorded yet. Governed checkouts will appear here.'
              : 'No transactions match the current filters.'}
          </p>
        ) : (
          <div className="ag-theme-quartz-dark ri-grid" style={{ height: 560, width: '100%' }}>
            <AgGridReact
              rowData={filtered}
              columnDefs={columnDefs}
              defaultColDef={{ resizable: true, sortable: true, filter: true, minWidth: 80 }}
              pagination={true}
              paginationPageSize={ATTEMPT_PAGE_SIZE}
              paginationPageSizeSelector={[10, 25, 50, 100]}
              getRowId={(params) => String(params.data.key || params.data.transactionId)}
              quickFilterText={query}
              animateRows={false}
              rowSelection={{ mode: 'singleRow' }}
              onRowClicked={(event) => setSelectedId(event.data.transactionId)}
              onGridReady={(event) => setTableApi(event.api)}
              overlayNoRowsTemplate={'<span class="ri-empty-overlay">No transactions match the selected filters.</span>'}
            />
          </div>
        )}
        <p className="tx-footnote">
          Payment/capture state is stored on receipts.{' '}
          <button type="button" className="text-button" onClick={() => navigate('/receipts')}>View receipts â†’</button>
        </p>
      </section>

      {selected && <AttemptDetails attempt={selected} onClose={() => setSelectedId('')} />}
    </>
  )
}

export default Transactions
