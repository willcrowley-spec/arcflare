import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowDownWideNarrow, Layers, Loader2, Sparkles, X } from 'lucide-react'
import clsx from 'clsx'
import { SearchBar } from '@/components/SearchBar'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import {
  useCancelRecommendations,
  useGenerateRecommendations,
  useRecommendationPipelineStatus,
  useRecommendations,
  useUpdateRecommendationStatus,
} from '@/hooks/useApi'
import { PortfolioDashboard } from './PortfolioDashboard'
import { usePortfolio } from './usePortfolio'
import { RecommendationCard } from './RecommendationCard'
import { RecommendationDetail } from './RecommendationDetail'
import type { Recommendation } from './RecommendationCard'

type StatusTab = 'active' | 'accepted' | 'dismissed'
type SortKey = 'score' | 'npv' | 'priority' | 'title'
type AutomationKey = 'deterministic' | 'agentic' | 'hybrid'

const PAGE_SIZE = 12

function sortApiParam(key: SortKey): string {
  switch (key) {
    case 'score':
      return '-composite_score'
    case 'npv':
      return '-estimated_roi'
    case 'priority':
      return '-priority'
    case 'title':
      return 'title'
    default:
      return '-composite_score'
  }
}

function normalizeRecommendation(raw: unknown): Recommendation | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  if (typeof r.title !== 'string') return null
  const id = r.id != null ? String(r.id) : ''
  if (!id) return null

  const recType = r.recommendation_type === 'synthesized' ? 'synthesized' : 'discovered'
  const autoRaw = typeof r.automation_type === 'string' ? r.automation_type.toLowerCase() : 'hybrid'
  const automation_type: Recommendation['automation_type'] =
    autoRaw === 'deterministic' || autoRaw === 'agentic' || autoRaw === 'hybrid' ? autoRaw : 'hybrid'

  const actionsRaw = Array.isArray(r.actions_json) ? r.actions_json : []
  const actions_json = actionsRaw.map((x, i) => {
    if (x && typeof x === 'object' && !Array.isArray(x)) {
      const o = x as Record<string, unknown>
      return {
        step: typeof o.step === 'number' ? o.step : i + 1,
        action:
          typeof o.action === 'string' ? o.action : typeof o.title === 'string' ? o.title : 'Action',
        effort: typeof o.effort === 'string' ? o.effort : '—',
      }
    }
    return { step: i + 1, action: typeof x === 'string' ? x : 'Action', effort: '—' }
  })

  const linked =
    Array.isArray(r.linked_process_ids) ?
      r.linked_process_ids.map((x) => String(x)).filter(Boolean)
    : []

  const enrichment_log = Array.isArray(r.enrichment_log) ? (r.enrichment_log as Record<string, unknown>[]) : []

  return {
    id,
    title: r.title,
    description: typeof r.description === 'string' ? r.description : null,
    category: typeof r.category === 'string' ? r.category : null,
    priority: typeof r.priority === 'string' ? r.priority : null,
    status: typeof r.status === 'string' ? r.status : 'active',
    recommendation_type: recType,
    automation_type,
    composite_score: typeof r.composite_score === 'number' ? r.composite_score : null,
    base_score: typeof r.base_score === 'number' ? r.base_score : null,
    llm_score: typeof r.llm_score === 'number' ? r.llm_score : null,
    llm_rationale: typeof r.llm_rationale === 'string' ? r.llm_rationale : null,
    score_divergence_flag: Boolean(r.score_divergence_flag),
    estimated_roi:
      r.estimated_roi != null && Number.isFinite(Number(r.estimated_roi)) ? Number(r.estimated_roi) : null,
    assumptions_json:
      r.assumptions_json && typeof r.assumptions_json === 'object' && !Array.isArray(r.assumptions_json) ?
        (r.assumptions_json as Record<string, unknown>)
      : {},
    scenarios_json:
      r.scenarios_json && typeof r.scenarios_json === 'object' && !Array.isArray(r.scenarios_json) ?
        (r.scenarios_json as Record<string, unknown>)
      : {},
    actions_json,
    linked_process_ids: linked,
    enrichment_log,
    analysis_inputs_json: Array.isArray(r.analysis_inputs_json) ? r.analysis_inputs_json : undefined,
  }
}

function normalizeList(data: unknown): { items: Recommendation[]; total: number; page: number; page_size: number } {
  if (!data || typeof data !== 'object') return { items: [], total: 0, page: 1, page_size: PAGE_SIZE }
  const d = data as {
    items?: unknown[]
    total?: number
    page?: number
    page_size?: number
  }
  const items = Array.isArray(d.items)
    ? (d.items.map(normalizeRecommendation).filter(Boolean) as Recommendation[])
    : []
  return {
    items,
    total: typeof d.total === 'number' ? d.total : items.length,
    page: typeof d.page === 'number' ? d.page : 1,
    page_size: typeof d.page_size === 'number' ? d.page_size : PAGE_SIZE,
  }
}

function useGridColumns() {
  const [cols, setCols] = useState(1)
  useEffect(() => {
    const update = () => {
      if (window.matchMedia('(min-width: 1024px)').matches) setCols(3)
      else if (window.matchMedia('(min-width: 768px)').matches) setCols(2)
      else setCols(1)
    }
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])
  return cols
}

function chunkRows<T>(arr: T[], size: number): T[][] {
  if (size < 1) return [arr]
  const out: T[][] = []
  for (let i = 0; i < arr.length; i += size) {
    out.push(arr.slice(i, i + size))
  }
  return out
}

const AUTOMATION_LABEL: Record<AutomationKey, string> = {
  deterministic: 'Deterministic',
  agentic: 'Agentic',
  hybrid: 'Hybrid',
}

const STAGE_LABELS: Record<string, string> = {
  stage_1_candidates: 'Discovering candidates…',
  stage_2_scoring: 'Scoring candidates…',
  stage_3_llm: 'AI analysis & narrative generation…',
  stage_4_persist: 'Computing projections & saving…',
}

function PipelineBanner({ currentStage, stageResults, onCancel, isCancelling }: {
  currentStage?: string | null
  stageResults?: Record<string, unknown>
  onCancel: () => void
  isCancelling: boolean
}) {
  const stageName = currentStage && currentStage in STAGE_LABELS
    ? STAGE_LABELS[currentStage]
    : 'Pipeline running'

  const completedStages: string[] = []
  const sr = stageResults ?? {}
  if (sr.stage_1) completedStages.push('Candidates found')
  if (sr.stage_2) completedStages.push('Scoring complete')
  if (sr.stage_3) completedStages.push('AI analysis complete')

  return (
    <div className="flex items-center gap-3 rounded-xl border border-navy-200 bg-navy-50 px-5 py-3.5">
      <Loader2 className="h-5 w-5 flex-shrink-0 animate-spin text-navy-600" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-navy-900">{stageName}</p>
        <p className="text-xs text-navy-600">
          {completedStages.length > 0
            ? completedStages.join(' → ')
            : 'Analyzing processes, scoring candidates, and generating financial projections. Typically 2–5 minutes.'}
        </p>
      </div>
      <button
        type="button"
        disabled={isCancelling}
        onClick={onCancel}
        className="inline-flex flex-shrink-0 items-center gap-1.5 rounded-lg border border-navy-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-700 shadow-sm hover:bg-navy-100 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <X className="h-3.5 w-3.5" />
        {isCancelling ? 'Cancelling…' : 'Cancel'}
      </button>
    </div>
  )
}

export default function RecommendationsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabRaw = (searchParams.get('status') || 'active').toLowerCase()
  const statusTab: StatusTab =
    tabRaw === 'accepted' ? 'accepted' : tabRaw === 'dismissed' ? 'dismissed' : 'active'
  const statusFilter = statusTab

  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('score')
  const [automationFilters, setAutomationFilters] = useState<Set<AutomationKey>>(() => new Set())
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const gridCols = useGridColumns()

  const apiAutomationType = automationFilters.size === 1 ? [...automationFilters][0] : undefined

  const { data: listData, isLoading: listLoading, isError: listError, error: listErr, refetch } =
    useRecommendations({
      page,
      page_size: PAGE_SIZE,
      status: statusFilter,
      sort: sortApiParam(sortKey),
      automation_type: apiAutomationType,
    })

  const queryClient = useQueryClient()
  const generateMutation = useGenerateRecommendations()
  const cancelMutation = useCancelRecommendations()
  const updateStatusMutation = useUpdateRecommendationStatus()
  const { data: pipelineStatus } = useRecommendationPipelineStatus()

  const pipelineRunning = pipelineStatus?.status === 'running' || pipelineStatus?.status === 'pending'
  const pipelineBusy = pipelineRunning || generateMutation.isPending

  const prevPipelineStatus = useRef<string | undefined>(undefined)
  useEffect(() => {
    const s = pipelineStatus?.status
    const prev = prevPipelineStatus.current
    if (prev !== undefined && (prev === 'running' || prev === 'pending') && (s === 'completed' || s === 'failed' || s === 'cancelled')) {
      void queryClient.invalidateQueries({ queryKey: ['recommendations'] })
    }
    prevPipelineStatus.current = s
  }, [pipelineStatus?.status, queryClient])

  const { items, total, page_size } = useMemo(() => normalizeList(listData), [listData])
  const portfolio = usePortfolio(total)

  const setTab = (next: StatusTab) => {
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev)
      p.set('status', next)
      return p
    })
    setPage(1)
    setExpandedId(null)
  }

  useEffect(() => {
    setPage(1)
  }, [q, sortKey, automationFilters])

  const filteredItems = useMemo(() => {
    let next = items
    if (automationFilters.size > 0 && automationFilters.size < 3) {
      next = next.filter((r) => automationFilters.has(r.automation_type))
    }
    if (!q.trim()) return next
    const qq = q.toLowerCase()
    return next.filter(
      (c) =>
        c.title.toLowerCase().includes(qq) ||
        (c.category ?? '').toLowerCase().includes(qq) ||
        (c.description ?? '').toLowerCase().includes(qq),
    )
  }, [items, q, automationFilters])

  const rowChunks = useMemo(() => chunkRows(filteredItems, gridCols), [filteredItems, gridCols])

  const totalPages = Math.max(1, Math.ceil(total / page_size))
  const startIdx = total === 0 ? 0 : (page - 1) * page_size + 1
  const endIdx = total === 0 ? 0 : Math.min(page * page_size, total)

  const toggleAutomation = (key: AutomationKey) => {
    setAutomationFilters((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const handleExpand = (id: string) => {
    setExpandedId((cur) => (cur === id ? null : id))
  }

  const handleStatusChange = (id: string, status: string) => {
    updateStatusMutation.mutate(
      { id, status },
      {
        onSuccess: () => setExpandedId(null),
      },
    )
  }

  if (listLoading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Recommendations</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Prioritized remediation and automation opportunities ranked by ROI, blast radius, and architectural fit.
          </p>
        </div>
        <LoadingState message="Loading recommendations…" />
      </div>
    )
  }

  if (listError) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Recommendations</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Prioritized remediation and automation opportunities ranked by ROI, blast radius, and architectural fit.
          </p>
        </div>
        <ErrorState message={listErr instanceof Error ? listErr.message : undefined} />
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Recommendations</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Prioritized remediation and automation opportunities ranked by ROI, blast radius, and architectural fit.
          </p>
        </div>
        <button
          type="button"
          disabled={pipelineBusy}
          onClick={() => generateMutation.mutate()}
          className="inline-flex items-center gap-2 self-start rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pipelineBusy ?
            <Loader2 className="h-4 w-4 animate-spin" />
          : <Sparkles className="h-4 w-4" />}
          {pipelineBusy ? 'Generating…' : 'Generate'}
        </button>
      </div>

      {pipelineBusy ? (
        <PipelineBanner
          currentStage={pipelineStatus?.current_stage}
          stageResults={pipelineStatus?.stage_results}
          onCancel={() => cancelMutation.mutate()}
          isCancelling={cancelMutation.isPending}
        />
      ) : pipelineStatus?.status === 'failed' ? (
        <div className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-5 py-3.5">
          <div>
            <p className="text-sm font-semibold text-red-900">Pipeline failed</p>
            <p className="text-xs text-red-600">
              {pipelineStatus.error || 'An unexpected error occurred. Check logs for details.'}
            </p>
          </div>
        </div>
      ) : null}

      <PortfolioDashboard portfolio={portfolio} />

      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Recommendation status">
          {(
            [
              ['active', 'Active'],
              ['accepted', 'Accepted'],
              ['dismissed', 'Dismissed'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={statusTab === key}
              onClick={() => setTab(key)}
              className={clsx(
                'rounded-full px-4 py-2 text-sm font-semibold ring-1 ring-inset transition-colors',
                statusTab === key ?
                  'bg-navy-800 text-white ring-navy-800'
                : 'bg-white text-slate-700 ring-slate-200 hover:bg-slate-50',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex w-full flex-col gap-3 lg:flex-row lg:items-center lg:justify-end xl:w-auto">
          <div className="relative flex min-w-[200px] items-center gap-2">
            <ArrowDownWideNarrow className="pointer-events-none absolute left-3 h-4 w-4 text-slate-400" aria-hidden />
            <select
              aria-label="Sort recommendations"
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="w-full cursor-pointer appearance-none rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-8 text-sm font-semibold text-navy-900 shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-navy-200"
            >
              <option value="score">Score</option>
              <option value="npv">NPV</option>
              <option value="priority">Priority</option>
              <option value="title">Title</option>
            </select>
          </div>

          <SearchBar
            value={q}
            onChange={setQ}
            placeholder="Search recommendations…"
            className="lg:min-w-[280px]"
          />
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Automation</span>
          {(['deterministic', 'agentic', 'hybrid'] as const).map((key) => {
            const on = automationFilters.has(key)
            return (
              <button
                key={key}
                type="button"
                onClick={() => toggleAutomation(key)}
                className={clsx(
                  'rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ring-inset transition-colors',
                  key === 'deterministic' &&
                    (on ?
                      'bg-emerald-50 text-emerald-900 ring-emerald-200'
                    : 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50'),
                  key === 'agentic' &&
                    (on ?
                      'bg-orange-50 text-orange-900 ring-orange-200'
                    : 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50'),
                  key === 'hybrid' &&
                    (on ?
                      'bg-blue-50 text-blue-900 ring-blue-200'
                    : 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50'),
                )}
              >
                {AUTOMATION_LABEL[key]}
              </button>
            )
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => portfolio.selectAll(filteredItems.map((c) => c.id))}
            disabled={filteredItems.length === 0}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Layers className="h-3.5 w-3.5" aria-hidden />
            Select visible
          </button>
          <button
            type="button"
            onClick={() => portfolio.clearAll()}
            disabled={portfolio.selectedIds.size === 0}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Clear portfolio
          </button>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Viewing {total === 0 ? 0 : `${startIdx}-${endIdx}`} of {total}
          </p>
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={<Sparkles className="h-10 w-10" />}
          title="No recommendations in this view"
          description="Generate recommendations after connecting a platform."
        />
      ) : filteredItems.length === 0 ? (
        <EmptyState
          icon={<Sparkles className="h-10 w-10" />}
          title="No matches"
          description="Try different filters or search terms."
        />
      ) : (
        <>
          <div className="space-y-6">
            {rowChunks.map((row, rowIdx) => {
              const expanded = row.find((r) => r.id === expandedId) ?? null
              return (
                <Fragment key={row.map((r) => r.id).join('|') || String(rowIdx)}>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {row.map((rec) => (
                      <RecommendationCard
                        key={rec.id}
                        rec={rec}
                        isSelected={portfolio.isSelected(rec.id)}
                        onToggleSelect={portfolio.toggle}
                        onExpand={handleExpand}
                        isExpanded={expandedId === rec.id}
                      />
                    ))}
                  </div>
                  {expanded ?
                    <RecommendationDetail rec={expanded} onStatusChange={handleStatusChange} />
                  : null}
                </Fragment>
              )
            })}
          </div>

          {totalPages > 1 ? (
            <div className="flex items-center justify-center gap-4">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-xs font-medium text-slate-500">
                Page {page} / {totalPages}
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
