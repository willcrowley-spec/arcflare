import clsx from 'clsx'
import { AlertTriangle } from 'lucide-react'

export interface Recommendation {
  id: string
  title: string
  description: string | null
  category: string | null
  priority: string | null
  status: string
  recommendation_type: 'discovered' | 'synthesized'
  automation_type: 'deterministic' | 'agentic' | 'hybrid'
  composite_score: number | null
  base_score: number | null
  llm_score: number | null
  llm_rationale: string | null
  score_divergence_flag: boolean
  estimated_roi: number | null
  assumptions_json: Record<string, unknown>
  scenarios_json: Record<string, unknown>
  arc_score_json: Record<string, unknown>
  actions_json: Array<{ step: number; action: string; effort: string }>
  impact_json: Record<string, unknown>
  linked_process_ids: string[]
  enrichment_log: Array<Record<string, unknown>>
  /** API payload may include scoring inputs with embedded `signals`. */
  analysis_inputs_json?: unknown[]
  portfolio_category: 'agent_candidate' | 'automation_integration' | 'needs_evidence' | 'no_build'
  automation_path: string
  recommended_build_path: string
  qualification_decision: string
  qualification_reasons: string[]
  disqualifiers: string[]
  evidence_requirements: string[]
  runtime_reasoning_required: boolean
  agent_suitability_score: number
  agent_suitability_rubric: Record<string, unknown>
  action_contract_readiness: string
  agent_readiness_status: 'ready' | 'needs_evidence' | 'not_agent' | 'blocked'
  generate_agent_allowed: boolean
  generate_agent_disabled_reason: string | null
  generate_agent_blockers: string[]
  recommended_next_action: string
  agent_fit_summary: string
  evidence_summary: string
}

export interface RecommendationCardProps {
  rec: Recommendation
  isSelected: boolean
  onToggleSelect: (id: string) => void
  onExpand: (id: string) => void
  isExpanded: boolean
}

function extractNpvRange(scenarios: Record<string, unknown>): {
  conservative: number | null
  expected: number | null
  optimistic: number | null
} {
  const get = (key: string) => {
    const s = scenarios[key]
    if (s && typeof s === 'object' && !Array.isArray(s)) {
      const npv = (s as Record<string, unknown>).npv
      return typeof npv === 'number' ? npv : null
    }
    return null
  }
  return { conservative: get('conservative'), expected: get('expected'), optimistic: get('optimistic') }
}

function formatCompactUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return '—'
  const v = Number(n)
  const abs = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1_000_000) {
    const x = abs / 1_000_000
    return `${sign}$${x >= 10 ? Math.round(x) : Math.round(x * 10) / 10}M`
  }
  if (abs >= 1_000) {
    const x = abs / 1_000
    return `${sign}$${Math.round(x)}K`
  }
  return `${sign}$${Math.round(abs)}`
}

function formatArcScore(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return '—'
  return String(Math.round(Number(n) * 100))
}

const PORTFOLIO_LABEL: Record<Recommendation['portfolio_category'], string> = {
  agent_candidate: 'Agent candidate',
  automation_integration: 'Automation & integration',
  needs_evidence: 'Needs evidence',
  no_build: 'No build',
}

const READINESS_PILL: Record<Recommendation['agent_readiness_status'], string> = {
  ready: 'bg-emerald-50 text-emerald-900 ring-emerald-200',
  needs_evidence: 'bg-amber-50 text-amber-900 ring-amber-200',
  not_agent: 'bg-slate-100 text-slate-700 ring-slate-200',
  blocked: 'bg-red-50 text-red-900 ring-red-200',
}

export function RecommendationCard({
  rec,
  isSelected,
  onToggleSelect,
  onExpand,
  isExpanded,
}: RecommendationCardProps) {
  const typePill =
    rec.recommendation_type === 'synthesized'
      ? 'bg-navy-50 text-navy-900 ring-navy-200'
      : 'bg-navy-50 text-navy-900 ring-navy-200'

  const autoPill =
    rec.automation_type === 'deterministic'
      ? 'bg-emerald-50 text-emerald-900 ring-emerald-200'
      : rec.automation_type === 'agentic'
        ? 'bg-orange-50 text-orange-900 ring-orange-200'
        : 'bg-navy-50 text-navy-900 ring-navy-200'

  const npvRange = extractNpvRange(rec.scenarios_json)
  const hasNpvBand =
    npvRange.conservative != null &&
    npvRange.optimistic != null &&
    Number.isFinite(npvRange.conservative) &&
    Number.isFinite(npvRange.optimistic)
  const npvTitle =
    hasNpvBand && npvRange.expected != null && Number.isFinite(npvRange.expected) ?
      `Expected NPV: ${formatCompactUsd(npvRange.expected)}`
    : undefined

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onExpand(rec.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onExpand(rec.id)
        }
      }}
      className={clsx(
        'relative flex cursor-pointer flex-col rounded-xl border border-slate-200/80 bg-white p-5 pr-12 shadow-sm ring-1 ring-slate-900/5 transition-colors',
        'hover:border-slate-300 hover:shadow-md',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-700',
        isExpanded && 'border-navy-300 bg-navy-50/30 ring-2 ring-navy-900/10',
      )}
    >
      <div
        className="absolute right-4 top-4 z-10"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(rec.id)}
          onClick={(e) => e.stopPropagation()}
          className="h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
          aria-label={`Select ${rec.title} for portfolio`}
        />
      </div>

      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
        {PORTFOLIO_LABEL[rec.portfolio_category] ?? 'Needs evidence'}
      </p>

      <h3 className="mt-2 text-lg font-semibold text-navy-900">{rec.title}</h3>

      <div className="mt-3 flex flex-wrap gap-2">
        <span
          className={clsx(
            'rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize ring-1 ring-inset',
            READINESS_PILL[rec.agent_readiness_status] ?? READINESS_PILL.needs_evidence,
          )}
        >
          {rec.agent_readiness_status.replace(/_/g, ' ')}
        </span>
        <span
          className={clsx(
            'rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1 ring-inset',
            typePill,
          )}
        >
          {rec.recommendation_type}
        </span>
        <span
          className={clsx(
            'rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize ring-1 ring-inset',
            autoPill,
          )}
        >
          {rec.automation_type}
        </span>
      </div>

      <p className="mt-3 line-clamp-2 text-sm leading-relaxed text-slate-600">
        {rec.agent_fit_summary || rec.description}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-700">
        <span className="font-medium tabular-nums">
          ARC Score: <span className="text-navy-900">{formatArcScore(rec.composite_score)}</span>
        </span>
        <span className="text-slate-400">·</span>
        <span className="font-medium tabular-nums" title={npvTitle}>
          NPV:{' '}
          <span className="text-emerald-800">
            {hasNpvBand ?
              `${formatCompactUsd(npvRange.conservative)}–${formatCompactUsd(npvRange.optimistic)}`
            : formatCompactUsd(rec.estimated_roi)}
          </span>
        </span>
        {rec.score_divergence_flag ? (
          <span className="inline-flex items-center gap-1 text-amber-600" title="Heuristic vs. AI score mismatch">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
            <span className="sr-only">Score divergence warning</span>
          </span>
        ) : null}
      </div>
    </article>
  )
}
