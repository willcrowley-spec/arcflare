import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Layers, Radar, Shield, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import { SearchBar } from '@/components/SearchBar'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import { useGenerateRecommendations, useRecommendations, useRecommendationSummary } from '@/hooks/useApi'

type RecRow = {
  id: string
  title: string
  description?: string | null
  category?: string | null
  priority?: string | null
  status: string
  estimated_roi?: number | string | null
  composite_score?: number | null
  analysis_inputs_json?: unknown[]
  actions_json?: unknown[]
  impact_json?: Record<string, unknown>
  architecture_health_json?: Record<string, unknown>
}

type Summary = {
  total?: number
  active?: number
  implemented?: number
  avg_roi?: number | null
  top_category?: string | null
}

function normalizeList(data: unknown): { items: RecRow[]; total: number; page: number; page_size: number } {
  if (!data || typeof data !== 'object') return { items: [], total: 0, page: 1, page_size: 50 }
  const d = data as {
    items?: unknown[]
    total?: number
    page?: number
    page_size?: number
  }
  const items = Array.isArray(d.items)
    ? (d.items as RecRow[]).filter((r) => r && typeof r.id === 'string' && typeof r.title === 'string')
    : []
  return {
    items,
    total: typeof d.total === 'number' ? d.total : items.length,
    page: typeof d.page === 'number' ? d.page : 1,
    page_size: typeof d.page_size === 'number' ? d.page_size : 50,
  }
}

function normalizeSummary(data: unknown): Summary {
  if (!data || typeof data !== 'object') return {}
  const s = data as Summary
  return s
}

function formatMoney(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(n))
}

function actionToString(a: unknown): string {
  if (typeof a === 'string') return a
  if (a && typeof a === 'object' && 'title' in a && typeof (a as { title: unknown }).title === 'string') {
    return (a as { title: string }).title
  }
  if (a && typeof a === 'object' && 'type' in a && typeof (a as { type: unknown }).type === 'string') {
    return (a as { type: string }).type.replace(/_/g, ' ')
  }
  return 'Action'
}

function inputToString(x: unknown): string {
  if (typeof x === 'string') return x
  if (x && typeof x === 'object') return JSON.stringify(x).slice(0, 120)
  return String(x)
}

const PAGE_SIZE = 6

export default function RecommendationsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = (searchParams.get('status') || 'active').toLowerCase()
  const statusFilter = tabParam === 'implemented' ? 'implemented' : 'active'

  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')

  const { data: listData, isLoading: listLoading, isError: listError, error: listErr, refetch } = useRecommendations({
    page,
    page_size: PAGE_SIZE,
    status: statusFilter,
  })
  const { data: summaryData, isLoading: sumLoading } = useRecommendationSummary()
  const generateMutation = useGenerateRecommendations()

  const { items, total, page_size } = useMemo(() => normalizeList(listData), [listData])
  const summary = useMemo(() => normalizeSummary(summaryData), [summaryData])

  const setTab = (next: 'active' | 'implemented') => {
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev)
      p.set('status', next)
      return p
    })
    setPage(1)
  }

  useEffect(() => {
    setPage(1)
  }, [q])

  const filteredCards = useMemo(() => {
    if (!q.trim()) return items
    const qq = q.toLowerCase()
    return items.filter(
      (c) =>
        c.title.toLowerCase().includes(qq) ||
        (c.category ?? '').toLowerCase().includes(qq) ||
        (c.description ?? '').toLowerCase().includes(qq),
    )
  }, [items, q])

  const featured = useMemo(() => {
    const pool = filteredCards
    if (!pool.length) return null
    const sorted = [...pool].sort((a, b) => {
      const ar = Number(a.estimated_roi ?? 0)
      const br = Number(b.estimated_roi ?? 0)
      if (br !== ar) return br - ar
      return (b.composite_score ?? 0) - (a.composite_score ?? 0)
    })
    return sorted[0]
  }, [filteredCards, items])

  const inputs = useMemo(() => {
    if (!featured?.analysis_inputs_json?.length) return []
    return featured.analysis_inputs_json.slice(0, 6).map(inputToString)
  }, [featured])

  const actions = useMemo(() => {
    if (!featured?.actions_json?.length) return []
    return featured.actions_json.map(actionToString)
  }, [featured])

  const roiDisplay = featured?.estimated_roi != null ? formatMoney(Number(featured.estimated_roi)) : formatMoney(summary.avg_roi ?? null)

  const arch = useMemo(() => {
    for (const r of items) {
      const h = r.architecture_health_json
      if (h && typeof h === 'object' && Object.keys(h).length) return h
    }
    return null
  }, [items])

  const metaSync = useMemo(() => {
    const v = arch?.metadata_sync_pct ?? arch?.metadata_sync
    if (typeof v === 'number' && v >= 0 && v <= 100) return v
    if (summary.total && summary.total > 0) {
      return Math.min(100, Math.round(((summary.active ?? 0) / summary.total) * 100))
    }
    return null
  }, [arch, summary])

  const procOpt = useMemo(() => {
    const v = arch?.process_optimization_pct ?? arch?.process_optimization
    if (typeof v === 'number' && v >= 0 && v <= 100) return v
    const avgComp =
      items.length > 0
        ? items.reduce((a, b) => a + (b.composite_score ?? 0), 0) / items.length
        : null
    if (avgComp != null) return Math.min(100, Math.round(avgComp * 100))
    return null
  }, [arch, items])

  const totalPages = Math.max(1, Math.ceil(total / page_size))
  const startIdx = total === 0 ? 0 : (page - 1) * page_size + 1
  const endIdx = total === 0 ? 0 : Math.min(page * page_size, total)

  const loading = listLoading || sumLoading

  if (loading) {
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
          disabled={generateMutation.isPending}
          onClick={() => generateMutation.mutate()}
          className="inline-flex items-center gap-2 self-start rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Sparkles className="h-4 w-4" />
          {generateMutation.isPending ? 'Generating…' : 'Generate'}
        </button>
      </div>

      {featured ? (
        <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-md ring-1 ring-slate-900/5">
          <div className="border-b border-slate-100 bg-gradient-to-r from-white to-slate-50 px-6 py-5">
            <div className="flex flex-wrap items-center gap-2">
              {featured.priority ? (
                <span className="rounded-full bg-red-50 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-red-800 ring-1 ring-red-200">
                  {featured.priority}
                </span>
              ) : null}
              {featured.category || summary.top_category ? (
                <span className="rounded-full bg-navy-50 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-navy-800 ring-1 ring-navy-200">
                  {(featured.category ?? summary.top_category ?? '').replace(/_/g, ' ')}
                </span>
              ) : null}
              <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-orange-50 px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-orange-900 ring-1 ring-orange-200">
                <Sparkles className="h-3.5 w-3.5" />
                Top recommendation
              </span>
            </div>
            <h2 className="mt-4 text-2xl font-semibold tracking-tight text-navy-900">{featured.title}</h2>
            <p className="mt-3 max-w-4xl text-sm leading-relaxed text-slate-600">
              {featured.description ?? 'No description provided for this recommendation.'}
            </p>
            <div className="mt-6 grid gap-6 lg:grid-cols-3">
              <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-900">Estimated ROI</p>
                <p className="mt-2 text-3xl font-semibold text-emerald-900">
                  {roiDisplay === '—' ? '—' : `${roiDisplay}/yr`}
                </p>
                <p className="mt-1 text-xs text-emerald-800/90">Modeled from catalog averages when item ROI is blank</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Analysis inputs</p>
                <ul className="mt-3 space-y-2 text-sm text-slate-800">
                  {(inputs.length ? inputs : ['Connected platform signals']).map((i) => (
                    <li key={i} className="flex items-center gap-2">
                      <Layers className="h-4 w-4 shrink-0 text-navy-600" />
                      <span className="min-w-0 break-words">{i}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Required multi-step action</p>
                <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-800">
                  {(actions.length ? actions : ['Review details in downstream systems']).map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ol>
              </div>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                type="button"
                disabled
                title="Coming soon"
                className="inline-flex items-center justify-center rounded-lg bg-navy-800 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Initialize Deployment
              </button>
              <button
                type="button"
                disabled
                title="Coming soon"
                className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Analysis Details
              </button>
            </div>
          </div>
        </section>
      ) : null}

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4 rounded-2xl border border-slate-200/80 bg-navy-800 p-6 text-white shadow-md ring-1 ring-black/10">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">Multi-system impact</h2>
              <p className="mt-1 text-sm text-slate-200">Aggregate signals from the current recommendation catalog</p>
            </div>
            <Radar className="h-7 w-7 text-orange-300" />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <ImpactStat
              label="Active recommendations"
              value={String(summary.active ?? 0)}
              hint={`${summary.total ?? 0} total in org`}
            />
            <ImpactStat
              label="Implemented"
              value={String(summary.implemented ?? 0)}
              hint="Closed-loop remediations"
            />
            <ImpactStat
              label="Avg modeled ROI"
              value={formatMoney(summary.avg_roi ?? null)}
              hint="Mean of estimated ROI across catalog"
            />
          </div>
          <button
            type="button"
            disabled
            title="Coming soon"
            className="mt-2 inline-flex w-full items-center justify-center rounded-lg bg-white/10 px-4 py-2.5 text-sm font-semibold text-white ring-1 ring-white/15 hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
          >
            Review Full Audit
          </button>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-navy-700" />
            <h2 className="text-lg font-semibold text-navy-900">Architecture health</h2>
          </div>
          <div className="mt-5 space-y-5">
            {metaSync != null ? (
              <HealthBar label="Metadata sync" value={metaSync} color="bg-emerald-500" />
            ) : (
              <p className="text-sm text-slate-500">Metadata sync scores appear when analysis populates health JSON.</p>
            )}
            {procOpt != null ? (
              <HealthBar label="Process optimization" value={procOpt} color="bg-amber-400" />
            ) : (
              <p className="text-sm text-slate-500">Process optimization inferred from composite scores when available.</p>
            )}
          </div>
          <p className="mt-4 text-xs text-slate-500">
            Health scores combine drift detection, test coverage signals, and operational SLO adherence.
          </p>
        </div>
      </section>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Recommendation status filter">
          {(['active', 'implemented'] as const).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={statusFilter === t}
              onClick={() => setTab(t)}
              className={clsx(
                'rounded-full px-4 py-2 text-sm font-semibold ring-1 ring-inset transition-colors',
                statusFilter === t ? 'bg-navy-800 text-white ring-navy-800' : 'bg-white text-slate-700 ring-slate-200 hover:bg-slate-50',
              )}
            >
              {t === 'active' ? 'Active' : 'Implemented'}
            </button>
          ))}
        </div>
        <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center lg:w-auto">
          <SearchBar
            value={q}
            onChange={setQ}
            placeholder="Search recommendations…"
            className="sm:min-w-[320px]"
          />
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Viewing {total === 0 ? 0 : `${startIdx}-${endIdx}`} of {total} recommendations
          </p>
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={<Sparkles className="h-10 w-10" />}
          title="No recommendations in this view"
          description="Generate recommendations after connecting a platform."
        />
      ) : filteredCards.length === 0 ? (
        <EmptyState
          icon={<Sparkles className="h-10 w-10" />}
          title="No matches"
          description="Try a different search term."
        />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            {filteredCards.map((c) => (
              <article
                key={c.id}
                className="flex flex-col rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm ring-1 ring-slate-900/5"
              >
                <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
                  {(c.category ?? 'General').replace(/_/g, ' ')}
                </p>
                <h3 className="mt-2 text-lg font-semibold text-navy-900">{c.title}</h3>
                <div className="mt-4 flex flex-wrap gap-2">
                  {[c.priority, c.status, c.estimated_roi != null ? formatMoney(Number(c.estimated_roi)) : null]
                    .filter(Boolean)
                    .map((t) => (
                      <span
                        key={String(t)}
                        className="rounded-full bg-slate-50 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200/80"
                      >
                        {String(t)}
                      </span>
                    ))}
                </div>
                <div className="mt-auto pt-6">
                  <button
                    type="button"
                    disabled
                    title="Coming soon"
                    className="w-full rounded-lg bg-navy-800 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {c.status === 'implemented' ? 'Review' : 'Implement'}
                  </button>
                </div>
              </article>
            ))}
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

function ImpactStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
      <p className="text-xs uppercase tracking-wide text-slate-200">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      <p className="mt-1 text-xs text-slate-300">{hint}</p>
    </div>
  )
}

function HealthBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="font-semibold text-navy-900">{value}%</span>
      </div>
      <div
        className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-slate-100 ring-1 ring-slate-200/80"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}
