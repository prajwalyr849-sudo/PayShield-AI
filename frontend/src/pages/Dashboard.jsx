import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Icon from '../components/Icon'
import PageHeader from '../components/PageHeader'
import { getAuditHistory } from '../services/api'
import { groupAttempts } from '../utils/transactions.js'
import { summarizeAuthorizationAttempts, METRIC_DEFINITIONS } from '../utils/metrics'

const decisions = ['ALLOW', 'REVIEW', 'BLOCK']
const RISK_LEVELS = ['LOW', 'MEDIUM', 'HIGH']

function decisionClass(decision) {
  return String(decision).toLowerCase()
}

function riskBand(score) {
  if (score == null || !Number.isFinite(Number(score))) return 'unknown'
  if (Number(score) >= 70) return 'high'
  if (Number(score) >= 40) return 'medium'
  return 'low'
}

function formatAmount(value, currency) {
  if (value == null || !Number.isFinite(Number(value))) return 'Unavailable'
  return `${Number(value).toFixed(2)} ${currency || 'USD'}`
}

function Dashboard() {
  const navigate = useNavigate()
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [timeRange, setTimeRange] = useState('30D')
  const [now] = useState(() => Date.now())

  useEffect(() => {
    setLoading(true)
    getAuditHistory(100)
      .then((response) => setRecords(response.records || []))
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoading(false))
  }, [])

  const rangeRecords = useMemo(() => {
    if (timeRange === 'YTD') {
      const year = new Date(now).getUTCFullYear()
      return records.filter((record) => new Date(record.timestamp).getUTCFullYear() === year)
    }
    const days = timeRange === '7D' ? 7 : timeRange === '90D' ? 90 : 30
    const cutoff = now - days * 24 * 60 * 60 * 1000
    return records.filter((record) => {
      const timestamp = Date.parse(record.timestamp || '')
      return Number.isFinite(timestamp) && timestamp >= cutoff
    })
  }, [now, records, timeRange])

  const attempts = useMemo(() => groupAttempts(rangeRecords), [rangeRecords])
  // Risk band distribution for the dashboard histogram. summarizeAuthorizationAttempts
  // intentionally does not compute risk levels (that metric lives on summarizeAttempts),
  // so derive it from the same attempt list without substituting one dataset for the other.
  const riskLevels = useMemo(() => {
    const levels = { LOW: 0, MEDIUM: 0, HIGH: 0, UNKNOWN: 0 }
    for (const attempt of attempts) {
      const level = attempt.riskLevel in levels ? attempt.riskLevel : 'UNKNOWN'
      levels[level] += 1
    }
    return levels
  }, [attempts])
  const summary = useMemo(() => {
    const counts = summarizeAuthorizationAttempts(rangeRecords)
    const protectedSpend = attempts
      .filter((attempt) => attempt.decision === 'ALLOW')
      .reduce((total, attempt) => total + (Number(attempt.amount) || 0), 0)
    const scored = attempts.filter((attempt) => attempt.riskScore != null)
    const averageRisk = scored.length
      ? Math.round(scored.reduce((total, attempt) => total + attempt.riskScore, 0) / scored.length)
      : null
    return { ...counts, protectedSpend, averageRisk, scoredCount: scored.length }
  }, [attempts, rangeRecords])

  const recent = attempts.slice(0, 5)
  const riskTotal = riskLevels.LOW + riskLevels.MEDIUM + riskLevels.HIGH

  return (
    <>
      {error && (
        <div className="api-error" role="alert">
          <strong>Unable to load records</strong>
          <p>{error}</p>
        </div>
      )}

      <PageHeader
        eyebrow="Trust Operating System for Agentic Commerce"
        title="PayShield AI"
        description="Let AI act. Keep humans in control."
        action={
          <div className="actions-row">
            <button type="button" className="outline-button" onClick={() => navigate('/assistant/search')}>
              <Icon name="search" size={14} /> Search Product
            </button>
            <button type="button" className="primary-button" onClick={() => navigate('/checkout')}>
              <Icon name="card" size={14} /> New Transaction
            </button>
          </div>
        }
      />

      <section className="page-panel" aria-label="Time period">
        <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
          <span style={{ fontSize:'11px', color:'var(--muted)', fontWeight:'600', textTransform:'uppercase', letterSpacing:'.08em' }}>Period</span>
          {['30D', '7D', '90D', 'YTD'].map((range) => (
            <button
              key={range}
              type="button"
              className={timeRange === range ? 'active' : ''}
              onClick={() => setTimeRange(range)}
              style={{
                padding: '6px 10px', border: '1px solid var(--line)', borderRadius: '7px',
                background: timeRange === range ? 'rgba(34,211,238,.15)' : 'rgba(13,27,44,.45)',
                color: timeRange === range ? 'var(--cyan)' : 'var(--muted)',
                fontSize: '11px', fontWeight: '600', cursor: 'pointer',
              }}
            >
              {range === '30D' ? '30 Days' : range === '7D' ? '7 Days' : range === '90D' ? '90 Days' : 'YTD'}
            </button>
          ))}
        </div>
      </section>

      <section className="page-panel" aria-label="Key metrics">
        <p className="metric-definition">
          <strong>{METRIC_DEFINITIONS.authorizationAttempts.label}:</strong>{' '}
          {METRIC_DEFINITIONS.authorizationAttempts.description} Counts unique
          transaction references, deduplicated by transaction ID — not raw audit
          lines. Compare with Risk Intelligence, which counts every audit
          decision record.
        </p>
        <div className="metrics-grid">
          <article className="metric-card">
            <div className="metric-icon cyan"><Icon name="card" size={18} /></div>
            <div className="metric-copy">
              <p>Authorization attempts</p>
              <strong>{summary.total}</strong>
              <span className="change-warning">{summary.total ? Math.round((summary.total / Math.max(summary.total, 1)) * 100) : 0}% <em>in period</em></span>
            </div>
            <div className="sparkline"><span /><span /><span /><span /><span /><span /><span /></div>
          </article>
          {['ALLOW', 'REVIEW', 'BLOCK'].map((decision) => (
            <article className={`metric-card metric-${decisionClass(decision)}`} key={decision}>
              <div className={`metric-icon ${decisionClass(decision)}`}>
                <Icon name={decision === 'ALLOW' ? 'check' : decision === 'REVIEW' ? 'alert' : 'close'} size={18} />
              </div>
              <div className="metric-copy">
                <p>{decision}</p>
                <strong>{summary[decision] || 0}</strong>
                <span>{summary.total ? Math.round((summary[decision] || 0) / summary.total * 100) : 0}% <em>of attempts</em></span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="page-panel" aria-label="Risk and enforcement">
        <div className="analysis-grid">
          <article className="panel risk-card">
            <div className="card-heading">
              <div>
                <p className="overline">Risk level distribution</p>
                <h2>Risk overview</h2>
              </div>
              <b>{summary.scoredCount ? `Avg: ${summary.averageRisk}/100` : 'No risk scores'}</b>
            </div>
            <div className="stitch-histogram">
              {RISK_LEVELS.map((level) => {
                const count = riskLevels[level] || 0
                const share = riskTotal ? Math.round((count / riskTotal) * 100) : 0
                return (
                  <div className="stitch-bar-column" key={level}>
                    <i className={level.toLowerCase()} style={{ height: `${riskTotal ? Math.max(4, share) : 4}%` }} />
                    <span>{level}</span>
                    <small>{count}</small>
                  </div>
                )
              })}
              {!riskTotal && <div className="stitch-empty">No risk scores recorded in this period.</div>}
            </div>
            <div className="stitch-engine-status">
              <span><span className="live-dot" /> Backend status: reachable</span>
              <b>{riskTotal} attempts scored · {timeRange}</b>
            </div>
          </article>

          <article className="panel verdicts-card">
            <div className="card-heading">
              <div>
                <p className="overline">Evaluation verdicts</p>
                <h2>Authorization outcomes</h2>
              </div>
              <small>{summary.total} attempts · {timeRange}</small>
            </div>
            <div className="stitch-verdict-grid">
              {decisions.map((decision) => (
                <article className={`stitch-verdict ${decisionClass(decision)}`} key={decision}>
                  <Icon name={decision === 'ALLOW' ? 'check' : decision === 'REVIEW' ? 'info' : 'alert'} size={19} />
                  <strong>{summary[decision] || 0}</strong>
                  <span>{decision}</span>
                </article>
              ))}
            </div>
          </article>
        </div>
      </section>

      <section className="page-panel" aria-label="Recent authorizations">
        <div className="card-heading">
          <div>
            <p className="overline">Recent activity</p>
            <h2>Recent authorizations</h2>
          </div>
          <button type="button" className="text-button" onClick={() => navigate('/transactions')}>
            View all <Icon name="arrow" size={14} />
          </button>
        </div>
        {loading && attempts.length === 0 ? (
          <p className="pr-muted" style={{ textAlign: 'center', padding: '40px 0' }}>Loading authorization records…</p>
        ) : recent.length === 0 ? (
          <div className="empty-state">No authorization records yet.</div>
        ) : (
          <div className="recent-list">
            {recent.map((attempt) => {
              const decision = attempt.decision
              const band = riskBand(attempt.riskScore)
              return (
                <article className="stitch-authorization" key={attempt.key}>
                  <div className="stitch-authorization-main">
                    <div className="stitch-merchant-icon"><Icon name="card" size={20} /></div>
                    <div>
                      <strong>{attempt.merchant || 'Merchant unavailable'}</strong>
                      <span>{attempt.transactionId}{attempt.hasMultipleEvents ? ` · ${attempt.eventCount} events` : ''}</span>
                    </div>
                    <b>{formatAmount(attempt.amount, attempt.currency)}</b>
                  </div>
                  <div className="stitch-authorization-status">
                    <span className={`stitch-decision ${decisionClass(decision)}`}>{decision}</span>
                    <span className={`stitch-risk-inline ${band}`}>Risk {attempt.riskScore ?? 'n/a'}/100{attempt.riskLevel ? ` · ${attempt.riskLevel}` : ''}</span>
                    <small>{attempt.timestamp || 'Time unavailable'}</small>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>
    </>
  )
}

export default Dashboard
