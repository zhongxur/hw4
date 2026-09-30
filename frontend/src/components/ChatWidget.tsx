// Floating "Ask Dan" chat panel (bottom-right). Talks to POST /api/chat.
//  * logged in  -> history is loaded from / saved to the DB by the backend
//  * guest      -> history lives in sessionStorage and is sent with each message
//  * every message carries the current page context (which product is open, selected size, ...)
//  * when the agent returns show_on_page=true, its cards replace the Products grid (Problem 7)
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, money } from '../api'
import type { ChatMessage, ChatTurn } from '../api'
import { useAuth } from '../context/AuthContext'
import { useShop } from '../context/ShopContext'
import { Markdown } from './Markdown'

const GUEST_KEY = 'cc_guest_chat'
const STARTERS = ['What hoodies do you have?', 'Navy crewnecks under $60', 'Anything with a bulldog on it?']

function loadGuest(): ChatMessage[] {
  try {
    return JSON.parse(sessionStorage.getItem(GUEST_KEY) ?? '[]') as ChatMessage[]
  } catch {
    return []
  }
}
function saveGuest(msgs: ChatMessage[]) {
  try {
    sessionStorage.setItem(GUEST_KEY, JSON.stringify(msgs.slice(-30)))
  } catch {
    /* ignore */
  }
}

export function ChatWidget() {
  const { user, ready } = useAuth()
  const { pageContext, setChatResults, chatOpen, setChatOpen, pendingQuestion, consumePendingQuestion } = useShop()
  const navigate = useNavigate()
  const location = useLocation()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  // whose conversation `messages` holds — keeps a logged-in chat from leaking into guest storage on logout
  const [owner, setOwner] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [unread, setUnread] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // (re)load history whenever the signed-in user changes
  useEffect(() => {
    if (!ready) return
    setError(null)
    if (user) {
      const who = `user:${user.id}`
      setOwner(who)
      setMessages([])
      api.chatHistory().then(setMessages).catch(() => setMessages([]))
    } else {
      setOwner('guest')
      setMessages(loadGuest())
    }
  }, [user, ready])

  useEffect(() => {
    if (owner === 'guest' && !user) saveGuest(messages)
  }, [messages, owner, user])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending, chatOpen])

  useEffect(() => {
    if (chatOpen) {
      setUnread(false)
      setTimeout(() => inputRef.current?.focus(), 150)
    }
  }, [chatOpen])

  const send = useCallback(
    async (text: string) => {
      const message = text.trim()
      if (!message || sending) return
      setError(null)
      setInput('')
      const mine: ChatMessage = { id: `u${Date.now()}`, role: 'user', content: message, products: [] }
      const history: ChatTurn[] = user
        ? [] // the backend reads a logged-in user's history from the DB
        : messages.map((m) => ({ role: m.role, content: m.content, product_ids: m.products.map((p) => p.product_id) }))
      setMessages((prev) => [...prev, mine])
      setSending(true)
      try {
        const res = await api.chat(message, pageContext, history)
        setMessages((prev) => [
          ...prev,
          { id: res.run_id, role: 'assistant', content: res.reply, products: res.products, suggestions: res.suggestions },
        ])
        if (res.show_on_page && res.products.length) {
          setChatResults({ label: res.search_label || message, products: res.products, runId: res.run_id })
          if (location.pathname !== '/products') navigate('/products?from=chat')
        }
        if (!chatOpen) setUnread(true)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Something went wrong')
      } finally {
        setSending(false)
      }
    },
    [sending, user, messages, pageContext, setChatResults, location.pathname, navigate, chatOpen],
  )

  // "Ask Dan about this" buttons on pages drop a question here
  useEffect(() => {
    if (chatOpen && pendingQuestion && !sending) {
      const q = consumePendingQuestion()
      if (q) void send(q)
    }
  }, [chatOpen, pendingQuestion, sending, consumePendingQuestion, send])

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void send(input)
  }

  const clear = async () => {
    if (user) await api.clearChatHistory().catch(() => undefined)
    setMessages([])
    setChatResults(null)
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')
  const contextLabel =
    pageContext.page === 'product' && pageContext.product_name ? `Looking at: ${pageContext.product_name}` : null

  return (
    <>
      <button
        className={`chat-fab ${chatOpen ? 'hidden' : ''}`}
        onClick={() => setChatOpen(true)}
        aria-label="Open chat with Dan"
      >
        <span className="chat-fab-face">🐾</span>
        <span className="chat-fab-text">Ask Dan</span>
        {unread && <span className="chat-dot" />}
      </button>

      <section className={`chat ${chatOpen ? 'open' : ''}`} aria-label="Shop assistant chat" aria-hidden={!chatOpen} inert={!chatOpen}>
        <header className="chat-head">
          <div className="chat-avatar">D</div>
          <div className="chat-title">
            <strong>Dan · Campus Customs</strong>
            <span>{user ? `Chatting as ${user.first_name} · history saved` : 'Guest · log in to save this chat'}</span>
          </div>
          <button className="icon-btn" title="Clear chat" onClick={clear} aria-label="Clear chat">⟲</button>
          <button className="icon-btn" title="Minimize" onClick={() => setChatOpen(false)} aria-label="Close chat">✕</button>
        </header>

        {contextLabel && <div className="chat-context">👀 {contextLabel}</div>}

        <div className="chat-list" ref={listRef}>
          {messages.length === 0 && (
            <div className="chat-empty">
              <div className="chat-bubble bot">
                <Markdown
                  text={`Hey${user ? ` ${user.first_name}` : ''}! I'm **Dan**. Ask me what we carry, what's in stock in your size, or about any item you're looking at.`}
                />
              </div>
              <div className="chips">
                {STARTERS.map((s) => (
                  <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`chat-row ${m.role}`}>
              <div className={`chat-bubble ${m.role === 'user' ? 'me' : 'bot'}`}>
                {m.role === 'user' ? m.content : <Markdown text={m.content} />}
              </div>
              {m.role === 'assistant' && m.products.length > 0 && (
                <div className="chat-cards">
                  {m.products.slice(0, 6).map((p) => (
                    <Link key={p.product_id} to={`/products/${p.product_id}`} className="mini-card">
                      <img src={p.image_url} alt="" />
                      <span className="mini-name">{p.name}</span>
                      <span className="mini-meta">
                        {money(p.price)} · {p.in_stock ? `${p.total_stock} in stock` : 'sold out'}
                      </span>
                    </Link>
                  ))}
                  {m.products.length > 6 && (
                    <button
                      className="mini-card mini-more"
                      onClick={() => {
                        setChatResults({ label: 'From your chat', products: m.products, runId: String(m.id) })
                        navigate('/products?from=chat')
                      }}
                    >
                      +{m.products.length - 6} more on the page →
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
          {sending && (
            <div className="chat-row assistant pending">
              <div className="chat-bubble bot typing" aria-label="Dan is typing">
                <i />
                <i />
                <i />
              </div>
            </div>
          )}
          {error && <div className="chat-error">⚠️ {error}</div>}
        </div>

        {!sending && lastAssistant?.suggestions && lastAssistant.suggestions.length > 0 && (
          <div className="chips chips-footer">
            {lastAssistant.suggestions.map((s) => (
              <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
            ))}
          </div>
        )}

        <form className="chat-form" onSubmit={onSubmit}>
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            maxLength={1000}
            placeholder={pageContext.page === 'product' ? 'Ask about this item…' : 'Ask about sizes, stock, styles…'}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send(input)
              }
            }}
          />
          <button className="send" disabled={sending || !input.trim()} aria-label="Send">➤</button>
        </form>
      </section>
    </>
  )
}
