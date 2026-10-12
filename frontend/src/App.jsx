import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import RiskIntelligence from './pages/RiskIntelligence'
import Alerts from './pages/Alerts'
import Settings from './pages/Settings'
import Checkout from './pages/Checkout'

function AppLayout() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-content">
        <Topbar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/risk-intelligence" element={<RiskIntelligence />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/checkout/return" element={<Checkout />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

function App() {
  return <BrowserRouter><AppLayout /></BrowserRouter>
}

export default App
