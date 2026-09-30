import { Link } from 'react-router-dom'
import { usePageContext } from '../context/ShopContext'

export default function About() {
  usePageContext({ path: '/about', page: 'about' })
  return (
    <div className="about">
      <header className="page-head">
        <span className="eyebrow">About us</span>
        <h1>A local shop that bleeds Bulldog Blue.</h1>
      </header>

      <div className="about-grid">
        <div className="about-copy">
          <p className="lede">
            Campus Customs started with a simple idea: the shirt you wear to your first seminar, your first
            Harvard–Yale game and your reunion should come from people who actually live here.
          </p>
          <p>
            We're a New Haven shop, not a warehouse three states away. We carry the classics — the heavyweight
            crewneck, the big-letter hoodie, the old-school Y — next to newer pieces like college quarter-zips,
            vintage-wash bulldogs and the tee that settles this year's rivalry.
          </p>
          <p>
            Every one of the fourteen residential colleges gets its own crest, and every sport gets its own
            left-chest mark, so you can rep Morse or rowing or both. When something sells out in your size, we'll
            tell you straight and point you to what we do have.
          </p>
          <p>
            New this year: <strong>Dan</strong>, our online shop assistant. Ask Dan the questions you'd ask at the
            register — “Is this in a medium?”, “Got anything navy under sixty bucks?” — and he'll check the real
            inventory and put the matching gear right on the page.
          </p>
          <Link to="/products" className="btn btn-primary">Browse the shop</Link>
        </div>

        <aside className="about-cards">
          <div className="about-card">
            <span className="big-num">102</span>
            <span>styles on the floor</span>
          </div>
          <div className="about-card">
            <span className="big-num">14</span>
            <span>residential college crests</span>
          </div>
          <div className="about-card">
            <span className="big-num">XS–XXL</span>
            <span>sizes, stock shown live</span>
          </div>
          <div className="about-card accent">
            <span>“For God, for Country, and for Yale” — and for the parents who need a gift before the train home.</span>
          </div>
        </aside>
      </div>
    </div>
  )
}
