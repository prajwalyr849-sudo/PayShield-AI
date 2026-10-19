import { useEffect, useState } from 'react'
import Icon from '../Icon'
import {
  approveGuardBuyReview,
  guardBuy,
  guardBuyCheckout,
  getLiveRating,
  rateAssistantProduct,
} from '../../services/api'

const ratingCache = new Map()

function decisionLabel(decision) {
  if (decision === 'ALLOW') return 'ALLOW'
  if (decision === 'REVIEW') return 'REVIEW'
  return 'BLOCK'
}

const PRICE_METHOD_LABELS = {
  json_ld: 'structured data (JSON-LD)',
  meta: 'price metadata',
  microdata: 'microdata',
  labelled_text: 'labelled page text',
  snippet: 'search snippet',
}

const PRICE_TYPE_LABELS = {
  selling_price: 'current price',
  sale_price: 'sale price',
  list_price: 'list/MRP price',
  aggregate: 'price range',
}

const IDENTITY_MATCH_LABELS = {
  MATCH: 'Matches request',
  PARTIAL_MATCH: 'Partial match',
  MISMATCH: 'Different product',
  UNKNOWN: 'Not determined',
}

const RETRIEVAL_STATUS_LABELS = {
  retrieved: 'source page retrieved',
  http_error: 'source page not found or errored',
  blocked: 'source page blocked retrieval',
  timeout: 'source page timed out',
  network_error: 'source page unreachable',
  non_html: 'source page was not a product page',
  unfetchable: 'source page cannot be fetched',
}

const PROVIDER_LABELS = {
  channel3: 'Channel3',
  'endless-search': 'Live Search',
}

const EVIDENCE_STATUS_LABELS = {
  VERIFIED: 'Verified offer',
  CANDIDATE: 'Candidate evidence',
  CONFLICT: 'Conflicting offers',
  UNAVAILABLE: 'No usable offer',
}

const EVIDENCE_TONE = {
  VERIFIED: 'green',
  CANDIDATE: 'amber',
  CONFLICT: 'red',
  UNAVAILABLE: 'red',
}

function formatPrice(value, currency) {
  if (value == null) return ''
  return `${Number(value).toFixed(2)} ${currency || 'USD'}`
}

function formatFreshness(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const mins = Math.round((now - date) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} hr ago`
  return `${Math.round(hours / 24)} days ago`
}

function AiAssessment({ rating, loading, error, onRetry }) {
  const head = (
    <div className="pr-assessment-head">
      <h5 className="pr-section-title">AI assessment</h5>
      <span className="pr-advisory-tag">Advisory</span>
      {rating?.available && rating.ai_score != null && <span className="pr-ai-score">{rating.ai_score}/100</span>}
    </div>
  )

  if (loading) {
    return (
      <section className="pr-section pr-ai-assessment" aria-label="AI assessment">
        {head}
        <p className="pr-muted">Assessing evidence…</p>
      </section>
    )
  }
  if (error) {
    return (
      <section className="pr-section pr-ai-assessment" aria-label="AI assessment">
        {head}
        <p className="pr-muted">{error}</p>
        <button type="button" className="pr-outline-button pr-small-button" onClick={onRetry}>Retry assessment</button>
      </section>
    )
  }
  if (!rating) return null
  return (
    <section className="pr-section pr-ai-assessment" aria-label="AI assessment">
      {head}
      {!rating.available && (
        <p className="pr-muted">{rating.explanation || 'AI assessment is unavailable for this product.'}</p>
      )}
      {rating.available && rating.explanation && <p className="pr-rationale">{rating.explanation}</p>}
      {rating.available && rating.strengths?.length > 0 && (
        <p className="pr-ai-line"><strong>Strengths:</strong> {rating.strengths.join('; ')}</p>
      )}
      {rating.available && rating.concerns?.length > 0 && (
        <p className="pr-ai-line"><strong>Concerns:</strong> {rating.concerns.join('; ')}</p>
      )}
      {rating.available && rating.missing_information?.length > 0 && (
        <p className="pr-ai-line"><strong>Missing information:</strong> {rating.missing_information.join('; ')}</p>
      )}
      <p className="pr-disclaimer">
        {rating.disclaimer
          || 'AI assessment is advisory only. It never authorizes payment and is separate from the PayShield decision below.'}
      </p>
    </section>
  )
}

function DecisionPanel({ decision, reviewed, reviewLoading, checkoutLoading, onApprove, onCheckout }) {
  const level = (decision.decision || 'BLOCK').toLowerCase()
  const priceState = decision.price_verified
    ? `verified from source${decision.price != null ? ` · ${formatPrice(decision.price, decision.price_currency || decision.currency)}` : ''}`
    : 'not verified by the source'
  const priceProvenance = decision.price_verified
    ? [PRICE_TYPE_LABELS[decision.price_type] || decision.price_type, PRICE_METHOD_LABELS[decision.price_method] || decision.price_method]
      .filter(Boolean)
      .join(' · ')
    : decision.price_unverified_reason
  const availabilityState = decision.availability && decision.availability !== 'Unknown'
    ? decision.availability
    : 'unknown'

  return (
    <div className={`pr-decision decision-${level}`} role="status" aria-live="polite">
      <div className="pr-decision-head">
        <span className={`pr-decision-badge ${level}`}>{decisionLabel(decision.decision)}</span>
        <span className="pr-decision-origin">PayShield decision</span>
        {decision.risk_score != null && (
          <span className="pr-muted pr-decision-risk">Risk {decision.risk_score}/100 · {decision.risk_level}</span>
        )}
      </div>

      <p className="pr-decision-reason">{decision.reason}</p>

      {decision.reasons?.length > 0 && (
        <div className="pr-decision-reasons-block">
          <h6 className="pr-decision-subtitle">Why this decision</h6>
          <ul className="pr-decision-reasons">
            {decision.reasons.filter(Boolean).map((reason, index) => <li key={index}>{reason}</li>)}
          </ul>
        </div>
      )}

      <p className="pr-decision-evidence">
        <span className="pr-evidence-label">Server evidence at decision time:</span>{' '}
        price <strong className={decision.price_verified ? '' : 'pr-unverified'}>{priceState}</strong>
        {decision.price_verified && priceProvenance && (
          <span className="pr-evidence-provenance"> ({priceProvenance})</span>
        )}
        {(!decision.price_verified && decision.price_unverified_reason) && (
          <span className="pr-evidence-provenance"> · {decision.price_unverified_reason}</span>
        )}
        {' · '}availability <strong className={availabilityState === 'unknown' ? 'pr-unverified' : ''}>{availabilityState}</strong>
        {decision.identity_match && decision.identity_match !== 'UNKNOWN' && (
          <span>
            {' · '}identity{' '}
            <strong className={decision.identity_match !== 'MATCH' ? 'pr-unverified' : ''}>
              {IDENTITY_MATCH_LABELS[decision.identity_match] || decision.identity_match}
            </strong>
          </span>
        )}
        {' · '}source {decision.source_domain || decision.retailer || 'unknown'}
        {decision.provider && (
          <span>
            {' · '}provider{' '}
            <strong>{PROVIDER_LABELS[decision.provider] || decision.provider}</strong>
            {decision.is_fallback ? ' (fallback)' : ''}
          </span>
        )}
        {decision.evidence_status && (
          <span>
            {' · '}evidence{' '}
            <strong className={decision.evidence_status !== 'VERIFIED' ? 'pr-unverified' : ''}>
              {EVIDENCE_STATUS_LABELS[decision.evidence_status] || decision.evidence_status}
            </strong>
          </span>
        )}
        {decision.condition && decision.condition !== 'unknown' && (
          <span>
            {' · '}condition{' '}
            <strong className={decision.condition !== 'new' ? 'pr-unverified' : ''}>{decision.condition}</strong>
          </span>
        )}
        {decision.decision === 'ALLOW' && (
          <span className="pr-checkout-note">
            {' · '}Checkout amount: <strong>{formatPrice(decision.amount, decision.currency)}</strong> {decision.checkout_amount_verified ? '(verified from stored evidence)' : '(revalidation pending)'}
          </span>
        )}
      </p>

      {decision.decision === 'REVIEW' && (
        <div className="pr-decision-actions">
          <p className="pr-review-note">
            This REVIEW is a PayShield decision, separate from the advisory AI assessment above.
            Approving runs a fresh server-side re-evaluation against the stored evidence and current
            policy. Approval does <strong>not</strong> guarantee authorization to pay — checkout stays
            blocked unless PayShield re-evaluates to ALLOW.
          </p>
          <button type="button" className="pr-primary-button" onClick={onApprove} disabled={reviewLoading}>
            {reviewLoading ? 'Re-evaluating…' : 'Approve review & re-evaluate'}
          </button>
        </div>
      )}

      {decision.decision === 'ALLOW' && (
        <div className="pr-decision-actions">
          <p className="pr-review-note">
            PayShield authorized this purchase on the stored evidence. Continue to the PayPal Sandbox
            to approve the payment.
          </p>
          <button type="button" className="pr-primary-button" onClick={onCheckout} disabled={checkoutLoading}>
            {checkoutLoading ? 'Opening PayPal Sandbox…' : 'Continue to PayPal Sandbox'}
          </button>
        </div>
      )}

      {decision.decision === 'BLOCK' && (
        <p className="pr-review-note pr-review-note-blocked">
          Checkout is refused. PayShield will not create or capture a payment for this decision.
        </p>
      )}

      {reviewed && (
        <div className={`pr-review-result ${level}`}>
          <strong>Re-evaluation result: {decisionLabel(decision.decision)}</strong>
          <span>
            {decision.decision === 'ALLOW'
              ? 'Checkout is now available.'
              : decision.decision === 'REVIEW'
                ? 'Checkout remains blocked pending the required review.'
                : 'Checkout is refused.'}
          </span>
        </div>
      )}
    </div>
  )
}

function ProductResultCard({ result, query }) {
  const reference = result.product_reference || result.id
  const [rating, setRating] = useState(() => ratingCache.get(reference) || null)
  const [ratingLoading, setRatingLoading] = useState(false)
  const [ratingError, setRatingError] = useState('')
  const [liveRating, setLiveRating] = useState(null)
  const [liveRatingLoading, setLiveRatingLoading] = useState(false)
  const [liveRatingError, setLiveRatingError] = useState('')
  const [decision, setDecision] = useState(null)
  const [guardLoading, setGuardLoading] = useState(false)
  const [reviewLoading, setReviewLoading] = useState(false)
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [reviewed, setReviewed] = useState(false)
  const [error, setError] = useState('')
  const [lastAction, setLastAction] = useState('guard')
  const [expanded, setExpanded] = useState(false)

  const priceVerified = Boolean(result.price_verified && result.price != null)
  const availability = result.availability && result.availability !== 'Unknown'
    ? result.availability
    : 'Unknown'
  const sourceDomain = result.source_domain || result.retailer || 'Unknown'
  const identityMatch = (result.identity_match || 'UNKNOWN').toUpperCase()
  const identityReasons = Array.isArray(result.identity_reasons) ? result.identity_reasons.filter(Boolean) : []
  const showIdentity = Boolean(result.identity_match) && identityMatch !== 'UNKNOWN'
  const retrievalStatus = (result.retrieval_status || '').toLowerCase()
  const showRetrieval = Boolean(retrievalStatus) && retrievalStatus !== 'retrieved'
  const providerLabel = PROVIDER_LABELS[result.provider] || result.provider || ''
  const evidenceStatus = (result.evidence_status || '').toUpperCase()
  const evidenceStatusLabel = EVIDENCE_STATUS_LABELS[evidenceStatus] || ''
  const sellerLabel = result.seller || result.retailer || result.source_domain || 'Unknown'
  const condition = (result.condition && result.condition !== 'unknown') ? result.condition : ''
  const variant = result.variant || ''
  const offerCount = Number(result.offer_count) || 0
  const conflicts = Array.isArray(result.conflicts) ? result.conflicts.filter(Boolean) : []

  const loadRating = async () => {
    if (!reference || ratingLoading) return
    setRatingLoading(true)
    setRatingError('')
    try {
      const data = await rateAssistantProduct({ product_reference: reference, query })
      ratingCache.set(reference, data)
      setRating(data)
    } catch (requestError) {
      setRatingError(requestError.message || 'AI assessment failed.')
    } finally {
      setRatingLoading(false)
    }
  }

  const loadLiveRating = async () => {
    if (!reference || liveRatingLoading) return
    setLiveRatingLoading(true)
    setLiveRatingError('')
    try {
      const data = await getLiveRating({
        productReference: reference,
        sourceUrl: result.source_url || '',
      })
      setLiveRating(data)
    } catch (requestError) {
      setLiveRatingError(requestError.message || 'Live rating unavailable.')
    } finally {
      setLiveRatingLoading(false)
    }
  }

  useEffect(() => {
    if (expanded && reference && !ratingCache.has(reference)) {
      loadRating()
    }
    if (expanded && reference && result.source_url) {
      loadLiveRating()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expanded, reference])

  const handleGuardBuy = async () => {
    if (guardLoading) return
    setLastAction('guard')
    setGuardLoading(true)
    setError('')
    setDecision(null)
    setReviewed(false)
    try {
      const data = await guardBuy({ product_reference: reference, quantity: 1 })
      setDecision(data)
    } catch (requestError) {
      setError(requestError.message || 'Guard Buy decision failed.')
    } finally {
      setGuardLoading(false)
    }
  }

  const handleApproveReview = async () => {
    if (reviewLoading || !decision?.decision_reference) return
    setLastAction('review')
    setReviewLoading(true)
    setError('')
    try {
      const data = await approveGuardBuyReview({
        decision_reference: decision.decision_reference,
        approved: true,
      })
      setDecision(data)
      setReviewed(true)
    } catch (requestError) {
      setError(requestError.message || 'Review approval failed.')
    } finally {
      setReviewLoading(false)
    }
  }

  const handleCheckout = async () => {
    if (checkoutLoading || !decision?.decision_reference) return
    setLastAction('checkout')
    setCheckoutLoading(true)
    setError('')
    try {
      const data = await guardBuyCheckout({ decision_reference: decision.decision_reference })
      if (data.approval_url) {
        window.location.assign(data.approval_url)
      } else {
        setError(data.reason || 'PayShield did not open a Sandbox approval page.')
      }
    } catch (requestError) {
      setError(requestError.message || 'Sandbox checkout failed.')
    } finally {
      setCheckoutLoading(false)
    }
  }

  const handleRetry = () => {
    setError('')
    if (lastAction === 'review') handleApproveReview()
    else if (lastAction === 'checkout') handleCheckout()
    else handleGuardBuy()
  }

  return (
    <article className="pr-card">
      <div className="pr-media">
        {result.image_url ? (
          <img
            src={result.image_url}
            alt={result.title}
            className="pr-product-image"
            onError={(event) => { event.currentTarget.hidden = true }}
          />
        ) : (
          <div className="pr-product-placeholder" aria-label="Product image unavailable">
            <Icon name="card" size={30} />
          </div>
        )}
      </div>

      <div className="pr-body">
        <header className="pr-head">
          <div className="pr-head-lines">
            <div className="pr-source-row">
              <span className="pr-source-label">{providerLabel ? providerLabel.toUpperCase() : 'SOURCE EVIDENCE'}</span>
              {result.is_fallback && <span className="pr-fallback-tag">fallback</span>}
              <span className={`pr-evidence-badge tone-${EVIDENCE_TONE[evidenceStatus] || 'red'}`}>{evidenceStatusLabel}</span>
            </div>
            <h4 className="pr-title">{result.title}</h4>
            {(variant || condition) && (
              <p className="pr-variant">
                {variant && <span>{variant}</span>}
                {variant && condition && <span> · </span>}
                {condition && <span>{condition.charAt(0).toUpperCase() + condition.slice(1)}</span>}
              </p>
            )}
          </div>
          <div className="pr-price-col">
            <div className="pr-price">
              {priceVerified ? formatPrice(result.price, result.price_currency || result.currency) : 'Not verified'}
              <span className="pr-price-currency">{result.currency || 'USD'}</span>
            </div>
            {priceVerified && result.price_retrieved_at && (
              <span className="pr-freshness">Retrieved {formatFreshness(result.price_retrieved_at)}</span>
            )}
          </div>
        </header>

        <div className="pr-meta">
          <div className="pr-meta-item">
            <span className="pr-meta-label">Merchant</span>
            <span className="pr-meta-value">{sellerLabel}</span>
          </div>
          {result.source_url && (
            <a className="pr-source-link" href={result.source_url} target="_blank" rel="noreferrer">
              <Icon name="link" size={13} /> Open source
            </a>
          )}
        </div>

        <div className="pr-actions">
          <button
            type="button"
            className="pr-outline-button pr-small-button"
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? 'Collapse details' : 'Expand details'}
          </button>
          <button
            type="button"
            className="pr-primary-button pr-review-btn"
            onClick={handleGuardBuy}
            disabled={guardLoading}
          >
            {guardLoading ? 'Reviewing…' : 'Review purchase'}
          </button>
        </div>

        {expanded && (
          <>
          <section className="pr-section pr-evidence-section" aria-label="Source evidence">
            <div className="pr-section-head">
              <h5 className="pr-section-title">Source evidence</h5>
              {result.source_url && (
                <a className="pr-section-link" href={result.source_url} target="_blank" rel="noreferrer">
                  Open original source →
                </a>
              )}
            </div>
            {result.snippet
              ? <p className="pr-snippet">{result.snippet}</p>
              : <p className="pr-snippet pr-muted">No evidence snippet was provided by the source.</p>}
            <dl className="pr-evidence-meta">
              <div className="pr-meta-item">
                <dt>Price</dt>
                <dd className={priceVerified ? '' : 'pr-unverified'}>
                  {priceVerified ? formatPrice(result.price, result.price_currency || result.currency) : 'Not verified'}
                </dd>
              </div>
              <div className="pr-meta-item">
                <dt>Availability</dt>
                <dd className={availability === 'Unknown' ? 'pr-unverified' : ''}>{availability}</dd>
              </div>
              <div className="pr-meta-item">
                <dt>Source</dt>
                <dd>{sourceDomain}</dd>
              </div>
              {sellerLabel && sellerLabel !== sourceDomain && (
                <div className="pr-meta-item">
                  <dt>Seller</dt>
                  <dd>{sellerLabel}</dd>
                </div>
              )}
              {condition && (
                <div className="pr-meta-item">
                  <dt>Condition</dt>
                  <dd className={condition !== 'new' ? 'pr-unverified' : ''}>{condition}</dd>
                </div>
              )}
              {variant && (
                <div className="pr-meta-item">
                  <dt>Variant</dt>
                  <dd>{variant}</dd>
                </div>
              )}
              {offerCount > 1 && (
                <div className="pr-meta-item">
                  <dt>Offers</dt>
                  <dd>{offerCount} merchant offers</dd>
                </div>
              )}
              {showIdentity && (
                <div className="pr-meta-item">
                  <dt>Identity match</dt>
                  <dd className={identityMatch !== 'MATCH' ? 'pr-unverified' : ''}>
                    {IDENTITY_MATCH_LABELS[identityMatch] || identityMatch}
                  </dd>
                </div>
              )}
            </dl>
            {showIdentity && identityMatch !== 'MATCH' && identityReasons.length > 0 && (
              <p className="pr-provenance pr-unverified">{identityReasons.join('; ')}</p>
            )}
            {showRetrieval && (
              <p className="pr-provenance pr-unverified">
                {RETRIEVAL_STATUS_LABELS[retrievalStatus] || `source page status: ${retrievalStatus}`}
                {result.retrieval_reason ? ` — ${result.retrieval_reason}` : ''}
              </p>
            )}
            {conflicts.length > 0 && (
              <p className="pr-provenance pr-unverified">Conflicting offers: {conflicts.join('; ')}</p>
            )}
            {result.is_fallback && (
              <p className="pr-provenance pr-unverified">
                These results came from the fallback provider, not the primary structured provider. Treat them as candidates to verify.
              </p>
            )}
            {priceVerified && (
              <p className="pr-provenance">
                {[`Verified from ${sourceDomain || 'source'} via ${PRICE_METHOD_LABELS[result.price_method] || result.price_method}`, result.price_type ? `(${PRICE_TYPE_LABELS[result.price_type] || result.price_type})` : '', result.price_source_url && result.price_source_url !== result.source_url ? 'on source page' : ''].filter(Boolean).join(' ')}
                {result.price_retrieved_at && (
                  <span>
                    {' · '}retrieved {new Date(result.price_retrieved_at).toLocaleString()}
                  </span>
                )}
              </p>
            )}
            {!priceVerified && result.price_unverified_reason && (
              <p className="pr-provenance pr-unverified">{result.price_unverified_reason}</p>
            )}
            {result.search_timestamp && (
              <time className="pr-time" dateTime={result.search_timestamp}>
                Retrieved {new Date(result.search_timestamp).toLocaleString()}
              </time>
            )}
          </section>

          {liveRatingLoading && (
            <section className="pr-section pr-ai-assessment" aria-label="Live rating">
              <div className="pr-assessment-head">
                <h5 className="pr-section-title">Live buyer rating</h5>
                <span className="pr-advisory-tag">Advisory</span>
              </div>
              <p className="pr-muted">Retrieving live rating…</p>
            </section>
          )}
          {!liveRatingLoading && liveRating && (
            <section className="pr-section pr-ai-assessment" aria-label="Live rating">
              <div className="pr-assessment-head">
                <h5 className="pr-section-title">Live buyer rating</h5>
                <span className="pr-advisory-tag">Advisory</span>
                {liveRating.available && liveRating.rating != null && (
                  <span className="pr-ai-score">{liveRating.rating}/5</span>
                )}
                {liveRating.review_count != null && (
                  <span className="pr-muted">· {liveRating.review_count} reviews</span>
                )}
              </div>
              {!liveRating.available && (
                <p className="pr-muted">
                  {liveRating.reason || 'Live rating is not available for this product.'}
                </p>
              )}
              {liveRating.available && liveRating.provider && (
                <p className="pr-muted">
                  Source: {liveRating.provider}{liveRating.retrieved_at ? ` · retrieved ${new Date(liveRating.retrieved_at).toLocaleString()}` : ''}
                </p>
              )}
              {liveRating.cache_hit && (
                <p className="pr-muted">From cache (last checked {liveRating.retrieved_at ? new Date(liveRating.retrieved_at).toLocaleString() : 'unknown'})</p>
              )}
              <p className="pr-disclaimer">
                {liveRating.disclaimer || 'Live buyer rating is advisory consumer-sentiment evidence. It never sets PayShield ALLOW, REVIEW, or BLOCK decisions by itself.'}
              </p>
            </section>
          )}
          {!liveRatingLoading && liveRatingError && (
            <section className="pr-section pr-ai-assessment" aria-label="Live rating">
              <div className="pr-assessment-head">
                <h5 className="pr-section-title">Live buyer rating</h5>
                <span className="pr-advisory-tag">Advisory</span>
              </div>
              <p className="pr-muted">{liveRatingError}</p>
            </section>
          )}

          <AiAssessment
            rating={rating}
            loading={ratingLoading}
            error={ratingError}
            onRetry={loadRating}
          />

          <section className="pr-section pr-guard-section" aria-label="PayShield authorization">
            <div className="pr-section-head">
              <h5 className="pr-section-title">PayShield authorization</h5>
              <span className="pr-section-hint">Deterministic risk, policy &amp; decision engines</span>
            </div>

            {!decision && !guardLoading && !error && (
              <div className="pr-guard-actions">
                <button
                  type="button"
                  className="pr-primary-button pr-guard-button"
                  onClick={handleGuardBuy}
                  disabled={guardLoading}
                >
                  Guard Buy
                </button>
                <p className="pr-guard-hint">
                  Runs PayShield on the server-side stored evidence. The AI assessment never authorizes payment.
                </p>
              </div>
            )}

            {guardLoading && <p className="pr-muted pr-guard-loading">Running PayShield governance checks…</p>}

            {error && (
              <div className="pr-api-error pr-guard-error" role="alert">
                <strong>Guard Buy could not complete</strong>
                <p>{error}</p>
                <button type="button" className="pr-outline-button pr-small-button" onClick={handleRetry}>Retry</button>
              </div>
            )}

            {decision && (
              <DecisionPanel
                decision={decision}
                reviewed={reviewed}
                reviewLoading={reviewLoading}
                checkoutLoading={checkoutLoading}
                onApprove={handleApproveReview}
                onCheckout={handleCheckout}
              />
            )}
          </section>
          </>
          )}
      </div>
    </article>
  )
}

export default ProductResultCard
