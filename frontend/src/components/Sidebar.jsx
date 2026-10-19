import { NavLink, useLocation } from 'react-router-dom'
import compactLogo from '../assets/payshield - logo.jpeg'
import Icon from './Icon'
import { useAlerts } from '../context/AlertsContext'

const links = [
  { label: 'Dashboard', icon: 'dashboard', path: '/' },
  { label: 'Assistant Chat', icon: 'radar', path: '/assistant' },
  { label: 'Product Search', icon: 'search', path: '/assistant/search' },
  { label: 'Transactions', icon: 'card', path: '/transactions' },
  { label: 'Receipts', icon: 'check', path: '/receipts' },
  { label: 'Risk Intelligence', icon: 'radar', path: '/risk-intelligence' },
  { label: 'Alerts', icon: 'bell', path: '/alerts', showsAlertCount: true },
  { label: 'Policies', icon: 'shield-check', path: '/policies' },
  { label: 'Audit Logs', icon: 'document', path: '/audit-logs' },
  { label: 'Settings', icon: 'settings', path: '/settings' },
]

function Sidebar({ collapsed, onToggleCollapse }) {
  const { counts } = useAlerts()
  const location = useLocation()

  return (
    <aside className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <button
        type="button"
        className="sidebar-toggle"
        aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        onClick={() => onToggleCollapse((prev) => !prev)}
      >
        <Icon name={collapsed ? 'chevron-right' : 'chevron-left'} size={16} />
      </button>
      {!collapsed && (
        <NavLink className="brand brand-link" to="/">
          <img src={compactLogo} alt="PayShield AI logo" />
          <div>
            <strong>PayShield</strong><small>AI</small>
          </div>
        </NavLink>
      )}
      <nav className="sidebar-nav">
        {links.map((link) => {
          const count = link.showsAlertCount ? counts.total : 0
          const isActive = location.pathname === link.path ||
            (link.path === '/' && location.pathname === '/')
          return (
            <NavLink
              key={link.label}
              className={({ isActive: linkActive }) =>
                `nav-link ${linkActive || isActive ? 'active' : ''}`}
              to={link.path}
              end={link.path === '/' || link.path === '/assistant'}
            >
              <Icon name={link.icon} size={16} />
              {!collapsed && (
                <>
                  <span>{link.label}</span>
                  {count > 0 && <b>{count}</b>}
                </>
              )}
            </NavLink>
          )
        })}
      </nav>
      {!collapsed && (
        <div className="sidebar-bottom">
          <button
            type="button"
            className="sidebar-toggle-text"
            onClick={() => onToggleCollapse((prev) => !prev)}
          >
            <Icon name={collapsed ? 'chevron-right' : 'chevron-left'} size={14} />
            <span>{collapsed ? 'Expand' : 'Collapse'}</span>
          </button>
          <div className="security-note">
            <span className="lock-icon">⌁</span>
            <div>
              <strong>Backend governed</strong>
              <span>Risk and policy enforcement active</span>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}

export default Sidebar
