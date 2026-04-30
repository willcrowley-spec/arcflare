import { create } from 'zustand'
import type { PlatformConnection } from '@/types'

type ConnectionState = {
  connections: PlatformConnection[]
  selectedId: string | null
  setConnections: (connections: PlatformConnection[]) => void
  upsertConnection: (connection: PlatformConnection) => void
  removeConnection: (id: string) => void
  select: (id: string | null) => void
  reset: () => void
}

export const useConnectionStore = create<ConnectionState>((set) => ({
  connections: [],
  selectedId: null,
  setConnections: (connections) => set({ connections }),
  upsertConnection: (connection) =>
    set((s) => {
      const idx = s.connections.findIndex((c) => c.id === connection.id)
      if (idx === -1) return { connections: [...s.connections, connection] }
      const next = [...s.connections]
      next[idx] = connection
      return { connections: next }
    }),
  removeConnection: (id) =>
    set((s) => ({
      connections: s.connections.filter((c) => c.id !== id),
      selectedId: s.selectedId === id ? null : s.selectedId,
    })),
  select: (id) => set({ selectedId: id }),
  reset: () => set({ connections: [], selectedId: null }),
}))
