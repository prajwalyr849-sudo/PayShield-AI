import { NavLink } from 'react-router-dom'
import compactLogo from '../assets/payshield - logo.jpeg'
import Icon from './Icon'

const links = [
  { label: 'Dashboard', icon: 'dashboard', path: '/' },
  { label: 'Transactions', icon: 'card', path: '/transactions' },
  { label: 'Risk Intelligence', icon: 'radar', path: '/risk-intelligence' },
  { label: 'Alerts', icon: 'bell', count: 3, path: '/alerts' },
  { label: 'Settings', icon: 'settings', path: '/settings' },
]

function Sidebar() {
  return (
    <aside className="sidebar">
      <NavLink className="brand brand-link" to="/"><img src={compactLogo} alt="PayShield AI logo" /><div><strong>PayShield</strong><small>AI</small></div></NavLink>
      <div className="workspace-switcher">
        <div className="workspace-avatar">P</div>
        <div><strong>PayShield workspace</strong><span>Production</span></div>
        <Icon name="chevronDown" size={14} />
      </div>
      <p className="nav-label">Workspace</p>
      <nav className="sidebar-nav">
        {links.map((link) => (
          <NavLink key={link.label} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} to={link.path} end={link.path === '/'}>
            <Icon name={link.icon} size={17} /><span>{link.label}</span>{link.count && <b>{link.count}</b>}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="security-note"><span className="lock-icon">⌁</span><div><strong>Protected by AI</strong><span>Model v2.4.1 active</span></div></div>
        <div className="profile-mini"><div className="profile-avatar">AS</div><div><strong>Alex Smith</strong><span>Admin</span></div><span className="more">•••</span></div>
      </div>
    </aside>
  )
}

export default Sidebar
