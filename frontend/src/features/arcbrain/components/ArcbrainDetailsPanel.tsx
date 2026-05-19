import { AlertTriangle, FileSearch, GitBranch, HelpCircle, Loader2, RefreshCw, type LucideIcon } from 'lucide-react'
import type { ArcbrainBlastRadius, ArcbrainEvidenceRef, ArcbrainLens, ArcbrainNode, ArcbrainSearchResult, ArcbrainSummary } from '@/types'
import { formatCurrency, formatPercent } from '@/features/arcbrain/graph/model'

interface ArcbrainDetailsPanelProps {
  node: ArcbrainNode | null
  summary: ArcbrainSummary
  lens: ArcbrainLens
  nodeLoading: boolean
  blastRadius: ArcbrainBlastRadius | null
  blastRadiusLoading: boolean
  replacementHeatLoading: boolean
  searchResult: ArcbrainSearchResult | null
}

export function ArcbrainDetailsPanel({
  node,
  summary,
  lens,
  nodeLoading,
  blastRadius,
  blastRadiusLoading,
  replacementHeatLoading,
  searchResult,
}: ArcbrainDetailsPanelProps) {
  const evidence = normalizeEvidenceRefs(node?.evidence_refs)
  const assumptions = searchResult?.assumptions ?? []
  const missing = searchResult?.missing_evidence ?? []

  return (
    <aside className="min-w-0 space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-navy-900">Trust & Details</h2>
            <p className="mt-1 text-sm text-slate-600">
              {node ? 'Selected graph record' : 'Select a node to inspect evidence.'}
            </p>
          </div>
          {nodeLoading ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" /> : <FileSearch className="h-5 w-5 text-slate-400" />}
        </div>

        {node ? (
          <div className="mt-4 space-y-4">
            <div>
              <p className="break-words text-lg font-semibold leading-snug text-navy-900">{node.label}</p>
              <p className="mt-1 text-xs font-semibold uppercase text-slate-500">{String(node.node_type).replace(/_/g, ' ')}</p>
              {node.summary ? <p className="mt-3 text-sm leading-relaxed text-slate-700">{node.summary}</p> : null}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <MiniMetric label="Confidence" value={formatPercent(node.confidence)} />
              <MiniMetric label="Replaceability" value={formatPercent(node.replaceability_score)} />
              <MiniMetric label="Economic value" value={formatCurrency(node.economic_value)} />
              <MiniMetric label="Risk" value={node.risk_level ?? 'unknown'} />
            </div>

            <EvidenceSection title="Evidence" empty="No evidence refs returned for this node." items={evidence} />
            <TextList title="Assumptions" icon={HelpCircle} empty="No assumptions returned for the current question." items={assumptions} />
            <TextList title="Missing Evidence" icon={AlertTriangle} empty="No missing-evidence fields returned for the current question." items={missing} />
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-600">The graph is loaded, but no node is selected.</p>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-navy-900">Lens Facts</h3>
          {(blastRadiusLoading || replacementHeatLoading) ? <RefreshCw className="h-4 w-4 animate-spin text-slate-400" /> : <GitBranch className="h-4 w-4 text-slate-400" />}
        </div>
        <div className="mt-3 space-y-2 text-sm text-slate-700">
          {lens === 'blast_radius' ? (
            <>
              <FactRow label="Upstream" value={String(blastRadius?.upstream_nodes?.length ?? 0)} />
              <FactRow label="Downstream" value={String(blastRadius?.downstream_nodes?.length ?? 0)} />
              <FactRow label="Affected processes" value={String(blastRadius?.affected_processes?.length ?? 0)} />
              <FactRow label="Risk impact" value={blastRadius?.risk_impact ?? 'n/a'} />
            </>
          ) : (
            <>
              <FactRow label="High risk nodes" value={String(summary.high_risk_count ?? 'n/a')} />
              <FactRow label="Stale evidence" value={String(summary.stale_count ?? 'n/a')} />
              <FactRow label="Missing evidence" value={String(summary.missing_evidence_count ?? 'n/a')} />
              <FactRow label="Manual density" value={formatPercent(summary.manual_work_density)} />
            </>
          )}
        </div>
      </section>
    </aside>
  )
}

function MiniMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-navy-900">{value}</p>
    </div>
  )
}

function FactRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
      <span className="text-slate-500">{label}</span>
      <span className="truncate font-semibold text-navy-900">{value ?? 'n/a'}</span>
    </div>
  )
}

function EvidenceSection({ title, items, empty }: { title: string; items: ArcbrainEvidenceRef[]; empty: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase text-slate-500">{title}</p>
      {items.length > 0 ? (
        <div className="mt-2 space-y-2">
          {items.slice(0, 5).map((item, index) => (
            <div key={`${item.id ?? item.label ?? index}`} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <p className="truncate text-sm font-semibold text-navy-900">{item.label ?? item.source_ref ?? item.id ?? 'Evidence'}</p>
              <p className="mt-1 text-xs text-slate-500">
                {[item.source_type, formatPercent(item.confidence)].filter(Boolean).join(' / ')}
              </p>
              {item.excerpt ? <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-600">{item.excerpt}</p> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200">{empty}</p>
      )}
    </div>
  )
}

function TextList({
  title,
  items,
  empty,
  icon: Icon,
}: {
  title: string
  items: string[]
  empty: string
  icon: LucideIcon
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase text-slate-500">{title}</p>
      {items.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {items.slice(0, 5).map((item) => (
            <li key={item} className="flex gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
              <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-orange-500" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600 ring-1 ring-slate-200">{empty}</p>
      )}
    </div>
  )
}

function normalizeEvidenceRefs(items: ArcbrainNode['evidence_refs'] | undefined): ArcbrainEvidenceRef[] {
  if (!Array.isArray(items)) return []
  return items.map((item) => (typeof item === 'string' ? { id: item, label: item } : item))
}
