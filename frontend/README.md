# Campus Customs — front end

React 19 + Vite + TypeScript. See `../README.md` for how to run the whole app.

```bash
npm install
npm run dev     # http://localhost:5173 — proxies /api and /images to the FastAPI backend on :8000
npm run build   # type-check + production build
```

- `src/pages/` — Home, Products, ProductDetail, About, Login, Register
- `src/components/ChatWidget.tsx` — floating "Ask Dan" chat (talks to `POST /api/chat`)
- `src/context/ShopContext.tsx` — page context + chat results shared between the chat and the pages
- `src/api.ts` — typed API client
