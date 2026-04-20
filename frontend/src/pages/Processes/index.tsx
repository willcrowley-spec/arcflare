import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Eye,
  GitBranch,
  Layers,
  Sparkles,
  Workflow,
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
  useDiscoveryStatus,
  useProcesses,
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

type EvidenceSource = {
  type: string
  id?: string
  chunk_id?: string
  api_name?: string
  label?: string
  category?: string
  document_name?: string
  excerpt?: string
  relevance?: string
  confidence?: number
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
  evidence_sources?: EvidenceSource[]
  actors?: Array<{ name: string; type: string }>
  trigger_conditions?: Array<{ description: string }>
  system_touchpoints?: Array<{ name: string; type: string; operation?: string }>
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

  const renderProcessDetails = useCallback(
    (p: ProcessItem) => {
      const evidence = p.evidence_sources ?? []
      const actors = p.actors ?? []
      const triggers = p.trigger_conditions ?? []
      const touchpoints = p.system_touchpoints ?? []
      const hasEnrichment = actors.length > 0 || triggers.length > 0 || touchpoints.length > 0

      return (
        <div className="space-y-3">
          {p.level === 'domain' ? (
            <Link
              to={`/processes/${p.id}/map`}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
            >
              <GitBranch className="h-3.5 w-3.5" />
              Open process map
            </Link>
          ) : null}

          {hasEnrichment ? (
            <div className="grid gap-2 sm:grid-cols-3">
              {actors.length > 0 ? (
                <div className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Actors</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {actors.map((a, i) => (
                      <span key={i} className={clsx(
                        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1',
                        a.type === 'system' ? 'bg-violet-50 text-violet-800 ring-violet-200' :
                        a.type === 'integration' ? 'bg-sky-50 text-sky-800 ring-sky-200' :
                        'bg-slate-100 text-slate-700 ring-slate-200',
                      )}>
                        {a.name}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              {triggers.length > 0 ? (
                <div className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Triggers</p>
                  <ul className="mt-1.5 space-y-1">
                    {triggers.slice(0, 3).map((t, i) => (
                      <li key={i} className="text-xs text-slate-700">{t.description}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {touchpoints.length > 0 ? (
                <div className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">System Touchpoints</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {touchpoints.slice(0, 6).map((tp, i) => (
                      <span key={i} className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200">
                        {tp.name}{tp.operation ? ` (${tp.operation})` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {p.automation_potential || p.value_classification ? (
            <div className="flex flex-wrap gap-2">
              {p.automation_potential ? (
                <span className={clsx(
                  'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1',
                  p.automation_potential === 'high' ? 'bg-emerald-50 text-emerald-800 ring-emerald-200' :
                  p.automation_potential === 'medium' ? 'bg-amber-50 text-amber-800 ring-amber-200' :
                  'bg-slate-100 text-slate-700 ring-slate-200',
                )}>
                  Automation: {p.automation_potential}
                </span>
              ) : null}
              {p.value_classification ? (
                <span className={clsx(
                  'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ring-1',
                  p.value_classification === 'VA' ? 'bg-emerald-50 text-emerald-800 ring-emerald-200' :
                  p.value_classification === 'BVA' ? 'bg-sky-50 text-sky-800 ring-sky-200' :
                  'bg-orange-50 text-orange-800 ring-orange-200',
                )}>
                  {p.value_classification === 'VA' ? 'Value-Adding' : p.value_classification === 'BVA' ? 'Business-Necessary' : 'Non-Value'}
                </span>
              ) : null}
            </div>
          ) : null}

          {evidence.length > 0 ? (
            <div className="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2.5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Evidence ({evidence.length} sources)
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {evidence.map((ev, i) => (
                  <span
                    key={i}
                    title={ev.relevance || ev.excerpt || ''}
                    className={clsx(
                      'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1',
                      ev.type === 'metadata_object' && 'bg-blue-50 text-blue-800 ring-blue-200',
                      ev.type === 'automation' && 'bg-violet-50 text-violet-800 ring-violet-200',
                      ev.type === 'component' && 'bg-indigo-50 text-indigo-800 ring-indigo-200',
                      ev.type === 'document_chunk' && 'bg-amber-50 text-amber-800 ring-amber-200',
                      ev.type === 'community' && 'bg-teal-50 text-teal-800 ring-teal-200',
                    )}
                  >
                    {ev.type === 'metadata_object' ? ev.api_name || ev.label :
                     ev.type === 'automation' ? ev.api_name || ev.label :
                     ev.type === 'component' ? ev.api_name :
                     ev.type === 'document_chunk' ? ev.document_name :
                     ev.type}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )
    },
    [],
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
                  child.needs_review
                    ? 'border-orange-300 bg-orange-50/30 ring-1 ring-orange-200/60'
                    : 'border-slate-200/60',
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
                      <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 px-2 py-0.5 text-[11px] font-semibold text-orange-800 ring-1 ring-orange-300/80">
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
                    <div className="mt-2">{renderProcessDetails(child)}</div>
                    {childKids.length > 0 ? renderChildren(childKids, depth + 1) : null}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )
    },
    [open, handleAccordionToggle, renderProcessDetails],
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
                {renderProcessDetails(p)}
                {kids.length > 0 ? renderChildren(kids, 0) : null}
              </div>
            </AccordionRow>
          )
        })}
      </div>
    )
  }, [filtered, handleAccordionToggle, open, renderProcessDetails, renderChildren])

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
              helpText="Steps flagged by AI with low confidence scores or insufficient evidence. Expand a process below and look for amber-highlighted items to review evidence sources."
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

