import { useEffect, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { capturePayPalOrder, createPayPalOrder } from '../services/api'

function Checkout() {
  const [form, setForm] = useState({
    amount: '25.00',
    currency: 'USD',
    category: 'services',
    merchant_name: 'Sandbox merchant',
    user_id: 'sandbox-user',
  })
  const [returnOrderId] = useState(
    () => new URLSearchParams(window.location.search).get('token'),
  )
  const [cancelled] = useState(
    () => new URLSearchParams(window.location.search).get('cancelled'),
  )
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (returnOrderId) {
      capturePayPalOrder(returnOrderId)
        .then(setResult)
        .catch((requestError) => setError(requestError.message))
        .finally(() => setLoading(false))
    }
  }, [cancelled, returnOrderId])

  const displayResult = result || (cancelled ? {
    decision: 'BLOCK',
    payment_status: 'CANCELLED',
    reason: 'Buyer cancelled PayPal approval.',
  } : null)

  const update = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }))
  }

  const startCheckout = async (event) => {
    event.preventDefault()
    setError('')
    setResult(null)
    setLoading(true)
    try {
      const order = await createPayPalOrder(form)
      window.location.assign(order.approval_url)
    } catch (requestError) {
      setError(requestError.message)
      setLoading(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Sandbox checkout"
        title="PayPal checkout"
        description="Create a protected Sandbox order, approve it in PayPal, and let PayShield evaluate before capture."
      />
      <section className="checkout-layout">
        <form className="panel checkout-form" onSubmit={startCheckout}>
          <div className="card-heading">
            <div><p className="overline">Payment intent</p><h2>Start Sandbox checkout</h2></div>
            <span className="demo-label">SANDBOX</span>
          </div>
          <label>Amount<input value={form.amount} onChange={update('amount')} inputMode="decimal" required /></label>
          <label>Currency<input value={form.currency} onChange={update('currency')} maxLength={3} required /></label>
          <label>Category<input value={form.category} onChange={update('category')} required /></label>
          <label>Merchant<input value={form.merchant_name} onChange={update('merchant_name')} required /></label>
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? 'Waiting for checkout…' : 'Continue to PayPal'}
          </button>
          {error && <p className="api-error">{error}</p>}
        </form>
        {displayResult && (
          <section className="panel checkout-result">
            <p className="overline">Final payment state</p>
            <h2>{displayResult.payment_status || 'NOT_CAPTURED'}</h2>
            <strong className={`checkout-decision ${String(displayResult.decision).toLowerCase()}`}>
              {displayResult.decision || 'BLOCK'}
            </strong>
            <p>{displayResult.reason}</p>
            {displayResult.risk_assessment && (
              <p>Risk score: {displayResult.risk_assessment.score ?? 'n/a'} · Level: {displayResult.risk_assessment.level ?? 'n/a'}</p>
            )}
          </section>
        )}
      </section>
    </>
  )
}

export default Checkout
