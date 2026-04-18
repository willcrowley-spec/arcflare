import { create } from 'zustand'

interface ChatState {
  isOpen: boolean
  activeThreadId: string | null
  anchorContext: { type: string; id: string } | null
  /** Pre-filled prompt injected by contextual entry points (e.g. "Chat with AI" on a gap). */
  initialPrompt: string | null
  streamingMessageId: string | null
  pendingActionsCount: number
  /** Tracks recently dismissed gap IDs so the user can undo. */
  dismissedGaps: Map<string, ReturnType<typeof setTimeout>>
  agentName: string
  thinkingPhase: string | null
  setThinkingPhase: (phase: string | null) => void
  openChat: () => void
  openContextualChat: (anchor: { type: string; id: string }, prompt?: string) => void
  closeChat: () => void
  setActiveThread: (id: string | null) => void
  consumeInitialPrompt: () => string | null
  setStreamingMessageId: (id: string | null) => void
  setPendingActionsCount: (n: number) => void
  dismissGap: (id: string) => void
  undoGapDismiss: (id: string) => void
  clearDismissedGap: (id: string) => void
}

const UNDO_DELAY = 5000

export const useChatStore = create<ChatState>((set, get) => ({
  isOpen: false,
  activeThreadId: null,
  anchorContext: null,
  initialPrompt: null,
  streamingMessageId: null,
  pendingActionsCount: 0,
  dismissedGaps: new Map(),
  agentName: 'Arc',
  thinkingPhase: null,
  setThinkingPhase: (phase) => set({ thinkingPhase: phase }),

  openChat: () => set({ isOpen: true }),

  openContextualChat: (anchor, prompt) =>
    set({ isOpen: true, anchorContext: anchor, activeThreadId: null, initialPrompt: prompt ?? null }),

  closeChat: () => set({ isOpen: false, anchorContext: null, initialPrompt: null }),

  setActiveThread: (id) => set({ activeThreadId: id }),

  consumeInitialPrompt: () => {
    const p = get().initialPrompt
    if (p) set({ initialPrompt: null })
    return p
  },

  setStreamingMessageId: (id) => set({ streamingMessageId: id }),
  setPendingActionsCount: (n) => set({ pendingActionsCount: n }),

  dismissGap: (id) => {
    const existing = get().dismissedGaps.get(id)
    if (existing) clearTimeout(existing)
    const timer = setTimeout(() => {
      get().clearDismissedGap(id)
    }, UNDO_DELAY)
    set((s) => {
      const next = new Map(s.dismissedGaps)
      next.set(id, timer)
      return { dismissedGaps: next }
    })
  },

  undoGapDismiss: (id) => {
    const timer = get().dismissedGaps.get(id)
    if (timer) clearTimeout(timer)
    set((s) => {
      const next = new Map(s.dismissedGaps)
      next.delete(id)
      return { dismissedGaps: next }
    })
  },

  clearDismissedGap: (id) => {
    set((s) => {
      const next = new Map(s.dismissedGaps)
      next.delete(id)
      return { dismissedGaps: next }
    })
  },
}))
