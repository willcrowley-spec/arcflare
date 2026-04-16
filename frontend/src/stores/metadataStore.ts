import { create } from 'zustand'
import type { MetadataObject } from '@/types'

type MetadataState = {
  objects: MetadataObject[]
  selectedObjectId: string | null
  setObjects: (objects: MetadataObject[]) => void
  upsertObject: (obj: MetadataObject) => void
  selectObject: (id: string | null) => void
}

export const useMetadataStore = create<MetadataState>((set) => ({
  objects: [],
  selectedObjectId: null,
  setObjects: (objects) => set({ objects }),
  upsertObject: (obj) =>
    set((s) => {
      const idx = s.objects.findIndex((o) => o.id === obj.id)
      if (idx === -1) return { objects: [...s.objects, obj] }
      const next = [...s.objects]
      next[idx] = obj
      return { objects: next }
    }),
  selectObject: (id) => set({ selectedObjectId: id }),
}))
