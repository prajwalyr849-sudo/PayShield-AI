const STATUS_META = {
  COMPLETED: { label: 'Completed', tone: 'allow' },
  PENDING: { label: 'Pending', tone: 'review' },
  REVIEW_REQUIRED: { label: 'Review required', tone: 'review' },
  FAILED: { label: 'Failed', tone: 'block' },
  CANCELLED: { label: 'Cancelled', tone: 'block' },
  BLOCKED: { label: 'Blocked', tone: 'block' },
  EXPIRED: { label: 'Expired', tone: 'block' },
  REFUNDED: { label: 'Refunded', tone: 'review' },
  PARTIALLY_REFUNDED: { label: 'Partially refunded', tone: 'review' },
}

const DECISION_TONE = { ALLOW: 'allow', REVIEW: 'review', BLOCK: 'block' }

function statusMeta(status) {
  const key = String(status || '').toUpperCase()
  return STATUS_META[key] || { label: key || 'Unknown', tone: 'review' }
}

function decisionTone(decision) {
  return DECISION_TONE[String(decision || '').toUpperCase()] || 'review'
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

function itemTitle(item) {
  return item?.name || item?.title || item?.description || 'Item'
}

function itemQuantity(item) {
  const quantity = Number(item?.quantity)
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 1
}

function itemUnitPrice(item) {
  const raw = item?.unit_price ?? item?.price ?? item?.unit_amount?.value
  const numeric = Number(raw)
  return Number.isFinite(numeric) ? numeric : null
}

function lineItems(receipt) {
  const payment = receipt?.snapshots?.payment
  if (payment && Array.isArray(payment.items) && payment.items.length) {
    return payment.items.filter(Boolean)
  }
  const product = receipt?.snapshots?.product
  if (product && (product.title || product.description)) {
    return [{
      name: product.title,
      description: product.description,
      sku: product.sku,
      quantity: product.quantity ?? receipt.quantity ?? 1,
      unit_price: product.price,
    }]
  }
  return []
}

function ReceiptItem({ item }) {
  const unit = itemUnitPrice(item)
  const quantity = itemQuantity(item)
  return (
    <div className="receipt-line">
      <div className="receipt-line-main">
        <strong>{itemTitle(item)}</strong>
        {item.sku && <span className="receipt-line-sku">SKU: {item.sku}</span>}
        {item.description && <span className="receipt-line-desc">{item.description}</span>}
      </div>
      <div className="receipt-line-qty">
        <span>{quantity} × {unit == null ? 'Not available' : formatAmount(unit, null)}</span>
        {unit != null && <strong>{formatAmount(unit * quantity, null)}</strong>}
      </div>
    </div>
  )
}

function Receipt({ receipt, heading = 'Payment receipt', compact = false }) {
  if (!receipt) return null

  const meta = statusMeta(receipt.status)
  const decision = String(receipt.decision || '').toUpperCase()
  const items = lineItems(receipt)
  const product = receipt.snapshots?.product || {}
  const risk = receipt.snapshots?.risk || {}
  const policy = receipt.snapshots?.policy || {}
  const ai = receipt.snapshots?.ai_assessment || receipt.snapshots?.ai || null
  const merchant = receipt.merchant_name || product.retailer || product.title || 'Merchant unavailable'
  const category = receipt.merchant_category || product.category || ''
  const riskScore = receipt.risk_score ?? risk.score
  const riskLevel = receipt.risk_level || risk.level
  const payment = receipt.snapshots?.payment || {}
  const capture = payment.capture || {}
  const verifiedAt = payment.verified_at || receipt.updated_at
  const captureStatus = payment.capture_status || (capture && capture.status)
  const orderStatus = payment.order_status
  const evidenceSource = product.source_domain || product.retailer || product.source_url || ''
  const evidenceRetrievedAt = product.price_retrieved_at || receipt.updated_at

  return (
    <article className={`receipt ${compact ? 'receipt-compact' : ''}`} aria-label={heading}>
      <header className="receipt-head">
        <div>
          <p className="overline">{heading}</p>
          <h3 className="receipt-id">{receipt.receipt_id || 'Receipt ID unavailable'}</h3>
        </div>
        <span className={`decision-badge ${meta.tone}`}>{meta.label}</span>
      </header>

      <div className="receipt-summary">
        <div className="receipt-summary-main">
          <strong className="receipt-merchant">{merchant}</strong>
          {category && <span className="receipt-category">{category}</span>}
        </div>
        <strong className="receipt-total">{formatAmount(receipt.amount, receipt.currency)}</strong>
      </div>

      <dl className="evidence-meta receipt-meta">
        <div className="evidence-meta-item">
          <dt>PayShield decision</dt>
          <dd><span className={`receipt-decision ${decisionTone(decision)}`}>{decision || 'Not available'}</span></dd>
        </div>
        <div className="evidence-meta-item">
          <dt>Risk</dt>
          <dd>{riskScore == null && !riskLevel ? 'Not available' : `${riskScore ?? 'n/a'}${riskLevel ? ` · ${riskLevel}` : ''}`}</dd>
        </div>
        <div className="evidence-meta-item">
          <dt>Recorded</dt>
          <dd>{formatDate(receipt.created_at || receipt.updated_at)}</dd>
        </div>
        {verifiedAt && (
          <div className="evidence-meta-item">
            <dt>PayPal verified</dt>
            <dd>{formatDate(verifiedAt)}</dd>
          </div>
        )}
      </dl>

      {items.length > 0 && (
        <section className="receipt-section" aria-label="Line items">
          <h4 className="section-title">Items</h4>
          <div className="receipt-lines">
            {items.map((item, index) => (
              <ReceiptItem key={`${itemTitle(item)}-${index}`} item={item} />
            ))}
          </div>
        </section>
      )}

      <section className="receipt-section receipt-identifiers" aria-label="Identifiers">
        <h4 className="section-title">References</h4>
        <dl className="evidence-meta">
          <div className="evidence-meta-item"><dt>Order</dt><dd>{receipt.order_id || 'Not available'}</dd></div>
          <div className="evidence-meta-item"><dt>Capture</dt><dd>{receipt.capture_id || 'Not available'}</dd></div>
          <div className="evidence-meta-item"><dt>Transaction</dt><dd>{receipt.transaction_id || 'Not available'}</dd></div>
          {captureStatus && (
            <div className="evidence-meta-item"><dt>Capture status</dt><dd>{String(captureStatus)}</dd></div>
          )}
          {orderStatus && (
            <div className="evidence-meta-item"><dt>Order status</dt><dd>{String(orderStatus)}</dd></div>
          )}
        </dl>
      </section>

      {evidenceSource && (
        <section className="receipt-section" aria-label="Evidence">
          <h4 className="section-title">Product evidence</h4>
          <dl className="evidence-meta">
            <div className="evidence-meta-item"><dt>Source</dt><dd>{evidenceSource}</dd></div>
            {evidenceRetrievedAt && (
              <div className="evidence-meta-item"><dt>Retrieved</dt><dd>{formatDate(evidenceRetrievedAt)}</dd></div>
            )}
          </dl>
        </section>
      )}

      {receipt.reason && (
        <p className={`receipt-reason ${meta.tone}`}>{receipt.reason}</p>
      )}

      <section className="receipt-section receipt-decision-section" aria-label="PayShield authorization">
        <div className="receipt-section-head">
          <h4 className="section-title">PayShield authorization</h4>
          <span className="receipt-origin">Authoritative</span>
        </div>
        <p className={`receipt-decision-line ${decisionTone(decision)}`}>
          Decision: <strong>{decision || 'Not available'}</strong>
          {receipt.payment_status_raw ? ` · PayPal: ${receipt.payment_status_raw}` : ''}
        </p>
        {receipt.snapshots?.decision?.explanation && (
          <p className="receipt-explanation">{receipt.snapshots.decision.explanation}</p>
        )}
        {(policy.reasons?.length > 0 || policy.reason || policy.decision) && (
          <div className="receipt-policy">
            <h5 className="section-title">Policy evaluation (stage result)</h5>
            {policy.decision && (
              <p className="receipt-policy-decision">
                Policy outcome at evaluation time: <strong>{String(policy.decision).toUpperCase()}</strong>
              </p>
            )}
            {policy.reason && <p>{policy.reason}</p>}
            {Array.isArray(policy.reasons) && policy.reasons.length > 0 && (
              <ul className="decision-reasons">
                {policy.reasons.filter(Boolean).map((entry, index) => <li key={index}>{typeof entry === 'string' ? entry : entry?.message || JSON.stringify(entry)}</li>)}
              </ul>
            )}
            {policy.decision && decision && String(policy.decision).toUpperCase() !== decision && (
              <p className="receipt-policy-caveat">
                The policy stage above is not the basis for the final decision. The authoritative
                outcome is <strong>{decision}</strong>: {receipt.reason || 'see the recorded reason above'}.
              </p>
            )}
          </div>
        )}
      </section>

      {ai && (
        <section className="receipt-section receipt-ai" aria-label="AI advisory">
          <div className="ai-assessment-head">
            <h4 className="section-title">AI assessment</h4>
            <span className="ai-advisory-tag">Advisory only</span>
            {ai.ai_score != null && <span className="ai-score">{ai.ai_score}</span>}
          </div>
          {(ai.summary || ai.rationale) && <p className="ai-rationale">{ai.summary || ai.rationale}</p>}
          <p className="ai-disclaimer">The AI assessment is advisory and never authorizes or blocks payment on its own.</p>
        </section>
      )}
    </article>
  )
}

export default Receipt
