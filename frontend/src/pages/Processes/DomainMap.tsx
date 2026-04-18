import { useCallback, useEffect, useRef, useState } from 'react'
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
import type { DomainGraphNode } from '@/types'

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
  const initRef = useRef(false)

  const { fitView } = useReactFlow()

  const direction: 'LR' | 'TB' = (settings?.process_map_direction as 'LR' | 'TB') ?? 'TB'

  useEffect(() => {
    initRef.current = false
    setLayoutReady(false)
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
        fitView({ padding: 0.1, duration: 300 })
      })
    })

    return () => {
      cancelled = true
    }
  }, [graphData, collapsedIds, direction, setNodes, setEdges, fitView])

  const handleDirectionChange = useCallback(
    (dir: 'LR' | 'TB') => {
      updateSettings.mutate({
        process_map_direction: dir,
        process_map_default_state: settings?.process_map_default_state ?? 'collapsed',
      })
    },
    [updateSettings, settings],
  )

  const handleExpandAll = useCallback(() => {
    setCollapsedIds(new Set())
  }, [])

  const handleCollapseAll = useCallback(() => {
    if (!graphData) return
    const allContainers = collectContainerIds(graphData.hierarchy)
    setCollapsedIds(new Set(allContainers))
  }, [graphData])

  const handleResetLayout = useCallback(() => {
    if (!id) return
    clearPositions.mutate()
  }, [id, clearPositions])

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
        <LoadingState message="Loading domain graph…" />
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
            {graphData.domain.name ? `Domain Map · ${graphData.domain.name}` : 'Domain Map'}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Full end-to-end process map. Click containers to expand/collapse. Drag nodes to rearrange.
          </p>
        </div>
      </div>

      <div className="h-[680px] overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
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
            <Panel position="top-right" className="m-3">
              <MapToolbar
                direction={direction}
                onDirectionChange={handleDirectionChange}
                onExpandAll={handleExpandAll}
                onCollapseAll={handleCollapseAll}
                onResetLayout={handleResetLayout}
              />
            </Panel>
          </ReactFlow>
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
