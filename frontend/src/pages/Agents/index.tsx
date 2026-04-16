import { useMemo, useState } from 'react'
import { Cpu, Plus } from 'lucide-react'
import { DataTable, type ColumnDef } from '@/components/DataTable'
import { SearchBar } from '@/components/SearchBar'
import { StatusBadge } from '@/components/StatusBadge'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import { useAgents, useCreateAgent, useFleetAnalytics } from '@/hooks/useApi'

type AgentApi = {
  id: string
  name: string
  model?: string | null
  model_version?: string | null
  monthly_cap?: number | string | null
  total_spend: number | string
  total_tokens?: number
  status: string
  accuracy: number
  tasks_completed: number
  capability_tags?: string[]
}

type FleetKpis = {
  total_agents?: number
  active_agents?: number
  total_spend?: number | string
  total_tokens?: number
  total_tasks?: number
}

function normalizeAgents(data: unknown): { items: AgentApi[]; kpis: FleetKpis } {
  if (!data || typeof data !== 'object') return { items: [], kpis: {} }
  const d = data as { items?: unknown[]; kpis?: FleetKpis }
  const items = Array.isArray(d.items)
    ? (d.items as AgentApi[]).filter((a) => a && typeof a.id === 'string' && typeof a.name === 'string')
    : []
  return { items, kpis: d.kpis ?? {} }
}

function normalizeFleet(data: unknown): {
  kpis: FleetKpis
  by_model: Record<string, number>
} {
  if (!data || typeof data !== 'object') return { kpis: {}, by_model: {} }
  const d = data as { kpis?: FleetKpis; by_model?: Record<string, number> }
  return {
    kpis: d.kpis ?? {},
    by_model: d.by_model && typeof d.by_model === 'object' ? d.by_model : {},
  }
}

function formatUsd(n: number | string | null | undefined): string {
  if (n == null || n === '') return '—'
  const num = typeof n === 'string' ? parseFloat(n) : n
  if (Number.isNaN(num)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(num)
}

function capPct(spend: number, cap: number): number {
  if (!cap || cap <= 0) return 0
  return Math.min(100, Math.round((spend / cap) * 100))
}

function runtimeBadgeStatus(status: string): string {
  const s = status.toLowerCase()
  if (s === 'active') return 'RUNNING'
  if (s === 'idle') return 'IDLE'
  if (s === 'error') return 'ERROR'
  if (s === 'deploying') return 'DEPLOYING'
  return status.toUpperCase().replace(/_/g, ' ')
}

type AgentRow = {
  id: string
  name: string
  model: string
  runtime: string
  tasks: string
  accuracy: string
  spend: string
}

export default function AgentsPage() {
  const [q, setQ] = useState('')
  const { data: agentsData, isLoading: agentsLoading, isError: agentsErr, error: agentsError, refetch } = useAgents()
  const { data: fleetData, isLoading: fleetLoading } = useFleetAnalytics()
  const createMutation = useCreateAgent()

  const { items, kpis } = useMemo(() => normalizeAgents(agentsData), [agentsData])
  const { by_model } = useMemo(() => normalizeFleet(fleetData), [fleetData])

  const chartData = useMemo(() => {
    const entries = Object.entries(by_model)
    if (!entries.length) return []
    return entries.map(([name, v]) => ({ name: name.length > 12 ? `${name.slice(0, 12)}…` : name, v }))
  }, [by_model])

  const topAgents = useMemo(() => {
    const sorted = [...items].sort((a, b) => {
      const as = Number(a.total_spend ?? 0)
      const bs = Number(b.total_spend ?? 0)
      return bs - as
    })
    return sorted.slice(0, 2)
  }, [items])

  const rows: AgentRow[] = useMemo(() => {
    return items.map((r) => ({
      id: r.id,
      name: r.name,
      model: r.model ?? '—',
      runtime: runtimeBadgeStatus(r.status),
      tasks: (r.tasks_completed ?? 0).toLocaleString(),
      accuracy: `${Number(r.accuracy ?? 0).toFixed(1)}%`,
      spend: `${formatUsd(r.total_spend)} / ${(r.total_tokens ?? 0).toLocaleString()} tokens`,
    }))
  }, [items])

  const filteredRows = useMemo(() => {
    if (!q.trim()) return rows
    const qq = q.toLowerCase()
    return rows.filter((r) => r.name.toLowerCase().includes(qq) || r.model.toLowerCase().includes(qq))
  }, [rows, q])

  const avgAccuracy = useMemo(() => {
    if (!items.length) return null
    const sum = items.reduce((a, b) => a + Number(b.accuracy ?? 0), 0)
    return sum / items.length
  }, [items])

  const fleetAvailability = useMemo(() => {
    const t = kpis.total_agents ?? items.length
    const a = kpis.active_agents ?? items.filter((x) => x.status.toLowerCase() === 'active').length
    if (!t) return null
    return Math.round((a / t) * 100)
  }, [kpis, items])

  const columns: ColumnDef<AgentRow>[] = [
    {
      id: 'name',
      header: 'Agent',
      sortValue: (r) => r.name,
      cell: (r) => <span className="font-medium text-navy-900">{r.name}</span>,
    },
    {
      id: 'model',
      header: 'Model',
      sortValue: (r) => r.model,
      cell: (r) => <span className="text-slate-700">{r.model}</span>,
    },
    {
      id: 'runtime',
      header: 'Status',
      sortValue: (r) => r.runtime,
      cell: (r) => <StatusBadge status={r.runtime} />,
    },
    {
      id: 'tasks',
      header: 'Tasks (30d)',
      sortValue: (r) => Number(r.tasks.replace(/,/g, '')),
      cell: (r) => <span className="tabular-nums text-slate-700">{r.tasks}</span>,
    },
    {
      id: 'acc',
      header: 'Accuracy',
      sortValue: (r) => parseFloat(r.accuracy),
      cell: (r) => <span className="tabular-nums text-slate-700">{r.accuracy}</span>,
    },
    {
      id: 'spend',
      header: 'Spend / Tokens',
      sortValue: (r) => r.spend,
      cell: (r) => <span className="text-sm text-slate-700">{r.spend}</span>,
    },
  ]

  const loading = agentsLoading || fleetLoading

  if (loading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Agent Management</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Monitor runtime health, spend guardrails, and task quality across the deployed agent fleet.
          </p>
        </div>
        <LoadingState message="Loading agents…" />
      </div>
    )
  }

  if (agentsErr) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Agent Management</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Monitor runtime health, spend guardrails, and task quality across the deployed agent fleet.
          </p>
        </div>
        <ErrorState message={agentsError instanceof Error ? agentsError.message : undefined} />
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
          <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Agent Management</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Monitor runtime health, spend guardrails, and task quality across the deployed agent fleet.
          </p>
        </div>
        <button
          type="button"
          disabled={createMutation.isPending}
          onClick={() =>
            createMutation.mutate({
              name: `Agent ${new Date().toISOString().slice(0, 19).replace('T', ' ')}`,
              model: 'gpt-4o-mini',
              monthly_cap: 500,
            })
          }
          className="inline-flex items-center gap-2 self-start rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Plus className="h-4 w-4" />
          {createMutation.isPending ? 'Deploying…' : 'Deploy New Agent'}
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={<Cpu className="h-10 w-10" />}
          title="No agents deployed yet."
          description="Deploy an agent to start tracking usage, spend, and accuracy here."
        />
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            {topAgents.map((a) => {
              const cap = Number(a.monthly_cap ?? 0)
              const spent = Number(a.total_spend ?? 0)
              const pct = capPct(spent, cap)
              const tags = Array.isArray(a.capability_tags) ? a.capability_tags : []
              return (
                <section
                  key={a.id}
                  className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-navy-900">{a.name}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {(a.model ?? '—').toUpperCase()} · {a.model_version ?? 'Standard'}
                      </p>
                    </div>
                    <StatusBadge status={runtimeBadgeStatus(a.status)} />
                  </div>
                  <div className="mt-5 grid gap-4 sm:grid-cols-2">
                    <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Monthly cap</p>
                      <p className="mt-2 text-xl font-semibold text-navy-900">{cap ? formatUsd(cap) : '—'}</p>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Spend</p>
                      <p className="mt-2 text-xl font-semibold text-navy-900">{formatUsd(spent)}</p>
                      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white ring-1 ring-slate-200">
                        <div className="h-full rounded-full bg-orange-500" style={{ width: `${pct}%` }} />
                      </div>
                      <p className="mt-2 text-xs font-semibold text-slate-600">{pct}% of cap utilized</p>
                    </div>
                  </div>
                  <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap gap-2">
                      {(tags.length ? tags : ['Agent']).map((t) => (
                        <span
                          key={t}
                          className="rounded-full bg-navy-50 px-2.5 py-0.5 text-[11px] font-semibold text-navy-800 ring-1 ring-navy-200/80"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                    <button
                      type="button"
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
                    >
                      Configure
                    </button>
                  </div>
                </section>
              )
            })}
          </div>

          <section className="rounded-2xl border border-slate-200/80 bg-navy-800 p-6 text-white shadow-md ring-1 ring-black/10">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/10">
                  <Cpu className="h-6 w-6 text-orange-300" />
                </span>
                <div>
                  <h2 className="text-lg font-semibold">Fleet efficiency</h2>
                  <p className="text-sm text-slate-200">Agents by model (fleet analytics)</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
                  <p className="text-xs uppercase tracking-wide text-slate-200">Avg accuracy</p>
                  <p className="mt-2 text-2xl font-semibold">
                    {avgAccuracy != null ? `${avgAccuracy.toFixed(1)}%` : '—'}
                  </p>
                </div>
                <div className="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
                  <p className="text-xs uppercase tracking-wide text-slate-200">Fleet availability</p>
                  <p className="mt-2 text-2xl font-semibold text-emerald-300">
                    {fleetAvailability != null ? `${fleetAvailability}%` : '—'}
                  </p>
                </div>
              </div>
            </div>
            <div className="mt-6 h-56 w-full rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
              {chartData.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <XAxis dataKey="name" stroke="#cbd5e1" tick={{ fill: '#e2e8f0', fontSize: 12 }} />
                    <YAxis hide />
                    <Tooltip
                      cursor={{ fill: 'rgba(255,255,255,0.06)' }}
                      contentStyle={{
                        background: '#0f1736',
                        border: '1px solid rgba(255,255,255,0.12)',
                        borderRadius: 8,
                      }}
                      labelStyle={{ color: '#e2e8f0' }}
                    />
                    <Bar dataKey="v" fill="#fb923c" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-300">
                  No model distribution yet.
                </div>
              )}
            </div>
          </section>

          <div className="space-y-4">
            <div className="max-w-xl">
              <SearchBar value={q} onChange={setQ} placeholder="Search agents…" />
            </div>
            <DataTable
              columns={columns}
              rows={filteredRows}
              rowKey={(r) => r.id}
              pageSize={4}
              searchPlaceholder=""
              showSearch={false}
              resourceName="agents"
              emptyLabel="No agents match your search."
            />
          </div>
        </>
      )}
    </div>
  )
}
