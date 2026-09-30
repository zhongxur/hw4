import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { Facets, ProductCard as Card } from '../api'
import { ProductCard } from '../components/ProductCard'
import { usePageContext, useShop } from '../context/ShopContext'

const SORTS: [string, string][] = [
  ['featured', 'Best match'],
  ['price_asc', 'Price: low → high'],
  ['price_desc', 'Price: high → low'],
  ['name', 'Name A–Z'],
]

export default function Products() {
  const [params, setParams] = useSearchParams()
  const { chatResults, setChatResults, askDan } = useShop()
  const [facets, setFacets] = useState<Facets | null>(null)
  const [products, setProducts] = useState<Card[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const q = params.get('q') ?? ''
  const category = params.get('category') ?? ''
  const size = params.get('size') ?? ''
  const sort = params.get('sort') ?? 'featured'
  const inStock = params.get('in_stock') === '1'
  const fromChat = params.get('from') === 'chat' && chatResults !== null
  const [draft, setDraft] = useState(q)

  useEffect(() => {
    setDraft(q)
  }, [q])
  useEffect(() => {
    api.facets().then(setFacets).catch(() => setFacets(null))
  }, [])

  useEffect(() => {
    if (fromChat) return
    setLoading(true)
    setError(null)
    const t = setTimeout(() => {
      api
        .products({ q, category, size, sort, in_stock: inStock })
        .then(setProducts)
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false))
    }, 120)
    return () => clearTimeout(t)
  }, [q, category, size, sort, inStock, fromChat])

  const shown = fromChat ? chatResults!.products : products
  usePageContext({
    path: '/products',
    page: 'products',
    visible_product_ids: shown.slice(0, 24).map((p) => p.product_id),
  })

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    next.delete('from')
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)))
    setParams(next, { replace: true })
  }

  const clearChat = () => {
    setChatResults(null)
    update({})
  }

  const activeFilters = useMemo(
    () => [q && `“${q}”`, category, size && `Size ${size}`, inStock && 'In stock'].filter(Boolean) as string[],
    [q, category, size, inStock],
  )

  return (
    <div className="products-page">
      <header className="page-head">
        <span className="eyebrow">The shop</span>
        <h1>{fromChat ? chatResults!.label : category || 'All Bulldog Blue gear'}</h1>
        <p className="muted">
          {fromChat
            ? `${shown.length} item${shown.length === 1 ? '' : 's'} picked by Dan from your chat`
            : loading
              ? 'Loading…'
              : `${shown.length} style${shown.length === 1 ? '' : 's'}${activeFilters.length ? ` · ${activeFilters.join(' · ')}` : ''}`}
        </p>
      </header>

      {fromChat && (
        <div className="chat-banner" role="status">
          <span className="chat-banner-icon">🐾</span>
          <div>
            <strong>Results from your chat with Dan</strong>
            <span>Click any card for sizes and stock. Keep chatting to refine the list.</span>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={clearChat}>Show all products</button>
        </div>
      )}

      {!fromChat && (
        <div className="filters">
          <form
            className="search"
            onSubmit={(e) => {
              e.preventDefault()
              update({ q: draft.trim() || null })
            }}
          >
            <span aria-hidden="true">⌕</span>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Search “bulldog”, “Morse”, “navy”…"
              aria-label="Search products"
            />
            {draft && (
              <button type="button" className="icon-btn" aria-label="Clear search" onClick={() => { setDraft(''); update({ q: null }) }}>
                ✕
              </button>
            )}
          </form>
          <div className="chips" role="group" aria-label="Category">
            <button className={`chip ${!category ? 'active' : ''}`} onClick={() => update({ category: null })}>All</button>
            {facets?.categories.map((c) => (
              <button key={c.name} className={`chip ${category === c.name ? 'active' : ''}`} onClick={() => update({ category: c.name })}>
                {c.name} <small>{c.count}</small>
              </button>
            ))}
          </div>
          <div className="filter-row">
            <div className="sizes" role="group" aria-label="In stock in size">
              <span className="filter-label">In my size</span>
              {(facets?.sizes ?? ['XS', 'S', 'M', 'L', 'XL', 'XXL']).map((s) => (
                <button key={s} className={`size-pill ${size === s ? 'active' : ''}`} onClick={() => update({ size: size === s ? null : s })}>
                  {s}
                </button>
              ))}
            </div>
            <label className="toggle">
              <input type="checkbox" checked={inStock} onChange={(e) => update({ in_stock: e.target.checked ? '1' : null })} />
              <span>Hide sold out</span>
            </label>
            <select value={sort} onChange={(e) => update({ sort: e.target.value === 'featured' ? null : e.target.value })} aria-label="Sort">
              {SORTS.map(([v, label]) => (
                <option key={v} value={v}>{label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {error && <div className="alert">Couldn't load products: {error}. Is the backend running on :8000?</div>}

      {!loading && !fromChat && shown.length === 0 && !error && (
        <div className="empty">
          <p>No styles match those filters.</p>
          <button className="btn btn-ghost" onClick={() => askDan(`I'm looking for ${q || category || 'something'} — what do you have?`)}>
            🐾 Ask Dan instead
          </button>
        </div>
      )}

      <div className={`grid ${loading && !fromChat ? 'grid-loading' : ''}`} key={fromChat ? chatResults!.runId : 'catalogue'}>
        {shown.map((p, i) => (
          <ProductCard key={p.product_id} product={p} index={i} />
        ))}
      </div>
    </div>
  )
}
