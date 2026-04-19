import { memo, useState, useRef, useEffect } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { FileSpreadsheet, FileText, FileType2, Server, Workflow, X } from 'lucide-react'
import clsx from 'clsx'

export type StepNodeData = {
  title: string
  subtitle: string
  variant: 'doc' | 'process' | 'record'
  processId?: string
}

function StepNodeComponent({ data }: NodeProps<Node<StepNodeData>>) {
  const [expanded, setExpanded] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

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

  const hasOverflow = data.subtitle.length > 80

  return (
    <div className="relative">
      <div
        className={clsx(
          'w-[240px] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-md ring-1 ring-slate-900/5 transition-shadow',
          hasOverflow && 'cursor-pointer hover:shadow-lg hover:ring-navy-200',
        )}
        onClick={() => hasOverflow && setExpanded((v) => !v)}
      >
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

      {expanded ? (
        <div
          ref={popoverRef}
          className="nodrag nopan absolute left-1/2 top-full z-50 mt-2 w-80 -translate-x-1/2 rounded-xl border border-slate-200 bg-white p-4 shadow-2xl ring-1 ring-slate-900/10"
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
          <p className="text-xs leading-relaxed text-slate-600">{data.subtitle}</p>
        </div>
      ) : null}
    </div>
  )
}

export default memo(StepNodeComponent)
