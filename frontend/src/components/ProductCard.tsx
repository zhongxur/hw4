import { Link } from 'react-router-dom'
import { money } from '../api'
import type { ProductCard as Card } from '../api'

export function stockBadge(p: Pick<Card, 'in_stock' | 'total_stock'>) {
  if (!p.in_stock) return <span className="badge badge-out">Sold out</span>
  if (p.total_stock <= 12) return <span className="badge badge-low">Low stock</span>
  return null
}

export function ProductCard({ product, index = 0, compact = false }: { product: Card; index?: number; compact?: boolean }) {
  return (
    <Link
      to={`/products/${product.product_id}`}
      className={`card ${compact ? 'card-compact' : ''} ${product.in_stock ? '' : 'card-out'}`}
      style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}
      data-product-id={product.product_id}
    >
      <div className="card-img">
        <img src={product.image_url} alt={product.name} loading="lazy" />
        {stockBadge(product)}
      </div>
      <div className="card-body">
        <div className="card-eyebrow">{product.category}</div>
        <div className="card-title">{product.name}</div>
        {!compact && <p className="card-desc">{product.short_description}</p>}
        <div className="card-foot">
          <span className="price">{money(product.price)}</span>
          <span className="swatches" aria-label={product.colors.join(', ')}>
            {product.colors.slice(0, 4).map((c) => (
              <i key={c} title={c} style={{ background: swatch(c) }} />
            ))}
          </span>
        </div>
      </div>
    </Link>
  )
}

// DB colours are free text ("heather gray", "navy blue"); map the common words to a swatch.
const SWATCHES: [string, string][] = [
  ['navy', '#14284b'], ['royal', '#1d4fbf'], ['blue', '#2a64b8'], ['heather', '#b9b9b4'], ['charcoal', '#46474a'],
  ['gray', '#9a9b9e'], ['grey', '#9a9b9e'], ['white', '#ffffff'], ['black', '#1b1b1b'], ['red', '#c0322e'],
  ['green', '#2f7a47'], ['yellow', '#f1c83a'], ['gold', '#c9a23a'], ['coral', '#ef8a74'], ['pink', '#f2a6c0'],
  ['cream', '#efe6cf'], ['oatmeal', '#ded2bb'], ['maroon', '#6d1f2b'], ['orange', '#e2742b'], ['brown', '#7a5236'],
  ['purple', '#6b4ba1'], ['khaki', '#c3b089'], ['silver', '#c9ccd1'],
]
export function swatch(color: string): string {
  const c = color.toLowerCase()
  return SWATCHES.find(([k]) => c.includes(k))?.[1] ?? '#d9d4c7'
}
