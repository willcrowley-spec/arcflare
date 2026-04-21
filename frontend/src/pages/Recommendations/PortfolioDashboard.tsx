import { useMemo, type ReactNode } from 'react'
import clsx from 'clsx'
import { BarChart3 } from 'lucide-react'
import { ValueChart, type ValueChartScenarios } from './ValueChart'
import type { UsePortfolioReturn } from './usePortfolio'

const currencyFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

export interface PortfolioDashboardProps {
  portfolio: UsePortfolioReturn
}

function toChartScenarios(projections: NonNullable<UsePortfolioReturn['projections']>): ValueChartScenarios {
  return {
    optimistic: {
      cumulative: projections.optimistic.cumulative,
      cumulative_benefit: projections.optimistic.cumulative_benefit,
      hard_savings: projections.optimistic.hard_savings,
      soft_savings: projections.optimistic.soft_savings,
    },
    expected: {
      cumulative: projections.expected.cumulative,
      cumulative_benefit: projections.expected.cumulative_benefit,
      hard_savings: projections.expected.hard_savings,
      soft_savings: projections.expected.soft_savings,
    },
    conservative: {
      cumulative: projections.conservative.cumulative,
      cumulative_benefit: projections.conservative.cumulative_benefit,
      hard_savings: projections.conservative.hard_savings,
      soft_savings: projections.conservative.soft_savings,
    },
  }
}

function KpiCard({
  label,
  children,
  className,
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={clsx(
        'rounded-xl bg-white/5 p-4 ring-1 ring-white/10',
        className,
      )}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-200">{label}</p>
      <div className="mt-2">{children}</div>
    </div>
  )
}

const TYPE_ORDER = ['deterministic', 'agentic', 'hybrid'] as const

export function PortfolioDashboard({ portfolio }: PortfolioDashboardProps) {
  const { projections, isLoading, selectedIds, listTotal } = portfolio
  const chartScenarios = useMemo(
    () => (projections ? toChartScenarios(projections) : null),
    [projections],
  )

  const npvExpected = projections?.npv.expected
  const headcountY5 = projections?.expected.headcount_deflection?.[4]
  const paybackExpected = projections?.payback_month.expected

  const byType = projections?.by_automation_type

  const noneSelected = selectedIds.size === 0

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-navy-800 p-6 text-white shadow-md ring-1 ring-black/10">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <BarChart3 className="mt-0.5 h-7 w-7 shrink-0 text-orange-300" aria-hidden />
          <div>
            <h2 className="text-lg font-semibold">Portfolio value</h2>
            <p className="mt-1 text-sm text-slate-200">
              Aggregate 5-year projections for your selection — scenarios reflect optimistic, expected, and conservative
              assumptions.
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-slate-300">3-scenario projection</span>
        </div>
      </div>

      {noneSelected ? (
        <p className="mt-6 rounded-xl border border-dashed border-white/20 bg-white/5 px-4 py-6 text-center text-sm text-slate-300">
          Select recommendations below to see aggregate projections
        </p>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <div className="rounded-xl bg-white p-4 ring-1 ring-slate-200/80">
              {isLoading ? (
                <div className="flex min-h-[320px] items-center justify-center text-sm font-medium text-slate-500">
                  Loading projections…
                </div>
              ) : (
                <ValueChart scenarios={chartScenarios} height={320} />
              )}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <KpiCard label="5-Year NPV (expected)">
              <p className="text-2xl font-semibold tabular-nums text-emerald-400">
                {npvExpected != null && Number.isFinite(npvExpected) ? currencyFmt.format(npvExpected) : '—'}
              </p>
            </KpiCard>
            <KpiCard label="Headcount deflection">
              <p className="text-xl font-semibold tabular-nums text-white">
                {headcountY5 != null && Number.isFinite(headcountY5)
                  ? `${headcountY5.toFixed(1)} positions`
                  : '—'}
              </p>
              <p className="mt-1 text-xs text-slate-300">Year 5, expected case</p>
            </KpiCard>
            <KpiCard label="Payback period">
              <p className="text-xl font-semibold tabular-nums text-white">
                {paybackExpected != null && paybackExpected > 0 ? `${paybackExpected} months` : '—'}
              </p>
              <p className="mt-1 text-xs text-slate-300">Expected case</p>
            </KpiCard>
            <KpiCard label="Selected">
              <p className="text-lg font-semibold tabular-nums">
                {selectedIds.size} of {listTotal} recommendations
              </p>
            </KpiCard>
            <KpiCard label="By type">
              <div className="flex flex-wrap gap-2">
                {TYPE_ORDER.map((t) => {
                  const n = byType?.[t] ?? 0
                  const label =
                    t === 'deterministic' ? 'Deterministic' : t === 'agentic' ? 'Agentic' : 'Hybrid'
                  return (
                    <span
                      key={t}
                      className={clsx(
                        'rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ring-1',
                        t === 'deterministic' && 'bg-emerald-500/15 text-emerald-200 ring-emerald-400/40',
                        t === 'agentic' && 'bg-violet-500/15 text-violet-200 ring-violet-400/40',
                        t === 'hybrid' && 'bg-orange-500/15 text-orange-200 ring-orange-400/40',
                      )}
                    >
                      {label} · {n}
                    </span>
                  )
                })}
              </div>
              {!byType ? (
                <p className="mt-2 text-xs text-slate-400">Breakdown appears when the API returns type counts.</p>
              ) : null}
            </KpiCard>
          </div>
        </div>
      )}
    </section>
  )
}
