import { memo, useState } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { Plus } from 'lucide-react'

interface CollapsedData extends Record<string, unknown> {
  label: string
  leafCount: number
  depth: number
  isCollapsed: boolean
  processId: string
  isDimmed?: boolean
  isHighlighted?: boolean
  onToggle?: (id: string) => void
}

function CollapsedContainerComponent({ data }: NodeProps<Node<CollapsedData>>) {
  const [showTooltip, setShowTooltip] = useState(false)

  return (
    <div
      className={[
        'relative flex w-[260px] cursor-pointer items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2.5 shadow-sm transition hover:border-slate-400 hover:shadow-md',
        data.isDimmed ? 'opacity-35' : '',
        data.isHighlighted ? 'ring-2 ring-orange-200' : '',
      ].filter(Boolean).join(' ')}
      onClick={() => data.onToggle?.(data.processId)}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-slate-300" />
      <span className="truncate text-xs font-semibold text-slate-800">{data.label}</span>
      <span className="ml-auto shrink-0 text-[10px] font-medium text-slate-500">
        {data.leafCount} steps
      </span>
      <Plus className="h-3.5 w-3.5 shrink-0 text-slate-400" />
      <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-slate-300" />
      {showTooltip && data.label.length > 28 ? (
        <div className="absolute left-0 top-full z-50 mt-1 max-w-xs rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-navy-900 shadow-xl ring-1 ring-slate-900/5">
          {data.label}
        </div>
      ) : null}
    </div>
  )
}

export default memo(CollapsedContainerComponent)
