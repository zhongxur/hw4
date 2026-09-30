import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { usePageContext } from '../context/ShopContext'

export default function Register() {
  usePageContext({ path: '/register', page: 'register' })
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ first_name: '', last_name: '', email: '', password: '', confirm: '' })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const tooShort = form.password.length > 0 && form.password.length < 8
  const mismatch = form.confirm.length > 0 && form.confirm !== form.password
  const valid =
    form.first_name.trim() && form.last_name.trim() && /\S+@\S+\.\S+/.test(form.email) && form.password.length >= 8 && !mismatch && form.confirm

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!valid) return
    setError(null)
    setBusy(true)
    try {
      const { confirm: _confirm, ...body } = form
      void _confirm
      await register(body)
      navigate('/products')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the account')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <form className="auth-card" onSubmit={submit} noValidate>
        <span className="eyebrow">Join the shop</span>
        <h1>Create account</h1>
        <p className="muted">Save your chats with Dan and pick up where you left off.</p>
        <div className="two">
          <label>
            First name
            <input autoComplete="given-name" value={form.first_name} onChange={set('first_name')} required />
          </label>
          <label>
            Last name
            <input autoComplete="family-name" value={form.last_name} onChange={set('last_name')} required />
          </label>
        </div>
        <label>
          Email
          <input type="email" autoComplete="email" value={form.email} onChange={set('email')} required />
        </label>
        <label>
          Password
          <input type="password" autoComplete="new-password" value={form.password} onChange={set('password')} required />
          <small className={tooShort ? 'hint bad' : 'hint'}>At least 8 characters.</small>
        </label>
        <label>
          Confirm password
          <input type="password" autoComplete="new-password" value={form.confirm} onChange={set('confirm')} required />
          {mismatch && <small className="hint bad">Passwords don't match.</small>}
        </label>
        {error && <div className="alert" role="alert">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy || !valid}>
          {busy ? 'Creating…' : 'Create account'}
        </button>
        <p className="auth-alt">
          Already have one? <Link to="/login">Log in</Link>
        </p>
      </form>
    </div>
  )
}
