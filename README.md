# Homework 4 — Campus Customs Shop + Chatbot

A Yale apparel storefront (React + Vite + TypeScript) with **Dan**, a PydanticAI shopping assistant behind
FastAPI. Dan looks up real prices and per-size stock in SQLite and pushes search results onto the page as
product cards. He remembers logged-in shoppers and knows which product you're looking at.

```
hw4/
├── AI_prompts.md            prompts I typed to my vibe coder, per problem
├── requirements.txt         Python deps (backend)
├── .env.example             copy to .env and add your Portkey key
├── frontend/                Vite React TS app (pages, chat widget, styles)
├── backend/
│   ├── main.py              FastAPI app: products, auth, chat routes, /images
│   ├── agent.py             PydanticAI agent, guardrails, audit trail
│   ├── tools.py             SQLite lookups behind the agent tools + REST API
│   ├── models.py            Pydantic types (tool results, agent I/O, API)
│   └── prompts/prompt.md    system prompt: voice, tool rules, safety
└── output/
    ├── harness.md           how the whole system works (DB, tools, safety, specs)
    ├── usability.md         Problem 9 improvements
    ├── design.md            Problem 10 design notes
    ├── app_check.html       Problem 11 screenshots + captions
    ├── app_check_images/
    └── audit_trail.json     append-only agent log
```

## 1. Put the data pack in place (not in git)

Unzip the course data pack so that you have:

```
hw4/data/campus_customs.db
hw4/data/products/*.jpg
```

(`CAMPUS_DB` / `CAMPUS_DATA_DIR` in `.env` can point somewhere else.)

## 2. Backend (Python 3.10+)

```bash
cd hw4
cp .env.example .env               # then put your PORTKEY_API_KEY in .env
python -m venv .venv && source .venv/bin/activate    # or: uv venv --python 3.12 .venv
pip install -r requirements.txt                       # or: uv pip install -r requirements.txt
cd backend
uvicorn main:app --reload --port 8000
```

Check it: <http://localhost:8000/api/health> → `{"ok": true, "products": 102, ...}`.
On first start the backend adds a `sessions` table to the database.

## 3. Front end (Node 20+)

In a second terminal:

```bash
cd hw4/frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` and `/images` to the backend on port 8000.

## 4. Try it

- Log in with the seed test user `test@campuscustoms.yale.edu` / `password`, or create an account.
- Open the chat (bottom right) → "What hoodies do you have?" → the cards appear on the Products page.
- Open any product → pick a size → "Ask Dan about this item", or type "do you have this in pink?".
- "I want the Baseball Left Chest Crewneck in XL" → sold out, and Dan offers in-stock alternatives.
- Agent activity is appended to `output/audit_trail.json`.

## Notes

- Model: `gpt-5.6-luna` through the Portkey gateway (`CAMPUS_MODEL` to change).
- Passwords are stored as salted PBKDF2-SHA256 hashes; see `output/harness.md` §3.
- `.env`, `data/` (database + images), `node_modules/` and `.venv/` are git-ignored.
- This is a class demo storefront and not an official Yale site. Checkout is disabled.
