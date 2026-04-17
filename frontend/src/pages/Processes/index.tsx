import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  GitBranch,
  Sparkles,
  Timer,
  Workflow,
} from 'lucide-react'
import clsx from 'clsx'
import { KpiCard } from '@/components/KpiCard'
import { SearchBar } from '@/components/SearchBar'
import { StatusBadge } from '@/components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import { useGenerateProcesses, useProcesses } from '@/hooks/useApi'

type ProcessKpis = {
  total_processes?: number
  avg_efficiency?: number | null
  automation_coverage?: number | null
  active_count?: number | null
  draft_count?: number
  published_count?: number
}

type ProcessItem = {
  id: string
  name: string
  category?: string | null
  description?: string | null
  efficiency_score?: number | null
  automation_level?: string | null
  source?: string | null
  status: string
  sub_process_count: number
  managed_asset_count: number
}

function normalizeProcessList(data: unknown): { items: ProcessItem[]; kpis: ProcessKpis } {
  if (!data || typeof data !== 'object') return { items: [], kpis: {} }
  const d = data as { items?: unknown[]; kpis?: ProcessKpis }
  const items = Array.isArray(d.items)
    ? (d.items as ProcessItem[]).filter((p) => p && typeof p.id === 'string')
    : []
  return { items, kpis: d.kpis ?? {} }
}

function processHealthFromStatus(status: string): 'OPTIMIZED' | 'NEEDS ATTENTION' | 'DRAFT' {
  const s = status.toLowerCase()
  if (s === 'published') return 'OPTIMIZED'
  if (s === 'draft') return 'DRAFT'
  return 'NEEDS ATTENTION'
}

export default function ProcessesPage() {
  const { data, isLoading, isError, error, refetch } = useProcesses()
  const generateMutation = useGenerateProcesses()
  const { items, kpis } = useMemo(() => normalizeProcessList(data), [data])

  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [q, setQ] = useState('')

  function toggle(id: string) {
    setOpen((s) => ({ ...s, [id]: !s[id] }))
  }

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase()
    if (!qq) return items
    return items.filter(
      (p) =>
        p.name.toLowerCase().includes(qq) ||
        (p.category ?? '').toLowerCase().includes(qq) ||
        (p.description ?? '').toLowerCase().includes(qq) ||
        (p.automation_level ?? '').toLowerCase().includes(qq),
    )
  }, [items, q])

  const totalProcesses = kpis.total_processes ?? items.length
  const avgEff = kpis.avg_efficiency
  const automationPct =
    kpis.automation_coverage != null
      ? typeof kpis.automation_coverage === 'number'
        ? `${kpis.automation_coverage.toFixed(1)}%`
        : String(kpis.automation_coverage)
      : avgEff != null
        ? `${Number(avgEff).toFixed(1)}%`
        : '—'
  const activeOrPublished = kpis.active_count ?? kpis.published_count ?? 0
  const draftAttention = kpis.draft_count ?? 0

  if (isLoading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Business Processes</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            End-to-end operational map with automation coverage, latency hotspots, and agent-assisted steps.
          </p>
        </div>
        <LoadingState message="Loading processes…" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Business Processes</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            End-to-end operational map with automation coverage, latency hotspots, and agent-assisted steps.
          </p>
        </div>
        <ErrorState message={error instanceof Error ? error.message : undefined} />
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
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Business Processes</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            End-to-end operational map with automation coverage, latency hotspots, and agent-assisted steps.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {items[0] ? (
            <Link
              to={`/processes/${items[0].id}/map`}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
            >
              <GitBranch className="h-4 w-4" />
              Process Map
            </Link>
          ) : null}
          <button
            type="button"
            disabled={generateMutation.isPending}
            onClick={() => generateMutation.mutate()}
            className="inline-flex items-center gap-2 rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Sparkles className="h-4 w-4" />
            {generateMutation.isPending ? 'Generating…' : 'Generate'}
          </button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard
          icon={Workflow}
          label="Total processes"
          value={String(totalProcesses)}
          sublabel={`${activeOrPublished} published · ${draftAttention} draft`}
        />
        <KpiCard
          icon={Activity}
          label="Automation coverage (avg)"
          value={automationPct}
          sublabel="From efficiency / coverage KPIs"
        />
        <KpiCard
          icon={AlertTriangle}
          label="Draft processes"
          value={String(draftAttention)}
          sublabel="Candidates for review and publishing"
        />
      </div>

      <div className="max-w-xl">
        <SearchBar
          value={q}
          onChange={setQ}
          placeholder="Search processes, owners, or systems…"
        />
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Workflow className="h-10 w-10" />}
          title="No processes discovered"
          description="Connect a platform and run analysis first."
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((p) => {
            const expanded = open[p.id] ?? false
            const meta = [
              `${p.sub_process_count} sub-processes`,
              `${p.managed_asset_count} assets`,
              p.category ? p.category : 'Uncategorized',
            ].join(' · ')
            return (
              <AccordionRow
                key={p.id}
                id={p.id}
                title={p.name}
                meta={meta}
                status={processHealthFromStatus(p.status)}
                expanded={expanded}
                onToggle={() => toggle(p.id)}
              >
                <div className="space-y-3">
                  {p.description ? <p className="text-sm text-slate-600">{p.description}</p> : null}
                  <div className="flex flex-wrap gap-2">
                    <Link
                      to={`/processes/${p.id}/map`}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
                    >
                      <GitBranch className="h-3.5 w-3.5" />
                      Open process map
                    </Link>
                  </div>
                  {p.automation_level || p.efficiency_score != null ? (
                    <SubProcess
                      title="Automation profile"
                      tags={
                        [p.automation_level, p.efficiency_score != null ? `Efficiency ${Number(p.efficiency_score).toFixed(1)}` : null].filter(
                          Boolean,
                        ) as string[]
                      }
                      stat={p.source ? `Source: ${p.source}` : 'Mined from connected platforms'}
                      tone="ok"
                    />
                  ) : null}
                </div>
              </AccordionRow>
            )
          })}
        </div>
      )}
    </div>
  )
}

function AccordionRow({
  title,
  meta,
  status,
  expanded,
  onToggle,
  children,
  id,
}: {
  title: string
  meta: string
  status: 'OPTIMIZED' | 'NEEDS ATTENTION' | 'DRAFT'
  expanded: boolean
  onToggle: () => void
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
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left hover:bg-slate-50/80"
      >
        <div className="flex items-start gap-3">
          <span className="mt-0.5 text-slate-400" aria-hidden="true">
            {expanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
          </span>
          <div>
            <p className="text-base font-semibold text-navy-900">{title}</p>
            <p className="mt-1 text-sm text-slate-600">{meta}</p>
          </div>
        </div>
        <StatusBadge status={status} />
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
