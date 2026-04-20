import {
  Award,
  Briefcase,
  Building,
  ChevronDown,
  ChevronRight,
  Code2,
  ExternalLink,
  FileText,
  Landmark,
  Lightbulb,
  ShieldCheck,
  Target,
  TrendingUp,
  Users,
} from 'lucide-react'
import clsx from 'clsx'
import { type ReactNode, useMemo, useState } from 'react'

type ResearchData = {
  profile_json: Record<string, unknown>
  company_summary?: string | null
  industry?: string | null
  employee_range?: string | null
  revenue_range?: string | null
  completed_at?: string | null
  sources_json?: unknown[]
  facts_json?: unknown[]
}

const card =
  'rounded-xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-900/5'

function SectionHeader({
  icon,
  title,
  subtitle,
  badge,
  open,
  onToggle,
}: {
  icon: ReactNode
  title: string
  subtitle?: string
  badge?: ReactNode
  open: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-start gap-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-500"
    >
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-50 text-slate-500 ring-1 ring-slate-200/80">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-navy-900">{title}</h3>
          {badge}
        </div>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {open ? (
        <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-slate-400" aria-hidden />
      ) : (
        <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-400" aria-hidden />
      )}
    </button>
  )
}

function Chip({ children, color = 'slate' }: { children: ReactNode; color?: string }) {
  const colors: Record<string, string> = {
    slate: 'bg-slate-50 text-slate-700 ring-slate-200/80',
    indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200/80',
    emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200/80',
    amber: 'bg-amber-50 text-amber-700 ring-amber-200/80',
    sky: 'bg-sky-50 text-sky-700 ring-sky-200/80',
  }
  return (
    <span className={clsx('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1', colors[color] || colors.slate)}>
      {children}
    </span>
  )
}

function FactItem({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{label}</span>
      <span className="text-sm text-navy-900">{value}</span>
    </div>
  )
}

function SourceLink({ url, title }: { url?: string; title?: string }) {
  if (!url) return null
  const display = title || new URL(url).hostname
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 hover:underline"
    >
      {display}
      <ExternalLink className="h-2.5 w-2.5" aria-hidden />
    </a>
  )
}

function r(obj: unknown, key: string): unknown {
  if (obj && typeof obj === 'object' && key in obj) return (obj as Record<string, unknown>)[key]
  return undefined
}

function rStr(obj: unknown, key: string): string | null {
  const v = r(obj, key)
  return typeof v === 'string' && v.trim() ? v.trim() : null
}

function rArr(obj: unknown, key: string): unknown[] {
  const v = r(obj, key)
  return Array.isArray(v) ? v : []
}

function rObj(obj: unknown, key: string): Record<string, unknown> | null {
  const v = r(obj, key)
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

export function EnrichmentProfile({ data }: { data: Record<string, unknown> }) {
  const research = data as unknown as ResearchData
  const p = research.profile_json ?? {}

  const overview = rObj(p, 'overview')
  const sizeAndScale = rObj(p, 'size_and_scale')
  const icp = rObj(p, 'ideal_customer_profile')
  const financialDrivers = rObj(p, 'financial_drivers')
  const products = rArr(p, 'products_and_services')
  const techStack = rObj(p, 'technology_stack')
  const structure = rObj(p, 'corporate_structure')
  const market = rObj(p, 'market_presence')
  const meta = rObj(p, 'research_metadata')
  const companySummary = rStr(p, 'company_summary') || research.company_summary

  const [openSections, setOpenSections] = useState<Set<string>>(new Set(['overview', 'icp']))
  const toggle = (id: string) =>
    setOpenSections((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const verifiedCount = useMemo(() => {
    const facts = research.facts_json ?? []
    return facts.filter((f: unknown) => rStr(f, 'verification_status') === 'confirmed').length
  }, [research.facts_json])

  const completedAt = research.completed_at
    ? new Date(research.completed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    : null

  const hasContent = companySummary || (icp && Object.keys(icp).length > 0)
  if (!hasContent) return null

  const icpSegments = rArr(icp, 'segments').filter((s): s is string => typeof s === 'string')
  const icpPersonas = rArr(icp, 'buyer_personas').filter((s): s is string => typeof s === 'string')
  const icpValueProps = rArr(icp, 'value_propositions').filter((s): s is string => typeof s === 'string')
  const icpPositioning = rStr(icp, 'competitive_positioning')

  const techMentioned = rArr(techStack, 'mentioned_technologies').filter((s): s is string => typeof s === 'string')
  const techIntegrations = rArr(techStack, 'integrations').filter((s): s is string => typeof s === 'string')

  const structExecs = rArr(structure, 'key_executives')
  const structDepts = rArr(structure, 'departments_mentioned').filter((s): s is string => typeof s === 'string')
  const structSubs = rArr(structure, 'subsidiaries').filter((s): s is string => typeof s === 'string')
  const structParent = rStr(structure, 'parent_company')

  const pressItems = rArr(market, 'press_mentions')
  const awards = rArr(market, 'awards_recognition').filter((s): s is string => typeof s === 'string')
  const socialProfiles = rObj(market, 'social_profiles')

  const growthSignals = rArr(sizeAndScale, 'growth_signals').filter((s): s is string => typeof s === 'string')

  const finGrowthIndicators = rArr(financialDrivers, 'growth_indicators').filter((s): s is string => typeof s === 'string')
  const finRevenueDrivers = rArr(financialDrivers, 'revenue_drivers').filter((s): s is string => typeof s === 'string')

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-navy-900">Organization Intelligence</h2>
          <p className="text-sm text-slate-600">
            AI-researched profile built from {meta ? `${r(meta, 'pages_analyzed')} pages, ${r(meta, 'facts_extracted')} facts extracted, ${verifiedCount} verified` : 'web research'}.
          </p>
        </div>
        {completedAt && (
          <span className="text-xs text-slate-400">Researched {completedAt}</span>
        )}
      </div>

      <div className={clsx(card, 'divide-y divide-slate-100')}>
        {/* Company Overview */}
        <div className="p-5">
          <SectionHeader
            icon={<Building className="h-4 w-4" aria-hidden />}
            title="Company Overview"
            open={openSections.has('overview')}
            onToggle={() => toggle('overview')}
          />
          {openSections.has('overview') && (
            <div className="mt-4 space-y-4 pl-11">
              {companySummary && (
                <div className="prose prose-sm prose-slate max-w-none">
                  {companySummary.split('\n').filter(Boolean).map((para, i) => (
                    <p key={i}>{para}</p>
                  ))}
                </div>
              )}
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <FactItem label="Industry" value={rStr(overview, 'industry')} />
                <FactItem label="Founded" value={rStr(overview, 'founded')} />
                <FactItem label="Headquarters" value={rStr(overview, 'headquarters')} />
                <FactItem label="Employees" value={research.employee_range || rStr(sizeAndScale, 'employee_range')} />
                <FactItem label="Revenue" value={research.revenue_range || rStr(sizeAndScale, 'revenue_range')} />
                <FactItem label="Funding" value={rStr(sizeAndScale, 'total_funding')} />
              </div>
              {growthSignals.length > 0 && (
                <div className="space-y-1.5">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Growth signals</span>
                  <div className="flex flex-wrap gap-1.5">
                    {growthSignals.map((s, i) => <Chip key={i} color="emerald">{s}</Chip>)}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Ideal Customer Profile */}
        {(icpSegments.length > 0 || icpPersonas.length > 0 || icpValueProps.length > 0 || icpPositioning) && (
          <div className="p-5">
            <SectionHeader
              icon={<Target className="h-4 w-4" aria-hidden />}
              title="Ideal Customer Profile"
              subtitle="Who they sell to and how they differentiate"
              open={openSections.has('icp')}
              onToggle={() => toggle('icp')}
            />
            {openSections.has('icp') && (
              <div className="mt-4 space-y-4 pl-11">
                {icpSegments.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Target segments</span>
                    <div className="flex flex-wrap gap-1.5">
                      {icpSegments.map((s, i) => <Chip key={i} color="indigo">{s}</Chip>)}
                    </div>
                  </div>
                )}
                {icpPersonas.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Buyer personas</span>
                    <div className="flex flex-wrap gap-1.5">
                      {icpPersonas.map((s, i) => <Chip key={i} color="sky">{s}</Chip>)}
                    </div>
                  </div>
                )}
                {icpValueProps.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Value propositions</span>
                    <ul className="space-y-1 text-sm text-navy-900">
                      {icpValueProps.map((v, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden />
                          {v}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {icpPositioning && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Competitive positioning</span>
                    <p className="text-sm text-navy-900">{icpPositioning}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Financial Drivers */}
        {financialDrivers && (
          <div className="p-5">
            <SectionHeader
              icon={<TrendingUp className="h-4 w-4" aria-hidden />}
              title="Financial Drivers"
              badge={
                rStr(financialDrivers, 'is_speculative') !== null || (financialDrivers as Record<string, unknown>).is_speculative === true
                  ? <Chip color="amber">Speculative</Chip>
                  : undefined
              }
              open={openSections.has('financial')}
              onToggle={() => toggle('financial')}
            />
            {openSections.has('financial') && (
              <div className="mt-4 space-y-4 pl-11">
                <div className="grid gap-4 sm:grid-cols-2">
                  <FactItem label="Business model" value={rStr(financialDrivers, 'business_model')} />
                  <FactItem label="Pricing model" value={rStr(financialDrivers, 'pricing_model')} />
                </div>
                {finGrowthIndicators.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Growth indicators</span>
                    <ul className="space-y-1 text-sm text-navy-900">
                      {finGrowthIndicators.map((g, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <TrendingUp className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden />
                          {g}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {finRevenueDrivers.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Revenue drivers</span>
                    <ul className="space-y-1 text-sm text-navy-900">
                      {finRevenueDrivers.map((d, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <Landmark className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-500" aria-hidden />
                          {d}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Products & Services */}
        {products.length > 0 && (
          <div className="p-5">
            <SectionHeader
              icon={<Briefcase className="h-4 w-4" aria-hidden />}
              title="Products & Services"
              subtitle={`${products.length} identified`}
              open={openSections.has('products')}
              onToggle={() => toggle('products')}
            />
            {openSections.has('products') && (
              <div className="mt-4 pl-11">
                <div className="grid gap-3 sm:grid-cols-2">
                  {products.map((prod, i) => {
                    const name = rStr(prod, 'name')
                    const desc = rStr(prod, 'description')
                    const sources = rArr(prod, 'sources')
                    return (
                      <div key={i} className="rounded-lg border border-slate-100 bg-slate-50/50 px-4 py-3">
                        {name && <p className="text-sm font-medium text-navy-900">{name}</p>}
                        {desc && desc !== name && <p className="mt-0.5 text-xs text-slate-600">{desc}</p>}
                        {sources.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-2">
                            {sources.map((s, j) => <SourceLink key={j} url={rStr(s, 'url') ?? undefined} />)}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Technology Stack */}
        {(techMentioned.length > 0 || techIntegrations.length > 0) && (
          <div className="p-5">
            <SectionHeader
              icon={<Code2 className="h-4 w-4" aria-hidden />}
              title="Technology Stack"
              subtitle={`${techMentioned.length} technologies, ${techIntegrations.length} integrations`}
              open={openSections.has('tech')}
              onToggle={() => toggle('tech')}
            />
            {openSections.has('tech') && (
              <div className="mt-4 space-y-4 pl-11">
                {techMentioned.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Mentioned technologies</span>
                    <div className="flex flex-wrap gap-1.5">
                      {techMentioned.map((t, i) => <Chip key={i} color="sky">{t}</Chip>)}
                    </div>
                  </div>
                )}
                {techIntegrations.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Integrations</span>
                    <div className="flex flex-wrap gap-1.5">
                      {techIntegrations.map((t, i) => <Chip key={i}>{t}</Chip>)}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Corporate Structure */}
        {(structExecs.length > 0 || structDepts.length > 0 || structSubs.length > 0 || structParent) && (
          <div className="p-5">
            <SectionHeader
              icon={<Users className="h-4 w-4" aria-hidden />}
              title="Corporate Structure"
              open={openSections.has('structure')}
              onToggle={() => toggle('structure')}
            />
            {openSections.has('structure') && (
              <div className="mt-4 space-y-4 pl-11">
                {structParent && <FactItem label="Parent company" value={structParent} />}
                {structExecs.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Key executives</span>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {structExecs.map((exec, i) => {
                        const name = rStr(exec, 'name')
                        const source = rStr(exec, 'source')
                        if (!name) return null
                        return (
                          <div key={i} className="flex items-center gap-2 text-sm text-navy-900">
                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[10px] font-bold text-slate-500">
                              {name.charAt(0).toUpperCase()}
                            </span>
                            <span className="min-w-0 truncate">{name}</span>
                            {source && <SourceLink url={source} title="" />}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
                {structSubs.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Subsidiaries / acquisitions</span>
                    <div className="flex flex-wrap gap-1.5">
                      {structSubs.map((s, i) => <Chip key={i}>{s}</Chip>)}
                    </div>
                  </div>
                )}
                {structDepts.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Departments</span>
                    <div className="flex flex-wrap gap-1.5">
                      {structDepts.map((d, i) => <Chip key={i}>{d}</Chip>)}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Market Presence */}
        {(pressItems.length > 0 || awards.length > 0 || (socialProfiles && Object.keys(socialProfiles).length > 0)) && (
          <div className="p-5">
            <SectionHeader
              icon={<Award className="h-4 w-4" aria-hidden />}
              title="Market Presence"
              open={openSections.has('market')}
              onToggle={() => toggle('market')}
            />
            {openSections.has('market') && (
              <div className="mt-4 space-y-4 pl-11">
                {socialProfiles && Object.keys(socialProfiles).length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Social profiles</span>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(socialProfiles).map(([platform, url]) =>
                        typeof url === 'string' ? (
                          <a
                            key={platform}
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded-full bg-slate-50 px-2.5 py-1 text-xs font-medium text-navy-800 ring-1 ring-slate-200/80 hover:bg-indigo-50 hover:text-indigo-700"
                          >
                            {platform}
                            <ExternalLink className="h-2.5 w-2.5" aria-hidden />
                          </a>
                        ) : null,
                      )}
                    </div>
                  </div>
                )}
                {awards.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Awards & recognition</span>
                    <ul className="space-y-1 text-sm text-navy-900">
                      {awards.map((a, i) => (
                        <li key={i} className="flex items-start gap-2">
                          <Award className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" aria-hidden />
                          {a}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {pressItems.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Press mentions</span>
                    <ul className="space-y-1.5">
                      {pressItems.map((item, i) => {
                        const title = rStr(item, 'title')
                        const url = rStr(item, 'url')
                        if (!title) return null
                        return (
                          <li key={i} className="flex items-start gap-2 text-sm text-navy-900">
                            <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden />
                            <span>
                              {title}
                              {url && (
                                <span className="ml-1.5">
                                  <SourceLink url={url} title="source" />
                                </span>
                              )}
                            </span>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Research Metadata footer */}
        {meta && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-[11px] text-slate-400">
            <span className="inline-flex items-center gap-1">
              <ShieldCheck className="h-3 w-3" aria-hidden />
              {String(r(meta, 'facts_verified') ?? 0)} confirmed facts
            </span>
            <span>{String(r(meta, 'total_sources') ?? 0)} sources</span>
            <span>{String(r(meta, 'pages_analyzed') ?? 0)} pages crawled</span>
            <span>{String(r(meta, 'search_results_found') ?? 0)} search results</span>
            {String(r(meta, 'verification_rate') ?? '') && (
              <span>
                {(Number(r(meta, 'verification_rate')) * 100).toFixed(0)}% verification rate
              </span>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
