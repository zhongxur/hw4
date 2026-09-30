"""main.py — Campus Customs FastAPI app. Run from backend/:

    uvicorn main:app --reload --port 8000

Routes (the Vite dev server proxies /api and /images here):
    GET    /api/health
    GET    /api/products            ?q=&category=&color=&max_price=&size=&in_stock=&sort=
    GET    /api/products/{id}
    GET    /api/categories
    POST   /api/auth/register       {first_name, last_name, email, password}
    POST   /api/auth/login          {email, password}
    GET    /api/auth/me             (Bearer token)
    POST   /api/auth/logout         (Bearer token)
    POST   /api/chat                {message, page, history}  (Bearer token optional)
    GET    /api/chat/history        (Bearer token)
    DELETE /api/chat/history        (Bearer token)
    GET    /images/<file>           product photos from data/products

Auth: passwords are stored as salted PBKDF2-SHA256 hashes (never plaintext). A login returns a
random session token; only its SHA-256 is stored in the `sessions` table.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import agent
import tools
from models import (
    AuthResponse,
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    CustomerInfo,
    LoginRequest,
    ProductCard,
    ProductDetail,
    RegisterRequest,
    UserOut,
)

PBKDF2_ITERATIONS = 600_000          # new hashes (OWASP 2023+ guidance for PBKDF2-SHA256)
LEGACY_PBKDF2_ITERATIONS = 120_000   # seed users: pbkdf2_sha256$<salt>$<hex>
SESSION_DAYS = 7
LOGIN_ATTEMPTS = 5                   # failed logins per email per window before 429
LOGIN_WINDOW_S = 15 * 60
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="Campus Customs API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)
if (tools.DATA_DIR / "products").is_dir():
    app.mount("/images", StaticFiles(directory=tools.DATA_DIR / "products"), name="images")


@app.on_event("startup")
def ensure_tables() -> None:
    with tools.connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id)")


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) == 4 and parts[0] == "pbkdf2_sha256":        # ours: alg$iter$salt$hash
        _, iters, salt, digest = parts
        iterations = int(iters)
    elif len(parts) == 3 and parts[0] == "pbkdf2_sha256":      # seed data: alg$salt$hash
        _, salt, digest = parts
        iterations = LEGACY_PBKDF2_ITERATIONS
    else:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return hmac.compare_digest(test, digest)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with tools.connect() as conn:
        conn.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                     (_token_hash(token), user_id, now.isoformat(), (now + timedelta(days=SESSION_DAYS)).isoformat()))
    return token


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[CustomerInfo]:
    token = _bearer(authorization)
    if not token:
        return None
    with tools.connect() as conn:
        row = conn.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?",
                           (_token_hash(token),)).fetchone()
    if row is None or datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return tools.get_customer(row["user_id"])


def require_user(user: Optional[CustomerInfo] = Depends(optional_user)) -> CustomerInfo:
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


def _user_out(c: CustomerInfo) -> UserOut:
    return UserOut(id=c.user_id, first_name=c.first_name, last_name=c.last_name, email=c.email)


_failed_logins: dict[str, deque[float]] = defaultdict(deque)


def _throttle(email: str) -> None:
    q = _failed_logins[email]
    while q and q[0] < time.time() - LOGIN_WINDOW_S:
        q.popleft()
    if len(q) >= LOGIN_ATTEMPTS:
        raise HTTPException(429, "Too many failed logins. Try again in a few minutes.")


# ---------------------------------------------------------------------------
# Routes: catalogue
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "products": len(tools._catalogue_rows()), "model": agent.model_name()}


@app.get("/api/products", response_model=list[ProductCard])
def list_products(
    q: str = "", category: Optional[str] = None, color: Optional[str] = None,
    max_price: Optional[float] = None, size: Optional[str] = None, in_stock: bool = False,
    sort: str = Query("featured", pattern="^(featured|price_asc|price_desc|name)$"),
) -> list[ProductCard]:
    if q or category or color or max_price or size or in_stock:
        cards = [c for _, c in tools.search_catalogue(q, category=category, color=color, max_price=max_price,
                                                       size=size, in_stock_only=in_stock)]
    else:
        cards = tools.load_catalogue()
    if sort == "price_asc":
        cards.sort(key=lambda c: (c.price, c.name))
    elif sort == "price_desc":
        cards.sort(key=lambda c: (-c.price, c.name))
    elif sort == "name":
        cards.sort(key=lambda c: c.name)
    return cards


@app.get("/api/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: str) -> ProductDetail:
    detail = tools.product_detail(product_id)
    if detail is None:
        raise HTTPException(404, "Product not found")
    return detail


@app.get("/api/categories")
def get_categories() -> dict[str, object]:
    return {"categories": tools.categories(), "colors": tools.all_colors()[:16], "sizes": tools.SIZE_ORDER}


# ---------------------------------------------------------------------------
# Routes: auth
# ---------------------------------------------------------------------------
@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
def register(body: RegisterRequest) -> AuthResponse:
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Please enter a valid email address.")
    if body.password.strip() != body.password or len(set(body.password)) < 4:
        raise HTTPException(422, "Choose a stronger password (8+ characters, not all the same).")
    first, last = body.first_name.strip(), body.last_name.strip()
    with tools.connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email,)).fetchone():
            raise HTTPException(409, "An account with that email already exists. Try logging in.")
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            (f"{first} {last}", email, hash_password(body.password), first, last),
        )
        user_id = cur.lastrowid
    customer = tools.get_customer(int(user_id))
    assert customer is not None
    return AuthResponse(token=new_session(customer.user_id), user=_user_out(customer))


@app.post("/api/auth/login", response_model=AuthResponse)
def login(body: LoginRequest) -> AuthResponse:
    email = body.email.strip().lower()
    _throttle(email)
    with tools.connect() as conn:
        row = conn.execute("SELECT id, password_hash FROM users WHERE lower(email) = ?", (email,)).fetchone()
    # same error for unknown email and wrong password (don't reveal which accounts exist)
    if row is None or not verify_password(body.password, row["password_hash"]):
        _failed_logins[email].append(time.time())
        raise HTTPException(401, "Email or password is incorrect.")
    _failed_logins.pop(email, None)
    customer = tools.get_customer(row["id"])
    assert customer is not None
    return AuthResponse(token=new_session(customer.user_id), user=_user_out(customer))


@app.get("/api/auth/me", response_model=UserOut)
def me(user: CustomerInfo = Depends(require_user)) -> UserOut:
    return _user_out(user)


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(default=None)) -> dict[str, bool]:
    token = _bearer(authorization)
    if token:
        with tools.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes: chat
# ---------------------------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: Optional[CustomerInfo] = Depends(optional_user)) -> ChatResponse:
    if user:
        # logged in: history comes from the DB (the browser's copy is ignored)
        rows = tools.load_chat_history(user.user_id, agent.HISTORY_MESSAGES)
        history = [ChatTurn(role=r["role"], content=r["content"][:4000], product_ids=r["product_ids"][:12])
                   for r in rows if r["role"] in ("user", "assistant")]
    else:
        history = body.history[-agent.HISTORY_MESSAGES:]
    response = await agent.run_chat(body.message, user, body.page, history)
    if user:
        clean, _ = agent.guard_input(body.message)       # never store a redacted secret
        tools.save_chat_message(user.user_id, "user", clean, [])
        tools.save_chat_message(user.user_id, "assistant", response.reply, response.products)
    return response


@app.get("/api/chat/history", response_model=list[ChatMessageOut])
def chat_history(limit: int = Query(50, ge=1, le=200), user: CustomerInfo = Depends(require_user)) -> list[ChatMessageOut]:
    rows = tools.load_chat_history(user.user_id, limit)
    return [ChatMessageOut(id=r["id"], role=r["role"], content=r["content"],
                           products=tools.cards_for(r["product_ids"]), created_at=r["created_at"])
            for r in rows if r["role"] in ("user", "assistant")]


@app.delete("/api/chat/history")
def clear_history(user: CustomerInfo = Depends(require_user)) -> dict[str, int]:
    return {"deleted": tools.clear_chat_history(user.user_id)}
