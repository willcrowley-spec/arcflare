import { formatCurrency, formatPercent, type ArcbrainGraphModel } from '@/features/arcbrain/graph/model'

interface ArcbrainHeaderProps {
  summary?: ArcbrainGraphModel['summary']
}

export function ArcbrainHeader({ summary }: ArcbrainHeaderProps) {
  return (
    <div className="space-y-4">
      <div className="flex min-w-0 flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Arcbrain</h1>
          <p className="mt-2 max-w-3xl break-words text-sm leading-relaxed text-slate-600">
            Evidence-backed operating graph for replacement planning, blast-radius analysis, and executive trust review.
          </p>
        </div>
      </div>

      <div className="grid w-full max-w-full min-w-0 gap-3 md:grid-cols-4">
        <MetricTile label="Nodes" value={String(summary?.node_count ?? 'n/a')} />
        <MetricTile label="Edges" value={String(summary?.edge_count ?? 'n/a')} />
        <MetricTile label="Evidence coverage" value={formatPercent(summary?.evidence_coverage)} />
        <MetricTile label="Replacement value" value={formatCurrency(summary?.replacement_value)} />
      </div>
    </div>
  )
}

export function ArcbrainStatusPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
      <span className="text-slate-500">{label}:</span>
      {value.replace(/_/g, ' ')}
    </span>
  )
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="w-full max-w-full min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
      <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight text-navy-900">{value}</p>
    </div>
  )
}
