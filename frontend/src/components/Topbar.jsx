import { NavLink, useLocation } from 'react-router-dom'
import compactLogo from '../assets/payshield - logo.jpeg'
import Icon from './Icon'

function Topbar() {
  const location = useLocation()
  const activeNav = location.pathname === '/' ? 'Dashboard' : location.pathname.slice(1).split('-').map((word) => word[0].toUpperCase() + word.slice(1)).join(' ')
  return (
    <header className="topbar">
      <NavLink className="mobile-brand" to="/"><img src={compactLogo} alt="PayShield AI logo" /><strong>PayShield<small>AI</small></strong></NavLink>
      <div className="breadcrumbs"><span>Overview</span><span className="breadcrumb-divider">/</span><strong>{activeNav}</strong></div>
      <div className="topbar-actions">
        <div className="system-status"><span className="pulse-dot" /> System operational</div>
        <button className="icon-button notification-button" type="button" aria-label="Notifications"><Icon name="bell" size={18} /><span /></button>
        <div className="topbar-user"><div className="profile-avatar">AS</div><div><strong>Alex Smith</strong><span>Administrator</span></div><Icon name="chevronDown" size={14} /></div>
      </div>
    </header>
  )
}

export default Topbar
