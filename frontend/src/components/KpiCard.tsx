import clsx from 'clsx'
import type { LucideIcon } from 'lucide-react'
import { TrendingDown, TrendingUp } from 'lucide-react'

type Trend = 'up' | 'down' | 'neutral'

type KpiCardProps = {
  icon: LucideIcon
  label: string
  value: string
  sublabel?: string
  trend?: Trend
  trendLabel?: string
  className?: string
}

export function KpiCard({
  icon: Icon,
  label,
  value,
  sublabel,
  trend,
  trendLabel,
  className,
}: KpiCardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm ring-1 ring-slate-900/5',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
          <p className="mt-2 text-3xl font-semibold tracking-tight text-navy-900">{value}</p>
          {sublabel ? <p className="mt-1 text-sm text-slate-500">{sublabel}</p> : null}
        </div>
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-navy-50 text-navy-700">
          <Icon className="h-5 w-5" strokeWidth={1.75} />
        </div>
      </div>
      {trend && trend !== 'neutral' && trendLabel ? (
        <div className="mt-4 flex items-center gap-1.5 text-sm">
          {trend === 'up' ? (
            <TrendingUp className="h-4 w-4 text-emerald-600" />
          ) : (
            <TrendingDown className="h-4 w-4 text-red-500" />
          )}
          <span className={trend === 'up' ? 'text-emerald-700' : 'text-red-600'}>{trendLabel}</span>
        </div>
      ) : null}
    </div>
  )
}
