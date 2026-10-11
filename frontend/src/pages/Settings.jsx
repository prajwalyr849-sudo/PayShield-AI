import { useState } from 'react'
import PageHeader from '../components/PageHeader'

function Toggle({ checked, onChange }) {
  return <button type="button" aria-pressed={checked} className={`toggle ${checked ? 'on' : ''}`} onClick={() => onChange(!checked)}><span /></button>
}

function Settings() {
  const [settings, setSettings] = useState({ highRisk: true, dailyDigest: true, realTime: true, browser: false })
  const update = (key) => (value) => setSettings((current) => ({ ...current, [key]: value }))
  return <><PageHeader eyebrow="Workspace configuration" title="Settings" description="Manage your profile, risk preferences, and notifications." /><div className="settings-grid"><section className="settings-nav panel"><span className="settings-nav-active">Profile</span><span>Risk preferences</span><span>Notification preferences</span><span>Security</span><span>System information</span></section><div className="settings-content"><article className="settings-section panel"><div className="settings-title"><div><p className="overline">Profile</p><h2>Account details</h2></div><button className="outline-button" type="button">Edit profile</button></div><div className="profile-form"><div className="large-avatar">AS</div><label>Full name<input defaultValue="Alex Smith" /></label><label>Email address<input defaultValue="alex@payshield.ai" type="email" /></label><label>Role<input defaultValue="Administrator" disabled /></label></div></article><article className="settings-section panel"><div className="settings-title"><div><p className="overline">Risk preferences</p><h2>Decision controls</h2></div><span className="demo-label">FRONTEND ONLY</span></div><SettingRow title="Block high-risk payments" description="Automatically block payments above the high-risk threshold." value={settings.highRisk} onChange={update('highRisk')} /><SettingRow title="Review medium-risk payments" description="Route medium-risk activity to your review queue." value={true} onChange={() => {}} /></article><article className="settings-section panel"><div className="settings-title"><div><p className="overline">Notifications</p><h2>Notification preferences</h2></div></div><SettingRow title="Daily risk digest" description="Receive a daily summary of payment risk activity." value={settings.dailyDigest} onChange={update('dailyDigest')} /><SettingRow title="Real-time high-risk alerts" description="Get notified immediately when a high-risk payment is detected." value={settings.realTime} onChange={update('realTime')} /><SettingRow title="Browser notifications" description="Show alerts from PayShield in your browser." value={settings.browser} onChange={update('browser')} /></article><article className="settings-section panel"><div className="settings-title"><div><p className="overline">System information</p><h2>PayShield environment</h2></div></div><div className="system-grid"><span>Model version <b>Demo v2.4.1</b></span><span>Environment <b>Production workspace</b></span><span>API connection <b className="connected"><i /> Not connected</b></span></div></article></div></div></>
}

function SettingRow({ title, description, value, onChange }) {
  return <div className="setting-row"><div><strong>{title}</strong><p>{description}</p></div><Toggle checked={value} onChange={onChange} /></div>
}

export default Settings
