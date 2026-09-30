// "Recently viewed" strip — product ids kept in localStorage by the product page.
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ProductCard as Card } from '../api'
import { ProductCard } from './ProductCard'

const KEY = 'cc_recent'

export function rememberViewed(id: string) {
  try {
    const ids = JSON.parse(localStorage.getItem(KEY) ?? '[]') as string[]
    localStorage.setItem(KEY, JSON.stringify([id, ...ids.filter((x) => x !== id)].slice(0, 8)))
  } catch {
    /* ignore */
  }
}

function readViewed(): string[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '[]') as string[]
  } catch {
    return []
  }
}

export function RecentlyViewed({ exclude }: { exclude?: string }) {
  const [items, setItems] = useState<Card[]>([])
  useEffect(() => {
    const ids = readViewed().filter((id) => id !== exclude).slice(0, 4)
    if (!ids.length) {
      setItems([])
      return
    }
    api.products().then((all) => setItems(ids.map((id) => all.find((p) => p.product_id === id)).filter((p): p is Card => Boolean(p))))
      .catch(() => setItems([]))
  }, [exclude])
  if (!items.length) return null
  return (
    <section className="section">
      <div className="section-head">
        <h2>Recently viewed</h2>
      </div>
      <div className="grid grid-4">
        {items.map((p, i) => (
          <ProductCard key={p.product_id} product={p} index={i} compact />
        ))}
      </div>
    </section>
  )
}
