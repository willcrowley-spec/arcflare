import { memo, useEffect, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import '@xyflow/react/dist/style.css'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import { ArrowLeft, FileSpreadsheet, FileText, FileType2, Network, Server, Workflow } from 'lucide-react'
import clsx from 'clsx'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import { useProcess } from '@/hooks/useApi'

type DemoData = {
  title: string
  subtitle: string
  variant: 'doc' | 'process' | 'record'
}

type ApiGraphNode = {
  id: string
  type?: string
  label?: string | null
  position?: { x: number; y: number }
}

type ApiGraphEdge = {
  id: string
  source: string
  target: string
  label?: string | null
}

type ProcessGraphPayload = {
  nodes?: ApiGraphNode[]
  edges?: ApiGraphEdge[]
}

function mapNodeVariant(nodeType: string | undefined): DemoData['variant'] {
  const t = (nodeType ?? '').toUpperCase()
  if (t.includes('DOC') || t.includes('BUSINESS_DOC') || t.includes('FILE')) return 'doc'
  if (t.includes('RECORD') || t.includes('DATA') || t.includes('OBJECT')) return 'record'
  return 'process'
}

function toFlowNodes(nodes: ApiGraphNode[] | undefined): Node<DemoData>[] {
  if (!nodes?.length) return []
  return nodes.map((n) => {
    const variant = mapNodeVariant(n.type)
    const pos = n.position && typeof n.position.x === 'number' && typeof n.position.y === 'number' ? n.position : { x: 0, y: 0 }
    return {
      id: n.id,
      type: 'demo',
      position: pos,
      data: {
        title: n.label?.trim() || 'Untitled step',
        subtitle: (n.type ?? 'process').replace(/_/g, ' '),
        variant,
      },
    }
  })
}

function toFlowEdges(edges: ApiGraphEdge[] | undefined): Edge[] {
  if (!edges?.length) return []
  return edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label ?? '',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  }))
}

function DemoNode({ data }: NodeProps<Node<DemoData>>) {
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
            <p className="mt-1 text-[11px] text-slate-500">{data.subtitle}</p>
          </div>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-slate-300" />
    </div>
  )
}

const nodeTypes = { demo: memo(DemoNode) }

function extractGraph(payload: unknown): ProcessGraphPayload | null {
  if (!payload || typeof payload !== 'object') return null
  const root = payload as { graph?: unknown }
  const g = root.graph
  if (!g || typeof g !== 'object') return null
  const graph = g as ProcessGraphPayload
  return graph
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
            Drag nodes to rearrange. Positions are saved automatically.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold text-slate-700 shadow-sm ring-1 ring-slate-900/5">
          <LegendSwatch label="Metadata" className="bg-navy-800" />
          <LegendSwatch label="Data Records" className="bg-emerald-500" />
          <LegendSwatch label="Documents" className="bg-orange-500" />
          <span className="ml-2 inline-flex items-center gap-1 text-slate-500">
            <Network className="h-4 w-4" />
            Interactive graph
          </span>
        </div>
      </div>

      <div className="h-[620px] overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.4}
          maxZoom={1.4}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={16} color="#e7e9ef" />
          <Controls showInteractive={false} />
          <Panel position="top-left" className="m-3 rounded-lg bg-white/90 px-3 py-2 text-xs text-slate-600 shadow-sm ring-1 ring-slate-200 backdrop-blur">
            Legend applies to node color bars · edges carry integration semantics
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
