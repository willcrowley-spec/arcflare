import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { ChevronDown } from 'lucide-react'
import clsx from 'clsx'

interface ContainerNodeData extends Record<string, unknown> {
  label: string
  leafCount: number
  depth: number
  isCollapsed: boolean
  processId: string
  onToggle?: (id: string) => void
}

const DEPTH_STYLES: Record<number, { header: string; body: string; border: string }> = {
  1: { header: 'bg-navy-800 text-white', body: 'bg-navy-50', border: 'border-navy-200' },
  2: { header: 'bg-slate-600 text-white', body: 'bg-slate-50', border: 'border-slate-300' },
  3: { header: 'bg-slate-400 text-white', body: 'bg-white', border: 'border-slate-200' },
}

function getDepthStyle(depth: number) {
  if (depth >= 4) return { header: 'bg-slate-300 text-slate-800', body: 'bg-white', border: 'border-dashed border-slate-200' }
  return DEPTH_STYLES[depth] ?? DEPTH_STYLES[3]
}

function ContainerNodeComponent({ data }: NodeProps<Node<ContainerNodeData>>) {
  const style = getDepthStyle(data.depth)

  return (
    <div className={clsx('rounded-xl border overflow-hidden', style.border, style.body)} style={{ width: '100%', height: '100%' }}>
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-slate-300" />
      <button
        type="button"
        onClick={() => data.onToggle?.(data.processId)}
        className={clsx('flex w-full items-center gap-2 px-3 py-2 text-left', style.header)}
      >
        <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate text-xs font-semibold">{data.label}</span>
        <span className="ml-auto shrink-0 rounded-full bg-white/20 px-1.5 py-0.5 text-[10px] font-medium">
          {data.leafCount} steps
        </span>
      </button>
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-slate-300" />
    </div>
  )
}

export default memo(ContainerNodeComponent)
