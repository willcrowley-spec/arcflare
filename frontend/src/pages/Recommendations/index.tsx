import { useMemo, useState } from 'react'
import { Layers, Radar, Shield, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import { SearchBar } from '@/components/SearchBar'

const featured = {
  title: 'Deploy Lead Enrichment & Scoring Agent',
  desc: 'Orchestrate enrichment and scoring with governed field alignment across HubSpot and Salesforce, eliminating duplicate manual review while preserving audit trails.',
  roi: '$428,500',
  inputs: ['Salesforce Metadata', 'HubSpot Records', 'Word Docs (Standards)'],
  actions: [
    'Deploy Sylvanas-01 Agent',
    'Align 14 HubSpot/SFDC Fields',
    'Deprecate Legacy v2 Flows',
  ],
}

const cards = [
  {
    domain: 'REVENUE OPS',
    title: 'Integrate GraphQL Resolvers',
    tags: ['Automation', 'MuleSoft/API Specs'],
    cta: 'Implement',
  },
  {
    domain: 'SENTINEL AGENT',
    title: 'Narrow OAuth Scope',
    tags: ['Security Patch', 'Salesforce', 'Excel'],
    cta: 'Remediate',
  },
  {
    domain: 'GOVERNANCE BOT',
    title: 'Schema Standardization',
    tags: ['Process Change', 'HubSpot', 'PDF'],
    cta: 'Apply Standards',
  },
]

export default function RecommendationsPage() {
  const [tab, setTab] = useState<'ACTIVE' | 'IMPLEMENTED'>('ACTIVE')
  const [q, setQ] = useState('')

  const filteredCards = useMemo(() => {
    if (!q.trim()) return cards
    const qq = q.toLowerCase()
    return cards.filter((c) => c.title.toLowerCase().includes(qq) || c.domain.toLowerCase().includes(qq))
  }, [q])

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Recommendations</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Prioritized remediation and automation opportunities ranked by ROI, blast radius, and architectural fit.
        </p>
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-md ring-1 ring-slate-900/5">
        <div className="border-b border-slate-100 bg-gradient-to-r from-white to-slate-50 px-6 py-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-red-50 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-red-800 ring-1 ring-red-200">
              Critical path
            </span>
            <span className="rounded-full bg-navy-50 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-navy-800 ring-1 ring-navy-200">
              Lead management
            </span>
            <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-orange-50 px-3 py-1 text-[11px] font-bold uppercase tracking-wide text-orange-900 ring-1 ring-orange-200">
              <Sparkles className="h-3.5 w-3.5" />
              Top agent strategy
            </span>
          </div>
          <h2 className="mt-4 text-2xl font-semibold tracking-tight text-navy-900">{featured.title}</h2>
          <p className="mt-3 max-w-4xl text-sm leading-relaxed text-slate-600">{featured.desc}</p>
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-900">Estimated ROI</p>
              <p className="mt-2 text-3xl font-semibold text-emerald-900">{featured.roi}/yr</p>
              <p className="mt-1 text-xs text-emerald-800/90">Modeled from reclaimed hours + error reduction</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Analysis inputs</p>
              <ul className="mt-3 space-y-2 text-sm text-slate-800">
                {featured.inputs.map((i) => (
                  <li key={i} className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-navy-600" />
                    {i}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Required multi-step action</p>
              <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-800">
                {featured.actions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ol>
            </div>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-lg bg-navy-800 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900"
            >
              Initialize Deployment
            </button>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50"
            >
              Analysis Details
            </button>
          </div>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4 rounded-2xl border border-slate-200/80 bg-navy-800 p-6 text-white shadow-md ring-1 ring-black/10">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold">Multi-system impact</h2>
              <p className="mt-1 text-sm text-slate-200">Projected lift when the recommendation set is fully implemented</p>
            </div>
            <Radar className="h-7 w-7 text-orange-300" />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <ImpactStat label="Agent coverage" value="64.2%" hint="Of tier-1 workflows" />
            <ImpactStat label="Data consistency gain" value="+18.4%" hint="Cross-system keys aligned" />
            <ImpactStat label="Manual hours reclaimed" value="1,240/mo" hint="Across GTM ops" />
          </div>
          <button
            type="button"
            className="mt-2 inline-flex w-full items-center justify-center rounded-lg bg-white/10 px-4 py-2.5 text-sm font-semibold text-white ring-1 ring-white/15 hover:bg-white/15 sm:w-auto"
          >
            Review Full Audit
          </button>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-navy-700" />
            <h2 className="text-lg font-semibold text-navy-900">Architecture health</h2>
          </div>
          <div className="mt-5 space-y-5">
            <HealthBar label="Metadata sync" value={99.4} color="bg-emerald-500" />
            <HealthBar label="Process optimization" value={78} color="bg-amber-400" />
          </div>
          <p className="mt-4 text-xs text-slate-500">
            Health scores combine drift detection, test coverage signals, and operational SLO adherence.
          </p>
        </div>
      </section>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          {(['ACTIVE', 'IMPLEMENTED'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={clsx(
                'rounded-full px-4 py-1.5 text-sm font-semibold ring-1 ring-inset transition-colors',
                tab === t ? 'bg-navy-800 text-white ring-navy-800' : 'bg-white text-slate-700 ring-slate-200 hover:bg-slate-50',
              )}
            >
              {t === 'ACTIVE' ? 'Active' : 'Implemented'}
            </button>
          ))}
        </div>
        <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center lg:w-auto">
          <SearchBar
            value={q}
            onChange={setQ}
            placeholder="Search recommendations…"
            className="sm:min-w-[320px]"
          />
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Viewing 1-3 of 9 recommendations
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {filteredCards.map((c) => (
          <article
            key={c.title}
            className="flex flex-col rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm ring-1 ring-slate-900/5"
          >
            <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{c.domain}</p>
            <h3 className="mt-2 text-lg font-semibold text-navy-900">{c.title}</h3>
            <div className="mt-4 flex flex-wrap gap-2">
              {c.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-slate-50 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200/80"
                >
                  {t}
                </span>
              ))}
            </div>
            <div className="mt-auto pt-6">
              <button
                type="button"
                className="w-full rounded-lg bg-navy-800 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-navy-900"
              >
                {c.cta}
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function ImpactStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
      <p className="text-xs uppercase tracking-wide text-slate-200">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      <p className="mt-1 text-xs text-slate-300">{hint}</p>
    </div>
  )
}

function HealthBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="font-semibold text-navy-900">{value}%</span>
      </div>
      <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-slate-100 ring-1 ring-slate-200/80">
        <div className={clsx('h-full rounded-full', color)} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}
