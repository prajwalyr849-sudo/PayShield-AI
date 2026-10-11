export const transactions = [
  { id: 'TXN-84291', amount: '₹5,000', rawAmount: 5000, previousSpending: '₹1,000', recipient: 'Unknown merchant', score: 80, level: 'High', decision: 'Blocked', time: '2 min ago', timestamp: 'Oct 06, 2026 · 02:41 AM', signals: ['Unusual transaction amount', 'New recipient', 'Transaction outside usual hours'] },
  { id: 'TXN-84290', amount: '₹420', rawAmount: 420, previousSpending: '₹380', recipient: 'Swiggy', score: 12, level: 'Low', decision: 'Allowed', time: '8 min ago', timestamp: 'Oct 06, 2026 · 02:35 AM', signals: ['Known recipient'] },
  { id: 'TXN-84289', amount: '₹2,850', rawAmount: 2850, previousSpending: '₹1,900', recipient: 'Myntra', score: 54, level: 'Medium', decision: 'Review', time: '16 min ago', timestamp: 'Oct 06, 2026 · 02:27 AM', signals: ['Above average amount', 'New device'] },
  { id: 'TXN-84288', amount: '₹180', rawAmount: 180, previousSpending: '₹220', recipient: 'Spotify', score: 8, level: 'Low', decision: 'Allowed', time: '24 min ago', timestamp: 'Oct 06, 2026 · 02:19 AM', signals: ['Known recipient', 'Usual activity time'] },
  { id: 'TXN-84287', amount: '₹12,400', rawAmount: 12400, previousSpending: '₹2,000', recipient: 'Unknown merchant', score: 92, level: 'Critical', decision: 'Blocked', time: '31 min ago', timestamp: 'Oct 06, 2026 · 02:12 AM', signals: ['Unusual transaction amount', 'New recipient', 'Velocity anomaly'] },
]

export const metrics = [
  { label: 'Total transactions', value: '12,840', change: '+12.8%', note: 'vs. last month', tone: 'blue', icon: 'activity' },
  { label: 'Transactions analyzed', value: '12,516', change: '97.5%', note: 'analysis coverage', tone: 'cyan', icon: 'scan' },
  { label: 'High-risk transactions', value: '186', change: '+4.2%', note: 'needs attention', tone: 'amber', icon: 'alert' },
  { label: 'Blocked transactions', value: '74', change: '0.6%', note: 'of all transactions', tone: 'red', icon: 'shield' },
]
