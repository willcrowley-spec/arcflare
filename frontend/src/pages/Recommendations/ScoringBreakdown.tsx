import clsx from 'clsx'
import { Info } from 'lucide-react'

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
  helpText,
}: {
  label: string
  value: number
  barClass: string
  rightText?: string
  helpText?: string
}) {
  const v = clamp01(value)
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] items-center gap-3 text-sm">
      <span className="inline-flex items-center gap-1.5 text-slate-700">
        {label}
        {helpText ? <InfoHint text={helpText} /> : null}
      </span>
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

const ARC_DIMENSION_HELP: Record<string, string> = {
  value: 'Business payoff: saved time, affected users, frequency, and projected NPV.',
  feasibility: 'Practicality of building it: complexity, data readiness, true external integrations, and Salesforce-native scope.',
  suitability: 'Whether the work is appropriate to automate or agent-assist given judgment, control, and human-review needs.',
  evidence: 'How much structured evidence supports the recommendation: linked processes, linked steps, mapped replacements, and financial signals.',
  risk_inverse: 'Risk posture. Higher means fewer control, complexity, and external-integration concerns.',
}

function InfoHint({ text, className }: { text: string; className?: string }) {
  return (
    <span
      tabIndex={0}
      title={text}
      aria-label={text}
      className={clsx(
        'group relative inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 outline-none hover:text-navy-700 focus-visible:text-navy-700',
        className,
      )}
    >
      <Info className="h-3.5 w-3.5" aria-hidden />
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 hidden w-72 -translate-x-1/2 rounded-md bg-navy-900 px-3 py-2 text-left text-xs font-medium leading-relaxed text-white shadow-lg group-hover:block group-focus:block"
      >
        {text}
      </span>
    </span>
  )
}

function hasLegacySignalValues(signals: Record<string, number>): boolean {
  return [...GATE_KEYS, ...REFINEMENT_KEYS].some((key) => {
    const value = signals[key]
    return typeof value === 'number' && Number.isFinite(value) && value > 0
  })
}

function MissingArcScore({
  compositeScore,
  llmScore,
  divergenceFlag,
}: {
  compositeScore: number | null
  llmScore: number | null
  divergenceFlag: boolean
}) {
  return (
    <section className="rounded-xl border border-amber-200 bg-amber-50 p-5 ring-1 ring-amber-100">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wide text-amber-950">ARC Score not computed</h3>
          <p className="mt-1 max-w-2xl text-sm leading-relaxed text-amber-950/80">
            This recommendation was generated before the current scoring model was stored. Recalculate it to
            populate ARC dimensions, evidence gaps, and score provenance.
          </p>
        </div>
        <div className="text-right text-xs text-amber-950/80">
          <div>
            Stored score:{' '}
            <span className="font-semibold tabular-nums text-amber-950">{formatScoreValue(compositeScore)}</span>
          </div>
          <div>
            AI confidence:{' '}
            <span className="font-semibold tabular-nums text-amber-950">{formatScoreValue(llmScore)}</span>
          </div>
          {divergenceFlag ? <div className="font-semibold text-amber-950">Review flag is set</div> : null}
        </div>
      </div>
    </section>
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
  const hasLegacySignals = hasLegacySignalValues(signals)

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
                <h3 className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-navy-900">
                  ARC Score
                  <InfoHint text="Automation Readiness & Confidence. This is Arcflare's deterministic readiness score, not the LLM's confidence score." />
                </h3>
                <p className="mt-1 text-sm text-slate-600">
                  Automation Readiness & Confidence. Weighted formula: value 30%, feasibility 25%, suitability
                  20%, evidence 15%, risk inverse 10%.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className={clsx(
                      'rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ring-1 ring-inset',
                      DECISION_PILL[parsedArc.decision] ?? DECISION_PILL.review,
                    )}
                  >
                    {humanizeToken(parsedArc.decision)}
                  </span>
                  <InfoHint text="Decision bands combine the numeric score with gates. Defer can still have a strong score when risk or evidence needs review before build." />
                </span>
                <span className="text-3xl font-semibold tabular-nums text-navy-900">{parsedArc.scorePct}</span>
              </div>
            </div>
            <div className="mt-4 grid gap-3 text-xs text-slate-500 sm:grid-cols-3">
              <span className="inline-flex items-center gap-1.5">
                Method: {parsedArc.scoringMethod ?? 'rules'}
                <InfoHint text="Rules v1 means the final score is calculated by Arcflare from structured inputs. The LLM does not assign the final rank." />
              </span>
              <span className="inline-flex items-center gap-1.5">
                Features: {parsedArc.featureVersion ?? 'v1'}
                <InfoHint text="Feature version identifies the input recipe used for scoring so scores can be compared or recalculated later." />
              </span>
              <span className="inline-flex items-center gap-1.5">
                AI confidence: {formatArcPct(parsedArc.llmConfidence)}
                <InfoHint text="The LLM's original confidence in the recommendation. It is shown for comparison and divergence checks, not used as the final score." />
              </span>
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
                      helpText={ARC_DIMENSION_HELP[key]}
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
      ) : hasLegacySignals ? (
        <LegacyScoringBreakdown
          signals={signals}
          baseScore={baseScore}
          llmScore={llmScore}
          compositeScore={compositeScore}
          divergenceFlag={divergenceFlag}
        />
      ) : (
        <MissingArcScore
          compositeScore={compositeScore}
          llmScore={llmScore}
          divergenceFlag={divergenceFlag}
        />
      )}
    </div>
  )
}
