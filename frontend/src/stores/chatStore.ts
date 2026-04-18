import { create } from 'zustand'

interface ChatState {
  isOpen: boolean
  activeThreadId: string | null
  anchorContext: { type: string; id: string } | null
  streamingMessageId: string | null
  /** Updated when thread detail loads; drives launcher badge when chat is closed. */
  pendingActionsCount: number
  openChat: () => void
  openContextualChat: (anchor: { type: string; id: string }) => void
  closeChat: () => void
  setActiveThread: (id: string | null) => void
  setStreamingMessageId: (id: string | null) => void
  setPendingActionsCount: (n: number) => void
}

export const useChatStore = create<ChatState>((set) => ({
  isOpen: false,
  activeThreadId: null,
  anchorContext: null,
  streamingMessageId: null,
  pendingActionsCount: 0,
  openChat: () => set({ isOpen: true }),
  openContextualChat: (anchor) => set({ isOpen: true, anchorContext: anchor }),
  closeChat: () => set({ isOpen: false, anchorContext: null }),
  setActiveThread: (id) => set({ activeThreadId: id }),
  setStreamingMessageId: (id) => set({ streamingMessageId: id }),
  setPendingActionsCount: (n) => set({ pendingActionsCount: n }),
}))
