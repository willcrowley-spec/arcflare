import clsx from 'clsx'

export interface ScoringBreakdownProps {
  arcScore?: Record<string, unknown>
  signals: Record<string, number>
  baseScore: number
  llmScore: number | null
  compositeScore: number | null
  divergenceFlag: boolean
  className?: string
}

interface ArcDimension {
  score: number
  explanation?: string
}

interface ParsedArcScore {
  score: number
  scorePct: number
  decision: string
  dimensions: Record<string, ArcDimension>
  evidenceGaps: string[]
  blockers: string[]
  llmConfidence: number | null
  scoringMethod: string | null
  featureVersion: string | null
}

const GATE_KEYS = ['automation_potential', 'evidence_strength'] as const

const REFINEMENT_KEYS = [
  'value_classification',
  'complexity_inverse',
  'system_touchpoints',
  'failure_mode_risk',
  'handoff_gap',
] as const

const ARC_DIMENSION_ORDER = ['value', 'feasibility', 'suitability', 'evidence', 'risk_inverse']

const DECISION_PILL: Record<string, string> = {
  ready: 'bg-emerald-50 text-emerald-900 ring-emerald-200',
  review: 'bg-amber-50 text-amber-900 ring-amber-200',
  defer: 'bg-slate-100 text-slate-700 ring-slate-200',
  blocked: 'bg-red-50 text-red-900 ring-red-200',
}

function formatSignalLabel(key: string): string {
  return key
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
}

function humanizeToken(value: string): string {
  return formatSignalLabel(value)
}

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.min(1, Math.max(0, n))
}

function formatScoreValue(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return '-'
  return n.toFixed(2)
}

function formatArcPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return '-'
  return String(Math.round(Number(n) * 100))
}

function parseArcScore(raw?: Record<string, unknown>): ParsedArcScore | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const score = typeof raw.score === 'number' ? raw.score : null
  const dimensionsRaw = raw.dimensions
  if (score == null || !dimensionsRaw || typeof dimensionsRaw !== 'object' || Array.isArray(dimensionsRaw)) {
    return null
  }

  const dimensions: Record<string, ArcDimension> = {}
  for (const [key, value] of Object.entries(dimensionsRaw as Record<string, unknown>)) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) continue
    const obj = value as Record<string, unknown>
    const dimScore = typeof obj.score === 'number' ? obj.score : null
    if (dimScore == null) continue
    dimensions[key] = {
      score: dimScore,
      explanation: typeof obj.explanation === 'string' ? obj.explanation : undefined,
    }
  }

  return {
    score,
    scorePct: typeof raw.score_pct === 'number' ? raw.score_pct : Math.round(score * 100),
    decision: typeof raw.decision === 'string' ? raw.decision : 'review',
    dimensions,
    evidenceGaps: Array.isArray(raw.evidence_gaps) ? raw.evidence_gaps.map(String) : [],
    blockers: Array.isArray(raw.blockers) ? raw.blockers.map(String) : [],
    llmConfidence: typeof raw.llm_confidence === 'number' ? raw.llm_confidence : null,
    scoringMethod: typeof raw.scoring_method === 'string' ? raw.scoring_method : null,
    featureVersion: typeof raw.feature_version === 'string' ? raw.feature_version : null,
  }
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

function LegacyScoringBreakdown({
  signals,
  baseScore,
  llmScore,
  compositeScore,
  divergenceFlag,
}: Omit<ScoringBreakdownProps, 'arcScore' | 'className'>) {
  return (
    <>
      {divergenceFlag ? (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 ring-1 ring-amber-100"
          role="status"
        >
          Heuristic and AI assessment disagree - review recommended
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
    </>
  )
}

export function ScoringBreakdown({
  arcScore,
  signals,
  baseScore,
  llmScore,
  compositeScore,
  divergenceFlag,
  className,
}: ScoringBreakdownProps) {
  const parsedArc = parseArcScore(arcScore)

  return (
    <div className={clsx('space-y-6', className)}>
      {parsedArc ? (
        <>
          {divergenceFlag ? (
            <div
              className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 ring-1 ring-amber-100"
              role="status"
            >
              ARC Score and AI confidence disagree - review recommended
            </div>
          ) : null}

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">ARC Score</h3>
                <p className="mt-1 text-sm text-slate-600">Automation Readiness & Confidence</p>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={clsx(
                    'rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ring-1 ring-inset',
                    DECISION_PILL[parsedArc.decision] ?? DECISION_PILL.review,
                  )}
                >
                  {humanizeToken(parsedArc.decision)}
                </span>
                <span className="text-3xl font-semibold tabular-nums text-navy-900">{parsedArc.scorePct}</span>
              </div>
            </div>
            <div className="mt-4 grid gap-3 text-xs text-slate-500 sm:grid-cols-3">
              <span>Method: {parsedArc.scoringMethod ?? 'rules'}</span>
              <span>Features: {parsedArc.featureVersion ?? 'v1'}</span>
              <span>AI confidence: {formatArcPct(parsedArc.llmConfidence)}</span>
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">ARC dimensions</h3>
            <div className="space-y-3">
              {ARC_DIMENSION_ORDER.map((key) => {
                const dimension = parsedArc.dimensions[key]
                if (!dimension) return null
                return (
                  <div key={key} className="space-y-1.5">
                    <SignalBarRow
                      label={humanizeToken(key)}
                      value={dimension.score}
                      barClass={key === 'risk_inverse' ? 'bg-slate-600' : 'bg-navy-600'}
                      rightText={formatArcPct(dimension.score)}
                    />
                    {dimension.explanation ? (
                      <p className="text-xs leading-relaxed text-slate-500 sm:pl-[calc(33%+0.75rem)]">
                        {dimension.explanation}
                      </p>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </section>

          {parsedArc.blockers.length > 0 || parsedArc.evidenceGaps.length > 0 ? (
            <section className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">Gaps and blockers</h3>
              <div className="flex flex-wrap gap-2">
                {parsedArc.blockers.map((item) => (
                  <span
                    key={`blocker-${item}`}
                    className="rounded-full bg-red-50 px-2.5 py-1 text-xs font-semibold text-red-900 ring-1 ring-inset ring-red-200"
                  >
                    {humanizeToken(item)}
                  </span>
                ))}
                {parsedArc.evidenceGaps.map((item) => (
                  <span
                    key={`gap-${item}`}
                    className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 ring-1 ring-inset ring-slate-200"
                  >
                    {humanizeToken(item)}
                  </span>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : (
        <LegacyScoringBreakdown
          signals={signals}
          baseScore={baseScore}
          llmScore={llmScore}
          compositeScore={compositeScore}
          divergenceFlag={divergenceFlag}
        />
      )}
    </div>
  )
}
