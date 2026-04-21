import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { PortfolioProjection } from '@/types'

export type ScenarioData = PortfolioProjection['optimistic']

export interface UsePortfolioReturn {
  selectedIds: Set<string>
  toggle: (id: string) => void
  selectAll: (ids: string[]) => void
  clearAll: () => void
  isSelected: (id: string) => boolean
  projections: PortfolioProjection | null
  isLoading: boolean
  /** Total recommendations in the current list view (denominator for "N of M"). */
  listTotal: number
}

function selectionKeyFromSet(ids: Set<string>): string {
  return [...ids].sort().join('|')
}

function normalizePayback(
  raw: Record<string, unknown>,
): PortfolioProjection['payback_month'] {
  const fromPayback = raw.payback_month as PortfolioProjection['payback_month'] | undefined
  const fromTotal = raw.total_payback_month as PortfolioProjection['payback_month'] | undefined
  const pick = fromPayback ?? fromTotal
  if (pick && typeof pick === 'object') {
    return {
      optimistic: pick.optimistic ?? null,
      expected: pick.expected ?? null,
      conservative: pick.conservative ?? null,
    }
  }
  return { optimistic: null, expected: null, conservative: null }
}

function normalizeByAutomationType(
  raw: Record<string, unknown>,
): PortfolioProjection['by_automation_type'] | undefined {
  const bat = raw.by_automation_type as Record<string, number> | undefined
  if (!bat || typeof bat !== 'object') return undefined
  const out: Partial<Record<'deterministic' | 'agentic' | 'hybrid', number>> = {}
  for (const k of ['deterministic', 'agentic', 'hybrid'] as const) {
    const v = bat[k]
    if (typeof v === 'number' && Number.isFinite(v)) out[k] = v
  }
  return Object.keys(out).length ? out : undefined
}

function normalizePortfolioPayload(data: unknown): PortfolioProjection {
  if (!data || typeof data !== 'object') {
    throw new Error('Invalid portfolio projection response')
  }
  const d = data as Record<string, unknown>
  const scenarios = ['optimistic', 'expected', 'conservative'] as const
  const projection: PortfolioProjection = {
    optimistic: d.optimistic as PortfolioProjection['optimistic'],
    expected: d.expected as PortfolioProjection['expected'],
    conservative: d.conservative as PortfolioProjection['conservative'],
    npv: d.npv as PortfolioProjection['npv'],
    payback_month: normalizePayback(d),
    recommendation_count: Number(d.recommendation_count) || 0,
    by_automation_type: normalizeByAutomationType(d),
  }
  for (const s of scenarios) {
    const sc = projection[s]
    if (!sc || typeof sc !== 'object') {
      throw new Error(`Missing scenario: ${s}`)
    }
  }
  return projection
}

export function usePortfolio(listTotal: number): UsePortfolioReturn {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set())
  const selectionKey = useMemo(() => selectionKeyFromSet(selectedIds), [selectedIds])

  const [debouncedKey, setDebouncedKey] = useState('')
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedKey(selectionKey), 300)
    return () => window.clearTimeout(t)
  }, [selectionKey])

  const debouncedIds = useMemo(() => {
    if (!debouncedKey) return [] as string[]
    return debouncedKey.split('|').filter(Boolean)
  }, [debouncedKey])

  const isDebouncing = selectionKey !== debouncedKey

  const { data, isFetching } = useQuery({
    queryKey: ['recommendations', 'portfolio-projection', debouncedKey],
    queryFn: async () => {
      const raw = await api.recommendations.portfolioProjection(debouncedIds)
      return normalizePortfolioPayload(raw)
    },
    enabled: debouncedIds.length > 0,
  })

  const projections =
    selectedIds.size === 0 ? null : isDebouncing ? null : data ?? null

  const isLoading = selectedIds.size > 0 && (isDebouncing || isFetching)

  const toggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const selectAll = useCallback((ids: string[]) => {
    setSelectedIds(new Set(ids))
  }, [])

  const clearAll = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  const isSelected = useCallback((id: string) => selectedIds.has(id), [selectedIds])

  return {
    selectedIds,
    toggle,
    selectAll,
    clearAll,
    isSelected,
    projections,
    isLoading,
    listTotal,
  }
}
