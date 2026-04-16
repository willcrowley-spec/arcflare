import { useMemo, useState } from 'react'
import { Cpu, Plus } from 'lucide-react'
import { DataTable, type ColumnDef } from '@/components/DataTable'
import { SearchBar } from '@/components/SearchBar'
import { StatusBadge } from '@/components/StatusBadge'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const topAgents = [
  {
    name: 'Strategic Analyst',
    model: 'GPT-4O',
    tier: 'ENTERPRISE V2.1',
    status: 'RUNNING',
    cap: '$12,000',
    spent: '$8,640.22',
    pct: 72,
    tags: ['API', 'LLM'],
  },
  {
    name: 'Data Architect',
    model: 'CLAUDE 3.5 SONNET',
    tier: 'STANDARD',
    status: 'IDLE',
    cap: '$5,000',
    spent: '$750.00',
    pct: 15,
    tags: ['DB', 'CSV'],
  },
]

const chartData = [
  { name: 'W1', v: 42 },
  { name: 'W2', v: 58 },
  { name: 'W3', v: 51 },
  { name: 'W4', v: 64 },
  { name: 'W5', v: 70 },
  { name: 'W6', v: 66 },
]

type AgentRow = {
  id: string
  name: string
  model: string
  runtime: string
  tasks: string
  accuracy: string
  spend: string
}

const tableRows: AgentRow[] = [
  {
    id: '1',
    name: 'Strategic Analyst',
    model: 'GPT-4o-Turbo',
    runtime: 'Running',
    tasks: '12,482',
    accuracy: '98.2%',
    spend: '$8,640.22 / 12.2m tokens',
  },
  {
    id: '2',
    name: 'Customer Liaison',
    model: 'GPT-4o-Mini',
    runtime: 'Running',
    tasks: '48,912',
    accuracy: '94.1%',
    spend: '$1,240.50 / 84.5m tokens',
  },
  {
    id: '3',
    name: 'Data Architect',
    model: 'Claude 3.5 Sonnet',
    runtime: 'Idle',
    tasks: '2,301',
    accuracy: '99.8%',
    spend: '$750.00 / 1.2m tokens',
  },
  {
    id: '4',
    name: 'Compliance Bot',
    model: 'Custom Llama 3',
    runtime: 'Running',
    tasks: '9,122',
    accuracy: '100%',
    spend: '$128.45 / Self-hosted',
  },
  {
    id: '5',
    name: 'Insights Curator',
    model: 'GPT-4o',
    runtime: 'Idle',
    tasks: '812',
    accuracy: '97.1%',
    spend: '$412.10 / 3.4m tokens',
  },
  {
    id: '6',
    name: 'Field Mapper',
    model: 'GPT-4o-Mini',
    runtime: 'Running',
    tasks: '6,402',
    accuracy: '96.4%',
    spend: '$902.33 / 22.1m tokens',
  },
  {
    id: '7',
    name: 'Policy Navigator',
    model: 'Claude 3 Opus',
    runtime: 'Running',
    tasks: '3,881',
    accuracy: '99.1%',
    spend: '$2,410.00 / 6.8m tokens',
  },
  {
    id: '8',
    name: 'Voice Intake',
    model: 'Whisper Large v3',
    runtime: 'Idle',
    tasks: '441',
    accuracy: '95.0%',
    spend: '$88.20 / 0.4m tokens',
  },
]

export default function AgentsPage() {
  const [q, setQ] = useState('')

  const rows = useMemo(() => {
    if (!q.trim()) return tableRows
    const qq = q.toLowerCase()
    return tableRows.filter((r) => r.name.toLowerCase().includes(qq) || r.model.toLowerCase().includes(qq))
  }, [q])

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
      cell: (r) => <StatusBadge status={r.runtime.toUpperCase()} />,
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
          className="inline-flex items-center gap-2 self-start rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900"
        >
          <Plus className="h-4 w-4" />
          Deploy New Agent
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {topAgents.map((a) => (
          <section
            key={a.name}
            className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-navy-900">{a.name}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {a.model} · {a.tier}
                </p>
              </div>
              <StatusBadge status={a.status} />
            </div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Monthly cap</p>
                <p className="mt-2 text-xl font-semibold text-navy-900">{a.cap}</p>
              </div>
              <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Spend</p>
                <p className="mt-2 text-xl font-semibold text-navy-900">{a.spent}</p>
                <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white ring-1 ring-slate-200">
                  <div
                    className="h-full rounded-full bg-orange-500"
                    style={{ width: `${Math.min(100, a.pct)}%` }}
                  />
                </div>
                <p className="mt-2 text-xs font-semibold text-slate-600">{a.pct}% of cap utilized</p>
              </div>
            </div>
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-2">
                {a.tags.map((t) => (
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
        ))}
      </div>

      <section className="rounded-2xl border border-slate-200/80 bg-navy-800 p-6 text-white shadow-md ring-1 ring-black/10">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/10">
              <Cpu className="h-6 w-6 text-orange-300" />
            </span>
            <div>
              <h2 className="text-lg font-semibold">Fleet efficiency</h2>
              <p className="text-sm text-slate-200">Rolling 6-week throughput index (normalized)</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
              <p className="text-xs uppercase tracking-wide text-slate-200">Avg accuracy</p>
              <p className="mt-2 text-2xl font-semibold">98.4%</p>
            </div>
            <div className="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
              <p className="text-xs uppercase tracking-wide text-slate-200">Efficiency</p>
              <p className="mt-2 text-2xl font-semibold text-emerald-300">+12.4%</p>
            </div>
          </div>
        </div>
        <div className="mt-6 h-56 w-full rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <XAxis dataKey="name" stroke="#cbd5e1" tick={{ fill: '#e2e8f0', fontSize: 12 }} />
              <YAxis hide />
              <Tooltip
                cursor={{ fill: 'rgba(255,255,255,0.06)' }}
                contentStyle={{ background: '#0f1736', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8 }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Bar dataKey="v" fill="#fb923c" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="space-y-4">
        <div className="max-w-xl">
          <SearchBar value={q} onChange={setQ} placeholder="Search agents…" />
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.id}
          pageSize={4}
          searchPlaceholder=""
          showSearch={false}
          resourceName="agents"
        />
      </div>
    </div>
  )
}
