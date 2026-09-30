// Typed client for the FastAPI backend (backend/main.py). The Vite dev server proxies
// /api and /images to http://localhost:8000, so every URL here is relative.

export interface ProductCard {
  product_id: string
  name: string
  garment_type: string
  category: string
  price: number
  image_url: string
  short_description: string
  colors: string[]
  total_stock: number
  in_stock: boolean
}

export interface SizeStock {
  size: string
  quantity: number
  in_stock: boolean
}

export interface ProductDetail extends ProductCard {
  description: string
  search_tags: string[]
  sizes: SizeStock[]
}

export interface User {
  id: number
  first_name: string
  last_name: string
  email: string
}

export type PageType = 'home' | 'products' | 'product' | 'about' | 'login' | 'register' | 'other'

export interface PageContext {
  path: string
  page: PageType
  product_id?: string | null
  product_name?: string | null
  selected_size?: string | null
  visible_product_ids?: string[]
}

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
  product_ids?: string[]
}

export interface ChatResponse {
  run_id: string
  reply: string
  products: ProductCard[]
  show_on_page: boolean
  search_label: string | null
  suggestions: string[]
  stop_reason: string
}

export interface ChatMessage {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  products: ProductCard[]
  created_at?: string
  suggestions?: string[]
}

export interface Facets {
  categories: { name: string; count: number }[]
  colors: string[]
  sizes: string[]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const TOKEN_KEY = 'cc_token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode: the session just won't survive a reload */
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(path, { ...init, headers })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message)
  }
  return res.json() as Promise<T>
}

export interface ProductQuery {
  q?: string
  category?: string
  color?: string
  size?: string
  max_price?: number
  in_stock?: boolean
  sort?: string
}

export const api = {
  products(query: ProductQuery = {}) {
    const params = new URLSearchParams()
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== '' && v !== false) params.set(k, String(v))
    })
    const qs = params.toString()
    return request<ProductCard[]>(`/api/products${qs ? `?${qs}` : ''}`)
  },
  product: (id: string) => request<ProductDetail>(`/api/products/${encodeURIComponent(id)}`),
  facets: () => request<Facets>('/api/categories'),

  register: (body: { first_name: string; last_name: string; email: string; password: string }) =>
    request<{ token: string; user: User }>('/api/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (email: string, password: string) =>
    request<{ token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>('/api/auth/me'),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),

  chat: (message: string, page: PageContext, history: ChatTurn[]) =>
    request<ChatResponse>('/api/chat', { method: 'POST', body: JSON.stringify({ message, page, history }) }),
  chatHistory: () => request<ChatMessage[]>('/api/chat/history'),
  clearChatHistory: () => request<{ deleted: number }>('/api/chat/history', { method: 'DELETE' }),
}

export const money = (n: number) => `$${n.toFixed(2).replace(/\.00$/, '')}`
