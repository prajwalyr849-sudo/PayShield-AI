import { useCallback, useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import Icon from '../components/Icon'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'
import { getHealth, getSettingsPreferences, updateSettingsPreferences } from '../services/api'

function Toggle({ checked, onChange, id }) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      className={`toggle ${checked ? 'on' : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span />
    </button>
  )
}

function SettingRow({ title, description, value, onChange, id, disabled }) {
  return (
    <div className="setting-row">
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      <Toggle id={id} checked={value} onChange={onChange} disabled={disabled} />
    </div>
  )
}

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR']

const SECTIONS = [
  { key: 'identity', label: 'Profile & Identity' },
  { key: 'risk', label: 'Risk preferences' },
  { key: 'notifications', label: 'Notification preferences' },
  { key: 'system', label: 'System information' },
]

function Settings() {
  const { user, linkOAuth, unlinkIdentity, logout } = useAuth()
  const navigate = useNavigate()
  const [activeSection, setActiveSection] = useState('identity')
  const [identityMsg, setIdentityMsg] = useState('')

  const [prefs, setPrefs] = useState(null)
  const [savedPrefs, setSavedPrefs] = useState(null)
  const [controls, setControls] = useState([])
  const [prefsLoading, setPrefsLoading] = useState(true)
  const [prefsError, setPrefsError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')

  const [health, setHealth] = useState(null)
  const [healthError, setHealthError] = useState('')

  const loadPreferences = useCallback(async () => {
    setPrefsLoading(true)
    setPrefsError('')
    try {
      const data = await getSettingsPreferences()
      setPrefs(data.preferences)
      setSavedPrefs(data.preferences)
      setControls(data.security_controls || [])
    } catch (error) {
      setPrefsError(error.message || 'Unable to load preferences.')
    } finally {
      setPrefsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadPreferences()
    getHealth()
      .then(setHealth)
      .catch((error) => setHealthError(error.message || 'Health status unavailable.'))
  }, [loadPreferences])

  const dirty = useMemo(
    () => Boolean(prefs && savedPrefs) && JSON.stringify(prefs) !== JSON.stringify(savedPrefs),
    [prefs, savedPrefs],
  )

  const setPref = (key) => (value) => {
    setSaveMsg('')
    setPrefs((current) => ({ ...current, [key]: value }))
  }

  const savePreferences = async () => {
    if (!prefs || !dirty || saving) return
    setSaving(true)
    setPrefsError('')
    setSaveMsg('')
    try {
      const data = await updateSettingsPreferences(prefs)
      setPrefs(data.preferences)
      setSavedPrefs(data.preferences)
      setSaveMsg('Preferences saved.')
    } catch (error) {
      setPrefsError(error.message || 'Unable to save preferences.')
    } finally {
      setSaving(false)
    }
  }

  const handleUnlink = async (provider) => {
    setIdentityMsg('')
    try {
      await unlinkIdentity(provider)
      setIdentityMsg(`Successfully disconnected ${provider}.`)
    } catch (err) {
      setIdentityMsg(err.message || `Failed to disconnect ${provider}`)
    }
  }

  const handleLink = async (provider) => {
    setIdentityMsg('')
    try {
      await linkOAuth(provider)
    } catch (err) {
      setIdentityMsg(err.message || `Failed to initiate connection to ${provider}`)
    }
  }

  const initials = user?.full_name
    ? user.full_name.split(' ').map((n) => n[0]).slice(0, 2).join('').toUpperCase()
    : 'AS'

  const googleIdentity = user?.identities?.find((i) => i.provider === 'google')
  const paypalIdentity = user?.identities?.find((i) => i.provider === 'paypal')

  return (
    <>
      <PageHeader
        eyebrow="Workspace configuration"
        title="Settings"
        description="Manage your profile, authenticated identities, risk preferences, and notifications."
      />
      <div className="settings-grid">
        <nav className="settings-nav panel" aria-label="Settings sections">
          {SECTIONS.map((section) => (
            <button
              key={section.key}
              type="button"
              className={`settings-nav-item ${activeSection === section.key ? 'settings-nav-active' : ''}`}
              onClick={() => setActiveSection(section.key)}
            >
              {section.label}
            </button>
          ))}
        </nav>
        <div className="settings-content">
          {activeSection === 'identity' && (
            <>
              <article className="settings-section panel">
                <div className="settings-title">
                  <div>
                    <p className="overline">Identity & Access</p>
                    <h2>Account details</h2>
                  </div>
                  {user ? (
                    <button className="outline-button" type="button" onClick={logout}>Sign out</button>
                  ) : (
                    <button className="primary-button" type="button" onClick={() => navigate('/login')}>Sign in</button>
                  )}
                </div>
                <div className="profile-form">
                  <div className="large-avatar">{initials}</div>
                  <label>Full name<input defaultValue={user?.full_name || 'Guest User'} key={user?.full_name} readOnly /></label>
                  <label>Email address<input defaultValue={user?.primary_email || 'guest@payshield.ai'} key={user?.primary_email} type="email" readOnly /></label>
                  <label>Role<input defaultValue={user ? 'Authenticated User' : 'Guest / Evaluation'} disabled /></label>
                </div>
              </article>

              <article className="settings-section panel">
                <div className="settings-title">
                  <div>
                    <p className="overline">Connected Providers</p>
                    <h2>Multi-Identity Governance</h2>
                  </div>
                </div>
                {identityMsg && <p className="settings-inline-msg">{identityMsg}</p>}
                <div className="settings-stack">
                  {[
                    { key: 'google', label: 'Google Identity (OIDC)', identity: googleIdentity },
                    { key: 'paypal', label: 'PayPal Identity', identity: paypalIdentity },
                  ].map(({ key, label, identity }) => (
                    <div className="setting-row" key={key}>
                      <div>
                        <strong>{label}</strong>
                        <p>{identity ? `Connected as ${identity.email} (Verified)` : 'Not connected'}</p>
                      </div>
                      <button
                        type="button"
                        className="outline-button small-button"
                        onClick={() => (identity ? handleUnlink(key) : handleLink(key))}
                      >
                        {identity ? 'Disconnect' : `Connect ${key === 'google' ? 'Google' : 'PayPal'}`}
                      </button>
                    </div>
                  ))}
                </div>
              </article>
            </>
          )}

          {activeSection === 'risk' && (
            <article className="settings-section panel">
              <div className="settings-title">
                <div>
                  <p className="overline">Risk preferences</p>
                  <h2>Alerting & display</h2>
                </div>
                <span className="demo-label">SAVED TO YOUR ACCOUNT</span>
              </div>
              {prefsLoading ? (
                <p className="muted-text">Loading preferences…</p>
              ) : prefsError && !prefs ? (
                <div className="api-error" role="alert">
                  <strong>Preferences unavailable</strong>
                  <p>{prefsError}</p>
                  <button type="button" className="outline-button small-button" onClick={loadPreferences}>Retry</button>
                </div>
              ) : (
                <>
                  <div className="setting-row setting-row-control">
                    <div>
                      <strong>Risk alert threshold</strong>
                      <p>Flag payments at or above this risk score for alerting. Current: {prefs?.risk_alert_threshold}</p>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={prefs?.risk_alert_threshold ?? 70}
                      aria-label="Risk alert threshold"
                      onChange={(event) => setPref('risk_alert_threshold')(Number(event.target.value))}
                    />
                  </div>
                  <div className="setting-row">
                    <div>
                      <strong>Display currency</strong>
                      <p>Currency used when formatting amounts in the console.</p>
                    </div>
                    <select
                      value={prefs?.display_currency || 'USD'}
                      aria-label="Display currency"
                      onChange={(event) => setPref('display_currency')(event.target.value)}
                    >
                      {CURRENCIES.map((currency) => <option key={currency}>{currency}</option>)}
                    </select>
                  </div>

                  <div className="settings-divider" />
                  <p className="overline">Enforced controls (read-only)</p>
                  <p className="muted-text">
                    These are enforced by the deterministic risk, policy and payment engines. They
                    cannot be changed here, and no preference can override a BLOCK.
                  </p>
                  <ul className="security-control-list">
                    {controls.map((control) => (
                      <li key={control.key}>
                        <div>
                          <strong>{control.label}</strong>
                          <p>{control.description}</p>
                        </div>
                        <span className="security-control-value">{control.value}</span>
                      </li>
                    ))}
                  </ul>

                  <div className="settings-save-bar">
                    <button type="button" className="primary-button" onClick={savePreferences} disabled={!dirty || saving}>
                      {saving ? 'Saving…' : 'Save preferences'}
                    </button>
                    {dirty && !saving && <span className="settings-dirty">Unsaved changes</span>}
                    {saveMsg && <span className="settings-saved">{saveMsg}</span>}
                    {prefsError && prefs && <span className="settings-error">{prefsError}</span>}
                  </div>
                </>
              )}
            </article>
          )}

          {activeSection === 'notifications' && (
            <article className="settings-section panel">
              <div className="settings-title">
                <div>
                  <p className="overline">Notifications</p>
                  <h2>Notification preferences</h2>
                </div>
                <span className="demo-label">SAVED TO YOUR ACCOUNT</span>
              </div>
              {prefsLoading ? (
                <p className="muted-text">Loading preferences…</p>
              ) : prefsError && !prefs ? (
                <div className="api-error" role="alert">
                  <strong>Preferences unavailable</strong>
                  <p>{prefsError}</p>
                  <button type="button" className="outline-button small-button" onClick={loadPreferences}>Retry</button>
                </div>
              ) : (
                <>
                  <SettingRow
                    id="notify-daily-digest"
                    title="Daily risk digest"
                    description="Receive a daily summary of payment risk activity."
                    value={Boolean(prefs?.notify_daily_digest)}
                    onChange={setPref('notify_daily_digest')}
                  />
                  <SettingRow
                    id="notify-realtime"
                    title="Real-time high-risk alerts"
                    description="Get notified immediately when a high-risk payment is detected."
                    value={Boolean(prefs?.notify_realtime_alerts)}
                    onChange={setPref('notify_realtime_alerts')}
                  />
                  <SettingRow
                    id="notify-browser"
                    title="Browser notifications"
                    description="Show alerts from PayShield in your browser."
                    value={Boolean(prefs?.notify_browser)}
                    onChange={setPref('notify_browser')}
                  />
                  <div className="settings-save-bar">
                    <button type="button" className="primary-button" onClick={savePreferences} disabled={!dirty || saving}>
                      {saving ? 'Saving…' : 'Save preferences'}
                    </button>
                    {dirty && !saving && <span className="settings-dirty">Unsaved changes</span>}
                    {saveMsg && <span className="settings-saved">{saveMsg}</span>}
                  </div>
                </>
              )}
            </article>
          )}

          {activeSection === 'system' && (
            <article className="settings-section panel">
              <div className="settings-title">
                <div>
                  <p className="overline">System information</p>
                  <h2>PayShield environment</h2>
                </div>
                <button type="button" className="outline-button small-button" onClick={() => getHealth().then(setHealth).catch((error) => setHealthError(error.message))}>
                  <Icon name="activity" size={14} /> Refresh
                </button>
              </div>
              {healthError && !health && <p className="api-error">{healthError}</p>}
              {health ? (
                <>
                  <div className="system-grid">
                    <span>Overall status <b className={health.status === 'ok' ? 'ok' : 'warn'}>{health.status}</b></span>
                    <span>Application <b>{health.application?.name} {health.application?.version}</b></span>
                    {Object.entries(health.components || {}).map(([name, info]) => (
                      <span key={name}>{name.replace(/_/g, ' ')} <b className={info.status === 'ok' ? 'ok' : 'warn'}>{info.status}</b></span>
                    ))}
                  </div>
                  <div className="settings-divider" />
                  <p className="overline">Providers</p>
                  <div className="system-grid">
                    {Object.entries(health.providers || {}).map(([name, info]) => (
                      <span key={name}>
                        {name.replace(/_/g, ' ')}
                        <b className={info.configured ? 'ok' : 'warn'}>
                          {info.configured ? 'configured' : 'not configured'}
                          {typeof info.enabled === 'boolean' ? ` · ${info.enabled ? 'enabled' : 'disabled'}` : ''}
                        </b>
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                !healthError && <p className="muted-text">Loading environment status…</p>
              )}
              <p className="demo-note">Secrets and credentials are never exposed by this endpoint.</p>
            </article>
          )}
        </div>
      </div>
    </>
  )
}

export default Settings
