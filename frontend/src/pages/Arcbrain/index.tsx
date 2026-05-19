import { useEffect, useMemo, useState } from 'react'
import { BrainCircuit } from 'lucide-react'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import type { ArcbrainLens } from '@/types'
import { ArcbrainAskRail } from '@/features/arcbrain/components/ArcbrainAskRail'
import { ArcbrainDetailsPanel } from '@/features/arcbrain/components/ArcbrainDetailsPanel'
import { ArcbrainGraphSurface } from '@/features/arcbrain/components/ArcbrainGraphSurface'
import { ArcbrainHeader } from '@/features/arcbrain/components/ArcbrainHeader'
import { ArcbrainLensBar } from '@/features/arcbrain/components/ArcbrainLensBar'
import { normalizeArcbrainSnapshot, normalizeSearchResult } from '@/features/arcbrain/graph/model'
import {
  useArcbrainBlastRadius,
  useArcbrainNode,
  useArcbrainReplacementHeat,
  useArcbrainSearch,
  useArcbrainSnapshot,
} from '@/features/arcbrain/hooks/useArcbrain'

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
      <ArcbrainLensBar lens={lens} onLensChange={setLens} summary={graph.summary} />

      <div className="grid w-full max-w-full min-w-0 gap-5 overflow-hidden xl:grid-cols-[300px_minmax(0,1fr)] 2xl:grid-cols-[320px_minmax(0,1fr)_340px]">
        <ArcbrainAskRail
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
          <ArcbrainDetailsPanel
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
