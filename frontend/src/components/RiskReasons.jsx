const reasons = [
  { label: 'Unusual transaction amount', value: '42%', width: '84%', color: 'red', detail: 'High deviation from baseline' },
  { label: 'New recipient', value: '28%', width: '56%', color: 'amber', detail: 'No prior payment history' },
  { label: 'Transaction timing', value: '18%', width: '36%', color: 'blue', detail: 'Outside typical activity' },
  { label: 'Payment category', value: '12%', width: '24%', color: 'slate', detail: 'Elevated category risk' },
]
function RiskReasons() {
  return <article className="reasons-card panel"><div className="card-heading"><div><p className="overline">Explainable AI</p><h2>Why this was flagged</h2></div><button className="text-button" type="button">See details <span>→</span></button></div><p className="reasons-intro">Four signals contributed to the final risk score of <b>80</b>.</p><div className="reasons-list">{reasons.map((reason) => <div className="reason" key={reason.label}><div className="reason-meta"><span><i className={`reason-dot ${reason.color}`} />{reason.label}</span><strong>{reason.value}</strong></div><div className="reason-bar"><span className={reason.color} style={{ width: reason.width }} /></div><small>{reason.detail}</small></div>)}</div></article>
}
export default RiskReasons
