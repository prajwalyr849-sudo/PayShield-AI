import { useCallback, useEffect, useMemo, useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-quartz.css'
import PageHeader from '../components/PageHeader'
import Icon from '../components/Icon'
import { getAuditHistory } from '../services/api'
import { filterRows, summarizeRisk, toRiskRow } from '../utils/risk'
import { METRIC_DEFINITIONS } from '../utils/metrics'

const DECISIONS = ['ALLOW', 'REVIEW', 'BLOCK']
const RISK_LEVELS = ['LOW', 'MEDIUM', 'HIGH']
const PAGE_SIZE = 25

function formatAmount(row) {
  if (!row || row.amount == null || row.amount === '') return 'Unavailable'
  const value = Number(row.amount)
  if (!Number.isFinite(value)) return `${row.amount} ${row.currency || 'USD'}`
  return `${value.toFixed(2)} ${row.currency || 'USD'}`
}

function formatTime(value) {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

function percent(part, total) {
  if (!total) return 0
  return Math.round((part / total) * 100)
}

function StatusBadge({ value, kind = 'decision' }) {
  const text = value || 'UNKNOWN'
  return <span className={`ri-badge ${kind} ${String(text).toLowerCase()}`}>{text}</span>
}

function BadgeCellRenderer(params) {
  return <StatusBadge value={params.value} kind={params.kind} />
}

function DetailsCellRenderer(params) {
  const onOpen = params.context?.onOpenDetails
  return (
    <button
      type="button"
      className="outline-button small-button ri-details-button"
      onClick={() => onOpen?.(params.data)}
    >
      Details
    </button>
  )
}

function TruncateCellRenderer(params) {
  const value = params.value || 'Unavailable'
  return (
    <span className="ri-cell-truncate" title={String(value)}>
      {value}
    </span>
  )
}

function AmountCellRenderer(params) {
  const row = params.data || {}
  return <span className="ri-mono">{formatAmount(row)}</span>
}

const columnDefs = [
  { field: 'timestamp', headerName: 'Timestamp', sortable: true, filter: 'agDateColumnFilter', width: 175, valueFormatter: (p) => formatTime(p.value) },
  { field: 'transactionId', headerName: 'Attempt ID', sortable: true, filter: 'agTextColumnFilter', width: 160 },
  { field: 'orderReference', headerName: 'Order reference', sortable: true, filter: 'agTextColumnFilter', width: 170, cellRenderer: TruncateCellRenderer },
  { field: 'merchant', headerName: 'Merchant', sortable: true, filter: 'agTextColumnFilter', width: 150, cellRenderer: TruncateCellRenderer },
  { field: 'product', headerName: 'Product', sortable: true, filter: 'agTextColumnFilter', width: 180, cellRenderer: TruncateCellRenderer },
  { field: 'amount', headerName: 'Amount / currency', sortable: true, filter: 'agTextColumnFilter', width: 140, cellRenderer: AmountCellRenderer },
  { field: 'riskScore', headerName: 'Risk score', sortable: true, filter: 'agNumberColumnFilter', width: 95 },
  { field: 'riskLevel', headerName: 'Risk level', sortable: true, filter: 'agTextColumnFilter', width: 100, cellRenderer: (p) => <BadgeCellRenderer {...p} kind="risk" /> },
  { field: 'policyDecision', headerName: 'Policy outcome', sortable: true, filter: 'agTextColumnFilter', width: 120, cellRenderer: TruncateCellRenderer },
  { field: 'decision', headerName: 'Authorization decision', sortable: true, filter: 'agTextColumnFilter', width: 135, cellRenderer: (p) => <BadgeCellRenderer {...p} kind="decision" /> },
  { field: 'paymentStatus', headerName: 'Payment / capture', sortable: true, filter: 'agTextColumnFilter', width: 150, cellRenderer: TruncateCellRenderer },
  { field: 'evidenceStatus', headerName: 'Product evidence', sortable: true, filter: 'agTextColumnFilter', width: 135, cellRenderer: TruncateCellRenderer },
  { headerName: 'Details', sortable: false, filter: false, width: 95, pinned: 'right', cellRenderer: DetailsCellRenderer },
]

function DetailSection({ title, children }) {
  return (
    <section className="ri-detail-section" aria-label={title}>
      <h3>{title}</h3>
      {children}
    </section>
  )
}

function RiskIntelligence() {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null)
  const [selectedRow, setSelectedRow] = useState(null)
  const [query, setQuery] = useState('')
  const [tableApi, setTableApi] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setLastRefreshedAt(new Date())
    try {
      const response = await getAuditHistory(500)
      setRecords(response.records || [])
      setSelectedRow(null)
    } catch (requestError) {
      setError(requestError.message || 'Unable to load risk records.')
      setRecords([])
      setSelectedRow(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const summary = useMemo(() => summarizeRisk(records), [records])
  const rows = useMemo(() => records.map((record, index) => toRiskRow(record, index)), [records])
  const filteredRows = useMemo(() => filterRows(rows, query), [rows, query])

  // Derive extra columns unsupported by toRiskRow without fabricating data.
  const enrichedRows = useMemo(
    () =>
      filteredRows.map((row) => {
        const raw = row.raw && typeof row.raw === 'object' ? row.raw : {}
        return {
          ...row,
          product: raw.product_name || raw.product || raw.title || raw.product_reference || raw.product_id || '',
        }
      }),
    [filteredRows],
  )

  const latestRecordTimestamp = useMemo(() => {
    const timestamps = records
      .map((record) => record && record.timestamp)
      .filter(Boolean)
      .sort()
    return timestamps.length ? timestamps[timestamps.length - 1] : null
  }, [records])

  const onQuickFilterChanged = useCallback((event) => {
    tableApi?.setQuickFilter?.(event.target.value)
    setQuery(event.target.value)
  }, [tableApi])

  const headerAction = (
    <div className="ri-header-actions">
      {lastRefreshedAt && <span className="ri-updated">Updated {lastRefreshedAt.toLocaleString()}</span>}
      <button type="button" className="outline-button small-button" onClick={load} disabled={loading}>
        <Icon name="activity" size={14} /> {loading ? 'Refreshing…' : 'Refresh'}
      </button>
    </div>
  )

  const gridContext = useMemo(() => ({ onOpenDetails: setSelectedRow }), [])

  return (
    <>
      <PageHeader
        eyebrow="Security operations"
        title="Risk Intelligence"
        description="Understand transaction risk, policy enforcement and authorization outcomes."
        action={headerAction}
      />

      <p className="ri-data-note" role="note">
        Summary and table values are derived from {summary.total} audit decision records for the current authenticated user.
        They are not payment attempts or PayPal capture events. {latestRecordTimestamp ? `Latest record: ${formatTime(latestRecordTimestamp)}.` : ''}
      </p>

      {error && <p className="api-error" role="alert">{error}</p>}

      <p className="metric-definition">
        <strong>{METRIC_DEFINITIONS.auditDecisionRecords.label}:</strong>{' '}
        {METRIC_DEFINITIONS.auditDecisionRecords.description} Counts every raw
        audit line, including duplicate events for the same transaction — not
        unique transaction references. Compare with Transactions, which counts
        unique transaction references deduplicated by transaction ID.
      </p>

      <section className="ri-summary" aria-label="Decision summary">
        {DECISIONS.map((decision) => (
          <article className={`ri-card panel ri-card-${decision.toLowerCase()}`} key={decision}>
            <div className="ri-card-head">
              <span className="overline">{decision}</span>
              <span className={`ri-card-icon ${decision.toLowerCase()}`}><Icon name={decision === 'ALLOW' ? 'check' : decision === 'REVIEW' ? 'alert' : 'close'} size={16} /></span>
            </div>
            <strong className="ri-card-value">{summary.decisions[decision] || 0}</strong>
            <span className="ri-card-meta">{percent(summary.decisions[decision] || 0, summary.total)}% of {summary.total} audit decision records</span>
          </article>
        ))}
      </section>

      <section className="ri-panel-grid">
        <article className="panel ri-distribution" aria-label="Risk level distribution">
          <div className="table-heading"><div><h2>Risk distribution</h2><span>Across {summary.total} audit decision records</span></div></div>
          {summary.total === 0 ? (
            <p className="muted-text">No risk evaluations recorded yet.</p>
          ) : (
            <ul className="ri-bars">
              {RISK_LEVELS.map((level) => (
                <li key={level}>
                  <span className="ri-bar-label">{level}</span>
                  <span className="ri-bar-track"><span className={`ri-bar-fill ${level.toLowerCase()}`} style={{ width: `${percent(summary.riskLevels[level] || 0, summary.total)}%` }} /></span>
                  <span className="ri-bar-value">{summary.riskLevels[level] || 0}</span>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="panel ri-overview" aria-label="Enforcement overview">
          <div className="table-heading"><div><h2>Enforcement</h2><span>Summary of recorded outcomes</span></div></div>
          <dl className="ri-overview-list">
            <div><dt>Total audit decision records</dt><dd>{summary.total}</dd></div>
            <div><dt>Non-ALLOW outcomes</dt><dd>{summary.nonAllow}</dd></div>
            <div><dt>ALLOW rate</dt><dd>{percent(summary.decisions.ALLOW || 0, summary.total)}%</dd></div>
          </dl>
        </article>
      </section>

      <section className="page-panel panel" aria-label="Decision history">
        <div className="table-heading">
          <div>
            <h2>Decision history</h2>
            <span>{enrichedRows.length} of {rows.length} records</span>
          </div>
          <label className="ri-search">
            <Icon name="search" size={14} />
            <input
              type="search"
              value={query}
              placeholder="Search any field…"
              onChange={onQuickFilterChanged}
              aria-label="Search decision history"
            />
          </label>
        </div>

        {error && !loading && enrichedRows.length === 0 ? (
          <p className="api-error" role="alert">{error}</p>
        ) : loading && records.length === 0 ? (
          <p className="muted-text">Loading risk records…</p>
        ) : enrichedRows.length === 0 ? (
          <p className="muted-text">{rows.length === 0 ? 'No risk evaluations recorded yet.' : 'No records match your search.'}</p>
        ) : (
          <div className="ag-theme-quartz-dark ri-grid" style={{ height: 560, width: '100%' }}>
            <AgGridReact
              rowData={enrichedRows}
              columnDefs={columnDefs}
              defaultColDef={{ resizable: true, sortable: true, filter: true, minWidth: 80 }}
              pagination={true}
              paginationPageSize={PAGE_SIZE}
              paginationPageSizeSelector={[10, 25, 50, 100]}
              getRowId={(params) => String(params.data.key || params.data.transactionId || params.rowIndex)}
              quickFilterText={query}
              animateRows={false}
              rowSelection={{ mode: 'singleRow' }}
              onRowClicked={(event) => setSelectedRow(event.data)}
              onGridReady={(event) => setTableApi(event.api)}
              context={gridContext}
              loading={loading}
              overlayNoRowsTemplate={'<span class="ri-empty-overlay">No risk records match the selected filters.</span>'}
              domLayout="normal"
            />
          </div>
        )}

        {selectedRow && (
          <div className="ri-detail panel" role="region" aria-label={`Decision details for ${selectedRow.transactionId || 'record'}`}>
            <button type="button" className="outline-button small-button ri-detail-close" onClick={() => setSelectedRow(null)}>Close</button>
            <dl className="ri-detail-grid">
              <div><dt>Attempt / transaction ID</dt><dd className="ri-mono">{selectedRow.transactionId || 'Unavailable'}</dd></div>
              <div><dt>Order reference</dt><dd className="ri-mono">{selectedRow.orderReference || 'Unavailable'}</dd></div>
              <div><dt>Merchant</dt><dd>{selectedRow.merchant || 'Unavailable'}</dd></div>
              <div><dt>Product</dt><dd>{selectedRow.product || 'Unavailable'}</dd></div>
              <div><dt>Amount / currency</dt><dd>{formatAmount(selectedRow)}</dd></div>
              <div><dt>Authorization decision</dt><dd><StatusBadge value={selectedRow.decision} kind="decision" /></dd></div>
              <div><dt>Policy outcome</dt><dd>{selectedRow.policyDecision || 'Unavailable'}</dd></div>
              <div><dt>Risk score</dt><dd>{selectedRow.riskScore == null ? 'Unavailable' : `${selectedRow.riskScore}/100`}</dd></div>
              <div><dt>Risk level</dt><dd><StatusBadge value={selectedRow.riskLevel || 'UNKNOWN'} kind="risk" /></dd></div>
              <div><dt>Product evidence status</dt><dd>{selectedRow.evidenceStatus || 'Unavailable'}</dd></div>
              <div><dt>Payment / capture status</dt><dd>{selectedRow.paymentStatus || 'Unavailable'}</dd></div>
              <div><dt>Timestamp</dt><dd>{formatTime(selectedRow.timestamp)}</dd></div>
              <div className="ri-detail-wide"><dt>Decision reason</dt><dd>{selectedRow.reason || 'Explanation unavailable'}</dd></div>
            </dl>

            <div className="ri-detail-sections">
              <DetailSection title="1. Product evidence quality">
                <p>{selectedRow.evidenceStatus ? `Stored evidence status: ${selectedRow.evidenceStatus}.` : 'Evidence status unavailable.'} Product titles and source references are truncated in the table; full values appear here only when present.</p>
              </DetailSection>
              <DetailSection title="2. Risk assessment">
                <p>Risk score {selectedRow.riskScore == null ? 'unavailable' : `${selectedRow.riskScore}/100`}; risk level {selectedRow.riskLevel || 'unavailable'}. Risk output is advisory context and cannot by itself authorize payment.</p>
              </DetailSection>
              <DetailSection title="3. Deterministic policy result">
                <p>{selectedRow.policyDecision || 'Unavailable'}. Policy can return ALLOW, REVIEW or BLOCK independently of risk score.</p>
              </DetailSection>
              <DetailSection title="4. Final authorization decision">
                <p><StatusBadge value={selectedRow.decision} kind="decision" />. A policy BLOCK cannot be converted into ALLOW by retrying or by a low risk score.</p>
              </DetailSection>
              <DetailSection title="5. Actual payment / capture outcome">
                <p>{selectedRow.paymentStatus || 'Unavailable'}. Browser return parameters are not treated as proof of capture; server-confirmed capture status only.</p>
              </DetailSection>
              <DetailSection title="AI assessment (advisory only)">
                <p>Any AI-generated recommendation is advisory and cannot override deterministic risk, policy, evidence or payment guards.</p>
              </DetailSection>
            </div>
          </div>
        )}
      </section>
    </>
  )
}

export default RiskIntelligence
