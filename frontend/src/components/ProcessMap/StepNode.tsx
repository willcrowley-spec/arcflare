import { memo, useState, useRef, useEffect, type ReactNode } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { AlertTriangle, Bot, Database, FileSpreadsheet, FileText, FileType2, Server, Users, Workflow, X } from 'lucide-react'
import clsx from 'clsx'

export type StepNodeData = {
  title: string
  subtitle: string
  variant: 'doc' | 'process' | 'record'
  processId?: string
  level?: string
  status?: string
  confidenceScore?: number | null
  needsReview?: boolean
  automationPotential?: string | null
  valueClassification?: string | null
  actorLabels?: string[]
  touchpointLabels?: string[]
  evidenceCount?: number
  isDimmed?: boolean
  isHighlighted?: boolean
}

function titleCase(value?: string | null) {
  if (!value) return null
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function confidenceLabel(value?: number | null) {
  if (typeof value !== 'number') return null
  return `${Math.round(value * 100)}%`
}

function Badge({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'amber' | 'green' | 'blue' }) {
  const styles = {
    slate: 'border-slate-200 bg-slate-50 text-slate-600',
    amber: 'border-amber-200 bg-amber-50 text-amber-700',
    green: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    blue: 'border-sky-200 bg-sky-50 text-sky-700',
  }
  return (
    <span className={clsx('inline-flex max-w-full items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold', styles[tone])}>
      {children}
    </span>
  )
}

function StepNodeComponent({ data }: NodeProps<Node<StepNodeData>>) {
  const [expanded, setExpanded] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

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
  const confidence = confidenceLabel(data.confidenceScore)
  const automation = titleCase(data.automationPotential)
  const valueClass = data.valueClassification?.toUpperCase()
  const actorCount = data.actorLabels?.length ?? 0
  const touchpointCount = data.touchpointLabels?.length ?? 0
  const evidenceCount = data.evidenceCount ?? 0

  useEffect(() => {
    if (!expanded) return
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as globalThis.Node)) {
        setExpanded(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [expanded])

  const subtitle = data.subtitle ?? ''
  const hasOverflow = subtitle.length > 80

  return (
    <div className="relative">
      <div
        className={clsx(
          'w-[260px] overflow-hidden rounded-lg border bg-white shadow-sm ring-1 transition',
          data.isHighlighted ? 'border-orange-300 bg-orange-50/30 shadow-md ring-orange-200' : 'border-slate-200 ring-slate-900/5',
          data.isDimmed && 'opacity-20',
          hasOverflow && 'cursor-pointer hover:shadow-md hover:ring-navy-200',
        )}
        onClick={() => hasOverflow && setExpanded((v) => !v)}
      >
        <Handle type="target" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-slate-300" />
        <div className="p-3">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-50 ring-1 ring-slate-200/80">
              <Icon className="h-4 w-4 text-navy-800" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-start justify-between gap-2">
                <p className="min-w-0 text-sm font-semibold leading-snug text-navy-900">{data.title}</p>
                {data.needsReview ? (
                  <span title="Needs review" className="mt-0.5 shrink-0 rounded-full bg-amber-100 p-1 text-amber-700">
                    <AlertTriangle className="h-3 w-3" />
                  </span>
                ) : null}
              </div>
              <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-slate-500">{subtitle || 'No description captured yet.'}</p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {automation ? (
              <Badge tone={data.automationPotential?.toLowerCase() === 'high' ? 'green' : 'blue'}>
                <Bot className="h-2.5 w-2.5" />
                {automation}
              </Badge>
            ) : null}
            {valueClass ? <Badge>{valueClass}</Badge> : null}
            {confidence ? <Badge>{confidence}</Badge> : null}
          </div>

          <div className="mt-2 flex items-center gap-3 text-[10px] font-medium text-slate-500">
            <span className="inline-flex items-center gap-1">
              <Users className="h-3 w-3" />
              {actorCount}
            </span>
            <span className="inline-flex items-center gap-1">
              <Database className="h-3 w-3" />
              {touchpointCount}
            </span>
            <span>{evidenceCount} evidence</span>
          </div>
        </div>
        <Handle type="source" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-slate-300" />
      </div>

      {expanded ? (
        <div
          ref={popoverRef}
          className="nodrag nopan absolute left-1/2 top-full z-50 mt-2 w-80 -translate-x-1/2 rounded-lg border border-slate-200 bg-white p-4 shadow-2xl ring-1 ring-slate-900/10"
        >
          <div className="mb-2 flex items-start justify-between gap-2">
            <p className="text-sm font-bold text-navy-900">{data.title}</p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setExpanded(false) }}
              className="shrink-0 rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="text-xs leading-relaxed text-slate-600">{subtitle}</p>
        </div>
      ) : null}
    </div>
  )
}

export default memo(StepNodeComponent)
