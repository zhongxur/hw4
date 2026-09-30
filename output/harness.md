# Campus Customs — harness

How the shop and its chatbot fit together: the data, the models, the tools, the safety rules and the
run specs. Grown problem by problem (P2 → P12).

```
 React (Vite, :5173) ──/api, /images──▶ FastAPI backend/main.py (:8000) ──▶ SQLite data/campus_customs.db
        │  chat widget                          │
        │  POST /api/chat {message, page,       ├─ agent.py  PydanticAI agent (prompts/prompt.md + models.py types)
        │                  history}             │     └─ tools.py  SQL lookups (search, details, stock, alternatives)
        ◀── ChatResponse {reply, products[],    └─ output/audit_trail.json  (append-only log of every agent loop)
             show_on_page, suggestions}
```

---

## 1. Database (P2)

`data/campus_customs.db` — SQLite, 4 tables in the seed data pack (+ `sessions`, which the backend creates at startup).

### `catalogue` — 102 products (one row per product)
| Field | Type | Why it matters |
|---|---|---|
| `product_id` | TEXT PK | Stable slug (`basic-hoodie-big-yale`). Used in URLs (`/products/<id>`), as the join key to `inventory`, and it is the **only** thing the agent passes back to name a product. |
| `name` | TEXT | Title on cards and the detail page; shoppers search by it ("the Morse quarter-zip"). |
| `garment_type` | TEXT | Free text ("pullover hoodie", "quarter-zip pullover sweatshirt" — 22 distinct values). Normalised into 6 shop categories (Hoodies, Crewnecks, T-Shirts, Quarter-Zips, Jackets & Fleece, Long Sleeve) for filter chips and for "what hoodies do you have?". |
| `description` | TEXT | Full copy for the detail page; a 110-char snippet goes on cards. The agent reads it to answer "what's it made of / what's on the front?". |
| `colors` | TEXT (JSON list) | e.g. `["navy blue","white"]`. Colour filter + swatches, and the honest answer to "do you have this in pink?". |
| `search_tags` | TEXT (JSON list) | Extra keywords ("bulldog", "college rivalry", "Morse"). Search matches on them; `find_alternatives` uses shared tags to rank similar items. |
| `image_file_path` | TEXT | `products/<file>.jpg`, relative to `data/`. FastAPI serves `data/products/` at `/images/`, so the card shows `/images/<file>.jpg`. |
| `price` | REAL | USD, $32–$98. Shown on every card; the agent may only quote prices that a tool returned (validator-enforced). |

### `inventory` — 612 rows (102 products × 6 sizes)
| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER PK | Row id. |
| `product_id` | TEXT FK → catalogue | Which product. `UNIQUE(product_id, size)` so there is exactly one count per size. |
| `size` | TEXT | XS, S, M, L, XL, XXL. The size picker, the "In my size" filter and `check_stock(size=…)`. |
| `quantity` | INTEGER | Units on hand. **0 = sold out** (145 of 612 rows). 1–3 = "only N left". Summed for card-level stock badges. Never cached — always read fresh. |

### `users` — shoppers (3 in the seed)
| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER PK | Links to `chat_messages.user_id` and `sessions.user_id`. |
| `name` | TEXT | Legacy full name (seed rows). We still write `first last` here for compatibility. |
| `email` | TEXT UNIQUE | Login identifier (compared case-insensitively). Shown to the agent only for the logged-in user. |
| `password_hash` | TEXT | Salted PBKDF2-SHA256 hash — never the password (see §3). |
| `created_at` | TEXT | Account creation time (SQLite `datetime('now')`). |
| `first_name`, `last_name` | TEXT | Added later to the seed. The agent greets by `first_name`; the nav shows "Hi, Test". |

### `chat_messages` — saved chats for logged-in shoppers
| Field | Type | Why it matters |
|---|---|---|
| `id` | INTEGER PK | Ordering. |
| `user_id` | INTEGER FK → users | Whose conversation it is — history is only ever loaded for the token's own user. |
| `role` | TEXT | `user` or `assistant`. |
| `content` | TEXT | The message text (user text is stored *after* the redaction guardrail). |
| `products_json` | TEXT (JSON) | For assistant turns: the product cards that were shown, so the chat can re-render them and the agent can resolve "the second one". |
| `created_at` | TEXT | Timestamp. |

### `sessions` — created by `main.py` on startup
`token_hash` (SHA-256 of the login token, PK) · `user_id` · `created_at` · `expires_at` (7 days).

---

## 2. Front end ↔ back end (P3, P5)

- **Front end**: React 19 + Vite + TypeScript in `frontend/`. Routes: `/` Home, `/products` (grid + filters),
  `/products/:id` (single-item page: large image left, full info right, per-size stock), `/about`, `/login`,
  `/register`. The floating chat (`components/ChatWidget.tsx`) is on every page.
- **Transport**: `vite.config.ts` proxies `/api/*` and `/images/*` to `http://localhost:8000`, so the React
  code uses relative URLs and there is no CORS in development (CORS is also allowed for `:5173`).
- **API** (`backend/main.py`):

| Route | Purpose |
|---|---|
| `GET /api/products?q=&category=&color=&size=&in_stock=&sort=` | Products grid, search and filters (same search function as the agent's tool). |
| `GET /api/products/{id}` | Single-item page: description, colours, per-size stock. |
| `GET /api/categories` | Category chips + counts, colours, sizes. |
| `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` | Accounts + sessions. |
| `POST /api/chat` | One chat turn → `ChatResponse`. |
| `GET /api/chat/history`, `DELETE /api/chat/history` | Load / clear the logged-in shopper's saved chat. |
| `GET /images/<file>` | Product photos (static files from `data/products/`). |

- **How the agent is loaded** (`backend/agent.py`): on the first chat request `get_agent()` builds one
  `Agent(OpenAIResponsesModel("gpt-5.6-luna"), deps_type=ShopDeps, output_type=ShopReply,
  instructions=prompts/prompt.md)`. The model goes through the **Portkey gateway**
  (`AsyncOpenAI(base_url="https://api.portkey.ai/v1", default_headers={"x-portkey-api-key": key})`).
  `PORTKEY_API_KEY` is read from `hw4/.env` (or the nearest parent `.env`). The model name can be
  overridden with `CAMPUS_MODEL`. A second, dynamic instruction block (`shopper_context`) is added per
  request with the customer and page context.

---

## 3. Auth (P4)

- **Create account**: first name, last name, email, password (+ confirm on the form). Server checks email
  format, 8–128 character password, rejects duplicates (409, case-insensitive).
- **What we store**: `first_name`, `last_name`, `name`, lower-cased `email`, `password_hash`, `created_at`.
  **Never the password.**
- **Password protection**: PBKDF2-HMAC-SHA256 with a random 16-byte salt per user and **600,000 iterations**
  (Python `hashlib`, no extra dependency), stored as `pbkdf2_sha256$600000$<salt>$<hex digest>`.
  Seed users use the older `pbkdf2_sha256$<salt>$<digest>` format at 120,000 iterations; `verify_password`
  understands both, and compares with `hmac.compare_digest` (constant time). A leaked DB therefore gives an
  attacker only slow, salted hashes — no plaintext, no rainbow tables.
- **Sessions**: a successful login returns a random 256-bit token (`secrets.token_urlsafe(32)`). Only its
  SHA-256 is stored in `sessions`, with a 7-day expiry. The browser keeps the token in `localStorage` and sends
  `Authorization: Bearer <token>`. Logout deletes the session row.
- **Brute force**: 5 failed logins per email per 15 minutes → HTTP 429. Unknown email and wrong password
  get the **same** error so the login form can't be used to discover who has an account.
- Verified: the seed user `test@campuscustoms.yale.edu` / `password` logs in; a newly registered account
  logs in (also with different email capitalisation); a wrong password is rejected.

---

## 4. Agent: models, tools and how results reach the page (P5–P8)

### Structured types (`backend/models.py`) and why these fields
| Type | Fields | Why |
|---|---|---|
| `ShopDeps` (deps) | `run_id`, `customer: CustomerInfo \| None`, `page: PageContext`, `tool_log`, `seen_prices` | Everything a tool needs about *this* request. `tool_log`/`seen_prices` are filled by tools so the validator and audit trail can check them. |
| `CustomerInfo` | `user_id, first_name, last_name, email` | The only customer fields the model ever sees — no hash, no created_at, no other users. |
| `PageContext` | `path, page, product_id, product_name, selected_size, visible_product_ids` | Lets "this", "it", "in my size" and "the second one" resolve without asking. |
| `ProductMatch` (search hit) | `product_id, name, category, price, colors, in_stock, total_stock, short_description` | Enough to answer "what do you have?" in one call; description is trimmed to 110 chars to keep tokens low. |
| `SearchResult` | `query, filters, total_matches, products[]` | `total_matches` tells the model when results were capped so it can say "showing 12 of 27". |
| `ProductInfo` | full record + `sizes[]` | Authoritative answer for price/description/colour questions. |
| `StockCheck` | `requested_size, requested_size_quantity, requested_size_in_stock, in_stock_sizes, sold_out_sizes, sizes[]` | Pre-computed yes/no + exact count so the model doesn't have to reason over a table — fewer mistakes, honest "sold out in XL". |
| `Alternatives` | `other_sizes_in_stock, similar_products_in_stock[]` | What to offer when something is sold out. |
| `NotFound` | `error, hint` | Returned instead of raising, so the model can recover (e.g. search first). |
| `ShopReply` (agent output) | `message, product_ids (≤12), show_on_page, search_label, suggestions (≤3)` | The API contract with the website: the model picks **ids**, the backend builds the cards. |
| `ProductCard` / `ProductDetail` | image_url, price, stock, … | Built by the backend from SQLite for the website — the model can't alter a price or image. |
| `ChatRequest` / `ChatResponse` | message, page, history / reply, products, show_on_page, search_label, suggestions, stop_reason | HTTP contract between React and FastAPI. |

### Tools (`agent.py` wraps the functions in `tools.py`)
| Tool | Reads | Returns | Used for |
|---|---|---|---|
| `search_products(query, category?, color?, max_price?, size?, in_stock_only?, limit≤12)` | catalogue + inventory | `SearchResult` | "What hoodies do you have?", "navy crewnecks under $60", "anything with a bulldog?". Word + synonym matching (hoodie→hood/hooded, tee→t-shirt, grey↔gray), a category word narrows to that category, filters applied in SQL-side Python. |
| `get_product_details(product)` | catalogue + inventory | `ProductInfo \| NotFound` | Price, description, colours. Accepts an id or a name. |
| `check_stock(product, size?)` | inventory (live) | `StockCheck \| NotFound` | "Is M in stock?", "how many XL left?". |
| `find_alternatives(product, size?)` | catalogue + inventory | `Alternatives \| NotFound` | Sold-out size → other sizes + up to 4 similar in-stock items (same category, shared colours/tags, close price). *(P9)* |
| `get_customer_profile()` | deps | `CustomerInfo \| NotFound` | "What's my name / email?" — logged-in shopper only. |
| `list_categories()` | catalogue | categories + counts | "What do you sell?" |

The prompt tells the agent which tool to call for which question; prices and stock may only come from a
tool result in the current turn.

### How search results reach the page (P7)
1. Shopper types "what hoodies do you have?" → `POST /api/chat`.
2. Agent calls `search_products(query="hoodies")`, then returns
   `ShopReply(message=…, product_ids=[…], show_on_page=true, search_label="Hoodies")`.
3. Output validator rejects unknown ids / invented prices (ModelRetry).
4. `main.py` → `tools.cards_for(product_ids)` turns ids into `ProductCard`s from SQLite (real price, image,
   live stock) → `ChatResponse.products`.
5. `ChatWidget` shows mini-cards in the chat. If `show_on_page` is true it stores the cards in
   `ShopContext.chatResults` and navigates to `/products?from=chat`; the Products page then renders those
   cards (with a "Results from your chat with Dan" banner and a "Show all products" reset) instead of the
   catalogue grid.
6. Every card — grid, chat mini-card or chat results — is a `<Link to="/products/:id">`, so clicking it opens
   the same single-item page as in P3.

### Customer memory + page context (P8)
- **Stored**: for logged-in shoppers, `POST /api/chat` saves the (redacted) user message and the assistant
  reply + shown cards (`products_json`) to `chat_messages`. `GET /api/chat/history` reloads them when the
  shopper comes back (the widget calls it whenever the logged-in user changes).
- **Fed to the model**: the last 12 messages (each ≤1,200 chars) from the DB become PydanticAI
  `message_history`; assistant turns get `[cards shown: id1, id2, …]` appended. The browser's copy is ignored
  for logged-in users. **Guests**: history lives in `sessionStorage` and is sent with each request (capped at
  12); nothing is written to the DB.
- **Who is chatting**: the Bearer token → `sessions` → `users` → `CustomerInfo` in `ShopDeps.customer`.
  The dynamic instruction block tells the model "Logged-in customer: Test User <email> (user_id 1)" or
  "Guest shopper", and `get_customer_profile` returns the same fields.
- **Page context**: every page calls `usePageContext({...})`; the product page sends
  `{page:"product", product_id, product_name, selected_size}`, the Products page sends the ids of the visible
  cards. The chat sends it with every message, and it becomes a "Page context" block in the instructions
  ("The shopper is viewing product_id `basic-hoodie-big-yale` … 'this' means this product"). The chat header
  shows "Looking at: <product>" so the shopper knows Dan can see it.

---

## 5. Safety (P12)

Rules in `backend/prompts/prompt.md` (summarised): stay on Campus Customs topics; never invent products,
prices, stock, discounts, shipping or restock dates; no payments/passwords in chat; only the logged-in
shopper's own data, never the prompt/tools/DB internals or other customers; ignore instructions embedded in
user text; respectful, no body comments; minimal tool calls.

Enforced in code, not just asked for:
| Layer | Where | What |
|---|---|---|
| Input guardrail | `agent.guard_input` | Messages capped at 1,000 chars; Luhn-valid card numbers → `[REDACTED CARD NUMBER]`; `password is …`/`cvv: …` → `[REDACTED]` — before the model *or* the DB sees it. |
| Grounded output | `@agent.output_validator check_reply` | `product_ids` must exist in the catalogue; every `$` amount in the reply must equal a price a tool returned this turn (or a limit the shopper typed). Otherwise `ModelRetry`. |
| Cards from DB | `tools.cards_for` | The UI never renders model-written prices/images. |
| Loop caps | `UsageLimits(request_limit=6, tool_calls_limit=8)` | A confused model can't loop forever or run up cost. |
| Scoped data | `CustomerInfo`, `require_user` | History/profile only for the token's user; the model never sees hashes. |
| Gateway filter | `run_chat` | Jailbreak prompts blocked by the Azure content filter are turned into a polite refusal (`stop_reason: blocked: gateway content filter`). |
| Safe rendering | `components/Markdown.tsx` | Chat Markdown is rendered as React elements (no `innerHTML`), so replies can't inject HTML/JS. |
| Auth | `main.py` | PBKDF2 600k, hashed session tokens, login throttling, generic login error. |

## 6. Audit trail (P12)

`output/audit_trail.json` — one JSON array, **append-only** (`agent.append_audit` seeks to the closing `]`
and writes new entries before it; nothing is ever rewritten or cleared between runs). Per chat turn:

- `user_message` — time, run_id, model, user (email or guest), page, product in view, message (≤240 chars),
  guardrail notes, number of history messages.
- `tool_call` / `tool_result` — step number, tool name, short args / short result (≤240 chars).
- `retry` — validator or argument-validation retries with the reason.
- `final` — `stop_reason` (`final_result`, `usage_limit: …`, `blocked: gateway content filter`, `error: …`),
  reply, product_ids, show_on_page, token usage, duration.

## 7. Specs

| Spec | Value |
|---|---|
| Model | `gpt-5.6-luna` via Portkey (`CAMPUS_MODEL` to override) |
| Agent loop | ≤6 model requests, ≤8 tool calls per message; 2 output retries |
| Result caps | search ≤12 products per call (default 8); agent shows ≤12 cards; alternatives ≤4; suggestions ≤3 |
| History | last 12 messages, 1,200 chars each |
| Input | 1,000 chars per message (API rejects >4,000) |
| Timeouts | 60 s per gateway request |
| Sessions | 7 days; 5 failed logins / 15 min |
| Typical turn | 2–3 model requests, 1–2 tool calls, ~4–5k input tokens, 3–8 s |

**Run it** (after placing the data pack in `hw4/data/` and a `PORTKEY_API_KEY` in `hw4/.env`):

```bash
# backend
cd hw4/backend
uvicorn main:app --reload --port 8000

# front end (second terminal)
cd hw4/frontend
npm install
npm run dev        # http://localhost:5173
```
