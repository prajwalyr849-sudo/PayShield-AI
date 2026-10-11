import { Link } from 'react-router-dom'
import { transactions } from '../data/mockData'
import TransactionTable from './TransactionTable'

function RecentTransactions({ onSelect }) {
  return <article className="recent-card panel"><div className="card-heading"><div><p className="overline">Activity monitor</p><h2>Recent transactions</h2></div><Link className="outline-button" to="/transactions">View all transactions <span>→</span></Link></div><TransactionTable transactions={transactions} onSelect={onSelect} /></article>
}
export default RecentTransactions
