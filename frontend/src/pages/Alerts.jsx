import { useState } from 'react'
import PageHeader from '../components/PageHeader'
import Icon from '../components/Icon'

const alertData = [
  { severity: 'High', title: 'High-risk transaction detected', description: 'A payment with an 80/100 score was blocked automatically.', id: 'TXN-84291', time: '2 min ago', status: 'Open' },
  { severity: 'Medium', title: 'New recipient detected', description: 'A first-time recipient received a payment above the account baseline.', id: 'TXN-84289', time: '16 min ago', status: 'Investigating' },
  { severity: 'High', title: 'Unusual transaction amount', description: 'The amount is more than 12× the customer’s recent average spend.', id: 'TXN-84287', time: '31 min ago', status: 'Open' },
  { severity: 'Low', title: 'Multiple suspicious transactions', description: 'Three low-confidence signals were observed in a short period.', id: 'TXN-84280', time: '1 hr ago', status: 'Resolved' },
]

function Alerts() {
  const [filter, setFilter] = useState('All')
  const filtered = filter === 'All' ? alertData : alertData.filter((alert) => alert.severity === filter)
  return <><PageHeader eyebrow="Security center" title="Alerts" description="Monitor security events that need your attention." action={<span className="alert-count"><i />{alertData.filter((alert) => alert.status === 'Open').length} open alerts</span>} /><section className="page-panel panel"><div className="alert-filters">{['All', 'High', 'Medium', 'Low'].map((item) => <button type="button" key={item} className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)}>{item}{item !== 'All' && <span>{alertData.filter((alert) => alert.severity === item).length}</span>}</button>)}</div><div className="alert-list">{filtered.map((alert) => <article className={`alert-card ${alert.severity.toLowerCase()}`} key={`${alert.id}-${alert.title}`}><div className="alert-icon"><Icon name="alert" size={16} /></div><div className="alert-copy"><div><span className={`severity-badge ${alert.severity.toLowerCase()}`}>{alert.severity}</span><span className="alert-time">{alert.time}</span></div><h3>{alert.title}</h3><p>{alert.description}</p><small>{alert.id}</small></div><span className={`alert-status ${alert.status.toLowerCase()}`}>{alert.status}</span><button className="icon-button" type="button" aria-label={`Open ${alert.title}`}><Icon name="arrow" size={16} /></button></article>)}</div></section></>
}

export default Alerts
