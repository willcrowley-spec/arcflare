import { useCallback, useMemo, useState } from 'react'
import clsx from 'clsx'
import { Check, CheckCheck, GitBranch, MessageSquare, Pencil, Sparkles, X } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'
import { useRecalculateRecommendation } from '@/hooks/useApi'
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

const SKIP_KEYS = new Set(['overrides', 'source'])

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
    if (!SKIP_KEYS.has(k)) keys.add(k)
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
  const [tab, setTab] = useState<DetailTab>('overview')
  const auto = AUTOMATION_COPY[rec.automation_type] ?? AUTOMATION_COPY.hybrid

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
            <button
              type="button"
              onClick={() => onStatusChange(rec.id, 'implemented')}
              className="inline-flex items-center gap-1.5 rounded-lg bg-navy-700 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-navy-800"
            >
              <CheckCheck className="h-3.5 w-3.5" />
              Mark Implemented
            </button>
          )}
          <button
            type="button"
            disabled
            title="Coming soon"
            className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-500 disabled:cursor-not-allowed disabled:opacity-70"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Generate Agent
          </button>
        </div>
      </div>

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
