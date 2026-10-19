import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import Icon from '../components/Icon'
import PageHeader from '../components/PageHeader'
import Receipt from '../components/Receipt'
import { getReceipts } from '../services/api'

const STATUS_TONE = {
  COMPLETED: 'allow',
  PENDING: 'review',
  REVIEW_REQUIRED: 'review',
  FAILED: 'block',
  CANCELLED: 'block',
  BLOCKED: 'block',
  EXPIRED: 'block',
  REFUNDED: 'review',
  PARTIALLY_REFUNDED: 'review',
}

function statusTone(status) {
  return STATUS_TONE[String(status || '').toUpperCase()] || 'review'
}

function formatAmount(value, currency) {
  if (value == null || value === '') return 'Not available'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return `${value}`
  return `${currency || 'USD'} ${numeric.toFixed(2)}`
}

function formatDate(value) {
  if (!value) return 'Not available'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString()
}

function Receipts() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()
  const [receipts, setReceipts] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const runFetch = useCallback(
    () =>
      getReceipts(100)
        .then((response) => setReceipts(response.receipts || []))
        .catch((requestError) => {
          const message = requestError.message || 'Unable to load receipts.'
          if (requestError.status === 401) {
            setError('Session expired. Please sign in again.')
          } else {
            setError(message)
          }
        })
        .finally(() => setLoading(false)),
    [],
  )

  useEffect(() => {
    // Only fetch when authenticated and not still restoring the session.
    if (authLoading || !user) return
    runFetch()
  }, [runFetch, authLoading, user])

  const load = () => {
    setLoading(true)
    setError('')
    runFetch()
  }

  const selected = useMemo(
    () => receipts.find((entry) => entry.receipt_id === selectedId) || null,
    [receipts, selectedId],
  )

  // While the session is being restored, show a loading state.
  if (authLoading) {
    return (
      <div className="auth-loading-screen">
        <div className="spinner" />
        <p>Restoring PayShield session…</p>
      </div>
    )
  }

  // Not authenticated: show a clear sign-in prompt rather than an opaque error.
  if (!user) {
    return (
      <>
        <PageHeader
          eyebrow="Payment records"
          title="Receipts"
          description="Persistent, server-verified records of every PayShield-governed payment attempt."
        />
        <section className="page-panel panel">
          <div className="empty-state" style={{ textAlign: 'center', padding: '60px 20px' }}>
            <Icon name="alert-circle" size={48} style={{ marginBottom: 16, color: 'var(--amber)' }} />
            <h3 style={{ margin: '0 0 8px', color: 'var(--text)' }}>Authentication required</h3>
            <p style={{ margin: '0 0 20px', color: 'var(--muted)' }}>
              Please sign in to view your receipts. Receipts are scoped to your
              authenticated identity and are never shared with other users.
            </p>
            <button
              type="button"
              className="primary-button"
              onClick={() => navigate('/login')}
            >
              Sign in
            </button>
          </div>
        </section>
      </>
    )
  }

  return (
    <>
      <PageHeader
        eyebrow="Payment records"
        title="Receipts"
        description="Persistent, server-verified records of every PayShield-governed payment attempt."
        action={(
          <button type="button" className="outline-button small-button" onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        )}
      />
      {error && (
        <div className="api-error" role="alert">
          <strong>{error.includes('Session expired') ? 'Session expired' : 'Unable to load receipts'}</strong>
          <p>{error}</p>
          {error.includes('Session expired') && (
            <button type="button" className="outline-button small-button" onClick={() => navigate('/login')}>
              Sign in again
            </button>
          )}
        </div>
      )}
      <section className="receipts-layout">
        <div className="page-panel panel">
          <div className="table-heading">
            <div><h2>Your receipts</h2><span>{receipts.length} records</span></div>
          </div>
          {loading && <p className="muted-text">Loading receipts…</p>}
          {!loading && receipts.length === 0 && !error && (
            <p className="muted-text">No receipts yet. Completed or attempted checkouts will appear here.</p>
          )}
          <div className="receipts-list">
            {receipts.map((entry) => (
              <button
                type="button"
                key={entry.receipt_id}
                className={`receipt-row ${selectedId === entry.receipt_id ? 'selected' : ''}`}
                onClick={() => setSelectedId(entry.receipt_id)}
              >
                <div>
                  <strong>{entry.merchant_name || entry.snapshots?.product?.title || 'Merchant unavailable'}</strong>
                  <span>{formatDate(entry.created_at)}</span>
                </div>
                <div>
                  <strong>{formatAmount(entry.amount, entry.currency)}</strong>
                  <span className={`receipt-status ${statusTone(entry.status)}`}>{entry.status || 'Unknown'}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
        {selected && <Receipt receipt={selected} heading="Receipt detail" />}
      </section>
    </>
  )
}

export default Receipts
