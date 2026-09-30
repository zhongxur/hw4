import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { ProductCard as Card } from '../api'
import { ProductCard } from '../components/ProductCard'
import { RecentlyViewed } from '../components/RecentlyViewed'
import { usePageContext, useShop } from '../context/ShopContext'

const FEATURED = [
  'boola-boola-t-shirt', 'basic-hoodie-big-yale', 'district-vit-crewneck-vintage-bulldog',
  'brooks-brothers-bomber-jacket-yale', 'champion-reverse-weave-crewneck', 'morse-1-4-zip',
  '2025-yale-vs-harvard-t-shirt', 'district-vit-hoodie-vintage-sailor-bulldog',
]
const CATEGORY_BLURBS: Record<string, string> = {
  Hoodies: 'Pullovers & full-zips for the walk up Science Hill.',
  Crewnecks: 'Classic fleece, college crests, vintage bulldogs.',
  'T-Shirts': 'Game-day tees, colleges and a little Harvard trash talk.',
  'Quarter-Zips': 'Residential-college quarter-zips for the seminar look.',
  'Jackets & Fleece': 'Layers built for a New Haven February.',
  'Long Sleeve': 'Performance long sleeves for the morning run.',
}

export default function Home() {
  usePageContext({ path: '/', page: 'home' })
  const { askDan } = useShop()
  const [all, setAll] = useState<Card[]>([])

  useEffect(() => {
    api.products().then(setAll).catch(() => setAll([]))
  }, [])

  const featured = useMemo(
    () => FEATURED.map((id) => all.find((p) => p.product_id === id)).filter((p): p is Card => Boolean(p)),
    [all],
  )
  const categories = useMemo(() => {
    const seen = new Map<string, { count: number; image: string }>()
    for (const p of all) {
      const c = seen.get(p.category)
      if (c) c.count += 1
      else seen.set(p.category, { count: 1, image: p.image_url })
    }
    return [...seen.entries()].sort((a, b) => b[1].count - a[1].count)
  }, [all])
  const hero = featured.slice(0, 3)

  return (
    <div className="home">
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">New Haven, Connecticut</span>
          <h1>
            Wear the <em>Blue.</em>
            <br />
            Own the walk.
          </h1>
          <p className="lede">
            Campus Customs is the neighborhood shop for Bulldog Blue — hoodies, crewnecks, college crests and
            game-day tees for students, alumni and the parents who come to visit them.
          </p>
          <div className="hero-cta">
            <Link to="/products" className="btn btn-primary">Shop all 102 styles</Link>
            <button className="btn btn-ghost" onClick={() => askDan('What would you recommend for a first-year student?')}>
              🐾 Ask Dan what to get
            </button>
          </div>
          <ul className="hero-proof">
            <li><strong>6</strong> sizes, XS–XXL</li>
            <li><strong>Live</strong> stock by size</li>
            <li><strong>14</strong> residential colleges</li>
          </ul>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="pennant">YALE</div>
          {hero.map((p, i) => (
            <Link key={p.product_id} to={`/products/${p.product_id}`} className={`hero-tile t${i}`} tabIndex={-1}>
              <img src={p.image_url} alt="" />
            </Link>
          ))}
          <div className="stamp">
            BOOLA
            <br />
            BOOLA
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Shop by category</h2>
          <Link to="/products" className="link-arrow">See everything →</Link>
        </div>
        <div className="cat-grid">
          {categories.map(([name, info], i) => (
            <Link key={name} to={`/products?category=${encodeURIComponent(name)}`} className="cat-tile" style={{ animationDelay: `${i * 60}ms` }}>
              <img src={info.image} alt="" loading="lazy" />
              <div>
                <h3>{name}</h3>
                <p>{CATEGORY_BLURBS[name] ?? ''}</p>
                <span className="cat-count">{info.count} styles</span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Fresh off the press</h2>
          <span className="muted">Shop favorites this term</span>
        </div>
        <div className="grid">
          {featured.map((p, i) => (
            <ProductCard key={p.product_id} product={p} index={i} />
          ))}
        </div>
      </section>

      <RecentlyViewed />

      <section className="promise">
        <div>
          <h3>Real stock, not guesses</h3>
          <p>Every size on the site — and every answer from Dan — is read straight from our inventory.</p>
        </div>
        <div>
          <h3>Ask like you would at the counter</h3>
          <p>“Got this in pink?” “Navy crewnecks under $60?” Dan pulls the answer and the cards onto the page.</p>
        </div>
        <div>
          <h3>Made for the whole family</h3>
          <p>From XS to XXL, and from first-years to the Class of ’79 coming back for The Game.</p>
        </div>
      </section>
    </div>
  )
}
