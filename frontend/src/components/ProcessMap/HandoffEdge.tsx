import { memo, useState } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from '@xyflow/react'
import { AlertTriangle, ArrowRightLeft } from 'lucide-react'
import clsx from 'clsx'

type EdgeData = {
  label: string
  description?: string | null
  isGap?: boolean
  isAggregate?: boolean
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

export default memo(HandoffEdge)
