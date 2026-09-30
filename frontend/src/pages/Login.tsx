import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { usePageContext } from '../context/ShopContext'

export default function Login() {
  usePageContext({ path: '/login', page: 'login' })
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await login(email, password)
      navigate((location.state as { from?: string } | null)?.from ?? '/products')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  if (user) {
    return (
      <div className="auth">
        <div className="auth-card">
          <h1>You're logged in</h1>
          <p className="muted">Signed in as {user.email}.</p>
          <Link to="/products" className="btn btn-primary">Keep shopping</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="auth">
      <form className="auth-card" onSubmit={submit} noValidate>
        <span className="eyebrow">Welcome back</span>
        <h1>Log in</h1>
        <p className="muted">Your chats with Dan are saved to your account.</p>
        <label>
          Email
          <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <div className="pw">
            <input
              type={show ? 'text' : 'password'}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button type="button" className="pw-toggle" onClick={() => setShow((s) => !s)}>{show ? 'Hide' : 'Show'}</button>
          </div>
        </label>
        {error && <div className="alert" role="alert">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy || !email || !password}>
          {busy ? 'Logging in…' : 'Log in'}
        </button>
        <p className="auth-alt">
          New here? <Link to="/register">Create an account</Link>
        </p>
      </form>
    </div>
  )
}
