import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { FileSpreadsheet, FileText, FileType2, Server, Workflow } from 'lucide-react'
import clsx from 'clsx'

export type StepNodeData = {
  title: string
  subtitle: string
  variant: 'doc' | 'process' | 'record'
  processId?: string
}

function StepNodeComponent({ data }: NodeProps<Node<StepNodeData>>) {
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

export default memo(StepNodeComponent)
