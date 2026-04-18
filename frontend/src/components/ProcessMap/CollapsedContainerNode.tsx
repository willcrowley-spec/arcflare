import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { Plus } from 'lucide-react'

interface CollapsedData extends Record<string, unknown> {
  label: string
  leafCount: number
  depth: number
  isCollapsed: boolean
  processId: string
  onToggle?: (id: string) => void
}

function CollapsedContainerComponent({ data }: NodeProps<Node<CollapsedData>>) {
  return (
    <div
      className="flex w-[260px] cursor-pointer items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2.5 shadow-sm transition hover:border-slate-400 hover:shadow-md"
      onClick={() => data.onToggle?.(data.processId)}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-slate-300" />
      <span className="truncate text-xs font-semibold text-slate-800">{data.label}</span>
      <span className="ml-auto shrink-0 text-[10px] font-medium text-slate-500">
        {data.leafCount} steps
      </span>
      <Plus className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-slate-300" />
    </div>
  )
}

export default memo(CollapsedContainerComponent)
