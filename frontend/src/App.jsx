import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import RiskIntelligence from './pages/RiskIntelligence'
import Alerts from './pages/Alerts'
import Settings from './pages/Settings'
import AuditLogs from './pages/AuditLogs'
import Policies from './pages/Policies'
import Checkout from './pages/Checkout'
import Receipts from './pages/Receipts'
import Login from './pages/Login'
import AssistantChat from './pages/AssistantChat'
import ProductSearch from './pages/ProductSearch'
import { AuthProvider } from './context/AuthContext'
import { AlertsProvider } from './context/AlertsContext'
import ProtectedRoute from './components/ProtectedRoute'

function AppLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <AlertsProvider>
    <div className={`app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar collapsed={sidebarCollapsed} onToggleCollapse={setSidebarCollapsed} />
      <main className="main-content">
        <Topbar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/assistant" element={<AssistantChat />} />
          <Route path="/assistant/search" element={<ProductSearch />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/receipts" element={<Receipts />} />
          <Route path="/risk-intelligence" element={<RiskIntelligence />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/audit-logs" element={<AuditLogs />} />
          <Route path="/policies" element={<Policies />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/checkout/return" element={<Checkout />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
    </AlertsProvider>
  )
}

function ProtectedApp() {
  return (
    <ProtectedRoute>
      <AppLayout />
    </ProtectedRoute>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={<ProtectedApp />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
