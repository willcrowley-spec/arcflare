import clsx from 'clsx'
import type { ConnectionStatus, ProcessHealthStatus, RecordStatus } from '@/types'

export type BadgeStatus = ConnectionStatus | RecordStatus | ProcessHealthStatus | 'NEEDS ATTENTION'

const styles: Record<string, string> = {
  CONNECTED: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  SYNCING: 'bg-amber-50 text-amber-900 ring-amber-200',
  ERROR: 'bg-red-50 text-red-800 ring-red-200',
  DISCONNECTED: 'bg-slate-100 text-slate-700 ring-slate-200',
  PENDING: 'bg-slate-100 text-slate-700 ring-slate-200',
  CLEAN: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  ANALYZING: 'bg-sky-50 text-sky-800 ring-sky-200',
  CONFLICT: 'bg-red-50 text-red-800 ring-red-200',
  OPTIMIZED: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  'NEEDS ATTENTION': 'bg-red-50 text-red-800 ring-red-200',
  NEEDS_ATTENTION: 'bg-red-50 text-red-800 ring-red-200',
  DRAFT: 'bg-slate-100 text-slate-600 ring-slate-200',
  PARTIAL: 'bg-amber-50 text-amber-900 ring-amber-200',
  HIGH: 'bg-orange-50 text-orange-900 ring-orange-200',
  LOW: 'bg-slate-100 text-slate-600 ring-slate-200',
  ACTIVE: 'bg-sky-50 text-sky-800 ring-sky-200',
  IMPLEMENTED: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  ARCHIVED: 'bg-slate-100 text-slate-600 ring-slate-200',
  RUNNING: 'bg-emerald-50 text-emerald-900 ring-emerald-200',
  IDLE: 'bg-slate-100 text-slate-700 ring-slate-200',
}

function normalize(status: string): string {
  return status.replace(/\s+/g, ' ').trim()
}

export function StatusBadge({ status }: { status: BadgeStatus | string }) {
  const key = normalize(status)
  const className = styles[key] ?? 'bg-slate-100 text-slate-700 ring-slate-200'
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset',
        className,
      )}
    >
      {key}
    </span>
  )
}
