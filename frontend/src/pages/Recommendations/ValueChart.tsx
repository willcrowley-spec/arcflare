import clsx from 'clsx'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

/** Matches scenarios from financial_engine / scenarios_json */
export interface ValueChartScenarios {
  optimistic: { cumulative: number[]; hard_savings: number[]; soft_savings: number[] }
  expected: { cumulative: number[]; hard_savings: number[]; soft_savings: number[] }
  conservative: { cumulative: number[]; hard_savings: number[]; soft_savings: number[] }
}

export interface ValueChartProps {
  scenarios: ValueChartScenarios | null
  height?: number
  className?: string
}

const YEAR_LABELS = ['Year 0', 'Year 1', 'Year 2', 'Year 3', 'Year 4'] as const

const COLORS = {
  optimistic: '#10b981', // emerald-500
  expected: '#4c6ef5', // navy-600
  conservative: '#94a3b8', // slate-400
} as const

function atYear(arr: number[] | undefined, i: number): number {
  if (!arr?.length) return 0
  return arr[Math.min(i, arr.length - 1)] ?? 0
}

function buildRows(scenarios: ValueChartScenarios) {
  return YEAR_LABELS.map((yearLabel, i) => {
    const opt = atYear(scenarios.optimistic.cumulative, i)
    const exp = atYear(scenarios.expected.cumulative, i)
    const cons = atYear(scenarios.conservative.cumulative, i)
    const bandDelta = Math.max(0, opt - cons)

    return { yearLabel, optimistic: opt, expected: exp, conservative: cons, bandDelta }
  })
}

function formatAxisMoney(n: number): string {
  const v = Number(n)
  if (!Number.isFinite(v)) return '$0'
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1_000_000) {
    const x = abs / 1_000_000
    return `${sign}$${x >= 10 ? x.toFixed(0) : x.toFixed(1)}M`
  }
  if (abs >= 1_000) {
    const x = abs / 1_000
    return `${sign}$${x >= 10 ? x.toFixed(0) : x.toFixed(1)}K`
  }
  return `${sign}$${Math.round(abs)}`
}

function formatTooltipMoney(n: number): string {
  const v = Number(n)
  if (!Number.isFinite(v)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(v)
}

type TooltipPayloadItem = {
  dataKey?: string | number
  name?: string
  value?: number
  color?: string
  payload?: Record<string, unknown>
}

function ValueTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string
}) {
  if (!active || !payload?.length) return null

  const row = payload[0]?.payload as
    | { optimistic?: number; expected?: number; conservative?: number }
    | undefined

  const byKey = Object.fromEntries(
    payload.filter((p) => p.dataKey != null).map((p) => [String(p.dataKey), p.value]),
  ) as Record<string, number | undefined>

  const opt = row?.optimistic ?? byKey.optimistic
  const exp = row?.expected ?? byKey.expected
  const cons = row?.conservative ?? byKey.conservative

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg ring-1 ring-slate-900/5">
      <p className="font-semibold text-navy-900">{label}</p>
      <ul className="mt-2 space-y-1 text-slate-700">
        <li className="flex justify-between gap-6">
          <span className="text-emerald-600">Optimistic</span>
          <span className="font-medium tabular-nums">{formatTooltipMoney(opt ?? 0)}</span>
        </li>
        <li className="flex justify-between gap-6">
          <span className="text-navy-700">Expected</span>
          <span className="font-medium tabular-nums">{formatTooltipMoney(exp ?? 0)}</span>
        </li>
        <li className="flex justify-between gap-6">
          <span className="text-slate-500">Conservative</span>
          <span className="font-medium tabular-nums">{formatTooltipMoney(cons ?? 0)}</span>
        </li>
      </ul>
    </div>
  )
}

export function ValueChart({ scenarios, height = 320, className }: ValueChartProps) {
  if (!scenarios) {
    return (
      <div
        className={clsx(
          'flex min-h-[200px] items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center text-sm text-slate-500',
          className,
        )}
      >
        No projection data available for this recommendation.
      </div>
    )
  }

  const data = buildRows(scenarios)

  return (
    <div className={clsx('w-full', className)}>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="yearLabel" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={{ stroke: '#cbd5e1' }} />
          <YAxis
            tickFormatter={formatAxisMoney}
            tick={{ fill: '#64748b', fontSize: 11 }}
            axisLine={{ stroke: '#cbd5e1' }}
            width={56}
          />
          <ReferenceLine y={0} stroke="#475569" strokeWidth={1.5} strokeDasharray="4 2" label={{ value: 'Break-even', position: 'insideTopRight', fontSize: 10, fill: '#475569' }} />
          <Tooltip
            content={<ValueTooltip />}
            cursor={{ stroke: '#94a3b8', strokeWidth: 1, strokeDasharray: '4 4' }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            formatter={(value) => <span className="text-slate-600">{value}</span>}
          />

          <Area
            type="monotone"
            dataKey="conservative"
            stackId="conf"
            stroke="none"
            fill="rgba(0,0,0,0)"
            legendType="none"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="bandDelta"
            stackId="conf"
            name="Confidence range"
            stroke="none"
            fill="rgba(16, 185, 129, 0.10)"
            legendType="none"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="conservative"
            name="Conservative"
            stroke={COLORS.conservative}
            strokeWidth={2}
            dot={{ r: 3, fill: COLORS.conservative }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="expected"
            name="Expected"
            stroke={COLORS.expected}
            strokeWidth={2.5}
            dot={{ r: 3, fill: COLORS.expected }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="optimistic"
            name="Optimistic"
            stroke={COLORS.optimistic}
            strokeWidth={2}
            dot={{ r: 3, fill: COLORS.optimistic }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
