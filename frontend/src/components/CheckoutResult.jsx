import Icon from './Icon'

const CAPTURED_STATES = new Set(['COMPLETED', 'CAPTURED'])
const NOT_CAPTURED_STATES = new Set([
  'NOT_CAPTURED',
  'BLOCKED',
  'REVIEW_REQUIRED',
  'FAILED',
  'EXPIRED',
])

function redact(value) {
  if (!value) return 'Unavailable'
  const text = String(value)
  if (text.length <= 4) return '\u2022\u2022\u2022\u2022'
  return `\u2022\u2022\u2022\u2022${text.slice(-4)}`
}

function formatAmount(amount, currency) {
  if (amount == null || amount === '') return 'Unavailable'
  const value = Number(amount)
  if (!Number.isFinite(value)) return `${amount}`
  return `${value.toFixed(2)} ${currency || 'USD'}`
}

function formatDate(value) {
  if (!value) return 'Unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString()
}

function resolveOutcome({ capture, receipt, cancelled, loading }) {
  const rawPayment = String(capture?.payment_status || receipt?.payment_status_raw || '').toUpperCase()
  const receiptStatus = String(receipt?.status || '').toUpperCase()

  if (cancelled) return 'CANCELLED'
  if (CAPTURED_STATES.has(rawPayment) || CAPTURED_STATES.has(receiptStatus)) return 'CAPTURED'
  if (loading && !capture && !receipt) return 'PENDING'
  if (NOT_CAPTURED_STATES.has(rawPayment) || NOT_CAPTURED_STATES.has(receiptStatus)) return 'NOT_CAPTURED'
  return rawPayment || receiptStatus || 'PENDING'
}

function outcomeTone(outcome) {
  if (outcome === 'CAPTURED') return 'allow'
  if (outcome === 'PENDING') return 'review'
  return 'block'
}

function explanationFor(outcome, decision) {
  if (outcome === 'CANCELLED') return 'The buyer cancelled PayPal approval, so no payment was captured.'
  if (outcome === 'PENDING') return 'PayShield is verifying the payment server-side. No outcome is confirmed yet.'
  if (outcome === 'CAPTURED') return 'PayPal confirmed the capture server-side. The authorization decision is recorded separately below.'
  if (decision === 'BLOCK') return 'PayShield blocked this payment. No capture was requested or performed.'
  if (decision === 'REVIEW') return 'This payment requires review and was not captured.'
  if (decision === 'ALLOW') return 'PayShield authorized the payment, but no completed capture was confirmed by the server.'
  return 'The final payment state is not captured. See the details below.'
}

function DetailItem({ label, value, tone }) {
  return (
    <div className="checkout-detail-item">
      <dt>{label}</dt>
      <dd className={tone || ''}>{value || 'Unavailable'}</dd>
    </div>
  )
}

function CheckoutResult({ capture, receipt, cancelled, loading, error, orderId, onRetry }) {
  const outcome = resolveOutcome({ capture, receipt, cancelled, loading })
  const decision = String(capture?.decision || receipt?.decision || '').toUpperCase() || 'UNKNOWN'
  const tone = outcomeTone(outcome)

  const product = receipt?.snapshots?.product || capture?.snapshots?.product || {}
  const risk = capture?.risk_assessment || receipt?.snapshots?.risk || {}
  const policyReasons = receipt?.snapshots?.policy?.reasons
  const riskScore = risk.score ?? receipt?.risk_score ?? capture?.risk_score
  const riskLevel = risk.level || receipt?.risk_level || capture?.risk_level
  const merchant = receipt?.merchant_name || product.retailer || product.title || capture?.integrity_result?.registered_merchant || 'Unavailable'
  const productTitle = product.title || product.reference || 'Unavailable'
  const amount = receipt?.amount ?? capture?.amount
  const currency = receipt?.currency || capture?.currency
  const policyOutcome = capture?.policy_result?.decision || receipt?.snapshots?.policy?.decision || receipt?.policy_decision
  const policyReason = capture?.policy_result?.reason
    || receipt?.snapshots?.policy?.reason
    || (Array.isArray(policyReasons) ? policyReasons.filter(Boolean).join('; ') : '')
  const evidenceStatus = String(product.evidence_status || capture?.snapshots?.product?.evidence_status || '').toUpperCase()
  const evidenceSource = product.source_domain || product.retailer || product.source_url || capture?.snapshots?.product?.source_domain || ''

  return (
    <section className="checkout-result-v2" aria-label="Checkout result">
      <article className={`panel checkout-outcome outcome-${tone}`}>
        <div className="checkout-outcome-head">
          <span className="checkout-outcome-icon"><Icon name={outcome === 'CAPTURED' ? 'check' : outcome === 'PENDING' ? 'info' : 'alert'} size={20} /></span>
          <div>
            <p className="overline">Payment outcome</p>
            <h2>{loading && !capture && !receipt ? 'Verifying…' : outcome}</h2>
          </div>
          <span className={`ri-badge ${decision.toLowerCase()}`}>{decision}</span>
        </div>
        <p className="checkout-outcome-note">{explanationFor(outcome, decision)}</p>
        <p className="checkout-outcome-distinction">
          Authorization (PayShield decision) and payment capture (PayPal) are separate.
          An ALLOW decision does not by itself mean a payment was captured.
        </p>
        {loading && <p className="muted-text">Confirming the payment with the PayShield backend…</p>}
        {error && (
          <div className="api-error" role="alert">
            <strong>Could not verify the payment</strong>
            <p>{error}</p>
            {onRetry && <button type="button" className="outline-button small-button" onClick={onRetry}>Retry verification</button>}
          </div>
        )}
      </article>

      <article className="panel checkout-detail-card">
        <div className="table-heading"><div><h2>Transaction details</h2><span>Server-verified where available</span></div></div>
        <dl className="checkout-detail-grid">
          <DetailItem label="Merchant" value={merchant} />
          <DetailItem label="Product" value={productTitle} />
          <DetailItem label="Amount" value={formatAmount(amount, currency)} />
          <DetailItem label="Risk" value={riskScore == null && !riskLevel ? '' : `${riskScore ?? 'n/a'}/100 · ${riskLevel || 'n/a'}`} />
          <DetailItem label="PayShield decision" value={decision} tone={decision.toLowerCase()} />
          <DetailItem label="Policy outcome" value={policyOutcome} />
          <DetailItem label="PayPal order" value={redact(capture?.order_id || receipt?.order_id || orderId)} />
          <DetailItem label="Capture reference" value={redact(capture?.capture?.id || receipt?.capture_id)} />
          <DetailItem
            label="Evidence status"
            value={evidenceStatus ? `${evidenceStatus}${evidenceSource ? ` · ${evidenceSource}` : ''}` : ''}
          />
          <DetailItem label="Recorded" value={formatDate(receipt?.updated_at || receipt?.created_at)} />
        </dl>
        {policyReason && <p className="checkout-policy-reason"><strong>Policy:</strong> {policyReason}</p>}
        {!receipt && !loading && (
          <p className="muted-text">No persisted receipt is available for this checkout yet.</p>
        )}
      </article>
    </section>
  )
}

export default CheckoutResult
