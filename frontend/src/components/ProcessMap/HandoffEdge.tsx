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
  kind?: string
  confidenceScore?: number | null
  gapStatus?: string | null
  needsReview?: boolean
  evidenceSources?: Record<string, unknown>[]
  dataTransferred?: Record<string, unknown>[]
  transferMechanism?: string | null
  isDimmed?: boolean
  isHighlighted?: boolean
}

function HandoffEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, style }: EdgeProps<Edge<EdgeData>>) {
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition })
  const [hovered, setHovered] = useState(false)
  const isGap = data?.isGap ?? false
  const label = data?.label ?? 'handoff'
  const description = data?.description
  const confidence = typeof data?.confidenceScore === 'number' ? `${Math.round(data.confidenceScore * 100)}% confidence` : null
  const evidenceCount = data?.evidenceSources?.length ?? 0
  const transferCount = data?.dataTransferred?.length ?? 0

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
              data?.isDimmed && 'opacity-35',
              data?.isHighlighted && !isGap && 'border-orange-200 bg-orange-50 text-orange-700',
              hovered && !isGap && 'border-navy-300 bg-navy-50 text-navy-700 shadow-md',
              hovered && isGap && 'border-red-300 bg-red-100 shadow-md',
            )}
          >
            {isGap ? (
              <AlertTriangle className="h-2.5 w-2.5" />
            ) : (
              <ArrowRightLeft className="h-2.5 w-2.5 opacity-50" />
            )}
            <span className="max-w-[140px] truncate">{label}</span>
          </div>

          {hovered && (description || label.length > 16 || confidence || evidenceCount || transferCount || data?.gapStatus) ? (
            <div className="absolute left-1/2 top-full z-50 mt-2 -translate-x-1/2">
              <div className="w-72 rounded-lg border border-slate-200 bg-white p-3 shadow-xl ring-1 ring-slate-900/5">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  {isGap ? 'Gap identified' : data?.kind === 'sequence' ? 'Sequence' : 'Handoff'}
                </p>
                {label.length > 16 ? (
                  <p className="mt-1 text-xs font-semibold text-navy-900">{label}</p>
                ) : null}
                {description ? (
                  <p className={clsx('text-xs leading-relaxed text-slate-700', label.length > 16 ? 'mt-0.5' : 'mt-1')}>{description}</p>
                ) : null}
                <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] font-semibold text-slate-500">
                  {data?.gapStatus ? <span className="rounded bg-red-50 px-1.5 py-0.5 text-red-700">{data.gapStatus}</span> : null}
                  {confidence ? <span className="rounded bg-slate-50 px-1.5 py-0.5">{confidence}</span> : null}
                  {data?.transferMechanism ? <span className="rounded bg-slate-50 px-1.5 py-0.5">{data.transferMechanism}</span> : null}
                  {evidenceCount ? <span className="rounded bg-slate-50 px-1.5 py-0.5">{evidenceCount} evidence</span> : null}
                  {transferCount ? <span className="rounded bg-slate-50 px-1.5 py-0.5">{transferCount} data set</span> : null}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

export default memo(HandoffEdge)
