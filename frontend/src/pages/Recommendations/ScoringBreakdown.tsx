import clsx from 'clsx'

export interface ScoringBreakdownProps {
  signals: Record<string, number>
  baseScore: number
  llmScore: number | null
  compositeScore: number | null
  divergenceFlag: boolean
  className?: string
}

const GATE_KEYS = ['automation_potential', 'evidence_strength'] as const

const REFINEMENT_KEYS = [
  'value_classification',
  'complexity_inverse',
  'system_touchpoints',
  'failure_mode_risk',
  'handoff_gap',
] as const

function formatSignalLabel(key: string): string {
  return key
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
}

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.min(1, Math.max(0, n))
}

function formatScoreValue(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return '—'
  return n.toFixed(2)
}

function SignalBarRow({
  label,
  value,
  barClass,
  rightText,
}: {
  label: string
  value: number
  barClass: string
  /** If omitted, shows clamped numeric value (0–1) */
  rightText?: string
}) {
  const v = clamp01(value)
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] items-center gap-3 text-sm">
      <span className="text-slate-700">{label}</span>
      <div
        className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100 ring-1 ring-slate-200/80"
        role="presentation"
      >
        <div className={clsx('h-full rounded-full transition-[width]', barClass)} style={{ width: `${v * 100}%` }} />
      </div>
      <span className="min-w-[2.5rem] shrink-0 text-right text-xs font-semibold tabular-nums text-slate-800">
        {rightText ?? v.toFixed(2)}
      </span>
    </div>
  )
}

export function ScoringBreakdown({
  signals,
  baseScore,
  llmScore,
  compositeScore,
  divergenceFlag,
  className,
}: ScoringBreakdownProps) {
  return (
    <div className={clsx('space-y-6', className)}>
      {divergenceFlag ? (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 ring-1 ring-amber-100"
          role="status"
        >
          Heuristic and AI assessment disagree — review recommended
        </div>
      ) : null}

      <section className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">Gate signals</h3>
        <div className="space-y-3">
          {GATE_KEYS.map((key) => (
            <SignalBarRow
              key={key}
              label={formatSignalLabel(key)}
              value={signals[key] ?? 0}
              barClass="bg-navy-600"
            />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">Refinement signals</h3>
        <div className="space-y-3">
          {REFINEMENT_KEYS.map((key) => (
            <SignalBarRow
              key={key}
              label={formatSignalLabel(key)}
              value={signals[key] ?? 0}
              barClass="bg-slate-600"
            />
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">Scores</h3>
        <div className="space-y-3">
          <SignalBarRow label="Base score" value={baseScore} barClass="bg-emerald-500" />
          <SignalBarRow
            label="LLM score"
            value={llmScore ?? 0}
            barClass="bg-emerald-500"
            rightText={formatScoreValue(llmScore)}
          />
          <SignalBarRow
            label="Composite score"
            value={compositeScore ?? 0}
            barClass="bg-emerald-500"
            rightText={formatScoreValue(compositeScore)}
          />
        </div>
      </section>
    </div>
  )
}
