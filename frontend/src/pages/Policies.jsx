import { useCallback, useEffect, useState } from 'react'
import PageHeader from '../components/PageHeader'
import { getSecurityControls } from '../services/api'

function controlTone(value) {
  const v = String(value || '').toLowerCase()
  if (v.includes('on') || v === 'always on') return 'allow'
  if (v.includes('advisory')) return 'review'
  return 'review'
}

function PolicyControl({ control }) {
  const tone = controlTone(control.value)
  return (
    <article className="policy-control">
      <div className="policy-control-head">
        <div>
          <p className="overline">{control.label}</p>
          <strong>{control.key}</strong>
        </div>
        <span className={`control-badge ${tone}`}>
          {control.enabled === false ? 'Disabled' : control.value || 'Enabled'}
        </span>
      </div>
      <p className="policy-control-description">{control.description}</p>
    </article>
  )
}

function Policies() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const runFetch = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getSecurityControls()
      setData(response)
    } catch (requestError) {
      setError(requestError.message || 'Unable to load security controls.')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    runFetch()
  }, [runFetch])

  const load = () => {
    setLoading(true)
    setError('')
    runFetch()
  }

  const preferences = data?.preferences || {}
  const securityControls = data?.security_controls || []
  const editableFields = data?.editable_fields || []

  return (
    <>
      <PageHeader
        eyebrow="Security controls"
        title="Policies"
        description="Deterministic authorization rules enforced by PayShield. These are read-only and cannot be overridden from the UI."
        action={(
          <button type="button" className="outline-button small-button" onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        )}
      />
      {error && <p className="api-error" role="alert">{error}</p>}
      <section className="page-panel panel" aria-label="Policy enforcement controls">
        <div className="table-heading">
          <div>
            <h2>Enforced policy controls</h2>
            <span>{securityControls.length} rules configured</span>
          </div>
        </div>

        {loading && securityControls.length === 0 ? (
          <p className="muted-text">Loading security controls…</p>
        ) : securityControls.length === 0 ? (
          <p className="muted-text">No policy controls are currently configured.</p>
        ) : (
          <div className="policy-grid">
            {securityControls.map((control) => (
              <PolicyControl key={control.key} control={control} />
            ))}
          </div>
        )}
      </section>

      <section className="page-panel panel" aria-label="User preferences">
        <div className="table-heading">
          <div>
            <h2>User preferences</h2>
            <span>{editableFields.length} editable fields</span>
          </div>
        </div>
        {loading && Object.keys(preferences).length === 0 ? (
          <p className="muted-text">Loading preferences…</p>
        ) : Object.keys(preferences).length === 0 ? (
          <p className="muted-text">No preferences configured.</p>
        ) : (
          <dl className="preferences-list">
            {Object.entries(preferences).map(([key, value]) => (
              <div className="preference-item" key={key}>
                <dt>{key}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
        <p className="preferences-note">
          Preferences are user-configurable display and notification settings.
          Mandatory risk, policy and payment-guard enforcement (shown above) is
          served read-only and can never be changed from here.
        </p>
      </section>
    </>
  )
}

export default Policies
