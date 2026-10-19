import { useEffect, useRef, useState } from 'react'
import PageHeader from '../components/PageHeader'
import ProductResultCard from '../components/assistant/ProductResultCard'
import { getAssistantStatus, sendAssistantChat } from '../services/api'

const SUGGESTED_PROMPTS = [
  'Find a laptop under $800.',
  'Find headphones with long battery life.',
  'Explain the risks of this purchase.',
]

function AssistantChat() {
  const [budget, setBudget] = useState('')
  const [category, setCategory] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [country, setCountry] = useState('US')
  const [status, setStatus] = useState(null)
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatError, setChatError] = useState('')
  const [messages, setMessages] = useState([])
  const messagesRef = useRef(null)

  useEffect(() => {
    getAssistantStatus().then(setStatus).catch(() => setStatus(null))
  }, [])

  useEffect(() => {
    messagesRef.current?.scrollTo({
      top: messagesRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, chatLoading])

  const runTurn = async (rawText) => {
    const text = String(rawText ?? '').trim()
    if (!text || chatLoading) return
    const userMessage = { role: 'user', content: text }
    const history = [...messages, userMessage]
    setMessages(history)
    setChatInput('')
    setChatError('')
    setChatLoading(true)
    try {
      const response = await sendAssistantChat({
        query: text,
        messages: history,
        budget,
        category,
        currency,
        country,
      })
      setMessages([
        ...history,
        {
          role: 'assistant',
          content: response.reply,
          search_results: response.search_results || [],
        },
      ])
    } catch (error) {
      setChatError(error.message || 'Assistant request failed.')
    } finally {
      setChatLoading(false)
    }
  }

  const sendMessage = (event) => {
    event?.preventDefault()
    runTurn(chatInput)
  }

  const handleInputKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      runTurn(chatInput)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Autonomous Agentic Commerce"
        title="Assistant Chat"
        description="Ask for live product evidence. Answers are AI-generated and advisory; PayShield authorization always runs on the server."
      />
      <div className="assistant-container">
        <section className="assistant-controls-bar panel">
          <div className="assistant-context-controls">
            <input type="number" min="1" value={budget} onChange={(event) => setBudget(event.target.value)} placeholder="Max budget" aria-label="Maximum budget" />
            <select value={currency} onChange={(event) => setCurrency(event.target.value)} aria-label="Currency">
              <option>USD</option><option>EUR</option><option>GBP</option><option>INR</option>
            </select>
            <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Product category">
              <option value="">All categories</option><option value="electronics">Electronics</option><option value="office">Office</option><option value="software">Software</option><option value="travel">Travel</option>
            </select>
            <input value={country} maxLength={2} onChange={(event) => setCountry(event.target.value.toUpperCase())} placeholder="Country" aria-label="Country code" />
          </div>
          <div className="assistant-status-pill">
            <span className={`pulse-dot ${status?.live_search_configured ? '' : 'offline'}`} />
            <small>{status?.provider || 'Assistant unavailable'}</small>
          </div>
        </section>

        <section className="assistant-chat-panel panel">
          <div className="chat-messages-container" ref={messagesRef}>
            {!messages.length && (
              <div className="chat-empty-state">
                <p>
                  Ask about a product, budget, or feature. Live search evidence will appear with the answer.
                  Looking for a structured comparison instead? Use <strong>Product Search</strong>.
                </p>
                <div className="chat-suggestions">
                  {SUGGESTED_PROMPTS.map((prompt) => (
                    <button
                      type="button"
                      key={prompt}
                      className="outline-button small-button"
                      onClick={() => runTurn(prompt)}
                      disabled={chatLoading}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`chat-message ${message.role}-message`}>
                <div className="chat-bubble">
                  <p>{message.content}</p>
                  {message.search_results?.map((result) => (
                    <ProductResultCard
                      key={result.product_reference || result.id || `${result.source_url}-${result.search_timestamp}`}
                      result={result}
                      query={message.content}
                    />
                  ))}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div className="chat-message assistant-message">
                <div className="chat-bubble chat-loading">Searching and thinking…</div>
              </div>
            )}
          </div>
          <form onSubmit={sendMessage} className="chat-input-bar">
            <textarea
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="Ask for live product evidence…"
              aria-label="Assistant chat input"
              disabled={chatLoading}
              rows={2}
            />
            <button type="submit" className="primary-button" disabled={chatLoading || !chatInput.trim()}>
              {chatLoading ? 'Sending…' : 'Send'}
            </button>
          </form>
          {chatError && (
            <div className="api-error chat-error" role="alert">
              <strong>Assistant unavailable</strong>
              <p>{chatError}</p>
            </div>
          )}
        </section>
      </div>
    </>
  )
}

export default AssistantChat
