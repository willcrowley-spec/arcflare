import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import {
  AlertTriangle,
  BrainCircuit,
  CircleDollarSign,
  FileSearch,
  GitBranch,
  HelpCircle,
  Loader2,
  Radar,
  RefreshCw,
  Search,
  ShieldCheck,
} from 'lucide-react'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import type { ArcbrainEvidenceRef, ArcbrainLens, ArcbrainNode } from '@/types'
import { ArcbrainGraphSurface } from '@/features/arcbrain/components/ArcbrainGraphSurface'
import {
  formatCurrency,
  formatDateTime,
  formatPercent,
  normalizeArcbrainSnapshot,
  normalizeSearchResult,
} from '@/features/arcbrain/graph/model'
import {
  useArcbrainBlastRadius,
  useArcbrainNode,
  useArcbrainReplacementHeat,
  useArcbrainSearch,
  useArcbrainSnapshot,
} from '@/features/arcbrain/hooks/useArcbrain'

const LENSES: Array<{ id: ArcbrainLens; label: string; icon: typeof BrainCircuit }> = [
  { id: 'overview', label: 'Overview', icon: BrainCircuit },
  { id: 'replacement_heat', label: 'Replacement Heat', icon: CircleDollarSign },
  { id: 'blast_radius', label: 'Blast Radius', icon: Radar },
  { id: 'trust', label: 'Trust', icon: ShieldCheck },
]

const TEMPLATE_QUESTIONS = [
  'What work can we replace without increasing customer risk?',
  'Which processes have high value but weak evidence?',
  'What depends on the selected node?',
  'Where are manual handoffs concentrated?',
  'What evidence supports the top replacement decision?',
]

export default function ArcbrainPage() {
  const [lens, setLens] = useState<ArcbrainLens>('overview')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const snapshotQuery = useArcbrainSnapshot()
  const searchMutation = useArcbrainSearch()

  const graph = useMemo(() => normalizeArcbrainSnapshot(snapshotQuery.data), [snapshotQuery.data])
  const selectedNodeQuery = useArcbrainNode(selectedNodeId)
  const blastRadiusQuery = useArcbrainBlastRadius(selectedNodeId, lens)
  const replacementHeatQuery = useArcbrainReplacementHeat(lens)
  const searchResult = useMemo(() => normalizeSearchResult(searchMutation.data), [searchMutation.data])

  useEffect(() => {
    if (!selectedNodeId && graph.nodes.length > 0) {
      setSelectedNodeId(graph.nodes[0].id)
    }
  }, [graph.nodes, selectedNodeId])

  useEffect(() => {
    const recommended = searchResult?.recommended_view
    if (recommended === 'overview' || recommended === 'replacement_heat' || recommended === 'blast_radius' || recommended === 'trust') {
      setLens(recommended)
    }
    if (searchResult?.nodes[0]?.id) {
      setSelectedNodeId(searchResult.nodes[0].id)
    }
  }, [searchResult])

  const selectedNode =
    selectedNodeQuery.data ??
    graph.nodes.find((node) => node.id === selectedNodeId) ??
    searchResult?.nodes.find((node) => node.id === selectedNodeId) ??
    null

  const handleAsk = (nextQuestion?: string) => {
    const query = (nextQuestion ?? question).trim()
    if (!query) return
    setQuestion(query)
    searchMutation.mutate({ query, lens, focus_node_id: selectedNodeId, limit: 24 })
  }

  if (snapshotQuery.isLoading) {
    return (
      <div className="space-y-8">
        <ArcbrainHeader />
        <LoadingState message="Loading Arcbrain projection..." />
      </div>
    )
  }

  if (snapshotQuery.isError) {
    return (
      <div className="space-y-8">
        <ArcbrainHeader />
        <ErrorState
          message={
            snapshotQuery.error instanceof Error
              ? snapshotQuery.error.message
              : 'Arcbrain snapshot could not be loaded.'
          }
        />
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <h2 className="text-base font-semibold text-navy-900">Projection unavailable</h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600">
            Arcbrain could not load the operating graph for the selected organization. Confirm the org connection,
            authentication state, and backend health before trusting this screen.
          </p>
        </section>
      </div>
    )
  }

  if (graph.nodes.length === 0) {
    return (
      <div className="space-y-8">
        <ArcbrainHeader summary={graph.summary} />
        <EmptyState
          icon={<BrainCircuit className="h-10 w-10" />}
          title="Arcbrain has no graph yet"
          description="Connect and sync platform sources, run process discovery, and generate recommendations to populate the operating brain."
        />
      </div>
    )
  }

  return (
    <div className="w-full max-w-full min-w-0 overflow-hidden space-y-6">
      <ArcbrainHeader summary={graph.summary} />

      <section className="grid w-full max-w-full min-w-0 gap-4 overflow-hidden rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5 lg:grid-cols-[1fr_auto] lg:items-center">
        <div className="flex min-w-0 flex-wrap gap-2" role="tablist" aria-label="Arcbrain lens">
          {LENSES.map((item) => {
            const Icon = item.icon
            const active = lens === item.id
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setLens(item.id)}
                className={clsx(
                  'inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold ring-1 ring-inset transition-colors',
                  active
                    ? 'bg-navy-800 text-white ring-navy-800'
                    : 'bg-white text-slate-700 ring-slate-200 hover:bg-slate-50',
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            )
          })}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-3 text-xs text-slate-500">
          <StatusPill label="Projection" value={graph.summary.projection_status ?? 'ready'} />
          <StatusPill label="Staleness" value={graph.summary.staleness_status ?? 'unknown'} />
          <span>Generated {formatDateTime(graph.summary.generated_at)}</span>
        </div>
      </section>

      <div className="grid w-full max-w-full min-w-0 gap-5 overflow-hidden xl:grid-cols-[300px_minmax(0,1fr)] 2xl:grid-cols-[320px_minmax(0,1fr)_340px]">
        <AskRail
          question={question}
          setQuestion={setQuestion}
          onAsk={handleAsk}
          isAsking={searchMutation.isPending}
          error={searchMutation.error}
          searchResult={searchResult}
          suggestedQuestions={searchResult?.suggested_next_questions ?? []}
          onSelectNode={setSelectedNodeId}
        />

        <div className="min-w-0">
          <ArcbrainGraphSurface
            graph={graph}
            lens={lens}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
            searchResult={searchResult}
            blastRadius={blastRadiusQuery.data ?? null}
            replacementHeat={replacementHeatQuery.data ?? null}
          />
        </div>

        <div className="min-w-0 xl:col-span-2 2xl:col-span-1">
          <DetailsPanel
            node={selectedNode}
            summary={graph.summary}
            lens={lens}
            nodeLoading={selectedNodeQuery.isFetching}
            blastRadius={blastRadiusQuery.data ?? null}
            blastRadiusLoading={blastRadiusQuery.isFetching}
            replacementHeatLoading={replacementHeatQuery.isFetching}
            searchResult={searchResult}
          />
        </div>
      </div>
    </div>
  )
}

function ArcbrainHeader({ summary }: { summary?: ReturnType<typeof normalizeArcbrainSnapshot>['summary'] }) {
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

function AskRail({
  question,
  setQuestion,
  onAsk,
  isAsking,
  error,
  searchResult,
  suggestedQuestions,
  onSelectNode,
}: {
  question: string
  setQuestion: (value: string) => void
  onAsk: (question?: string) => void
  isAsking: boolean
  error: unknown
  searchResult: ReturnType<typeof normalizeSearchResult>
  suggestedQuestions: string[]
  onSelectNode: (nodeId: string) => void
}) {
  const answer = searchResult?.answer ?? null
  const confidence = searchResult?.confidence ?? null
  const pathNodes = searchResult?.nodes ?? []
  const supportingClaims = searchResult?.supporting_claims ?? []

  return (
    <aside className="min-w-0 space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
      <div>
        <h2 className="text-base font-semibold text-navy-900">Ask the Brain</h2>
        <p className="mt-1 text-sm text-slate-600">Ask a business question and inspect the nodes Arcbrain used.</p>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-semibold uppercase text-slate-500" htmlFor="arcbrain-question">
          Executive question
        </label>
        <textarea
          id="arcbrain-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={4}
          className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-navy-200"
          placeholder="Ask about replacement, risk, evidence, or dependencies..."
        />
        <button
          type="button"
          disabled={isAsking || !question.trim()}
          onClick={() => onAsk()}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-navy-800 px-3 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isAsking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          {isAsking ? 'Investigating...' : 'Ask'}
        </button>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase text-slate-500">Templates</p>
        {(suggestedQuestions.length > 0 ? suggestedQuestions : TEMPLATE_QUESTIONS).slice(0, 5).map((template) => (
          <button
            key={template}
            type="button"
            onClick={() => onAsk(template)}
            className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs font-medium leading-relaxed text-slate-700 hover:border-navy-200 hover:bg-white"
          >
            <span className="block break-words">{template}</span>
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error instanceof Error ? error.message : 'Arcbrain search failed.'}
        </div>
      ) : null}

      {answer ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase text-slate-500">Answer</p>
            <span className="text-xs font-semibold text-slate-500">{formatPercent(confidence)}</span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{answer}</p>
          {pathNodes.length > 0 ? (
            <div className="mt-3 space-y-2">
              <p className="text-xs font-semibold uppercase text-slate-500">Consulted nodes</p>
              <div className="flex flex-wrap gap-1.5">
                {pathNodes.slice(0, 8).map((node) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => onSelectNode(node.id)}
                    className="max-w-full truncate rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:border-orange-200 hover:text-orange-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-200"
                  >
                    {node.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {supportingClaims.length > 0 ? (
            <div className="mt-3">
              <p className="text-xs font-semibold uppercase text-slate-500">Evidence refs</p>
              <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-slate-600">
                {supportingClaims.slice(0, 5).map((item) => (typeof item === 'string' ? item : item.label ?? item.id ?? 'Evidence')).join(' / ')}
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  )
}

function DetailsPanel({
  node,
  summary,
  lens,
  nodeLoading,
  blastRadius,
  blastRadiusLoading,
  replacementHeatLoading,
  searchResult,
}: {
  node: ArcbrainNode | null
  summary: ReturnType<typeof normalizeArcbrainSnapshot>['summary']
  lens: ArcbrainLens
  nodeLoading: boolean
  blastRadius: ReturnType<typeof useArcbrainBlastRadius>['data'] | null
  blastRadiusLoading: boolean
  replacementHeatLoading: boolean
  searchResult: ReturnType<typeof normalizeSearchResult>
}) {
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

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="w-full max-w-full min-w-0 overflow-hidden rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-900/5">
      <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight text-navy-900">{value}</p>
    </div>
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

function StatusPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
      <span className="text-slate-500">{label}:</span>
      {value.replace(/_/g, ' ')}
    </span>
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
  icon: typeof AlertTriangle
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
