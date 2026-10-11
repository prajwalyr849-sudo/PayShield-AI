import { useState } from 'react'
import { Link } from 'react-router-dom'
import MetricCard from '../components/MetricCard'
import PageHeader from '../components/PageHeader'
import RecentTransactions from '../components/RecentTransactions'
import RiskCard from '../components/RiskCard'
import RiskReasons from '../components/RiskReasons'
import TransactionDetails from '../components/TransactionDetails'
import TransactionDrawer from '../components/TransactionDrawer'
import { metrics, transactions } from '../data/mockData'

const currentTransaction = transactions[0]

function Dashboard() {
  const [selectedTransaction, setSelectedTransaction] = useState(null)
  return <><PageHeader eyebrow="Tuesday, October 06, 2026" title={<>Good morning, Alex <span className="wave">✦</span></>} description="Here's what's happening across your payment network today." action={<button className="date-button" type="button">Last 30 days <span>⌄</span></button>} /><section className="metrics-grid" aria-label="Transaction overview">{metrics.map((metric) => <MetricCard key={metric.label} {...metric} />)}</section><section className="analysis-grid" aria-label="Risk intelligence"><RiskCard score={currentTransaction.score} /><TransactionDetails transaction={{ ...currentTransaction, time: '02:41 AM', category: 'Digital goods' }} /></section><section className="insight-grid"><RiskReasons /><div className="coverage-card panel"><div className="card-heading"><div><p className="overline">Network health</p><h2>Protection coverage</h2></div><span className="small-status"><span /> Live</span></div><div className="coverage-value">97.5<span>%</span></div><p className="muted-text">of payment activity is currently monitored by PayShield AI.</p><div className="coverage-bar"><span /></div><div className="coverage-footer"><span>12,516 analyzed</span><span>12,840 total</span></div></div></section><RecentTransactions onSelect={setSelectedTransaction} /><Link className="screen-reader-link" to="/transactions">Open all transactions</Link><footer className="footer"><span>PayShield AI · Risk intelligence for modern payments</span><span>All systems operational</span></footer><TransactionDrawer transaction={selectedTransaction} onClose={() => setSelectedTransaction(null)} /></>
}

export default Dashboard
