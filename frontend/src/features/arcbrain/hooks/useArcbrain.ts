import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { ArcbrainLens, ArcbrainSearchRequest } from '@/types'

export function useArcbrainSnapshot() {
  return useQuery({
    queryKey: ['arcbrain', 'snapshot'],
    queryFn: () => api.arcbrain.snapshot(),
    retry: false,
  })
}

export function useArcbrainNode(nodeId: string | null | undefined) {
  return useQuery({
    queryKey: ['arcbrain', 'node', nodeId],
    queryFn: () => api.arcbrain.node(nodeId!),
    enabled: !!nodeId,
    retry: false,
  })
}

export function useArcbrainBlastRadius(nodeId: string | null | undefined, lens: ArcbrainLens) {
  return useQuery({
    queryKey: ['arcbrain', 'blast-radius', nodeId],
    queryFn: () => api.arcbrain.blastRadius(nodeId!),
    enabled: !!nodeId && lens === 'blast_radius',
    retry: false,
  })
}

export function useArcbrainReplacementHeat(lens: ArcbrainLens) {
  return useQuery({
    queryKey: ['arcbrain', 'replacement-heat'],
    queryFn: () => api.arcbrain.replacementHeat(),
    enabled: lens === 'replacement_heat',
    retry: false,
  })
}

export function useArcbrainSearch() {
  return useMutation({
    mutationFn: (request: ArcbrainSearchRequest) => api.arcbrain.search(request),
  })
}
