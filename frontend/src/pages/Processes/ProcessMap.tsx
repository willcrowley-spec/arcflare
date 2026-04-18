import { memo, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import '@xyflow/react/dist/style.css'
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  getBezierPath,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRightLeft,
  FileSpreadsheet,
  FileText,
  FileType2,
  Network,
  Server,
  Workflow,
} from 'lucide-react'
import clsx from 'clsx'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import { useProcess } from '@/hooks/useApi'

type NodeData = {
  title: string
  subtitle: string
  variant: 'doc' | 'process' | 'record'
}

type EdgeData = {
  label: string
  description?: string | null
  isGap?: boolean
}

type ApiGraphNode = {
  id: string
  type?: string
  label?: string | null
  subtitle?: string | null
  position?: { x: number; y: number }
}

type ApiGraphEdge = {
  id: string
  source: string
  target: string
  label?: string | null
  description?: string | null
  is_gap?: boolean
}

type ProcessGraphPayload = {
  nodes?: ApiGraphNode[]
  edges?: ApiGraphEdge[]
}

function mapNodeVariant(nodeType: string | undefined): NodeData['variant'] {
  const t = (nodeType ?? '').toUpperCase()
  if (t.includes('DOC') || t.includes('BUSINESS_DOC') || t.includes('FILE')) return 'doc'
  if (t.includes('RECORD') || t.includes('DATA') || t.includes('OBJECT')) return 'record'
  return 'process'
}

function toFlowNodes(nodes: ApiGraphNode[] | undefined): Node<NodeData>[] {
  if (!nodes?.length) return []
  return nodes.map((n) => {
    const variant = mapNodeVariant(n.type)
    const pos =
      n.position && typeof n.position.x === 'number' && typeof n.position.y === 'number' ? n.position : { x: 0, y: 0 }
    return {
      id: n.id,
      type: 'processNode',
      position: pos,
      data: {
        title: n.label?.trim() || 'Untitled step',
        subtitle: n.subtitle?.trim() || (n.type ?? 'process').replace(/_/g, ' '),
        variant,
      },
    }
  })
}

function toFlowEdges(edges: ApiGraphEdge[] | undefined): Edge<EdgeData>[] {
  if (!edges?.length) return []
  return edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: 'handoff',
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: e.is_gap ? '#dc2626' : '#94a3b8' },
    style: { stroke: e.is_gap ? '#fca5a5' : '#cbd5e1', strokeWidth: e.is_gap ? 2 : 1.5 },
    data: {
      label: e.label ?? 'handoff',
      description: e.description,
      isGap: e.is_gap ?? false,
    },
  }))
}

function HandoffEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, style }: EdgeProps<Edge<EdgeData>>) {
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition })
  const [hovered, setHovered] = useState(false)
  const isGap = data?.isGap ?? false
  const label = data?.label ?? 'handoff'
  const description = data?.description

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
        >
          <div
            className={clsx(
              'flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold shadow-sm transition-all',
              'cursor-default select-none',
              isGap
                ? 'border border-red-200 bg-red-50 text-red-700'
                : 'border border-slate-200 bg-white text-slate-600',
              hovered && !isGap && 'border-navy-300 bg-navy-50 text-navy-700 shadow-md',
              hovered && isGap && 'border-red-300 bg-red-100 shadow-md',
            )}
          >
            {isGap ? (
              <AlertTriangle className="h-2.5 w-2.5" />
            ) : (
              <ArrowRightLeft className="h-2.5 w-2.5 opacity-50" />
            )}
            <span className="max-w-[100px] truncate">{label}</span>
          </div>

          {hovered && description ? (
            <div className="absolute left-1/2 top-full z-50 mt-2 -translate-x-1/2">
              <div className="w-64 rounded-lg border border-slate-200 bg-white p-3 shadow-xl ring-1 ring-slate-900/5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  {isGap ? 'Gap identified' : 'Handoff'}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-slate-700">{description}</p>
              </div>
            </div>
          ) : null}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

function ProcessNodeComponent({ data }: NodeProps<Node<NodeData>>) {
  const bar =
    data.variant === 'doc' ? 'bg-orange-500' : data.variant === 'process' ? 'bg-navy-800' : 'bg-emerald-500'
  const Icon =
    data.variant === 'doc'
      ? data.title.includes('Excel')
        ? FileSpreadsheet
        : data.title.includes('PDF')
          ? FileType2
          : FileText
      : data.variant === 'process'
        ? Workflow
        : Server

  return (
    <div className="w-[240px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-md ring-1 ring-slate-900/5">
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-slate-300" />
      <div className="flex">
        <div className={clsx('w-1.5 self-stretch', bar)} />
        <div className="flex flex-1 items-start gap-3 p-3">
          <span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-lg bg-slate-50 ring-1 ring-slate-200/80">
            <Icon className="h-4 w-4 text-navy-800" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-snug text-navy-900">{data.title}</p>
            <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-slate-500">{data.subtitle}</p>
          </div>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-slate-300" />
    </div>
  )
}

const nodeTypes = { processNode: memo(ProcessNodeComponent) }
const edgeTypes = { handoff: memo(HandoffEdge) }

function extractGraph(payload: unknown): ProcessGraphPayload | null {
  if (!payload || typeof payload !== 'object') return null
  const root = payload as { graph?: unknown }
  const g = root.graph
  if (!g || typeof g !== 'object') return null
  return g as ProcessGraphPayload
}

export default function ProcessMapPage() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, isError, error } = useProcess(id ?? '')

  const graph = useMemo(() => extractGraph(data), [data])
  const flowNodes = useMemo(() => toFlowNodes(graph?.nodes), [graph?.nodes])
  const flowEdges = useMemo(() => toFlowEdges(graph?.edges), [graph?.edges])

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges)

  useEffect(() => {
    setNodes(flowNodes)
    setEdges(flowEdges)
  }, [flowNodes, flowEdges, setNodes, setEdges])

  const processName =
    data && typeof data === 'object' && 'process' in data
      ? (data as { process?: { name?: string } }).process?.name
      : undefined

  const hasGraphData = Boolean(graph?.nodes?.length)
  const edgeCount = graph?.edges?.length ?? 0
  const gapCount = graph?.edges?.filter((e) => e.is_gap)?.length ?? 0

  const status =
    isError && error && typeof error === 'object' && 'status' in error && typeof (error as { status: unknown }).status === 'number'
      ? (error as { status: number }).status
      : undefined

  const onInit = useCallback((instance: { fitView: () => void }) => {
    setTimeout(() => instance.fitView(), 50)
  }, [])

  if (!id) {
    return (
      <div className="space-y-6">
        <BackHeader />
        <EmptyState
          icon={<Network className="h-10 w-10" />}
          title="No process selected"
          description="Choose a process from the list to view its map."
        />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <BackHeader />
        <LoadingState message="Loading process graph…" />
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
            title="Process not found"
            description="This process may have been removed or is not available for your organization."
          />
        ) : (
          <ErrorState message={msg} />
        )}
      </div>
    )
  }

  if (!hasGraphData) {
    return (
      <div className="space-y-6">
        <BackHeader />
        <EmptyState
          icon={<Network className="h-10 w-10" />}
          title="No graph data yet"
          description="Run process generation after connecting a platform to populate nodes and edges."
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
            {processName ? `Process Map · ${processName}` : 'Process Map'}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Drag nodes to rearrange. Hover edge pills for handoff details.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold text-slate-700 shadow-sm ring-1 ring-slate-900/5">
          <LegendSwatch label="Process" className="bg-navy-800" />
          <LegendSwatch label="Data" className="bg-emerald-500" />
          <LegendSwatch label="Document" className="bg-orange-500" />
          {edgeCount > 0 ? (
            <span className="ml-1 text-slate-400">
              {edgeCount} handoff{edgeCount !== 1 ? 's' : ''}
              {gapCount > 0 ? (
                <span className="ml-1 text-red-500">{gapCount} gap{gapCount !== 1 ? 's' : ''}</span>
              ) : null}
            </span>
          ) : null}
        </div>
      </div>

      <div className="h-[680px] overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onInit={onInit}
          fitView
          minZoom={0.3}
          maxZoom={1.6}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} color="#e7e9ef" />
          <Controls showInteractive={false} />
          <Panel position="top-left" className="m-3 rounded-lg bg-white/90 px-3 py-2 text-xs text-slate-500 shadow-sm ring-1 ring-slate-200 backdrop-blur">
            <span className="inline-flex items-center gap-1.5">
              <ArrowRightLeft className="h-3 w-3" /> Hover pills on edges for details
            </span>
          </Panel>
        </ReactFlow>
      </div>
    </div>
  )
}

function BackHeader() {
  return (
    <Link
      to="/processes"
      className="inline-flex items-center gap-2 text-sm font-medium text-navy-700 hover:text-navy-900"
    >
      <ArrowLeft className="h-4 w-4" />
      Back to Business Processes
    </Link>
  )
}

function LegendSwatch({ label, className }: { label: string; className: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={clsx('h-2.5 w-2.5 rounded-sm', className)} />
      {label}
    </span>
  )
}
