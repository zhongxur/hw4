// Shared shop state that links the chat widget and the pages:
//   * pageContext  — what the shopper is looking at (sent with every chat message, Problem 8)
//   * chatResults  — product cards the agent asked to show on the page (Problem 7)
//   * chat opener  — lets a page open the chat with a pre-filled question ("Ask Dan about this")
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { PageContext, ProductCard } from '../api'

export interface ChatResults {
  label: string
  products: ProductCard[]
  runId: string
}

interface ShopState {
  pageContext: PageContext
  setPageContext: (ctx: PageContext) => void
  chatResults: ChatResults | null
  setChatResults: (r: ChatResults | null) => void
  chatOpen: boolean
  setChatOpen: (open: boolean) => void
  pendingQuestion: string | null
  askDan: (question: string) => void
  consumePendingQuestion: () => string | null
}

const ShopContext = createContext<ShopState | null>(null)

export function ShopProvider({ children }: { children: ReactNode }) {
  const [pageContext, setPageContext] = useState<PageContext>({ path: '/', page: 'home' })
  const [chatResults, setChatResults] = useState<ChatResults | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)

  const askDan = useCallback((question: string) => {
    setPendingQuestion(question)
    setChatOpen(true)
  }, [])

  const consumePendingQuestion = useCallback(() => {
    const q = pendingQuestion
    setPendingQuestion(null)
    return q
  }, [pendingQuestion])

  const value = useMemo(
    () => ({
      pageContext, setPageContext, chatResults, setChatResults, chatOpen, setChatOpen,
      pendingQuestion, askDan, consumePendingQuestion,
    }),
    [pageContext, chatResults, chatOpen, pendingQuestion, askDan, consumePendingQuestion],
  )
  return <ShopContext.Provider value={value}>{children}</ShopContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useShop(): ShopState {
  const ctx = useContext(ShopContext)
  if (!ctx) throw new Error('useShop must be used inside <ShopProvider>')
  return ctx
}

/** Pages call this to tell the chat what the shopper is looking at. */
// eslint-disable-next-line react-refresh/only-export-components
export function usePageContext(ctx: PageContext): void {
  const { setPageContext } = useShop()
  const key = JSON.stringify(ctx)
  const last = useRef<string>('')
  useEffect(() => {
    if (last.current !== key) {
      last.current = key
      setPageContext(JSON.parse(key) as PageContext)
    }
  }, [key, setPageContext])
}
