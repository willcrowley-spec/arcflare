import { Fragment, useCallback, useMemo, useState } from 'react'
import clsx from 'clsx'
import { Check, CheckCheck, GitBranch, Info, MessageSquare, Pencil, Sparkles, Undo2, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useChatStore } from '@/stores/chatStore'
import { useGenerateAgentFromRecommendation, useRecalculateRecommendation } from '@/hooks/useApi'
import { ScoringBreakdown } from '@/pages/Recommendations/ScoringBreakdown'
import { ValueChart, type ValueChartScenarios } from '@/pages/Recommendations/ValueChart'
import type { Recommendation } from '@/pages/Recommendations/RecommendationCard'

export interface RecommendationDetailProps {
  rec: Recommendation
  onStatusChange: (id: string, status: string) => void
}

type DetailTab = 'overview' | 'assumptions' | 'scoring'

const TABS: { key: DetailTab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'assumptions', label: 'Assumptions' },
  { key: 'scoring', label: 'Scoring' },
]

const FRACTION_KEYS = new Set([
  'efficiency_gain',
  'productivity_dip',
  'change_management_factor',
  'discount_rate',
  'hard_savings_pct',
])

const SKIP_KEYS = new Set([
  'overrides',
  'source',
  'agentforce_pricing_basis',
  'investment_components',
  'investment_range',
  'touchpoint_classification',
])

function mergeSignalObjects(entries: unknown[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const entry of entries) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) continue
    const sig = (entry as { signals?: unknown }).signals
    if (!sig || typeof sig !== 'object' || Array.isArray(sig)) continue
    for (const [k, v] of Object.entries(sig)) {
      const n = typeof v === 'number' ? v : Number(v)
      if (Number.isFinite(n)) out[k] = n
    }
  }
  return out
}

function extractSignals(rec: Recommendation): Record<string, number> {
  const fromInputs: unknown[] = Array.isArray(rec.analysis_inputs_json) ? rec.analysis_inputs_json : []
  const fromLog =
    Array.isArray(rec.enrichment_log) ?
      rec.enrichment_log.filter((e) => e && typeof e === 'object' && 'signals' in e)
    : []
  return mergeSignalObjects([...fromInputs, ...fromLog])
}

function parseValueChartScenarios(raw: Record<string, unknown>): ValueChartScenarios | null {
  const keys = ['optimistic', 'expected', 'conservative'] as const
  const out: Record<string, Record<string, unknown>> = {}
  for (const k of keys) {
    const s = raw[k]
    if (!s || typeof s !== 'object' || Array.isArray(s)) return null
    const o = s as Record<string, unknown>
    if (!Array.isArray(o.cumulative)) return null
    out[k] = {
      cumulative: (o.cumulative as number[]).map(Number),
      cumulative_benefit: Array.isArray(o.cumulative_benefit) ? (o.cumulative_benefit as number[]).map(Number) : undefined,
      gross_benefit: Array.isArray(o.gross_benefit) ? (o.gross_benefit as number[]).map(Number) : undefined,
      hard_savings: Array.isArray(o.hard_savings) ? (o.hard_savings as number[]).map(Number) : [],
      soft_savings: Array.isArray(o.soft_savings) ? (o.soft_savings as number[]).map(Number) : [],
      total_investment: typeof o.total_investment === 'number' ? o.total_investment : 0,
      annual_op_cost: typeof o.annual_op_cost === 'number' ? o.annual_op_cost : 0,
      npv: typeof o.npv === 'number' ? o.npv : undefined,
      payback_month: typeof o.payback_month === 'number' ? o.payback_month : null,
    }
  }
  const npv = raw.npv && typeof raw.npv === 'object' ? (raw.npv as Record<string, number>) : undefined
  const payback = raw.payback_month && typeof raw.payback_month === 'object' ? (raw.payback_month as Record<string, number | null>) : undefined
  return { ...out, npv, payback_month: payback } as unknown as ValueChartScenarios
}

function humanizeKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function isFraction(key: string): boolean {
  return FRACTION_KEYS.has(key) || (key.endsWith('_pct') && true)
}

function isCurrency(key: string): boolean {
  return key.includes('cost') || key.includes('investment') || key.includes('spend')
}

function formatAssumptionCell(key: string, val: unknown): string {
  if (val == null) return '—'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'string') return val
  if (typeof val === 'number') {
    if (isCurrency(key)) {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)
    }
    if (FRACTION_KEYS.has(key) || (key.endsWith('_pct') && Math.abs(val) <= 1)) {
      return `${(val * 100).toFixed(1)}%`
    }
    return String(val)
  }
  if (Array.isArray(val)) {
    if (val.every((x) => typeof x === 'number')) {
      return val.map((x) => (typeof x === 'number' && x <= 1 && x >= 0 ? `${Math.round(x * 100)}%` : String(x))).join(', ')
    }
    return val.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(', ')
  }
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatCurrency(n: unknown): string {
  if (n == null || !Number.isFinite(Number(n))) return 'â€”'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(n))
}

function numericValue(n: unknown): number | null {
  if (n == null || !Number.isFinite(Number(n))) return null
  return Number(n)
}

function isStructuredObject(value: unknown): boolean {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function shouldShowAssumptionValue(key: string, value: unknown): boolean {
  if (SKIP_KEYS.has(key)) return false
  if (isStructuredObject(value)) return false
  if (Array.isArray(value)) {
    return value.every((item) => item == null || ['string', 'number', 'boolean'].includes(typeof item))
  }
  return true
}

function InfoHint({
  text,
  className,
  align = 'start',
}: {
  text: string
  className?: string
  align?: 'start' | 'center' | 'end'
}) {
  const positionClass =
    align === 'end' ? 'right-0'
    : align === 'center' ? 'left-1/2 -translate-x-1/2'
    : 'left-0'
  return (
    <span
      tabIndex={0}
      aria-label={text}
      className={clsx(
        'group relative inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-400 outline-none hover:text-navy-700 focus-visible:text-navy-700',
        className,
      )}
    >
      <Info className="h-3.5 w-3.5" aria-hidden />
      <span
        role="tooltip"
        className={clsx(
          'pointer-events-none absolute top-full z-30 mt-2 hidden w-72 max-w-[calc(100vw-2rem)] rounded-md bg-navy-900 px-3 py-2 text-left text-xs font-medium leading-relaxed text-white shadow-lg group-hover:block group-focus:block',
          positionClass,
        )}
      >
        {text}
      </span>
    </span>
  )
}

interface AssumptionRow {
  key: string
  rawValue: unknown
  displayValue: string
  isOverride: boolean
  editable: boolean
}

function assumptionTableRows(rec: Recommendation): AssumptionRow[] {
  const raw = rec.assumptions_json && typeof rec.assumptions_json === 'object' ? rec.assumptions_json : {}
  const overridesRaw = raw.overrides
  const overrides =
    overridesRaw && typeof overridesRaw === 'object' && !Array.isArray(overridesRaw) ?
      (overridesRaw as Record<string, unknown>)
    : {}

  const keys = new Set<string>()
  for (const k of Object.keys(raw)) {
    if (shouldShowAssumptionValue(k, raw[k])) keys.add(k)
  }
  for (const k of Object.keys(overrides)) {
    keys.add(k)
  }

  return [...keys].sort().map((key) => {
    const effective = key in overrides ? overrides[key] : raw[key]
    const isNumeric = typeof effective === 'number'
    return {
      key,
      rawValue: effective,
      displayValue: formatAssumptionCell(key, effective),
      isOverride: Object.prototype.hasOwnProperty.call(overrides, key),
      editable: isNumeric || typeof effective === 'string',
    }
  })
}

const INVESTMENT_COMPONENT_LABELS: Record<string, string> = {
  native_salesforce_build: 'Native Salesforce build',
  external_integration: 'External integration',
  agentforce_runtime: 'Agentforce runtime',
  governance_testing: 'Governance and testing',
  change_management: 'Change management',
}

const INVESTMENT_COMPONENT_HELP: Record<string, string> = {
  native_salesforce_build:
    'Estimated effort for Salesforce-native build work such as flows, Apex, objects, fields, pages, and configuration.',
  external_integration:
    'Estimated effort for true outside systems or APIs. Salesforce objects, fields, flows, Apex, and pages should not land here.',
  agentforce_runtime:
    'Planning allowance for agent runtime usage. It uses a versioned public-pricing assumption until actual usage data is available.',
  governance_testing:
    'Review, QA, permissions, regression testing, release checks, and controls needed before users rely on the automation.',
  change_management:
    'Enablement and rollout effort: stakeholder review, training, process updates, and adoption support.',
}

function getObject(raw: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = raw[key]
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function InvestmentSummary({ rec }: { rec: Recommendation }) {
  const assumptions = rec.assumptions_json && typeof rec.assumptions_json === 'object' ? rec.assumptions_json : {}
  const range = getObject(assumptions, 'investment_range')
  const components = getObject(assumptions, 'investment_components')
  const touchpoints = getObject(assumptions, 'touchpoint_classification')
  const pricingBasis = getObject(assumptions, 'agentforce_pricing_basis')
  const hasRange = Object.keys(range).length > 0
  if (!hasRange) return null

  const modelVersion = typeof assumptions.assumption_model_version === 'string' ? assumptions.assumption_model_version : null
  const nativeCount = Number(touchpoints.native_salesforce_touchpoint_count ?? 0)
  const externalCount = Number(touchpoints.external_integration_count ?? 0)
  const pilotValue = numericValue(range.pilot_mvp)
  const expectedValue = numericValue(range.expected)
  const enterpriseValue = numericValue(range.enterprise_hardened)
  const showSeparateExpected = pilotValue != null && expectedValue != null && pilotValue !== expectedValue
  const componentTotal = Object.values(components).reduce<number>(
    (sum, value) => sum + (Number.isFinite(Number(value)) ? Number(value) : 0),
    0,
  )
  const pricingUnit = typeof pricingBasis.unit === 'string' ? pricingBasis.unit : null
  const actionCost = numericValue(pricingBasis.estimated_action_cost_usd)

  return (
    <section className="mb-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h4 className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-navy-900">
            Investment range
            <InfoHint text="These are alternative planning cases, not additive line items. The expected pilot/MVP estimate is the total used by the financial projection." />
          </h4>
          <p className="mt-1 text-xs text-slate-500">
            The pilot/MVP estimate is the expected first-release investment. Enterprise hardening is the higher planning case.
          </p>
        </div>
        {modelVersion ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-inset ring-slate-200">
            {modelVersion}
            <InfoHint
              className="h-3.5 w-3.5"
              align="end"
              text="Version of Arcflare's deterministic assumption model. It lets us explain and compare estimates over time."
            />
          </span>
        ) : null}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.8fr)]">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs font-bold uppercase tracking-wide text-slate-500">
              <th className="py-2 pr-4 font-semibold">Case</th>
              <th className="py-2 text-right font-semibold">Total estimate</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-slate-100">
              <td className="py-2.5 pr-4">
                <div className="inline-flex items-center gap-1.5 font-medium text-navy-900">
                  Pilot / MVP expected
                  <InfoHint text="A first usable release estimate. This is the expected investment used in NPV/payback calculations, not a separate item to add to the component list." />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">Used in projected value and payback.</p>
              </td>
              <td className="py-2.5 text-right font-semibold tabular-nums text-navy-900">
                {formatCurrency(expectedValue ?? pilotValue)}
              </td>
            </tr>
            {showSeparateExpected ? (
              <tr className="border-b border-slate-100">
                <td className="py-2.5 pr-4">
                  <div className="inline-flex items-center gap-1.5 font-medium text-navy-900">
                    Pilot / MVP low case
                    <InfoHint text="Lower first-release case when the team can reuse more existing automation and defer nonessential hardening." />
                  </div>
                </td>
                <td className="py-2.5 text-right font-semibold tabular-nums text-navy-900">{formatCurrency(pilotValue)}</td>
              </tr>
            ) : null}
            <tr>
              <td className="py-2.5 pr-4">
                <div className="inline-flex items-center gap-1.5 font-medium text-navy-900">
                  Enterprise hardening
                  <InfoHint text="Higher case for stricter release management, security review, observability, regression coverage, and larger stakeholder rollout." />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">Alternate high case, not added to pilot/MVP.</p>
              </td>
              <td className="py-2.5 text-right font-semibold tabular-nums text-navy-900">{formatCurrency(enterpriseValue)}</td>
            </tr>
          </tbody>
        </table>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-slate-200">
              <p className="inline-flex items-center gap-1 font-semibold text-slate-500">
                Native touchpoints
                <InfoHint text="Salesforce-native objects, fields, flows, Apex, pages, and platform services touched by the recommendation." />
              </p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-navy-900">{Number.isFinite(nativeCount) ? nativeCount : 0}</p>
            </div>
            <div className="rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-slate-200">
              <p className="inline-flex items-center gap-1 font-semibold text-slate-500">
                External integrations
                <InfoHint text="True outside systems or APIs. These increase integration effort more than Salesforce-native metadata touchpoints." />
              </p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-navy-900">{Number.isFinite(externalCount) ? externalCount : 0}</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">
            Component breakdown
            <InfoHint text="These rows add up to the pilot/MVP expected total. They explain the estimate; they are not extra charges." />
          </div>
          <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 text-xs">
            {Object.entries(components).map(([key, value]) => (
              <Fragment key={key}>
                <dt className="inline-flex min-w-0 items-center gap-1 text-slate-500">
                  <span className="truncate">{INVESTMENT_COMPONENT_LABELS[key] ?? humanizeKey(key)}</span>
                  {INVESTMENT_COMPONENT_HELP[key] ? <InfoHint text={INVESTMENT_COMPONENT_HELP[key]} /> : null}
                </dt>
                <dd className="text-right font-semibold tabular-nums text-slate-800">{formatCurrency(value)}</dd>
              </Fragment>
            ))}
            <dt className="border-t border-slate-200 pt-2 font-semibold text-navy-900">Pilot/MVP total</dt>
            <dd className="border-t border-slate-200 pt-2 text-right font-bold tabular-nums text-navy-900">
              {formatCurrency(componentTotal || expectedValue || pilotValue)}
            </dd>
          </dl>
          {pricingUnit && actionCost != null ? (
            <p className="text-xs leading-relaxed text-slate-500">
              Runtime assumption: {formatCurrency(actionCost)} per {pricingUnit}. Replace with actual usage/pricing once known.
            </p>
          ) : null}
        </div>
      </div>
    </section>
  )
}

const AUTOMATION_COPY: Record<Recommendation['automation_type'], { label: string; detail: string; pill: string }> = {
  deterministic: {
    label: 'Deterministic',
    detail: 'Rule-based automation — no AI needed',
    pill: 'bg-emerald-50 text-emerald-950 ring-emerald-200',
  },
  agentic: {
    label: 'Agentic',
    detail: 'AI agent with judgment capabilities',
    pill: 'bg-orange-50 text-orange-950 ring-orange-200',
  },
  hybrid: {
    label: 'Hybrid',
    detail: 'Deterministic core with AI exception handling',
    pill: 'bg-navy-50 text-navy-900 ring-navy-200',
  },
}

const NEXT_ACTION_LABEL: Record<string, string> = {
  collect_evidence: 'Collect Evidence',
  define_integration_contract: 'Define Integration Contract',
  design_apex_automation: 'Design Apex Automation',
  design_flow: 'Design Apex Automation',
  design_metric_view: 'Design Metric View',
  document_policy_fix: 'Document Policy Fix',
  generate_agent: 'Generate Agent',
  no_build: 'No Build',
}

const EFFORT_PILL: Record<string, string> = {
  low: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  medium: 'bg-amber-50 text-amber-800 ring-amber-200',
  high: 'bg-red-50 text-red-800 ring-red-200',
}

function LlmAnalysisBlock({ label, text }: { label: string; text: string | null | undefined }) {
  if (!text) return null
  return (
    <div>
      <h4 className="text-xs font-bold uppercase tracking-wide text-navy-900">{label}</h4>
      <p className="mt-2 text-sm leading-relaxed text-slate-700">{text}</p>
    </div>
  )
}

function EditableCell({
  assumptionKey,
  rawValue,
  displayValue,
  onSave,
  isSaving,
}: {
  assumptionKey: string
  rawValue: unknown
  displayValue: string
  onSave: (key: string, value: number | string) => void
  isSaving: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  const startEdit = useCallback(() => {
    setDraft(typeof rawValue === 'number' ? String(rawValue) : String(rawValue ?? ''))
    setEditing(true)
  }, [rawValue])

  const commit = useCallback(() => {
    setEditing(false)
    const numVal = Number(draft)
    if (typeof rawValue === 'number' && Number.isFinite(numVal)) {
      if (numVal !== rawValue) onSave(assumptionKey, numVal)
    } else if (draft !== String(rawValue ?? '')) {
      onSave(assumptionKey, draft)
    }
  }, [draft, rawValue, assumptionKey, onSave])

  const cancel = useCallback(() => setEditing(false), [])

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <input
          type={typeof rawValue === 'number' ? 'number' : 'text'}
          step="any"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit()
            if (e.key === 'Escape') cancel()
          }}
          autoFocus
          disabled={isSaving}
          className="w-28 rounded border border-navy-300 bg-white px-2 py-1 text-sm tabular-nums text-navy-900 outline-none focus:ring-2 focus:ring-navy-200"
        />
        <button type="button" onClick={commit} disabled={isSaving} className="rounded p-0.5 text-emerald-600 hover:bg-emerald-50">
          <Check className="h-3.5 w-3.5" />
        </button>
        <button type="button" onClick={cancel} className="rounded p-0.5 text-slate-400 hover:bg-slate-100">
          <X className="h-3.5 w-3.5" />
        </button>
      </span>
    )
  }

  return (
    <span className="group inline-flex items-center gap-1.5">
      <span className="tabular-nums text-slate-800">{displayValue}</span>
      <button
        type="button"
        onClick={startEdit}
        className="rounded p-0.5 text-slate-300 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-slate-100 hover:text-slate-600"
        title="Edit value"
      >
        <Pencil className="h-3 w-3" />
      </button>
    </span>
  )
}

function OverviewTab({ rec, analysis }: { rec: Recommendation; analysis: Record<string, unknown> }) {
  const scenarios = parseValueChartScenarios(rec.scenarios_json ?? {})
  const linkedCount = Array.isArray(rec.linked_process_ids) ? rec.linked_process_ids.length : 0
  const actions = rec.actions_json ?? []

  return (
    <div className="space-y-6">
      {rec.agent_fit_summary ? (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h4 className="text-xs font-bold uppercase tracking-wide text-navy-900">Portfolio fit</h4>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{rec.agent_fit_summary}</p>
          {rec.evidence_summary ? (
            <p className="mt-2 text-xs leading-relaxed text-slate-500">{rec.evidence_summary}</p>
          ) : null}
        </section>
      ) : null}
      <LlmAnalysisBlock label="Current state" text={analysis.current_state as string} />
      <LlmAnalysisBlock label="Automation approach" text={analysis.automation_approach as string} />
      <LlmAnalysisBlock label="Executive summary" text={analysis.executive_summary as string} />
      <LlmAnalysisBlock label="Risks & dependencies" text={analysis.risks as string} />

      {!analysis.current_state && rec.llm_rationale ? (
        <div>
          <h4 className="text-xs font-bold uppercase tracking-wide text-navy-900">Assessment</h4>
          <blockquote className="mt-2 rounded-lg bg-slate-50 px-4 py-3 text-sm italic leading-relaxed text-slate-700 ring-1 ring-slate-200/80">
            {rec.llm_rationale}
          </blockquote>
        </div>
      ) : null}

      {rec.description && !analysis.executive_summary ? (
        <div>
          <h4 className="text-xs font-bold uppercase tracking-wide text-navy-900">Description</h4>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{rec.description}</p>
        </div>
      ) : null}

      {actions.length > 0 ? (
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h4 className="text-xs font-bold uppercase tracking-wide text-navy-900">Implementation steps</h4>
          <ol className="mt-3 space-y-2.5">
            {actions.map((a) => (
              <li key={a.step} className="flex items-start gap-3 text-sm">
                <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-navy-100 text-xs font-bold text-navy-700">
                  {a.step}
                </span>
                <span className="flex-1 text-slate-700">{a.action}</span>
                <span
                  className={clsx(
                    'flex-shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ring-1 ring-inset',
                    EFFORT_PILL[a.effort?.toLowerCase()] ?? 'bg-slate-50 text-slate-600 ring-slate-200',
                  )}
                >
                  {a.effort || '—'}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h4 className="text-xs font-bold uppercase tracking-wide text-navy-900">Projected value delivered</h4>
        <p className="mt-1 text-xs text-slate-500">Cumulative savings projected by scenario over 5 years.</p>
        <div className="mt-4">
          <ValueChart scenarios={scenarios} height={260} />
        </div>
      </section>

      {linkedCount > 0 ? (
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <GitBranch className="h-4 w-4 shrink-0 text-navy-500" aria-hidden />
          <span>
            Linked to <span className="font-semibold text-navy-900">{linkedCount}</span> process
            {linkedCount === 1 ? '' : 'es'}
          </span>
        </div>
      ) : null}
    </div>
  )
}

function AssumptionsTab({ rec }: { rec: Recommendation }) {
  const recalcMutation = useRecalculateRecommendation()
  const rows = useMemo(() => assumptionTableRows(rec), [rec])

  const handleSave = useCallback(
    (key: string, value: number | string) => {
      recalcMutation.mutate({ id: rec.id, overrides: { [key]: value } })
    },
    [rec.id, recalcMutation],
  )

  if (rows.length === 0) {
    return <p className="py-6 text-sm text-slate-500">No assumption parameters recorded for this recommendation.</p>
  }

  return (
    <>
      <InvestmentSummary rec={rec} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs font-bold uppercase tracking-wide text-slate-500">
              <th className="py-2.5 pr-4 font-semibold">Parameter</th>
              <th className="py-2.5 pr-4 font-semibold">Value</th>
              <th className="py-2.5 font-semibold">Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-b border-slate-100 last:border-0">
                <td className="py-3 pr-4 font-medium text-navy-900">{humanizeKey(row.key)}</td>
                <td className="py-3 pr-4">
                  {row.editable ? (
                    <EditableCell
                      assumptionKey={row.key}
                      rawValue={row.rawValue}
                      displayValue={row.displayValue}
                      onSave={handleSave}
                      isSaving={recalcMutation.isPending}
                    />
                  ) : (
                    <span className="tabular-nums text-slate-800">{row.displayValue}</span>
                  )}
                </td>
                <td className="py-3">
                  <span
                    className={clsx(
                      'inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset',
                      row.isOverride ?
                        'bg-orange-50 text-orange-900 ring-orange-200'
                      : 'bg-slate-100 text-slate-700 ring-slate-200',
                    )}
                  >
                    {row.isOverride ? 'User override' : 'Auto-estimated'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function ScoringTab({ rec }: { rec: Recommendation }) {
  const signals = extractSignals(rec)
  return (
    <ScoringBreakdown
      arcScore={rec.arc_score_json}
      signals={signals}
      baseScore={rec.base_score ?? 0}
      llmScore={rec.llm_score}
      compositeScore={rec.composite_score}
      divergenceFlag={rec.score_divergence_flag}
    />
  )
}

export function RecommendationDetail({ rec, onStatusChange }: RecommendationDetailProps) {
  const openContextualChat = useChatStore((s) => s.openContextualChat)
  const navigate = useNavigate()
  const generateAgent = useGenerateAgentFromRecommendation()
  const [tab, setTab] = useState<DetailTab>('overview')
  const auto = AUTOMATION_COPY[rec.automation_type] ?? AUTOMATION_COPY.hybrid
  const canGenerateAgent = Boolean(rec.generate_agent_allowed)
  const nextActionLabel = NEXT_ACTION_LABEL[rec.recommended_next_action] ?? 'Collect Evidence'
  const generateAgentLabel =
    generateAgent.isPending ? 'Generating...'
    : canGenerateAgent ? 'Generate Agent'
    : nextActionLabel

  const analysis: Record<string, unknown> = useMemo(() => {
    return rec.impact_json && typeof rec.impact_json === 'object' ? rec.impact_json : {}
  }, [rec])

  return (
    <div className="mt-4 rounded-2xl border border-slate-200/80 bg-slate-50/80 shadow-inner ring-1 ring-slate-900/5">
      {/* Header: automation type + action buttons */}
      <div className="flex flex-col gap-3 border-b border-slate-200/80 px-6 pt-5 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span
            className={clsx(
              'inline-flex items-center rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ring-1 ring-inset',
              auto.pill,
            )}
          >
            {auto.label}
          </span>
          <span className="text-xs text-slate-500">{auto.detail}</span>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => openContextualChat({ type: 'recommendation', id: rec.id })}
            className="inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-navy-900"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Refine
          </button>
          {rec.status === 'active' && (
            <>
              <button
                type="button"
                onClick={() => onStatusChange(rec.id, 'accepted')}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
              >
                <Check className="h-3.5 w-3.5" />
                Accept
              </button>
              <button
                type="button"
                onClick={() => onStatusChange(rec.id, 'dismissed')}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
              >
                Dismiss
              </button>
            </>
          )}
          {rec.status === 'accepted' && (
            <>
              <button
                type="button"
                onClick={() => onStatusChange(rec.id, 'active')}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
              >
                <Undo2 className="h-3.5 w-3.5" />
                Unaccept
              </button>
              <button
                type="button"
                onClick={() => onStatusChange(rec.id, 'implemented')}
                className="inline-flex items-center gap-1.5 rounded-lg bg-navy-700 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-navy-800"
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Mark Implemented
              </button>
            </>
          )}
          <button
            type="button"
            disabled={!canGenerateAgent || generateAgent.isPending}
            onClick={() => {
              generateAgent.mutate(rec.id, {
                onSuccess: (run) => navigate(`/agent-builder/${run.id}`),
              })
            }}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold shadow-sm',
              canGenerateAgent
                ? 'border border-orange-300 bg-orange-50 text-orange-900 hover:bg-orange-100'
                : 'border border-dashed border-slate-300 bg-slate-50 text-slate-500',
              'disabled:cursor-not-allowed disabled:opacity-70',
            )}
          >
            <Sparkles className="h-3.5 w-3.5" />
            {generateAgentLabel}
          </button>
        </div>
      </div>

      {!canGenerateAgent ? (
        <div className="border-b border-slate-200/80 bg-slate-100 px-6 py-2.5 text-xs text-slate-700">
          <span className="font-semibold text-navy-900">Agent Builder is not the next step.</span>{' '}
          {rec.generate_agent_disabled_reason || rec.agent_fit_summary || 'Arcflare needs stronger upstream evidence before an agent design can be generated.'}
          {rec.evidence_summary ? <span className="ml-1 text-slate-500">Evidence: {rec.evidence_summary}.</span> : null}
        </div>
      ) : null}

      {/* Tab bar */}
      <div className="flex gap-0 border-b border-slate-200/80 px-6" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'relative px-4 py-3 text-sm font-semibold transition-colors',
              tab === t.key
                ? 'text-navy-900 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-navy-800'
                : 'text-slate-500 hover:text-slate-700',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-6">
        {tab === 'overview' && <OverviewTab rec={rec} analysis={analysis} />}
        {tab === 'assumptions' && <AssumptionsTab rec={rec} />}
        {tab === 'scoring' && <ScoringTab rec={rec} />}
      </div>
    </div>
  )
}
