function TransactionDetails({ transaction }) {
  const rows = [
    ['Amount', transaction.amount, '12.4× higher than usual', 'danger'],
    ['Recipient', transaction.recipient, 'First-time recipient', 'warning'],
    ['Transaction time', transaction.time, 'Outside usual hours', 'warning'],
    ['Payment category', transaction.category, 'Higher fraud exposure', 'danger'],
  ]
  return <article className="details-card panel"><div className="card-heading"><div><p className="overline">Transaction context</p><h2>Transaction analysis</h2></div><span className="transaction-id">#84291</span></div><div className="amount-row"><span>Payment amount</span><strong>{transaction.amount}</strong><small>Previous spend <b>{transaction.previousSpending}</b></small></div><div className="details-list">{rows.slice(1).map(([label, value, note, tone]) => <div className="detail-row" key={label}><span>{label}</span><div><strong>{value}</strong><small className={tone}><i />{note}</small></div></div>)}</div></article>
}

export default TransactionDetails
