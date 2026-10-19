import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import compactLogo from '../assets/payshield - logo.jpeg'
import Icon from './Icon'
import { useAuth } from '../context/AuthContext'
import { useAlerts } from '../context/AlertsContext'

function Topbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const { counts } = useAlerts()
  const activeNav = location.pathname === '/' ? 'Dashboard' : location.pathname.slice(1).split('-').map((word) => word[0].toUpperCase() + word.slice(1)).join(' ')

  const initials = user?.full_name
    ? user.full_name
        .split(' ')
        .map((n) => n[0])
        .slice(0, 2)
        .join('')
        .toUpperCase()
    : 'AS'

  return (
    <header className="topbar">
      <NavLink className="mobile-brand" to="/"><img src={compactLogo} alt="PayShield AI logo" /><strong>PayShield<small>AI</small></strong></NavLink>
      <div className="breadcrumbs"><span>Overview</span><span className="breadcrumb-divider">/</span><strong>{activeNav}</strong></div>
      <div className="topbar-actions">
        <div className="system-status"><span className="pulse-dot" /> System operational</div>
        <button
          className="icon-button notification-button"
          type="button"
          aria-label="Open alerts"
          onClick={() => navigate('/alerts')}
        >
          <Icon name="bell" size={18} />
          {counts.total > 0 && <span />}
        </button>
        {user ? (
          <div className="topbar-user" onClick={() => navigate('/settings')} style={{ cursor: 'pointer' }} title="Manage Identity & Settings">
            <div className="profile-avatar">{initials}</div>
            <div>
              <strong>{user.full_name || 'PayShield User'}</strong>
              <span>{user.primary_email}</span>
            </div>
            <button
              type="button"
              className="outline-button"
              style={{ fontSize: '0.75rem', padding: '2px 8px', marginLeft: '6px' }}
              onClick={(e) => {
                e.stopPropagation()
                logout()
              }}
            >
              Sign out
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="primary-button"
            style={{ fontSize: '0.8rem', padding: '6px 12px' }}
            onClick={() => navigate('/login')}
          >
            Sign in
          </button>
        )}
      </div>
    </header>
  )
}

export default Topbar
