import { useEffect, useState } from 'react'
import PageHeader from '../components/PageHeader'
import Receipt from '../components/Receipt'
import CheckoutResult from '../components/CheckoutResult'
import { useAuth } from '../context/AuthContext'
import { capturePayPalOrder, createPayPalOrder, getReceipt, getReceiptByOrderId } from '../services/api'

function Checkout() {
  const { user } = useAuth() || {}
  const [returnOrderId] = useState(
    () => new URLSearchParams(window.location.search).get('token'),
  )
  const [cancelled] = useState(
    () => new URLSearchParams(window.location.search).get('cancelled'),
  )
  const [form, setForm] = useState({
    amount: '25.00',
    currency: 'USD',
    category: 'services',
    merchant_name: 'Sandbox merchant',
    user_id: user?.user_id || 'sandbox-user',
  })
  const [result, setResult] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(() => Boolean(new URLSearchParams(window.location.search).get('token')))
  const isReturn = Boolean(returnOrderId)

  useEffect(() => {
    if (!returnOrderId) return
    let active = true
    const loadReceipt = async (captureResult) => {
      try {
        if (captureResult?.receipt_id) {
          const fetched = await getReceipt(captureResult.receipt_id)
          if (active) setReceipt(fetched)
          return
        }
        const fetched = await getReceiptByOrderId(returnOrderId)
        if (active) setReceipt(fetched)
      } catch {
        if (active) setReceipt(null)
      }
    }
    capturePayPalOrder(returnOrderId)
      .then((captureResult) => {
        if (!active) return
        setResult(captureResult)
        if (captureResult?.payment_status === 'PENDING') {
          setTimeout(() => {
            if (!active) return
            capturePayPalOrder(returnOrderId).then((retried) => {
              if (!active) return
              setResult(retried)
              loadReceipt(retried)
            }).catch(() => {})
          }, 2000)
        }
        return loadReceipt(captureResult)
      })
      .catch((requestError) => { if (active) setError(requestError.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [cancelled, returnOrderId])

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
        {!isReturn && (
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
        )}
        {(isReturn || cancelled) && (
          <CheckoutResult
            capture={result}
            receipt={receipt}
            cancelled={Boolean(cancelled)}
            loading={loading}
            error={error}
            orderId={returnOrderId}
            onRetry={() => window.location.reload()}
          />
        )}
        {isReturn && receipt && <Receipt receipt={receipt} />}
      </section>
    </>
  )
}

export default Checkout
