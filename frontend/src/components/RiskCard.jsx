import { useEffect, useState } from 'react'

function RiskCard({ score }) {
  const [displayScore, setDisplayScore] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setDisplayScore((current) => current >= score ? score : current + 2), 18)
    return () => clearInterval(timer)
  }, [score])
  return (
    <article className="risk-card panel">
      <div className="card-heading risk-heading"><div><p className="overline">Live assessment · TXN-84291</p><h2>Risk intelligence</h2></div><span className="model-badge">AI MODEL <b>v2.4</b></span></div>
      <div className="risk-summary"><div><span className="risk-label">Risk score</span><div className="score"><strong>{displayScore}</strong><span>/100</span></div><span className="status-pill high">HIGH RISK</span></div><div className="decision"><span>Recommended decision</span><strong><i /> BLOCK</strong><small>Confidence 94.8%</small></div></div>
      <div className="meter-wrap"><div className="meter-labels"><span>Low</span><span>Medium</span><span>High</span></div><div className="risk-meter"><div className="meter-fill" style={{ width: `${displayScore}%` }}><span /></div></div><div className="meter-scale"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div></div>
      <div className="assessment-footer"><span><i className="green-dot" /> Analysis completed just now</span><button type="button">View full assessment <span>→</span></button></div>
    </article>
  )
}

export default RiskCard
