import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import '@xyflow/react/dist/style.css'
import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  useEdgesState,
  useNodesState,
  useReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
} from '@xyflow/react'
import { ArrowLeft, Loader2, Network } from 'lucide-react'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import {
  useDomainGraph,
  useProcessMapSettings,
  useUpdateProcessMapSettings,
  useClearDomainPositions,
  useSaveDomainPositions,
} from '@/hooks/useApi'
import { computeElkLayout } from '@/lib/elkLayout'
import ContainerNode from '@/components/ProcessMap/ContainerNode'
import CollapsedContainerNode from '@/components/ProcessMap/CollapsedContainerNode'
import StepNode from '@/components/ProcessMap/StepNode'
import HandoffEdge from '@/components/ProcessMap/HandoffEdge'
import { MapToolbar } from '@/components/ProcessMap/MapToolbar'
import { MapInspector } from '@/components/ProcessMap/MapInspector'
import type { DomainGraphEdge, DomainGraphNode, ProcessMapLens } from '@/types'

const nodeTypes = {
  stepNode: StepNode,
  containerNode: ContainerNode,
  collapsedContainer: CollapsedContainerNode,
}

const edgeTypes = {
  handoff: HandoffEdge,
}

function collectContainerIds(nodes: DomainGraphNode[]): string[] {
  const ids: string[] = []
  for (const n of nodes) {
    if (!n.is_leaf) {
      ids.push(n.id)
      ids.push(...collectContainerIds(n.children))
    }
  }
  return ids
}

type SearchItem = {
  id: string
  focusId?: string
  label: string
  text: string
  ancestors: string[]
}

function recordLabel(value: unknown, keys: string[]): string | null {
  if (typeof value === 'string') return value
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  for (const key of keys) {
    const item = record[key]
    if (typeof item === 'string' && item.trim()) return item.trim()
    if (typeof item === 'number') return String(item)
  }
  return null
}

function labels(values: Record<string, unknown>[] | undefined, keys: string[]): string[] {
  return (values ?? [])
    .map((value) => recordLabel(value, keys))
    .filter((value): value is string => Boolean(value))
}

function indexSearchItems(nodes: DomainGraphNode[], ancestors: string[] = []): SearchItem[] {
  const items: SearchItem[] = []
  for (const node of nodes) {
    const actorLabels = labels(node.actors, ['name', 'role', 'type'])
    const touchpointLabels = labels(node.system_touchpoints, ['object_api_name', 'api_name', 'name', 'system', 'metadata_type'])
    const evidenceLabels = labels(node.evidence_sources, ['api_name', 'document_name', 'name', 'type'])
    items.push({
      id: node.id,
      label: node.name,
      ancestors,
      text: [
        node.name,
        node.description,
        node.status,
        node.level,
        node.value_classification,
        node.automation_potential,
        ...actorLabels,
        ...touchpointLabels,
        ...evidenceLabels,
      ].filter(Boolean).join(' ').toLowerCase(),
    })
    items.push(...indexSearchItems(node.children, [...ancestors, node.id]))
  }
  return items
}

function collectNodeNames(nodes: DomainGraphNode[], map = new Map<string, string>()) {
  for (const node of nodes) {
    map.set(node.id, node.name)
    collectNodeNames(node.children, map)
  }
  return map
}

function edgeSearchText(edge: DomainGraphEdge, nodeNames: Map<string, string>): string {
  const evidenceLabels = labels(edge.evidence_sources, ['api_name', 'document_name', 'name', 'type'])
  const dataLabels = labels(edge.data_transferred, ['object', 'object_api_name', 'api_name', 'name'])
  return [
    edge.label,
    edge.description,
    edge.kind,
    edge.gap_status,
    edge.transfer_mechanism,
    nodeNames.get(edge.source_id),
    nodeNames.get(edge.target_id),
    ...evidenceLabels,
    ...dataLabels,
  ].filter(Boolean).join(' ').toLowerCase()
}

function DomainMapInner() {
  const { id } = useParams<{ id: string }>()
  const { data: graphData, isLoading, isError, error } = useDomainGraph(id ?? '')
  const { data: settings } = useProcessMapSettings()
  const updateSettings = useUpdateProcessMapSettings()
  const savePositions = useSaveDomainPositions()
  const clearPositions = useClearDomainPositions(id ?? '')

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set())
  const [layoutReady, setLayoutReady] = useState(false)
  const [lens, setLens] = useState<ProcessMapLens>('structure')
  const [searchQuery, setSearchQuery] = useState('')
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null)
  const initRef = useRef(false)
  const fitOnNextLayoutRef = useRef(true)

  const { fitView, getNode, setCenter } = useReactFlow()

  const direction: 'LR' | 'TB' = (settings?.process_map_direction as 'LR' | 'TB') ?? 'TB'
  const nodeNameById = useMemo(() => collectNodeNames(graphData?.hierarchy ?? []), [graphData])
  const searchItems = useMemo(() => {
    const nodeItems = indexSearchItems(graphData?.hierarchy ?? [])
    const nodeItemById = new Map(nodeItems.map((item) => [item.id, item]))
    const edgeItems =
      graphData?.edges.map((edge) => ({
        id: edge.id,
        focusId: edge.source_id,
        label: edge.label || 'Handoff',
        ancestors: nodeItemById.get(edge.source_id)?.ancestors ?? [],
        text: edgeSearchText(edge, nodeNameById),
      })) ?? []
    return [...nodeItems, ...edgeItems]
  }, [graphData, nodeNameById])
  const searchResults = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) return []
    return searchItems.filter((item) => item.text.includes(query))
  }, [searchItems, searchQuery])
  const highlightedIds = useMemo(() => {
    const ids = new Set<string>()
    if (focusedId) ids.add(focusedId)
    return ids
  }, [focusedId])

  useEffect(() => {
    initRef.current = false
    fitOnNextLayoutRef.current = true
    setLayoutReady(false)
    setFocusedId(null)
    setSelectedNode(null)
    setSelectedEdge(null)
    setSearchQuery('')
  }, [id])

  useEffect(() => {
    if (!graphData || initRef.current) return
    initRef.current = true
    const defaultState = settings?.process_map_default_state ?? 'collapsed'
    if (defaultState === 'collapsed') {
      const allContainers = collectContainerIds(graphData.hierarchy)
      setCollapsedIds(new Set(allContainers))
    }
  }, [graphData, settings])

  useEffect(() => {
    if (!graphData) return
    let cancelled = false

    const elkDir = direction === 'LR' ? 'RIGHT' : 'DOWN'

    computeElkLayout(graphData.hierarchy, graphData.edges, {
      direction: elkDir as 'RIGHT' | 'DOWN',
      collapsedIds,
      positions: graphData.positions,
      lens,
      highlightedIds,
    }).then(({ nodes: rfNodes, edges: rfEdges }) => {
      if (cancelled) return

      const withToggle = rfNodes.map((n) => {
        if (n.type === 'containerNode' || n.type === 'collapsedContainer') {
          return {
            ...n,
            data: {
              ...n.data,
              onToggle: (processId: string) => {
                setCollapsedIds((prev) => {
                  const next = new Set(prev)
                  if (next.has(processId)) {
                    next.delete(processId)
                  } else {
                    next.add(processId)
                  }
                  return next
                })
              },
            },
          }
        }
        return n
      })

      setNodes(withToggle)
      setEdges(rfEdges)
      setLayoutReady(true)

      requestAnimationFrame(() => {
        if (!focusedId && fitOnNextLayoutRef.current) {
          fitView({ padding: 0.1, duration: 300 })
          fitOnNextLayoutRef.current = false
        }
      })
    })

    return () => {
      cancelled = true
    }
  }, [graphData, collapsedIds, direction, lens, highlightedIds, focusedId, setNodes, setEdges, fitView])

  useEffect(() => {
    if (!focusedId || !layoutReady) return
    const timer = window.setTimeout(() => {
      const node = getNode(focusedId)
      if (!node) return
      const width = node.measured?.width ?? node.width ?? 260
      const height = node.measured?.height ?? node.height ?? 132
      setCenter(node.position.x + width / 2, node.position.y + height / 2, {
        zoom: 1,
        duration: 350,
      })
    }, 60)
    return () => window.clearTimeout(timer)
  }, [focusedId, getNode, layoutReady, setCenter])

  const handleDirectionChange = useCallback(
    (dir: 'LR' | 'TB') => {
      fitOnNextLayoutRef.current = true
      updateSettings.mutate({
        process_map_direction: dir,
        process_map_default_state: settings?.process_map_default_state ?? 'collapsed',
      })
    },
    [updateSettings, settings],
  )

  const handleExpandAll = useCallback(() => {
    fitOnNextLayoutRef.current = true
    setCollapsedIds(new Set())
  }, [])

  const handleCollapseAll = useCallback(() => {
    if (!graphData) return
    fitOnNextLayoutRef.current = true
    const allContainers = collectContainerIds(graphData.hierarchy)
    setCollapsedIds(new Set(allContainers))
  }, [graphData])

  const handleResetLayout = useCallback(() => {
    if (!id) return
    fitOnNextLayoutRef.current = true
    clearPositions.mutate()
  }, [id, clearPositions])

  const handleSearchSubmit = useCallback(() => {
    const first = searchResults[0]
    if (!first) return
    const focusId = first.focusId ?? first.id
    setCollapsedIds((prev) => {
      const next = new Set(prev)
      for (const ancestor of first.ancestors) {
        next.delete(ancestor)
      }
      next.delete(focusId)
      return next
    })
    setFocusedId(focusId)
  }, [searchResults])

  const handleSelectionChange = useCallback(({ nodes: selectedNodes, edges: selectedEdges }: { nodes: Node[]; edges: Edge[] }) => {
    setSelectedNode(selectedNodes[0] ?? null)
    setSelectedEdge(selectedEdges[0] ?? null)
  }, [])

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const handleNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      if (!id) return
      clearTimeout(saveTimerRef.current)
      saveTimerRef.current = setTimeout(() => {
        const positionMap: Record<string, { x: number; y: number }> = {}
        for (const n of nodes) {
          positionMap[n.id] = { x: n.position.x, y: n.position.y }
        }
        positionMap[node.id] = { x: node.position.x, y: node.position.y }
        savePositions.mutate({ domainId: id, positions: positionMap })
      }, 500)
    },
    [id, nodes, savePositions],
  )

  const status =
    isError && error && typeof error === 'object' && 'status' in error && typeof (error as { status: unknown }).status === 'number'
      ? (error as { status: number }).status
      : undefined

  if (!id) {
    return (
      <div className="space-y-6">
        <BackHeader />
        <EmptyState
          icon={<Network className="h-10 w-10" />}
          title="No process selected"
          description="Choose a domain process from the list to view its map."
        />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <BackHeader />
        <LoadingState message="Loading domain graph..." />
      </div>
    )
  }

  if (isError) {
    const msg = error instanceof Error ? error.message : undefined
    const is404 = status === 404
    return (
      <div className="space-y-6">
        <BackHeader />
        {is404 ? (
          <EmptyState
            icon={<Network className="h-10 w-10" />}
            title="Domain not found"
            description="This process may not be a domain or is not available for your organization."
          />
        ) : (
          <ErrorState message={msg} />
        )}
      </div>
    )
  }

  if (!graphData?.hierarchy?.length) {
    return (
      <div className="space-y-6">
        <BackHeader />
        <EmptyState
          icon={<Network className="h-10 w-10" />}
          title="No graph data yet"
          description="Run process discovery to populate the domain process hierarchy."
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <BackHeader />
          <h1 className="mt-4 font-display text-3xl font-bold tracking-tight text-navy-900">
            {graphData.domain.name ? `Domain Map / ${graphData.domain.name}` : 'Domain Map'}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Review process structure, handoffs, evidence, and automation fit on one analyst canvas.
          </p>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="h-[720px] overflow-hidden rounded-lg border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
          {!layoutReady && (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-slate-300" />
            </div>
          )}
          <div className={layoutReady ? 'h-full' : 'h-0 overflow-hidden'}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onSelectionChange={handleSelectionChange}
              onNodeDragStop={handleNodeDragStop}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              fitView
              minZoom={0.1}
              maxZoom={1.6}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={20} color="#e7e9ef" />
              <Controls showInteractive={false} />
              <MiniMap nodeStrokeWidth={3} pannable zoomable className="!bottom-2 !right-2" />
              <Panel position="top-left" className="m-3">
                <MapToolbar
                  direction={direction}
                  lens={lens}
                  searchQuery={searchQuery}
                  searchResultCount={searchResults.length}
                  onDirectionChange={handleDirectionChange}
                  onLensChange={setLens}
                  onSearchQueryChange={(query) => {
                    setSearchQuery(query)
                    if (!query.trim()) setFocusedId(null)
                  }}
                  onSearchSubmit={handleSearchSubmit}
                  onExpandAll={handleExpandAll}
                  onCollapseAll={handleCollapseAll}
                  onResetLayout={handleResetLayout}
                />
              </Panel>
            </ReactFlow>
          </div>
        </div>
        <div className="min-h-[360px] xl:h-[720px]">
          <MapInspector selectedNode={selectedNode} selectedEdge={selectedEdge} nodeNameById={nodeNameById} />
        </div>
      </div>
    </div>
  )
}

function BackHeader() {
  return (
    <Link to="/processes" className="inline-flex items-center gap-2 text-sm font-medium text-navy-700 hover:text-navy-900">
      <ArrowLeft className="h-4 w-4" />
      Back to Business Processes
    </Link>
  )
}

export default function DomainMapPage() {
  return (
    <ReactFlowProvider>
      <DomainMapInner />
    </ReactFlowProvider>
  )
}
