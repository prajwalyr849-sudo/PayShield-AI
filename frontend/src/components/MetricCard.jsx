import Icon from './Icon'

function MetricCard({ label, value, change, note, tone, icon }) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`}><Icon name={icon} size={18} /></div>
      <div className="metric-copy"><p>{label}</p><strong>{value}</strong><span className={tone === 'red' || tone === 'amber' ? 'change-warning' : ''}>{change} <em>{note}</em></span></div>
      <div className="sparkline"><span /><span /><span /><span /><span /><span /><span /></div>
    </article>
  )
}

export default MetricCard
