import clsx from 'clsx'
import { GitBranch, Sparkles } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'
import { ScoringBreakdown } from '@/pages/Recommendations/ScoringBreakdown'
import { ValueChart, type ValueChartScenarios } from '@/pages/Recommendations/ValueChart'
import type { Recommendation } from '@/pages/Recommendations/RecommendationCard'

export interface RecommendationDetailProps {
  rec: Recommendation
  onStatusChange: (id: string, status: string) => void
}

const FRACTION_KEYS = new Set([
  'efficiency_gain',
  'productivity_dip',
  'change_management_factor',
  'discount_rate',
  'hard_savings_pct',
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
  const out: Partial<ValueChartScenarios> = {}
  for (const k of keys) {
    const s = raw[k]
    if (!s || typeof s !== 'object' || Array.isArray(s)) return null
    const o = s as Record<string, unknown>
    if (!Array.isArray(o.cumulative)) return null
    out[k] = {
      cumulative: o.cumulative.map((x) => Number(x)),
      hard_savings: Array.isArray(o.hard_savings) ? o.hard_savings.map((x) => Number(x)) : [],
      soft_savings: Array.isArray(o.soft_savings) ? o.soft_savings.map((x) => Number(x)) : [],
    }
  }
  return out as ValueChartScenarios
}

function humanizeKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatAssumptionCell(key: string, val: unknown): string {
  if (val == null) return '—'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'string') return val
  if (typeof val === 'number') {
    if (key.includes('cost') || key.includes('investment') || key.includes('spend')) {
      return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val)
    }
    if (FRACTION_KEYS.has(key) || (key.endsWith('_pct') && Math.abs(val) <= 1)) {
      return `${(val * 100).toFixed(1)}%`
    }
    if (key.endsWith('_pct')) {
      return `${val}%`
    }
    return String(val)
  }
  if (Array.isArray(val)) {
    if (val.every((x) => typeof x === 'number')) {
      return val.map((x) => (typeof x === 'number' && x <= 1 && x >= 0 ? `${Math.round(x * 100)}%` : String(x))).join(', ')
    }
    return val.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(', ')
  }
  if (typeof val === 'object') {
    return JSON.stringify(val)
  }
  return String(val)
}

function assumptionTableRows(rec: Recommendation): { key: string; value: string; isOverride: boolean }[] {
  const raw = rec.assumptions_json && typeof rec.assumptions_json === 'object' ? rec.assumptions_json : {}
  const overridesRaw = raw.overrides
  const overrides =
    overridesRaw && typeof overridesRaw === 'object' && !Array.isArray(overridesRaw) ?
      (overridesRaw as Record<string, unknown>)
    : {}

  const skip = new Set(['overrides'])
  const keys = new Set<string>()
  for (const k of Object.keys(raw)) {
    if (!skip.has(k)) keys.add(k)
  }
  for (const k of Object.keys(overrides)) {
    keys.add(k)
  }

  return [...keys].sort().map((key) => {
    const effective = key in overrides ? overrides[key] : raw[key]
    return {
      key,
      value: formatAssumptionCell(key, effective),
      isOverride: Object.prototype.hasOwnProperty.call(overrides, key),
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
    pill: 'bg-blue-50 text-blue-950 ring-blue-200',
  },
}

export function RecommendationDetail({ rec, onStatusChange }: RecommendationDetailProps) {
  const openContextualChat = useChatStore((s) => s.openContextualChat)
  const signals = extractSignals(rec)
  const scenarios = parseValueChartScenarios(rec.scenarios_json ?? {})
  const rows = assumptionTableRows(rec)
  const auto = AUTOMATION_COPY[rec.automation_type] ?? AUTOMATION_COPY.hybrid
  const linkedCount = Array.isArray(rec.linked_process_ids) ? rec.linked_process_ids.length : 0

  return (
    <div className="mt-4 space-y-6 rounded-2xl border border-slate-200/80 bg-slate-50/80 p-6 shadow-inner ring-1 ring-slate-900/5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <span
            className={clsx(
              'inline-flex items-center rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ring-1 ring-inset',
              auto.pill,
            )}
          >
            {auto.label} automation
          </span>
          <p className="mt-2 max-w-2xl text-sm text-slate-700">{auto.detail}</p>
        </div>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">Scoring breakdown</h3>
        <div className="mt-4">
          <ScoringBreakdown
            signals={signals}
            baseScore={rec.base_score ?? 0}
            llmScore={rec.llm_score}
            compositeScore={rec.composite_score}
            divergenceFlag={rec.score_divergence_flag}
          />
        </div>
      </section>

      {rec.llm_rationale ?
        <section>
          <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">Assessment narrative</h3>
          <blockquote className="mt-3 border-l-4 border-navy-200 bg-white py-4 pl-4 pr-4 text-sm italic leading-relaxed text-slate-700 shadow-sm ring-1 ring-slate-900/5">
            {rec.llm_rationale}
          </blockquote>
        </section>
      : null}

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">Assumptions</h3>
        {rows.length === 0 ?
          <p className="mt-3 text-sm text-slate-500">No assumption parameters recorded for this recommendation.</p>
        : <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[480px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs font-bold uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-4 font-semibold">Parameter</th>
                  <th className="py-2 pr-4 font-semibold">Value</th>
                  <th className="py-2 font-semibold">Source</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key} className="border-b border-slate-100 last:border-0">
                    <td className="py-3 pr-4 font-medium text-navy-900">{humanizeKey(row.key)}</td>
                    <td className="py-3 pr-4 tabular-nums text-slate-800">{row.value}</td>
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
        }
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">Value projection</h3>
        <p className="mt-1 text-xs text-slate-500">Modeled cumulative savings by scenario (from current assumptions).</p>
        <div className="mt-4">
          <ValueChart scenarios={scenarios} showHardSoftSplit height={280} />
        </div>
      </section>

      <section className="flex items-center gap-2 text-sm text-slate-700">
        <GitBranch className="h-4 w-4 shrink-0 text-navy-600" aria-hidden />
        <span>
          Linked to <span className="font-semibold text-navy-900">{linkedCount}</span> process
          {linkedCount === 1 ? '' : 'es'}
        </span>
      </section>

      <div className="flex flex-wrap gap-3 border-t border-slate-200/80 pt-6">
        <button
          type="button"
          onClick={() => openContextualChat({ type: 'recommendation', id: rec.id })}
          className="inline-flex items-center justify-center rounded-lg bg-navy-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900"
        >
          Refine Assumptions
        </button>
        <button
          type="button"
          onClick={() => onStatusChange(rec.id, 'accepted')}
          className="inline-flex items-center justify-center rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700"
        >
          Accept
        </button>
        <button
          type="button"
          onClick={() => onStatusChange(rec.id, 'dismissed')}
          className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
        >
          Dismiss
        </button>
        <button
          type="button"
          disabled
          title="Coming soon"
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-2.5 text-sm font-semibold text-slate-500 disabled:cursor-not-allowed disabled:opacity-70"
        >
          <Sparkles className="h-4 w-4" aria-hidden />
          Generate Agent
        </button>
      </div>
    </div>
  )
}
