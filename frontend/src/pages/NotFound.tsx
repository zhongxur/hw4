import { Link } from 'react-router-dom'
import { usePageContext } from '../context/ShopContext'

export default function NotFound() {
  usePageContext({ path: window.location.pathname, page: 'other' })
  return (
    <div className="empty">
      <h1>Lost on Old Campus?</h1>
      <p>That page doesn't exist.</p>
      <Link to="/products" className="btn btn-primary">Back to the shop</Link>
    </div>
  )
}
