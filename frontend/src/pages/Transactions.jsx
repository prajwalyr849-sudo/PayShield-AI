import { useMemo, useState } from 'react'
import PageHeader from '../components/PageHeader'
import TransactionDrawer from '../components/TransactionDrawer'
import TransactionTable from '../components/TransactionTable'
import Icon from '../components/Icon'
import { transactions } from '../data/mockData'

function Transactions() {
  const [query, setQuery] = useState('')
  const [risk, setRisk] = useState('All risk levels')
  const [decision, setDecision] = useState('All decisions')
  const [selected, setSelected] = useState(null)
  const filtered = useMemo(() => transactions.filter((item) => {
    const matchesQuery = `${item.id} ${item.recipient}`.toLowerCase().includes(query.toLowerCase())
    const matchesRisk = risk === 'All risk levels' || item.level === risk
    const matchesDecision = decision === 'All decisions' || item.decision === decision
    return matchesQuery && matchesRisk && matchesDecision
  }), [query, risk, decision])
  return <><PageHeader eyebrow="Activity monitor" title="Transactions" description="Review, search, and investigate payment activity across your network." /><section className="page-panel panel"><div className="filters"><label className="search-field"><Icon name="search" size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search transaction ID or recipient" aria-label="Search transactions" /></label><select value={risk} onChange={(event) => setRisk(event.target.value)} aria-label="Filter by risk level"><option>All risk levels</option><option>Low</option><option>Medium</option><option>High</option><option>Critical</option></select><select value={decision} onChange={(event) => setDecision(event.target.value)} aria-label="Filter by decision"><option>All decisions</option><option>Allowed</option><option>Review</option><option>Blocked</option></select></div><div className="table-heading"><div><h2>All transactions</h2><span>{filtered.length} of {transactions.length} records</span></div><span className="demo-label">DEMO DATA</span></div><TransactionTable transactions={filtered} onSelect={setSelected} /></section><TransactionDrawer transaction={selected} onClose={() => setSelected(null)} /></>
}

export default Transactions
