import { useEffect, useState } from 'react'
import PageHeader from '../components/PageHeader'
import Icon from '../components/Icon'
import ProductResultCard from '../components/assistant/ProductResultCard'
import { getAssistantRecommendations, getAssistantStatus } from '../services/api'

function ProductSearch() {
  const [query, setQuery] = useState('')
  const [budget, setBudget] = useState('')
  const [category, setCategory] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [country, setCountry] = useState('US')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searched, setSearched] = useState(false)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    getAssistantStatus().then(setStatus).catch(() => setStatus(null))
  }, [])

  const runSearch = async (event) => {
    event?.preventDefault()
    if (!query.trim() || loading) return
    setLoading(true)
    setError('')
    setSearched(true)
    try {
      const data = await getAssistantRecommendations({
        query: query.trim(),
        budget,
        category,
        currency,
        country,
      })
      setResults(data.search_results || [])
    } catch (requestError) {
      setResults([])
      setError(requestError.message || 'Live product search is unavailable.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Product intelligence"
        title="Product Search"
        description="Structured, source-backed product evidence. Each offer shows where the price came from and whether it was verified."
      />

      <section className="page-panel" aria-label="Search controls">
        <div className="assistant-controls-bar panel">
          <div className="assistant-status-pill">
            <span className={`pulse-dot ${status?.live_search_configured ? '' : 'offline'}`} />
            <small>{status?.provider || 'Search provider unavailable'}</small>
          </div>
        </div>

        {error && (
          <div className="api-error" role="alert">
            <strong>Search unavailable</strong>
            <p>{error}</p>
          </div>
        )}

        <form onSubmit={runSearch} className="search-panel panel live-search-form">
          <div className="search-input-group">
            <Icon name="search" size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search products, features, or criteria"
              aria-label="Product search query"
              required
            />
          </div>
          <input
            type="number"
            min="1"
            value={budget}
            onChange={(event) => setBudget(event.target.value)}
            placeholder="Max budget"
            aria-label="Maximum budget"
          />
          <select value={currency} onChange={(event) => setCurrency(event.target.value)} aria-label="Currency">
            <option>USD</option><option>EUR</option><option>GBP</option><option>INR</option>
          </select>
          <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Product category">
            <option value="">All categories</option><option value="electronics">Electronics</option><option value="office">Office</option><option value="software">Software</option><option value="travel">Travel</option>
          </select>
          <input
            value={country}
            maxLength={2}
            onChange={(event) => setCountry(event.target.value.toUpperCase())}
            placeholder="Country"
            aria-label="Country code"
          />
          <button type="submit" className="primary-button" disabled={loading}>
            {loading ? 'Searching…' : 'Search'}
          </button>
        </form>
      </section>

      <section className="page-panel" aria-label="Search results">
        <div className="results-header">
          <div>
            <span className="overline">Live evidence</span>
            <h3>{results.length ? `${results.length} results` : searched ? 'No products found' : 'Search for a product'}</h3>
          </div>
        </div>

        {loading && results.length === 0 ? (
          <p className="pr-muted" style={{ textAlign:'center', padding:'40px 0' }}>Loading product evidence…</p>
        ) : results.length === 0 ? (
          <div className="empty-state">
            {searched
              ? 'The search provider returned no individual retailer product pages for this query. Try a specific model or product name, then search again.'
              : 'Enter a query above to fetch source-backed product evidence.'}
          </div>
        ) : (
          <div className="product-grid">
            {results.map((result) => (
              <ProductResultCard
                key={result.product_reference || result.id || `${result.source_url}-${result.search_timestamp}`}
                result={result}
                query={query}
              />
            ))}
          </div>
        )}
      </section>
    </>
  )
}

export default ProductSearch
