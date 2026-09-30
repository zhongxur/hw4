"""tools.py — database access for the shop and the plain functions behind the agent's tools.

Everything here reads `data/campus_customs.db` (SQLite) directly. agent.py wraps the public
lookup functions as PydanticAI tools; main.py reuses the same functions for the REST API, so
the website and the chatbot can never disagree about a price or a stock level.

    Catalogue    load_catalogue, product_card, product_detail, categories
    Agent tools  search_products, get_product_info, check_stock, find_alternatives
    Users/chat   get_customer, load_chat_history, save_chat_message

Limits that matter for cost or accuracy are the ALL-CAPS constants below.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional

from models import (
    Alternatives,
    CustomerInfo,
    NotFound,
    ProductCard,
    ProductDetail,
    ProductInfo,
    ProductMatch,
    SearchResult,
    SizeStock,
    StockCheck,
)

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("CAMPUS_DATA_DIR", PROJECT_DIR / "data"))
DB_PATH = Path(os.environ.get("CAMPUS_DB", DATA_DIR / "campus_customs.db"))
IMAGES_URL_PREFIX = "/images"          # main.py mounts data/products here

# --- limits ----------------------------------------------------------------
MAX_SEARCH_RESULTS = 12      # hard cap on products a search tool returns to the model
DEFAULT_SEARCH_RESULTS = 8
MAX_ALTERNATIVES = 4
SHORT_DESC_CHARS = 110       # card / tool snippet length
LOW_STOCK = 3                # "only N left" threshold used by the front end and the prompt
SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]

# Shop categories: garment_type in the DB is free text ("pullover hoodie", "quarter-zip pullover
# sweatshirt", ...). The first rule that matches wins, so order matters.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Quarter-Zips", ("quarter-zip", "1/4 zip", "1-4-zip")),
    ("Hoodies", ("hood",)),
    ("Jackets & Fleece", ("jacket", "fleece")),
    ("T-Shirts", ("t-shirt", "tee")),
    ("Long Sleeve", ("long-sleeve", "long sleeve")),
    ("Crewnecks", ("crew", "mockneck", "sweatshirt")),
]

# Words shoppers use -> words that appear in the catalogue.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "hoodie": ("hood", "hoodie", "hooded"),
    "hoody": ("hood", "hoodie", "hooded"),
    "sweatshirt": ("sweatshirt", "crewneck", "crew", "hood"),
    "sweater": ("sweater", "sweatshirt", "crewneck", "fleece"),
    "crewneck": ("crewneck", "crew"),
    "crew": ("crewneck", "crew"),
    "tee": ("t-shirt", "tee"),
    "tshirt": ("t-shirt", "tee"),
    "t-shirt": ("t-shirt", "tee"),
    "shirt": ("t-shirt", "shirt", "tee"),
    "quarter": ("quarter-zip", "1-4"),
    "zip": ("zip",),
    "jacket": ("jacket", "fleece", "bomber"),
    "coat": ("jacket", "fleece"),
    "fleece": ("fleece",),
    "grey": ("gray", "grey"),
    "gray": ("gray", "grey"),
    "blue": ("blue", "navy"),
    "navy": ("navy",),
    "pink": ("pink", "coral", "rose"),
    "dog": ("bulldog",),
    "bulldog": ("bulldog",),
}
STOPWORDS = {
    "a", "an", "the", "do", "you", "have", "any", "what", "which", "show", "me", "some", "for", "in",
    "of", "and", "or", "with", "i", "want", "need", "looking", "your", "yale", "campus", "customs",
    "is", "are", "there", "please", "under", "over", "below", "than", "less", "cheap", "size", "sizes", "can", "see", "all", "get", "like", "items", "item", "stuff", "gear",
}
# Query words that name a shop category. When one appears (and no explicit category was given)
# the search is narrowed to that category, so "navy crewneck" does not return hoodies.
CATEGORY_WORDS: dict[str, str] = {
    "hoodie": "Hoodies", "hoody": "Hoodies", "hood": "Hoodies", "hooded": "Hoodies",
    "crewneck": "Crewnecks", "crew": "Crewnecks",
    "t-shirt": "T-Shirts", "tshirt": "T-Shirts", "tee": "T-Shirts",
    "quarter-zip": "Quarter-Zips", "quarter": "Quarter-Zips",
    "jacket": "Jackets & Fleece", "fleece": "Jackets & Fleece", "coat": "Jackets & Fleece",
}
FIELD_WEIGHTS = {"name": 3.0, "garment_type": 3.0, "tags": 2.0, "colors": 2.0, "description": 1.0}


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. Put the data pack in hw4/data/ (see README)."
        )
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------
def category_of(garment_type: str) -> str:
    g = garment_type.lower()
    for label, needles in CATEGORY_RULES:
        if any(n in g for n in needles):
            return label
    return "Other"


def _short(text: str, n: int = SHORT_DESC_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def _size_key(size: str) -> int:
    return SIZE_ORDER.index(size) if size in SIZE_ORDER else len(SIZE_ORDER)


@lru_cache(maxsize=1)
def _catalogue_rows() -> tuple[dict[str, Any], ...]:
    """Catalogue text never changes while the server runs, so it is read once and cached.
    Stock is NOT cached — it is always read fresh (see _stock)."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM catalogue ORDER BY name").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["colors"] = json.loads(d["colors"] or "[]")
        d["search_tags"] = json.loads(d["search_tags"] or "[]")
        d["category"] = category_of(d["garment_type"])
        d["image_url"] = f"{IMAGES_URL_PREFIX}/{Path(d['image_file_path']).name}"
        out.append(d)
    return tuple(out)


def _catalogue_by_id() -> dict[str, dict[str, Any]]:
    return {r["product_id"]: r for r in _catalogue_rows()}


def _stock(product_ids: Optional[list[str]] = None) -> dict[str, list[SizeStock]]:
    sql = "SELECT product_id, size, quantity FROM inventory"
    args: list[Any] = []
    if product_ids is not None:
        if not product_ids:
            return {}
        sql += f" WHERE product_id IN ({','.join('?' * len(product_ids))})"
        args = list(product_ids)
    by_id: dict[str, list[SizeStock]] = {}
    with connect() as conn:
        for r in conn.execute(sql, args):
            by_id.setdefault(r["product_id"], []).append(
                SizeStock(size=r["size"], quantity=r["quantity"], in_stock=r["quantity"] > 0)
            )
    for sizes in by_id.values():
        sizes.sort(key=lambda s: _size_key(s.size))
    return by_id


def product_card(row: dict[str, Any], sizes: list[SizeStock]) -> ProductCard:
    total = sum(s.quantity for s in sizes)
    return ProductCard(
        product_id=row["product_id"], name=row["name"], garment_type=row["garment_type"],
        category=row["category"], price=row["price"], image_url=row["image_url"],
        short_description=_short(row["description"]), colors=row["colors"],
        total_stock=total, in_stock=total > 0,
    )


def load_catalogue() -> list[ProductCard]:
    stock = _stock()
    return [product_card(r, stock.get(r["product_id"], [])) for r in _catalogue_rows()]


def cards_for(product_ids: list[str]) -> list[ProductCard]:
    """Cards in the given order, silently skipping unknown ids."""
    rows = _catalogue_by_id()
    known = [pid for pid in dict.fromkeys(product_ids) if pid in rows]
    stock = _stock(known)
    return [product_card(rows[pid], stock.get(pid, [])) for pid in known]


def product_detail(product_id: str) -> Optional[ProductDetail]:
    row = _catalogue_by_id().get(product_id)
    if row is None:
        return None
    sizes = _stock([product_id]).get(product_id, [])
    card = product_card(row, sizes)
    return ProductDetail(**card.model_dump(), description=row["description"],
                         search_tags=row["search_tags"], sizes=sizes)


def categories() -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for r in _catalogue_rows():
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    order = [label for label, _ in CATEGORY_RULES] + ["Other"]
    return [{"name": c, "count": counts[c]} for c in order if c in counts]


def all_colors() -> list[str]:
    seen: dict[str, int] = {}
    for r in _catalogue_rows():
        for c in r["colors"]:
            seen[c] = seen.get(c, 0) + 1
    return [c for c, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


# ---------------------------------------------------------------------------
# Search (shared by the Products page search box and the agent's search tool)
# ---------------------------------------------------------------------------
def _terms(query: str) -> list[tuple[str, ...]]:
    """Each query word becomes a tuple of alternatives (synonyms + crude singular)."""
    words = re.findall(r"[a-z0-9][a-z0-9\-/]*", query.lower())
    out: list[tuple[str, ...]] = []
    for w in words:
        if w in STOPWORDS or len(w) < 2 or w.isdigit():
            continue
        stems = {w}
        if w.endswith("ies") and len(w) > 4:
            stems.add(w[:-3] + "y")
        if w.endswith("es") and len(w) > 4:
            stems.add(w[:-2])
        if w.endswith("s") and len(w) > 3:
            stems.add(w[:-1])
        alts: set[str] = set(stems)
        for s in stems:
            alts.update(SYNONYMS.get(s, ()))
        out.append(tuple(sorted(alts)))
    return out


def implied_category(query: str) -> tuple[Optional[str], str]:
    """('Hoodies', 'navy') for 'navy hoodies'. Returns (None, query) when no category word is used."""
    words = re.findall(r"[a-z0-9][a-z0-9\-/]*", query.lower())
    found: Optional[str] = None
    rest: list[str] = []
    for w in words:
        stem = w[:-1] if w.endswith("s") and len(w) > 3 else w
        cat = CATEGORY_WORDS.get(w) or CATEGORY_WORDS.get(stem)
        if cat and (found is None or found == cat):
            found = cat
        else:
            rest.append(w)
    if found is None:
        return None, query
    rest = [w for w in rest if w not in {"zip", "zips", "sleeve"}] if found == "Quarter-Zips" else rest
    return found, " ".join(rest)


def _score(row: dict[str, Any], terms: list[tuple[str, ...]]) -> float:
    fields = {
        "name": row["name"].lower(),
        "garment_type": row["garment_type"].lower(),
        "tags": " ".join(row["search_tags"]).lower(),
        "colors": " ".join(row["colors"]).lower(),
        "description": row["description"].lower(),
    }
    total = 0.0
    for alts in terms:
        best = 0.0
        for fname, text in fields.items():
            if any(a in text for a in alts):
                best = max(best, FIELD_WEIGHTS[fname])
        if best == 0.0:
            return 0.0          # every meaningful word must match somewhere (AND search)
        total += best
    return total


def search_catalogue(
    query: str = "",
    category: Optional[str] = None,
    color: Optional[str] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    size: Optional[str] = None,
    in_stock_only: bool = False,
) -> list[tuple[float, ProductCard]]:
    """Score + filter the whole catalogue. Returns (score, card) best first, uncapped."""
    if not category:
        implied, rest = implied_category(query)
        if implied:
            category, query = implied, rest
    terms = _terms(query)
    stock = _stock()
    size = size.upper().strip() if size else None
    color_alts = _terms(color)[0] if color and _terms(color) else None
    hits: list[tuple[float, ProductCard]] = []
    for row in _catalogue_rows():
        if category and row["category"].lower() != category.lower():
            continue
        if max_price is not None and row["price"] > max_price:
            continue
        if min_price is not None and row["price"] < min_price:
            continue
        if color_alts and not any(a in " ".join(row["colors"]).lower() for a in color_alts):
            continue
        sizes = stock.get(row["product_id"], [])
        if size and not any(s.size == size and s.in_stock for s in sizes):
            continue
        score = _score(row, terms) if terms else 1.0
        if score <= 0:
            continue
        card = product_card(row, sizes)
        if in_stock_only and not card.in_stock:
            continue
        hits.append((score, card))
    hits.sort(key=lambda sc: (-sc[0], not sc[1].in_stock, sc[1].name))
    return hits


def _match(card: ProductCard) -> ProductMatch:
    return ProductMatch(
        product_id=card.product_id, name=card.name, category=card.category, price=card.price,
        colors=card.colors, in_stock=card.in_stock, total_stock=card.total_stock,
        short_description=card.short_description,
    )


# ---------------------------------------------------------------------------
# Agent tool bodies (agent.py adds RunContext + audit logging around these)
# ---------------------------------------------------------------------------
def search_products(
    query: str,
    category: Optional[str] = None,
    color: Optional[str] = None,
    max_price: Optional[float] = None,
    size: Optional[str] = None,
    in_stock_only: bool = False,
    limit: int = DEFAULT_SEARCH_RESULTS,
) -> SearchResult:
    limit = max(1, min(int(limit), MAX_SEARCH_RESULTS))
    hits = search_catalogue(query, category=category, color=color, max_price=max_price,
                            size=size, in_stock_only=in_stock_only)
    if not hits and category is None and query:
        # a category word alone ("hoodies") can be stricter than the category filter — retry loosely
        cat = next((c["name"] for c in categories() if _terms(c["name"]) and
                    any(a in query.lower() for a in _terms(c["name"])[0])), None)
        if cat:
            hits = search_catalogue("", category=cat, color=color, max_price=max_price,
                                    size=size, in_stock_only=in_stock_only)
    filters = {k: v for k, v in {"category": category, "color": color, "max_price": max_price,
                                 "size": size, "in_stock_only": in_stock_only or None}.items() if v}
    return SearchResult(query=query, filters=filters, total_matches=len(hits),
                        products=[_match(c) for _, c in hits[:limit]])


def resolve_product(product_ref: str) -> Optional[str]:
    """Accept a product_id or a (partial) product name; return the product_id or None."""
    ref = product_ref.strip()
    rows = _catalogue_by_id()
    if ref in rows:
        return ref
    slug = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
    if slug in rows:
        return slug
    by_name = [r for r in rows.values() if r["name"].lower() == ref.lower()]
    if len(by_name) == 1:
        return by_name[0]["product_id"]
    hits = search_catalogue(ref)
    if hits and (len(hits) == 1 or hits[0][0] > hits[1][0]):
        return hits[0][1].product_id
    return None


def get_product_info(product_ref: str) -> ProductInfo | NotFound:
    pid = resolve_product(product_ref)
    detail = product_detail(pid) if pid else None
    if detail is None:
        return NotFound(error=f"No single product matches '{product_ref}'.",
                        hint="Call search_products to find the right product_id first.")
    return ProductInfo(
        product_id=detail.product_id, name=detail.name, garment_type=detail.garment_type,
        category=detail.category, price=detail.price, description=detail.description,
        colors=detail.colors, sizes=detail.sizes, total_stock=detail.total_stock,
    )


def check_stock(product_ref: str, size: Optional[str] = None) -> StockCheck | NotFound:
    pid = resolve_product(product_ref)
    detail = product_detail(pid) if pid else None
    if detail is None:
        return NotFound(error=f"No single product matches '{product_ref}'.",
                        hint="Call search_products to find the right product_id first.")
    result = StockCheck(
        product_id=detail.product_id, name=detail.name, price=detail.price,
        in_stock_sizes=[s.size for s in detail.sizes if s.in_stock],
        sold_out_sizes=[s.size for s in detail.sizes if not s.in_stock],
        sizes=detail.sizes,
    )
    if size:
        want = size.upper().strip().replace("2XL", "XXL")
        row = next((s for s in detail.sizes if s.size == want), None)
        result.requested_size = want
        result.requested_size_quantity = row.quantity if row else 0
        result.requested_size_in_stock = bool(row and row.in_stock)
    return result


def find_alternatives(product_ref: str, size: Optional[str] = None) -> Alternatives | NotFound:
    """When something is sold out: other sizes of the same item, and similar items that are in stock
    (same category first, sharing a colour or tag scores higher) in the requested size."""
    pid = resolve_product(product_ref)
    rows = _catalogue_by_id()
    if not pid:
        return NotFound(error=f"No single product matches '{product_ref}'.",
                        hint="Call search_products to find the right product_id first.")
    base = rows[pid]
    stock = _stock()
    want = size.upper().strip() if size else None
    scored: list[tuple[float, ProductCard]] = []
    base_tags = {t.lower() for t in base["search_tags"]}
    base_colors = {c.lower() for c in base["colors"]}
    for other in rows.values():
        if other["product_id"] == pid:
            continue
        sizes = stock.get(other["product_id"], [])
        if want and not any(s.size == want and s.in_stock for s in sizes):
            continue
        card = product_card(other, sizes)
        if not card.in_stock:
            continue
        score = 3.0 if other["category"] == base["category"] else 0.0
        score += len(base_colors & {c.lower() for c in other["colors"]})
        score += 0.5 * len(base_tags & {t.lower() for t in other["search_tags"]})
        score -= abs(other["price"] - base["price"]) / 50
        if score > 0:
            scored.append((score, card))
    scored.sort(key=lambda sc: -sc[0])
    own = stock.get(pid, [])
    return Alternatives(
        product_id=pid, name=base["name"], size=want,
        other_sizes_in_stock=[s.size for s in own if s.in_stock and s.size != want],
        similar_products_in_stock=[_match(c) for _, c in scored[:MAX_ALTERNATIVES]],
    )


# ---------------------------------------------------------------------------
# Users + chat history
# ---------------------------------------------------------------------------
def get_customer(user_id: int) -> Optional[CustomerInfo]:
    with connect() as conn:
        r = conn.execute("SELECT id, name, email, first_name, last_name FROM users WHERE id = ?",
                         (user_id,)).fetchone()
    if r is None:
        return None
    first, last = r["first_name"], r["last_name"]
    if not first:  # older rows only have `name`
        first, _, last = (r["name"] or "").partition(" ")
    return CustomerInfo(user_id=r["id"], first_name=first or "", last_name=last or "", email=r["email"])


def save_chat_message(user_id: int, role: str, content: str, products: list[ProductCard]) -> None:
    payload = json.dumps([p.model_dump() for p in products]) if role == "assistant" else None
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, ?, ?, ?)",
            (user_id, role, content, payload),
        )


def load_chat_history(user_id: int, limit: int) -> list[dict[str, Any]]:
    """Newest `limit` messages for this user, returned oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, role, content, products_json, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit),
        ).fetchall()
    out = []
    for r in reversed(rows):
        ids: list[str] = []
        if r["products_json"]:
            try:
                ids = [p["product_id"] for p in json.loads(r["products_json"]) if "product_id" in p]
            except (json.JSONDecodeError, TypeError):
                ids = []
        out.append({"id": r["id"], "role": r["role"], "content": r["content"],
                    "product_ids": ids, "created_at": r["created_at"]})
    return out


def clear_chat_history(user_id: int) -> int:
    with connect() as conn:
        cur = conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        return cur.rowcount
