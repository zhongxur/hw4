import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export function Nav() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const close = () => setOpen(false)

  return (
    <header className="nav-wrap">
      <div className="ticker" aria-hidden="true">
        <div className="ticker-track">
          {Array.from({ length: 2 }).map((_, i) => (
            <span key={i}>
              New Haven, CT ✦ Bulldog Blue since day one ✦ Ask Dan about any size, any time ✦ Boola Boola ✦
              Game-day ready ✦ 102 styles in the shop ✦&nbsp;
            </span>
          ))}
        </div>
      </div>
      <nav className="nav">
        <Link to="/" className="brand" onClick={close}>
          <span className="brand-badge">C</span>
          <span className="brand-text">
            Campus Customs<small>Yale Bulldog Blue</small>
          </span>
        </Link>
        <button className="nav-toggle" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span />
          <span />
          <span />
        </button>
        <div className={`nav-links ${open ? 'open' : ''}`}>
          <NavLink to="/" end onClick={close}>Home</NavLink>
          <NavLink to="/products" onClick={close}>Products</NavLink>
          <NavLink to="/about" onClick={close}>About Us</NavLink>
          {user ? (
            <>
              <span className="nav-hello">Hi, {user.first_name}</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={async () => {
                  close()
                  await logout()
                  navigate('/')
                }}
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login" onClick={close}>Log in</NavLink>
              <NavLink to="/register" className="btn btn-primary btn-sm" onClick={close}>Create account</NavLink>
            </>
          )}
        </div>
      </nav>
    </header>
  )
}
