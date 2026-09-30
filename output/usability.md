# Usability improvements (Problem 9)

Two front-end and two agent/backend improvements, each built into the running app.
Where to see each one is listed so a grader can find it quickly.

## Front end

### 1. Smart filter bar on the Products page
**What:** a sticky filter panel above the grid with a search box, category chips with counts
(Hoodies 27, Crewnecks 29, …), an **"In my size"** size filter that only shows items *in stock* in that
size, a **"Hide sold out"** toggle, and a sort menu (best match / price low→high / high→low / A–Z).
Filters live in the URL (`/products?category=Hoodies&size=M&in_stock=1`), so Back works and a filtered
view can be shared. If nothing matches, an **"Ask Dan instead"** button hands the query to the chat.
**Why:** 102 styles is too many to scroll. The most common shopper question is "what do you have in *my* size?".
Answering that with one tap cuts the frustrating click → sold out → back loop, and a shared link to a filtered
view is how a parent can send "pick one of these" to a student.
**Where:** `/products` · `frontend/src/pages/Products.tsx`, `GET /api/products` filters in `backend/main.py`.

### 2. Live-stock size picker + "Ask Dan about this item"
**What:** on the single-item page each size is a button that shows its live count ("15 left", "only 2",
struck-through "sold out"). Picking a size shows a coloured status line (✓ in stock / ⚡ only N left /
✕ sold out). The main button changes with context: **"Ask Dan about this item"** opens the chat and asks
"Is this in stock in M?". When the chosen size is sold out it becomes
**"Find me something similar in XL"**, which asks Dan for alternatives. The selected size is also sent to
the agent as page context.
**Why:** shoppers see availability *before* they commit, and "low stock" nudges a decision. A sold-out size
becomes a path to another sale instead of a dead end, and nobody has to type the product name into the chat.
**Where:** `/products/<id>` · `frontend/src/pages/ProductDetail.tsx`.

*(Smaller extras: "Recently viewed" strip on Home and product pages, one-tap starter/suggestion chips in the
chat, a "Looking at: <product>" chip in the chat header, "More hoodies in stock" on each product page.)*

## Agent / backend

### 3. `find_alternatives` tool — honest "sold out" that still sells
**What:** a new agent tool. When a shopper asks for a sold-out size, the agent calls
`find_alternatives(product, size)`. It returns the other in-stock sizes of that item plus up to 4 similar
products that **are in stock in the requested size**. They are ranked by same category, shared colours and
tags, and closest price. The prompt says: say "sold out in XL" plainly, then offer these. The cards appear
in the chat.
**Why:** before this, the agent could only say "sorry, sold out" (or, worse, guess). Now every sold-out answer
comes with real alternatives the shopper can buy today. That keeps the sale and stays honest, and the
recommendations come from SQL, not the model's imagination.
**Where:** ask "I want the Baseball Left Chest Crewneck in XL" · `tools.find_alternatives`, tool in `agent.py`.

### 4. Grounding + privacy guardrails around the model
**What:** two checks in code, not just prompt text:
- **Output validator** (`check_reply`): every `product_id` the model returns must exist in the catalogue,
  and every `$` amount in the reply must match a price a tool returned in that turn (or a budget the
  shopper typed). Otherwise the model gets a `ModelRetry` with the exact problem. The website builds cards
  from SQLite, so a price on screen can never be model-invented.
- **Input guardrail** (`guard_input`): messages are capped at 1,000 characters. Luhn-valid card numbers and
  "my password is …" / CVV / PIN values are redacted **before** the text reaches the model, the audit trail
  or the chat history table. Jailbreak attempts that the gateway's content filter blocks come back as a
  friendly refusal instead of an error.
**Why:** a wrong price or an invented product is the most damaging thing a shop bot can say, so this makes
the agent more accurate and trustworthy. Redaction keeps shoppers' secrets out of logs and the database,
which is safer for the customer and lowers liability for the business. The input cap also makes each turn
cheaper.
**Where:** `backend/agent.py` (`guard_input`, `check_reply`, `run_chat`). Try it: "my card is 4242 4242
4242 4242", then look at `output/audit_trail.json`.

*(Also: loop caps via `UsageLimits`, history trimmed to 12 messages and search results to ≤12 products to
keep each turn fast and cheap, and 3 tappable follow-up `suggestions` in every structured reply.)*
