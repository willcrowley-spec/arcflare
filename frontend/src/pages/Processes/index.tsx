import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  GitBranch,
  Layers,
  Sparkles,
  Timer,
  Workflow,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import { useQueryClient } from '@tanstack/react-query'
import { KpiCard } from '@/components/KpiCard'
import { SearchBar } from '@/components/SearchBar'
import { StatusBadge } from '@/components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import { DiscoveryPipeline } from '@/components/DiscoveryPipeline'
import { GapsPanel } from './GapsPanel'
import {
  useConfirmProcess,
  useDiscoveryStatus,
  useProcesses,
  useRejectProcess,
  useStartDiscovery,
} from '@/hooks/useApi'
import type { DiscoveryStatus } from '@/types'

type ProcessKpis = {
  total_processes?: number
  active_count?: number | null
  draft_count?: number
  published_count?: number
  domain_count?: number
  needs_review_count?: number
  gap_count?: number
}

type ProcessItem = {
  id: string
  name: string
  category?: string | null
  description?: string | null
  automation_potential?: string | null
  value_classification?: string | null
  source?: string | null
  status: string
  sub_process_count: number
  managed_asset_count: number
  level?: string
  confidence_score?: number | null
  needs_review?: boolean
  narrative?: string | null
  parent_id?: string | null
  children?: ProcessItem[]
}

function normalizeProcessList(data: unknown): {
  items: ProcessItem[]
  tree: ProcessItem[]
  kpis: ProcessKpis
} {
  if (!data || typeof data !== 'object') return { items: [], tree: [], kpis: {} }
  const d = data as { items?: unknown[]; tree?: unknown[]; kpis?: ProcessKpis }
  const items = Array.isArray(d.items)
    ? (d.items as ProcessItem[]).filter((p) => p && typeof p.id === 'string')
    : []
  const tree = Array.isArray(d.tree)
    ? (d.tree as ProcessItem[]).filter((p) => p && typeof p.id === 'string')
    : []
  return { items, tree, kpis: d.kpis ?? {} }
}

function hasPriorDiscovery(data: DiscoveryStatus | undefined): boolean {
  if (!data) return false
  const rid = data.run_id?.trim()
  if (rid) return true
  if (data.started_at || data.completed_at) return true
  if (data.status && data.status !== 'idle') return true
  return Object.keys(data.phases ?? {}).length > 0
}

function processHealthFromStatus(status: string): 'OPTIMIZED' | 'NEEDS ATTENTION' | 'DRAFT' {
  const s = status.toLowerCase()
  if (s === 'published' || s === 'confirmed') return 'OPTIMIZED'
  if (s === 'discovered') return 'DRAFT'
  if (s === 'rejected') return 'NEEDS ATTENTION'
  if (s === 'draft') return 'DRAFT'
  return 'NEEDS ATTENTION'
}

function confidenceBadgeForScore(score: number | null | undefined): ReactNode {
  if (score == null || Number.isNaN(score)) return null
  if (score >= 0.8) {
    return (
      <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 ring-1 ring-emerald-200/80">
        High confidence
      </span>
    )
  }
  if (score >= 0.5) {
    return (
      <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-900 ring-1 ring-amber-200/80">
        Medium confidence
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-800 ring-1 ring-red-200/80">
      Low confidence
    </span>
  )
}

export default function ProcessesPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error, refetch } = useProcesses()
  const { data: discoveryData } = useDiscoveryStatus()
  const startDiscovery = useStartDiscovery()
  const confirmMutation = useConfirmProcess()
  const rejectMutation = useRejectProcess()

  const { items, tree, kpis } = useMemo(() => normalizeProcessList(data), [data])

  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [q, setQ] = useState('')

  const prevDiscoveryStatusRef = useRef<string | undefined>(undefined)

  useEffect(() => {
    const s = discoveryData?.status
    const prev = prevDiscoveryStatusRef.current
    if (prev !== undefined && prev !== 'completed' && s === 'completed') {
      void queryClient.invalidateQueries({ queryKey: ['processes'] })
    }
    prevDiscoveryStatusRef.current = s
  }, [discoveryData?.status, queryClient])

  const handleAccordionToggle = useCallback((id: string) => {
    setOpen((s) => ({ ...s, [id]: !s[id] }))
  }, [])

  const displayTree = useMemo(() => (tree.length > 0 ? tree : items), [tree, items])

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase()
    if (!qq) return displayTree

    function matchesSearch(p: ProcessItem): boolean {
      return (
        p.name.toLowerCase().includes(qq) ||
        (p.category ?? '').toLowerCase().includes(qq) ||
        (p.description ?? '').toLowerCase().includes(qq) ||
        (p.narrative ?? '').toLowerCase().includes(qq) ||
        (p.automation_potential ?? '').toLowerCase().includes(qq) ||
        (p.value_classification ?? '').toLowerCase().includes(qq)
      )
    }

    function filterTree(nodes: ProcessItem[]): ProcessItem[] {
      return nodes.reduce<ProcessItem[]>((acc, node) => {
        const childMatches = filterTree(node.children ?? [])
        if (matchesSearch(node) || childMatches.length > 0) {
          acc.push({ ...node, children: childMatches.length > 0 ? childMatches : node.children })
        }
        return acc
      }, [])
    }

    return filterTree(displayTree)
  }, [displayTree, q])

  const discoveryKpis = useMemo(
    () => ({
      domainCount: kpis.domain_count ?? 0,
      needsReviewCount: kpis.needs_review_count ?? 0,
      gapCount: kpis.gap_count ?? 0,
      totalProcesses: kpis.total_processes ?? items.length,
    }),
    [kpis.domain_count, kpis.gap_count, kpis.needs_review_count, kpis.total_processes, items.length],
  )

  const priorDiscovery = hasPriorDiscovery(discoveryData)
  const discoveryRunning = discoveryData?.status === 'running'
  const discoveryBusy = discoveryRunning || startDiscovery.isPending

  const handleStartDiscovery = useCallback(() => {
    startDiscovery.mutate()
  }, [startDiscovery])

  const discoveryButton = useMemo(() => {
    if (discoveryBusy) {
      return (
        <button
          type="button"
          disabled
          className="inline-flex cursor-not-allowed items-center gap-2 rounded-lg border border-slate-200 bg-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-500 shadow-sm"
        >
          <Sparkles className="h-4 w-4 opacity-60" />
          Discovering…
        </button>
      )
    }
    if (!priorDiscovery) {
      return (
        <button
          type="button"
          onClick={handleStartDiscovery}
          className="inline-flex items-center gap-2 rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900"
        >
          <Sparkles className="h-4 w-4" />
          Discover Processes
        </button>
      )
    }
    return (
      <button
        type="button"
        onClick={handleStartDiscovery}
        className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
      >
        <Sparkles className="h-4 w-4 text-navy-700" />
        Re-discover
      </button>
    )
  }, [discoveryBusy, priorDiscovery, handleStartDiscovery])

  const renderProcessActions = useCallback(
    (p: ProcessItem) => {
      const isDiscovered = p.status.toLowerCase() === 'discovered'
      return (
        <div className="flex flex-wrap items-center gap-2">
          {p.level === 'domain' ? (
            <Link
              to={`/processes/${p.id}/map`}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
            >
              <GitBranch className="h-3.5 w-3.5" />
              Open process map
            </Link>
          ) : null}
          {isDiscovered ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={confirmMutation.isPending || rejectMutation.isPending}
                onClick={() => confirmMutation.mutate(p.id)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Check className="h-3.5 w-3.5" /> Confirm
              </button>
              <button
                type="button"
                disabled={confirmMutation.isPending || rejectMutation.isPending}
                onClick={() => rejectMutation.mutate(p.id)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-sm font-semibold text-red-700 shadow-sm hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <X className="h-3.5 w-3.5" /> Reject
              </button>
            </div>
          ) : null}
        </div>
      )
    },
    [confirmMutation, rejectMutation],
  )

  const renderChildren = useCallback(
    (children: ProcessItem[], depth: number) => {
      if (!children.length) return null
      return (
        <div className={clsx('space-y-2', depth === 0 ? 'mt-3' : 'mt-2 ml-4')}>
          {children.map((child) => {
            const childExpanded = open[child.id] ?? false
            const childHealth = processHealthFromStatus(child.status)
            const childConf = confidenceBadgeForScore(child.confidence_score ?? null)
            const childKids = child.children ?? []
            const childMeta = [
              childKids.length > 0 ? `${childKids.length} sub-processes` : null,
              child.level,
            ]
              .filter(Boolean)
              .join(' · ')
            return (
              <div
                key={child.id}
                className={clsx(
                  'rounded-lg border bg-white/60',
                  child.needs_review ? 'border-amber-200' : 'border-slate-200/60',
                )}
              >
                <button
                  type="button"
                  onClick={() => handleAccordionToggle(child.id)}
                  className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-slate-50/60"
                >
                  <div className="flex min-w-0 flex-1 items-start gap-2">
                    <span className="mt-0.5 shrink-0 text-slate-400">
                      {childExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-navy-900">{child.name}</p>
                      {childMeta ? <p className="mt-0.5 text-xs text-slate-500">{childMeta}</p> : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {child.needs_review ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200/80">
                        <Eye className="h-3 w-3" />
                        Needs review
                      </span>
                    ) : null}
                    {childConf}
                    <StatusBadge status={childHealth} />
                  </div>
                </button>
                {childExpanded ? (
                  <div className="border-t border-slate-100 px-4 py-3">
                    {child.description ? <p className="text-sm text-slate-600">{child.description}</p> : null}
                    {child.narrative ? (
                      <div className="mt-2 rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Narrative</p>
                        <p className="mt-1 text-sm leading-relaxed text-slate-700">{child.narrative}</p>
                      </div>
                    ) : null}
                    <div className="mt-2">{renderProcessActions(child)}</div>
                    {childKids.length > 0 ? renderChildren(childKids, depth + 1) : null}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )
    },
    [open, handleAccordionToggle, renderProcessActions],
  )

  const listSection = useMemo(() => {
    if (filtered.length === 0) {
      return (
        <EmptyState
          icon={<Workflow className="h-10 w-10" />}
          title="No processes discovered"
          description="Connect a platform and run discovery to populate this catalog."
        />
      )
    }
    return (
      <div className="space-y-3">
        {filtered.map((p) => {
          const expanded = open[p.id] ?? false
          const kids = p.children ?? []
          const childCount = kids.length || p.sub_process_count
          const meta = [
            childCount > 0 ? `${childCount} sub-processes` : null,
            p.managed_asset_count > 0 ? `${p.managed_asset_count} assets` : null,
            p.category ? p.category : null,
            p.level ? p.level : null,
          ]
            .filter(Boolean)
            .join(' · ')
          const health = processHealthFromStatus(p.status)
          const confBadge = confidenceBadgeForScore(p.confidence_score ?? null)
          return (
            <AccordionRow
              key={p.id}
              id={p.id}
              title={p.name}
              meta={meta}
              status={health}
              confidenceBadge={confBadge}
              expanded={expanded}
              onToggle={handleAccordionToggle}
            >
              <div className="space-y-3">
                {p.description ? <p className="text-sm text-slate-600">{p.description}</p> : null}
                {p.narrative ? (
                  <div className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2.5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Discovery narrative</p>
                    <p className="mt-1 text-sm leading-relaxed text-slate-700">{p.narrative}</p>
                  </div>
                ) : null}
                {renderProcessActions(p)}
                {kids.length > 0 ? renderChildren(kids, 0) : null}
              </div>
            </AccordionRow>
          )
        })}
      </div>
    )
  }, [filtered, handleAccordionToggle, open, renderProcessActions, renderChildren])

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Business Processes</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            End-to-end operational map with discovery-driven domains, review queues, and cross-domain handoff gaps.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(() => {
            const firstDomain = items.find((i) => i.level === 'domain')
            if (!firstDomain) return null
            return (
              <Link
                to={`/processes/${firstDomain.id}/map`}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
              >
                <GitBranch className="h-4 w-4" />
                Process Map
              </Link>
            )
          })()}
          {discoveryButton}
        </div>
      </div>

      <DiscoveryPipeline data={discoveryData} isActive={discoveryRunning} />

      {isLoading ? (
        <LoadingState message="Loading processes…" />
      ) : isError ? (
        <div className="space-y-4">
          <ErrorState message={error instanceof Error ? error.message : undefined} />
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <KpiCard
              icon={Layers}
              label="Domain processes"
              value={String(discoveryKpis.domainCount)}
              sublabel={`${discoveryKpis.totalProcesses} process steps in catalog`}
              helpText="Domains are the top-level business areas (e.g. Sales, Finance). The step count includes all sub-processes and individual steps discovered within those domains."
            />
            <KpiCard
              icon={Activity}
              label="Needs review"
              value={String(discoveryKpis.needsReviewCount)}
              sublabel="Flagged during discovery"
              helpText="Steps flagged by AI with low confidence scores or incomplete metadata. Expand a process below and look for amber-highlighted items. Use the Confirm or Reject buttons to review each one."
            />
            <KpiCard
              icon={AlertTriangle}
              label="Handoff gaps"
              value={String(discoveryKpis.gapCount)}
              sublabel="Cross-domain gaps detected"
              helpText="Points where a process in one domain hands off to another domain but no clear automation or documented procedure exists. Use 'Chat with AI' on each gap to investigate and document the handoff."
            />
          </div>

          <GapsPanel />

          <div className="max-w-xl">
            <SearchBar value={q} onChange={setQ} placeholder="Search processes, narratives, or systems…" />
          </div>

          {listSection}
        </>
      )}
    </div>
  )
}

function AccordionRow({
  title,
  meta,
  status,
  confidenceBadge,
  expanded,
  onToggle,
  children,
  id,
}: {
  title: string
  meta: string
  status: 'OPTIMIZED' | 'NEEDS ATTENTION' | 'DRAFT'
  confidenceBadge?: ReactNode
  expanded: boolean
  onToggle: (id: string) => void
  children: ReactNode
  id: string
}) {
  const panelId = `panel-${id}`
  const headerId = `header-${id}`
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
      <button
        type="button"
        id={headerId}
        onClick={() => onToggle(id)}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left hover:bg-slate-50/80"
      >
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <span className="mt-0.5 shrink-0 text-slate-400" aria-hidden="true">
            {expanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          </span>
          <div className="min-w-0">
            <p className="text-base font-semibold text-navy-900">{title}</p>
            <p className="mt-1 text-sm text-slate-600">{meta}</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          {confidenceBadge}
          <StatusBadge status={status} />
        </div>
      </button>
      {expanded ? (
        <div id={panelId} role="region" aria-labelledby={headerId} className="border-t border-slate-100 bg-slate-50/40 px-5 py-4">
          {children}
        </div>
      ) : null}
    </div>
  )
}

function SubProcess({
  title,
  tags,
  stat,
  tone,
  action,
}: {
  title: string
  tags: string[]
  stat: string
  tone: 'ok' | 'bad' | 'ai'
  action?: ReactNode
}) {
  return (
    <div
      className={clsx(
        'flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between',
        tone === 'bad' ? 'border-red-200 bg-red-50/60' : 'border-slate-200 bg-white',
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={clsx(
            'mt-0.5 flex h-9 w-9 items-center justify-center rounded-lg ring-1 ring-inset',
            tone === 'ai' && 'bg-violet-50 text-violet-700 ring-violet-200',
            tone === 'ok' && 'bg-emerald-50 text-emerald-700 ring-emerald-200',
            tone === 'bad' && 'bg-red-100 text-red-800 ring-red-200',
          )}
        >
          {tone === 'ai' ? <Sparkles className="h-4 w-4" /> : tone === 'bad' ? <Timer className="h-4 w-4" /> : <Workflow className="h-4 w-4" />}
        </span>
        <div>
          <p className="font-semibold text-navy-900">{title}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200/80"
              >
                {t}
              </span>
            ))}
          </div>
          <p className={clsx('mt-2 text-xs font-semibold', tone === 'bad' ? 'text-red-800' : 'text-slate-600')}>
            {stat}
          </p>
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
