import { memo, useMemo } from 'react'
import { Link } from 'react-router-dom'
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

type DemoData = {
  title: string
  subtitle: string
  variant: 'doc' | 'process' | 'record'
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

const initialNodes: Node<DemoData>[] = [
  {
    id: 'doc_arch',
    type: 'demo',
    position: { x: 40, y: 0 },
    data: { title: 'Architectural Standards', subtitle: 'Word Document', variant: 'doc' },
  },
  {
    id: 'doc_sla',
    type: 'demo',
    position: { x: 340, y: 0 },
    data: { title: 'Lead SLA Policy', subtitle: 'PDF', variant: 'doc' },
  },
  {
    id: 'doc_scoring',
    type: 'demo',
    position: { x: 640, y: 0 },
    data: { title: 'Scoring Model Config', subtitle: 'Excel', variant: 'doc' },
  },
  {
    id: 'proc_route',
    type: 'demo',
    position: { x: 40, y: 200 },
    data: { title: 'Inbound Lead Routing', subtitle: 'Salesforce Flow', variant: 'process' },
  },
  {
    id: 'proc_enrich',
    type: 'demo',
    position: { x: 340, y: 200 },
    data: { title: 'Lead Enrichment', subtitle: 'Manual Process', variant: 'process' },
  },
  {
    id: 'proc_score',
    type: 'demo',
    position: { x: 640, y: 200 },
    data: { title: 'AI Lead Scoring', subtitle: 'Einstein Discovery', variant: 'process' },
  },
  {
    id: 'data_hs',
    type: 'demo',
    position: { x: 40, y: 400 },
    data: { title: 'HubSpot Leads', subtitle: 'HubSpot Sync', variant: 'record' },
  },
  {
    id: 'data_lead',
    type: 'demo',
    position: { x: 340, y: 400 },
    data: { title: 'Lead Object', subtitle: 'Salesforce Lead', variant: 'record' },
  },
  {
    id: 'data_contact',
    type: 'demo',
    position: { x: 640, y: 400 },
    data: { title: 'Contact Object', subtitle: 'Salesforce Contact', variant: 'record' },
  },
]

const initialEdges: Edge[] = [
  {
    id: 'e1',
    source: 'doc_arch',
    target: 'proc_route',
    label: 'governs',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  },
  {
    id: 'e2',
    source: 'doc_sla',
    target: 'proc_route',
    label: 'constrains',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  },
  {
    id: 'e3',
    source: 'doc_scoring',
    target: 'proc_score',
    label: 'configures',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  },
  {
    id: 'e4',
    source: 'proc_route',
    target: 'data_hs',
    label: 'syncs to',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  },
  {
    id: 'e5',
    source: 'proc_enrich',
    target: 'data_lead',
    label: 'converts to',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  },
  {
    id: 'e6',
    source: 'proc_score',
    target: 'data_lead',
    label: 'feeds',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  },
  {
    id: 'e7',
    source: 'data_hs',
    target: 'data_lead',
    label: 'syncs to',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  },
  {
    id: 'e8',
    source: 'data_lead',
    target: 'data_contact',
    label: 'converts to',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
  },
]

export default function ProcessMapPage() {
  const nodesState = useMemo(() => initialNodes, [])
  const edgesState = useMemo(() => initialEdges, [])
  const [nodes, , onNodesChange] = useNodesState(nodesState)
  const [edges, , onEdgesChange] = useEdgesState(edgesState)

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <Link
            to="/processes"
            className="inline-flex items-center gap-2 text-sm font-medium text-navy-700 hover:text-navy-900"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Business Processes
          </Link>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-navy-900">Process Map</h1>
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

function LegendSwatch({ label, className }: { label: string; className: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={clsx('h-2.5 w-2.5 rounded-sm', className)} />
      {label}
    </span>
  )
}
