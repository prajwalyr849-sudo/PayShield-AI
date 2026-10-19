import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getAuditHistory } from '../services/api'
import { countAlerts, deriveAlerts } from '../utils/alerts'

const AlertsContext = createContext(null)

export function AlertsProvider({ children }) {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getAuditHistory(500)
      setRecords(response.records || [])
      setUpdatedAt(new Date())
    } catch (requestError) {
      // A failed request must not look like "no alerts".
      setError(requestError.message || 'Unable to load alert records.')
      setRecords([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const alerts = useMemo(() => deriveAlerts(records), [records])
  const counts = useMemo(() => countAlerts(alerts), [alerts])

  const value = useMemo(
    () => ({ alerts, counts, loading, error, updatedAt, refresh }),
    [alerts, counts, loading, error, updatedAt, refresh],
  )

  return <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>
}

export function useAlerts() {
  const context = useContext(AlertsContext)
  if (!context) {
    throw new Error('useAlerts must be used within an AlertsProvider')
  }
  return context
}
