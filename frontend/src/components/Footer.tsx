import { Link } from 'react-router-dom'

export function Footer() {
  return (
    <footer className="footer">
      <div className="footer-inner">
        <div>
          <div className="footer-brand">Campus Customs</div>
          <p>Bulldog Blue gear, printed and folded a short walk from Old Campus.</p>
        </div>
        <div className="footer-links">
          <Link to="/products">Shop all</Link>
          <Link to="/products?category=Hoodies">Hoodies</Link>
          <Link to="/products?category=Crewnecks">Crewnecks</Link>
          <Link to="/about">Our story</Link>
        </div>
        <p className="footer-note">
          MGT 409 class project · a demo storefront, not an official Yale site · no real orders are taken.
        </p>
      </div>
    </footer>
  )
}
