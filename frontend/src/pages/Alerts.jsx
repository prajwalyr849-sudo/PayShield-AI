import { useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import Icon from '../components/Icon'
import { useAlerts } from '../context/AlertsContext'

const FILTERS = ['All', 'High', 'Medium']

function Alerts() {
  const [filter, setFilter] = useState('All')
  const { alerts, counts, loading, error, refresh } = useAlerts()

  const filtered = useMemo(
    () => (filter === 'All' ? alerts : alerts.filter((alert) => alert.severity === filter)),
    [alerts, filter],
  )

  const action = (
    <div className="alert-header-actions">
      <span className="alert-count"><i />{counts.total} open {counts.total === 1 ? 'alert' : 'alerts'}</span>
      <button type="button" className="outline-button small-button" onClick={refresh} disabled={loading}>
        {loading ? 'Refreshing…' : 'Refresh'}
      </button>
    </div>
  )

  let listContent
  if (loading && !error) {
    listContent = <p className="muted-text">Loading alert records…</p>
  } else if (error) {
    listContent = <p className="api-error" role="alert">{error}</p>
  } else if (filtered.length === 0) {
    listContent = (
      <p className="muted-text">
        {filter === 'All'
          ? 'No alert records available. PayShield records an alert for every non-ALLOW decision.'
          : `No ${filter.toLowerCase()}-severity alerts.`}
      </p>
    )
  } else {
    listContent = (
      <div className="alert-list">
        {filtered.map((alert) => (
          <article className={`alert-card ${alert.severity.toLowerCase()}`} key={`${alert.id}-${alert.title}`}>
            <div className="alert-icon"><Icon name="alert" size={16} /></div>
            <div className="alert-copy">
              <div>
                <span className={`severity-badge ${alert.severity.toLowerCase()}`}>{alert.severity}</span>
                {alert.time && <span className="alert-time">{new Date(alert.time).toLocaleString()}</span>}
              </div>
              <h3>{alert.title}</h3>
              <p>{alert.description}</p>
              <small>{alert.id}</small>
            </div>
            <span className={`alert-status ${alert.status.toLowerCase()}`}>{alert.status}</span>
          </article>
        ))}
      </div>
    )
  }

  return (
    <>
      <PageHeader
        eyebrow="Security center"
        title="Alerts"
        description="Monitor non-ALLOW decisions recorded by the backend."
        action={action}
      />
      <section className="page-panel panel">
        <div className="alert-filters">
          {FILTERS.map((item) => (
            <button type="button" key={item} className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)}>
              {item}
              {item !== 'All' && <span>{counts[item] || 0}</span>}
            </button>
          ))}
        </div>
        {listContent}
      </section>
    </>
  )
}

export default Alerts
