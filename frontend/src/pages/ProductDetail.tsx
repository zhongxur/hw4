import { useEffect, useState } from 'react'
import type { MouseEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, money } from '../api'
import type { ProductCard as Card, ProductDetail as Detail } from '../api'
import { ProductCard, swatch } from '../components/ProductCard'
import { RecentlyViewed, rememberViewed } from '../components/RecentlyViewed'
import { usePageContext, useShop } from '../context/ShopContext'

const LOW = 3

export default function ProductDetail() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { askDan, chatResults } = useShop()
  const [product, setProduct] = useState<Detail | null>(null)
  const [related, setRelated] = useState<Card[]>([])
  const [error, setError] = useState<string | null>(null)
  const [size, setSize] = useState<string | null>(null)
  const [zoom, setZoom] = useState<{ x: number; y: number } | null>(null)

  useEffect(() => {
    setProduct(null)
    setError(null)
    setSize(null)
    api
      .product(id)
      .then((p) => {
        setProduct(p)
        rememberViewed(p.product_id)
        return api.products({ category: p.category, in_stock: true })
      })
      .then((list) => setRelated(list.filter((p) => p.product_id !== id).slice(0, 4)))
      .catch((e: Error) => setError(e.message))
  }, [id])

  usePageContext({
    path: `/products/${id}`,
    page: 'product',
    product_id: id,
    product_name: product?.name ?? null,
    selected_size: size,
  })

  if (error) {
    return (
      <div className="empty">
        <p>We couldn't find that item ({error}).</p>
        <Link to="/products" className="btn btn-primary">Back to the shop</Link>
      </div>
    )
  }
  if (!product) return <div className="detail skeleton" aria-busy="true" />

  const chosen = product.sizes.find((s) => s.size === size)
  const onMove = (e: MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    setZoom({ x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 })
  }

  return (
    <div className="detail-page">
      <nav className="crumbs">
        <button className="link-arrow" onClick={() => (chatResults ? navigate('/products?from=chat') : navigate(-1))}>
          ← Back
        </button>
        <span>/</span>
        <Link to={`/products?category=${encodeURIComponent(product.category)}`}>{product.category}</Link>
      </nav>

      <div className="detail">
        <div
          className={`detail-img ${zoom ? 'zooming' : ''}`}
          onMouseMove={onMove}
          onMouseLeave={() => setZoom(null)}
        >
          <img
            src={product.image_url}
            alt={product.name}
            style={zoom ? { transformOrigin: `${zoom.x}% ${zoom.y}%` } : undefined}
          />
          {!product.in_stock && <span className="badge badge-out big">Sold out</span>}
        </div>

        <div className="detail-info">
          <span className="eyebrow">{product.garment_type}</span>
          <h1>{product.name}</h1>
          <div className="detail-price">{money(product.price)}</div>

          <div className="detail-colors">
            {product.colors.map((c) => (
              <span key={c} className="color-tag">
                <i style={{ background: swatch(c) }} />
                {c}
              </span>
            ))}
          </div>

          <p className="detail-desc">{product.description}</p>

          <div className="size-block">
            <div className="size-head">
              <span className="filter-label">Size</span>
              <span className="muted">{product.total_stock} in stock across all sizes</span>
            </div>
            <div className="size-grid" role="radiogroup" aria-label="Choose a size">
              {product.sizes.map((s) => (
                <button
                  key={s.size}
                  role="radio"
                  aria-checked={size === s.size}
                  className={`size-btn ${size === s.size ? 'active' : ''} ${s.in_stock ? '' : 'out'}`}
                  onClick={() => setSize(s.size)}
                  title={s.in_stock ? `${s.quantity} left` : 'Sold out'}
                >
                  <strong>{s.size}</strong>
                  <small>{!s.in_stock ? 'sold out' : s.quantity <= LOW ? `only ${s.quantity}` : `${s.quantity} left`}</small>
                </button>
              ))}
            </div>
            <div className={`stock-line ${chosen ? (chosen.in_stock ? (chosen.quantity <= LOW ? 'low' : 'ok') : 'out') : ''}`} aria-live="polite">
              {!chosen && 'Pick a size to see live stock.'}
              {chosen && chosen.in_stock && chosen.quantity > LOW && `✓ ${chosen.quantity} in stock in ${chosen.size} — ready to go.`}
              {chosen && chosen.in_stock && chosen.quantity <= LOW && `⚡ Only ${chosen.quantity} left in ${chosen.size}.`}
              {chosen && !chosen.in_stock && `✕ ${chosen.size} is sold out.`}
            </div>
          </div>

          <div className="detail-actions">
            {chosen && !chosen.in_stock ? (
              <button className="btn btn-primary" onClick={() => askDan(`${chosen.size} is sold out in this one — what else could I get in ${chosen.size}?`)}>
                🐾 Find me something similar in {chosen.size}
              </button>
            ) : (
              <button className="btn btn-primary" onClick={() => askDan(size ? `Is this in stock in ${size}?` : 'Which sizes of this are in stock?')}>
                🐾 Ask Dan about this item
              </button>
            )}
            <button className="btn btn-ghost" onClick={() => askDan('Do you have this in another color?')}>Other colors?</button>
          </div>
          <p className="fine">Class demo shop — checkout is disabled. Stock shown is live from the store database.</p>
        </div>
      </div>

      {related.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>More {product.category.toLowerCase()} in stock</h2>
          </div>
          <div className="grid grid-4">
            {related.map((p, i) => (
              <ProductCard key={p.product_id} product={p} index={i} compact />
            ))}
          </div>
        </section>
      )}
      <RecentlyViewed exclude={product.product_id} />
    </div>
  )
}
