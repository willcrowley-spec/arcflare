import { useMemo, useState } from 'react'
import {
  Database,
  FileSpreadsheet,
  FileText,
  Layers,
  Link2,
  Search as SearchIcon,
} from 'lucide-react'
import clsx from 'clsx'
import { DataTable, type ColumnDef } from '@/components/DataTable'
import { SearchBar } from '@/components/SearchBar'
import { StatusBadge } from '@/components/StatusBadge'

type SourceFilter = 'ALL' | 'SALESFORCE' | 'HUBSPOT' | 'NETSUITE' | 'MULESOFT' | 'CONFLUENCE'

type AnalysisRow = {
  id: string
  name: string
  kind: 'Metadata' | 'Data Record' | 'Business Doc'
  platform: string
  platformKey: SourceFilter
  status: string
  lastUpdated: string
}

const rows: AnalysisRow[] = [
  {
    id: '1',
    name: 'AccountManager__c',
    kind: 'Metadata',
    platform: 'Salesforce',
    platformKey: 'SALESFORCE',
    status: 'CLEAN',
    lastUpdated: '5 mins ago',
  },
  {
    id: '2',
    name: 'Compliance_Audit_Log.xlsx',
    kind: 'Business Doc',
    platform: 'Confluence',
    platformKey: 'CONFLUENCE',
    status: 'CLEAN',
    lastUpdated: 'Yesterday',
  },
  {
    id: '3',
    name: 'ERP_Inbound_Mapping',
    kind: 'Metadata',
    platform: 'MuleSoft',
    platformKey: 'MULESOFT',
    status: 'CONFLICT',
    lastUpdated: '2 hrs ago',
  },
  {
    id: '4',
    name: 'FY24_Architectural_Standards.docx',
    kind: 'Business Doc',
    platform: 'NetSuite',
    platformKey: 'NETSUITE',
    status: 'ANALYZING',
    lastUpdated: '12 mins ago',
  },
  {
    id: '5',
    name: 'Lead_Record_77412',
    kind: 'Data Record',
    platform: 'HubSpot',
    platformKey: 'HUBSPOT',
    status: 'CLEAN',
    lastUpdated: '1 hr ago',
  },
]

const platformStyles: Record<string, string> = {
  Salesforce: 'bg-sky-50 text-sky-900 ring-sky-200',
  HubSpot: 'bg-orange-50 text-orange-900 ring-orange-200',
  NetSuite: 'bg-emerald-50 text-emerald-900 ring-emerald-200',
  MuleSoft: 'bg-violet-50 text-violet-900 ring-violet-200',
  Confluence: 'bg-blue-50 text-blue-900 ring-blue-200',
}

const sources = [
  { name: 'Salesforce', entities: '1,284', status: 'CONNECTED' as const },
  { name: 'HubSpot', entities: '892', status: 'CONNECTED' as const },
  { name: 'NetSuite', entities: '1,647', status: 'CONNECTED' as const },
  { name: 'MuleSoft', entities: '369', status: 'SYNCING' as const },
]

function KindIcon({ kind }: { kind: AnalysisRow['kind'] }) {
  if (kind === 'Metadata') return <Layers className="h-4 w-4 text-navy-600" />
  if (kind === 'Data Record') return <Database className="h-4 w-4 text-emerald-600" />
  return <FileText className="h-4 w-4 text-orange-600" />
}

export default function AnalysisPage() {
  const [tab, setTab] = useState<'ALL' | 'Metadata' | 'DATA' | 'DOCS'>('ALL')
  const [source, setSource] = useState<SourceFilter>('ALL')
  const [q, setQ] = useState('')

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (tab === 'Metadata' && r.kind !== 'Metadata') return false
      if (tab === 'DATA' && r.kind !== 'Data Record') return false
      if (tab === 'DOCS' && r.kind !== 'Business Doc') return false
      if (source !== 'ALL' && r.platformKey !== source) return false
      if (q.trim()) {
        const qq = q.toLowerCase()
        if (!r.name.toLowerCase().includes(qq) && !r.platform.toLowerCase().includes(qq)) return false
      }
      return true
    })
  }, [q, source, tab])

  const columns: ColumnDef<AnalysisRow>[] = [
    {
      id: 'name',
      header: 'Entity / Document',
      sortValue: (r) => r.name,
      cell: (r) => (
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-50 ring-1 ring-slate-200/80">
            <KindIcon kind={r.kind} />
          </span>
          <div>
            <p className="font-medium text-slate-900">{r.name}</p>
            <p className="text-xs text-slate-500">{r.kind}</p>
          </div>
        </div>
      ),
    },
    {
      id: 'type',
      header: 'Type',
      sortValue: (r) => r.kind,
      cell: (r) => <span className="text-slate-700">{r.kind}</span>,
    },
    {
      id: 'platform',
      header: 'Platform',
      sortValue: (r) => r.platform,
      cell: (r) => (
        <span
          className={clsx(
            'inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset',
            platformStyles[r.platform] ?? 'bg-slate-50 text-slate-800 ring-slate-200',
          )}
        >
          {r.platform}
        </span>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      sortValue: (r) => r.status,
      cell: (r) => <StatusBadge status={r.status} />,
    },
    {
      id: 'updated',
      header: 'Last Updated',
      sortValue: (r) => r.lastUpdated,
      cell: (r) => <span className="text-slate-600">{r.lastUpdated}</span>,
    },
  ]

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Analysis</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Unified visibility across metadata, operational records, and business documentation with live platform
            health.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center justify-center gap-2 self-start rounded-lg bg-navy-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm ring-1 ring-navy-900/10 hover:bg-navy-800"
        >
          <Link2 className="h-4 w-4" />
          + Connect
        </button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {(
            [
              ['ALL', 'All'],
              ['Metadata', 'Metadata'],
              ['DATA', 'Data Records'],
              ['DOCS', 'Business Docs'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={clsx(
                'rounded-full px-4 py-1.5 text-sm font-medium ring-1 ring-inset transition-colors',
                tab === key
                  ? 'bg-navy-800 text-white ring-navy-800'
                  : 'bg-white text-slate-700 ring-slate-200 hover:bg-slate-50',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
          <SearchBar value={q} onChange={setQ} placeholder="Search entities, platforms, or owners…" className="flex-1" />
          <div className="flex items-center gap-2 sm:min-w-[200px]">
            <SearchIcon className="hidden h-4 w-4 text-slate-400 sm:block" aria-hidden />
            <label className="sr-only" htmlFor="source-filter">
              Source filter
            </label>
            <select
              id="source-filter"
              value={source}
              onChange={(e) => setSource(e.target.value as SourceFilter)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-200"
            >
              <option value="ALL">All sources</option>
              <option value="SALESFORCE">Salesforce</option>
              <option value="HUBSPOT">HubSpot</option>
              <option value="NETSUITE">NetSuite</option>
              <option value="MULESOFT">MuleSoft</option>
              <option value="CONFLUENCE">Confluence</option>
            </select>
          </div>
        </div>
      </div>

      <DataTable columns={columns} rows={filtered} rowKey={(r) => r.id} pageSize={8} />

      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Platform Sources</h2>
            <p className="text-sm text-slate-600">Live connection inventory and entity coverage</p>
          </div>
          <FileSpreadsheet className="h-8 w-8 text-slate-300" aria-hidden />
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {sources.map((s) => (
            <div
              key={s.name}
              className="rounded-lg border border-slate-100 bg-slate-50/60 p-4 ring-1 ring-slate-900/5"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-navy-900">{s.name}</p>
                  <p className="mt-1 text-xs text-slate-500">{s.entities} entities indexed</p>
                </div>
                <StatusBadge status={s.status} />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
