import { useEffect, useState } from 'react'
import { Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import logo from '../assets/payshield - logo.jpeg'
import { getAuthProviderStatus, requestPasswordReset } from '../services/api'

function Login() {
  const { user, loginWithOAuth, loginDemo, loginEmail, registerEmail, loading: authLoading } = useAuth()
  const [searchParams] = useSearchParams()
  const location = useLocation()

  const [providerLoading, setProviderLoading] = useState(null)
  const [localError, setLocalError] = useState('')
  const [providerStatus, setProviderStatus] = useState(null)
  const [mode, setMode] = useState('signin')
  const [showPassword, setShowPassword] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', password: '', confirmPassword: '' })
  const [resetMessage, setResetMessage] = useState('')

  useEffect(() => {
    getAuthProviderStatus().then(setProviderStatus).catch(() => setProviderStatus(null))
  }, [])

  const urlError = searchParams.get('error')
  const displayError = localError || urlError

  const from = location.state?.from?.pathname || '/'

  if (!authLoading && user) {
    return <Navigate to={from} replace />
  }

  const handleOAuth = async (provider) => {
    setLocalError('')
    setProviderLoading(provider)
    try {
      await loginWithOAuth(provider)
    } catch (err) {
      setLocalError(err.message || `Failed to sign in with ${provider}`)
      setProviderLoading(null)
    }
  }

  const handleDemoLogin = async () => {
    setLocalError('')
    setProviderLoading('demo')
    try {
      await loginDemo()
    } catch (err) {
      setLocalError(err.message || 'Failed to sign in as demo user')
      setProviderLoading(null)
    }
  }

  const updateField = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }))

  const handleEmailSubmit = async (event) => {
    event.preventDefault()
    setLocalError('')
    setResetMessage('')
    if (mode === 'register' && form.password !== form.confirmPassword) {
      setLocalError('Passwords do not match.')
      return
    }
    setProviderLoading('email')
    try {
      if (mode === 'register') {
        await registerEmail(form.name.trim(), form.email.trim(), form.password, form.confirmPassword)
      } else {
        await loginEmail(form.email.trim(), form.password)
      }
    } catch (err) {
      setLocalError(err.message || 'Email authentication failed.')
    } finally {
      setProviderLoading(null)
    }
  }

  const handleForgotPassword = async () => {
    if (!form.email.trim()) {
      setLocalError('Enter your email address first.')
      return
    }
    setLocalError('')
    setResetMessage('')
    try {
      const result = await requestPasswordReset(form.email.trim())
      setResetMessage(
        result.status === 'setup_required'
          ? 'Password recovery is not configured yet. Contact the administrator.'
          : result.message,
      )
    } catch (err) {
      setLocalError(err.message || 'Unable to request password reset.')
    }
  }

  return (
    <div className="login-page">
      <div className="login-card panel">
        <header className="login-header">
          <img src={logo} alt="PayShield AI Logo" className="login-logo" />
          <span className="overline">Identity & Access Governance</span>
          <h1>Sign in to PayShield AI</h1>
          <p className="login-subtitle">
            Secure multi-provider authentication for autonomous agentic commerce.
          </p>
        </header>

        {displayError && (
          <div className="api-error login-error-banner" role="alert">
            <strong>Authentication Notice</strong>
            <p>{displayError}</p>
          </div>
        )}

        <form className="email-auth-form" onSubmit={handleEmailSubmit}>
          {mode === 'register' && (
            <label>
              Name
              <input value={form.name} onChange={updateField('name')} autoComplete="name" required />
            </label>
          )}
          <label>
            Email
            <input type="email" value={form.email} onChange={updateField('email')} autoComplete="email" required />
          </label>
          <label>
            Password
            <span className="password-input-wrap">
              <input
                type={showPassword ? 'text' : 'password'}
                value={form.password}
                onChange={updateField('password')}
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                minLength={mode === 'register' ? 12 : 1}
                required
              />
              <button type="button" className="password-toggle" onClick={() => setShowPassword((value) => !value)}>
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </span>
          </label>
          {mode === 'register' && (
            <label>
              Confirm password
              <input type={showPassword ? 'text' : 'password'} value={form.confirmPassword} onChange={updateField('confirmPassword')} autoComplete="new-password" required />
            </label>
          )}
          <button type="submit" className="primary-button email-submit" disabled={providerLoading !== null}>
            {providerLoading === 'email' ? 'Checking…' : mode === 'register' ? 'Create account' : 'Sign in with Email'}
          </button>
          {mode === 'signin' && (
            <button type="button" className="text-button forgot-password" onClick={handleForgotPassword}>
              Forgot password?
            </button>
          )}
          {resetMessage && <p className="login-success" role="status">{resetMessage}</p>}
          <button type="button" className="text-button auth-mode-switch" onClick={() => { setMode(mode === 'signin' ? 'register' : 'signin'); setLocalError('') }}>
            {mode === 'signin' ? 'Create an account' : 'Already have an account? Sign in'}
          </button>
        </form>

        <div className="oauth-buttons-container">
          <button
            type="button"
            className="oauth-btn google-btn"
            disabled={providerLoading !== null}
            onClick={() => handleOAuth('google')}
          >
            <svg className="oauth-icon" viewBox="0 0 24 24" width="20" height="20">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
              />
            </svg>
            <span>
              {providerLoading === 'google' ? 'Connecting to Google…' : 'Continue with Google'}
            </span>
          </button>
          {providerStatus && !providerStatus.google.configured && (
            <small className="provider-setup-note">{providerStatus.google.setup}</small>
          )}

          <button
            type="button"
            className="oauth-btn paypal-btn"
            disabled={providerLoading !== null}
            onClick={() => handleOAuth('paypal')}
          >
            <svg className="oauth-icon" viewBox="0 0 24 24" width="20" height="20">
              <path
                fill="#003087"
                d="M20.067 8.478c-.492-2.316-2.47-3.978-5.367-3.978H8.5c-.552 0-1 .448-1 1v13c0 .552.448 1 1 1h3.313c.487 0 .898-.352.977-.833l.865-5.247c.078-.481.49-.833.977-.833h1.082c3.488 0 6.035-1.748 6.78-4.912.443-1.884.05-3.197-1.427-4.197z"
              />
              <path
                fill="#0079C1"
                d="M18.64 12.675c-.745 3.164-3.292 4.912-6.78 4.912h-1.082c-.487 0-.899.352-.977.833l-.865 5.247c-.079.481-.49.833-.977.833H4.646c-.552 0-1-.448-1-1v-13c0-.552.448-1 1-1h6.2c2.897 0 4.875 1.662 5.367 3.978 1.477 1 1.87 2.313 1.427 4.197z"
              />
            </svg>
            <span>
              {providerLoading === 'paypal' ? 'Connecting to PayPal…' : 'Continue with PayPal'}
            </span>
          </button>
          {providerStatus && !providerStatus.paypal.configured && (
            <small className="provider-setup-note">{providerStatus.paypal.setup}</small>
          )}

          <div style={{ display: 'flex', alignItems: 'center', margin: '8px 0', gap: '8px', opacity: 0.6 }}>
            <hr style={{ flex: 1, borderColor: 'var(--border, #333)' }} />
            <small>or local evaluation</small>
            <hr style={{ flex: 1, borderColor: 'var(--border, #333)' }} />
          </div>

          <button
            type="button"
            className="outline-button"
            style={{ width: '100%', justifyContent: 'center', padding: '10px' }}
            disabled={providerLoading !== null}
            onClick={handleDemoLogin}
          >
            <span>
              {providerLoading === 'demo' ? 'Signing in as Alex Smith…' : 'Sign in as Demo Administrator (Alex Smith)'}
            </span>
          </button>
        </div>

        <footer className="login-security-notice">
          <div className="security-item">
            <span className="security-badge">Zero Passwords</span>
            <small>
              PayShield AI never asks for or stores your Google or PayPal password. Authentication is cryptographically verified via OpenID Connect.
            </small>
          </div>
          <div className="security-item">
            <span className="security-badge">Payment Isolation</span>
            <small>
              PayPal identity verifies who you are. Payment capture remains strictly governed by PayShield approval limit checks.
            </small>
          </div>
        </footer>
      </div>
    </div>
  )
}

export default Login
