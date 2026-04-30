import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Building2,
  CheckCircle2,
  Cloud,
  Database,
  FileSpreadsheet,
  Globe,
  Layers,
  Loader2,
  Map as MapIcon,
  Plus,
  Plug,
  Search,
  Users,
  Wrench,
  X,
  XCircle,
} from 'lucide-react'
import clsx from 'clsx'
import { useConnections, useModelCatalog, useOrgProfile, useOrgSettings, useProcessMapSettings, useReanalyze, useResearchLatest, useResearchStatus, useStartResearch, useUpdateOrgProfile, useUpdateOrgSettings, useUpdateProcessMapSettings } from '@/hooks/useApi'
import { EnrichmentProfile } from '@/components/EnrichmentProfile'
import { PromptsSection } from '@/components/PromptEditor/PromptsSection'
import { StatusBadge } from '@/components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import type { AnalysisConfig, ModelCatalog, ModelOperation, PlatformConnection } from '@/types'

type OrgProfileData = {
  name?: string
  plan_tier?: string
  settings_json?: Record<string, unknown>
}

const cardClass =
  'rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5'

function platformTypeToLabel(raw: string | undefined): string {
  const u = (raw ?? '').toUpperCase()
  const labels: Record<string, string> = {
    SALESFORCE: 'Salesforce',
    HUBSPOT: 'HubSpot',
    NETSUITE: 'NetSuite',
    MULESOFT: 'MuleSoft',
    CONFLUENCE: 'Confluence',
    CUSTOM: 'Custom',
  }
  return labels[u] ?? (raw ? raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase() : 'Platform')
}

function platformTypeToIcon(raw: string | undefined) {
  const u = (raw ?? '').toUpperCase()
  const map: Record<string, typeof Cloud> = {
    SALESFORCE: Cloud,
    HUBSPOT: Users,
    NETSUITE: Database,
    MULESOFT: Layers,
    CONFLUENCE: FileSpreadsheet,
    CUSTOM: Wrench,
  }
  return map[u] ?? Plug
}

function connectionBadgeStatus(status: string): string {
  const k = status.toLowerCase()
  const map: Record<string, string> = {
    connected: 'CONNECTED',
    pending: 'PENDING',
    syncing: 'SYNCING',
    error: 'ERROR',
    disconnected: 'DISCONNECTED',
  }
  return map[k] ?? status.replace(/_/g, ' ').toUpperCase()
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function formatUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

function readNumber(obj: Record<string, unknown> | undefined, keys: string[]): number | undefined {
  if (!obj) return undefined
  for (const k of keys) {
    const v = obj[k]
    if (typeof v === 'number' && !Number.isNaN(v)) return v
    if (typeof v === 'string' && v.trim()) {
      const n = Number(v)
      if (!Number.isNaN(n)) return n
    }
  }
  return undefined
}

function parseProfile(data: unknown): OrgProfileData {
  if (!data || typeof data !== 'object') return {}
  const o = data as Record<string, unknown>
  return {
    name: typeof o.name === 'string' ? o.name : undefined,
    plan_tier: typeof o.plan_tier === 'string' ? o.plan_tier : undefined,
    settings_json: o.settings_json && typeof o.settings_json === 'object' ? (o.settings_json as Record<string, unknown>) : undefined,
  }
}

function readCompanyFromSettings(settings: Record<string, unknown> | undefined) {
  const enrichment = settings?.enrichment && typeof settings.enrichment === 'object'
    ? (settings.enrichment as Record<string, unknown>)
    : undefined
  const company_name = typeof settings?.company_name === 'string' ? settings.company_name : undefined
  const domains = Array.isArray(settings?.domains)
    ? (settings.domains as unknown[]).filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
    : []
  const industry = typeof settings?.industry === 'string' ? settings.industry
    : typeof enrichment?.industry === 'string' ? enrichment.industry : undefined
  const headcount = readNumber(settings, ['headcount', 'estimated_headcount'])
    ?? readNumber(enrichment, ['headcount', 'estimated_headcount'])
  const annual_revenue = readNumber(settings, ['annual_revenue', 'estimated_annual_revenue'])
    ?? readNumber(enrichment, ['annual_revenue', 'estimated_annual_revenue'])
  return { company_name, domains, industry, headcount, annual_revenue }
}

function connectionEstimatedSpend(c: PlatformConnection): number | undefined {
  const cfg = c.sync_config_json
  return readNumber(cfg, ['estimated_annual_spend', 'annual_spend', 'estimated_spend'])
}

function normalizeAnalysisSettings(x: unknown): AnalysisConfig | null {
  if (!x || typeof x !== 'object') return null
  const o = x as Record<string, unknown>
  const velocity = typeof o.velocity_window_days === 'number' ? o.velocity_window_days : 30
  const minVec = typeof o.min_records_for_vectorization === 'number' ? o.min_records_for_vectorization : 1
  return {
    velocity_window_days: velocity,
    min_records_for_vectorization: minVec,
    embedding_provider: typeof o.embedding_provider === 'string' ? o.embedding_provider : 'default',
    vector_store_provider: typeof o.vector_store_provider === 'string' ? o.vector_store_provider : 'default',
    llm_provider: typeof o.llm_provider === 'string' ? o.llm_provider : 'default',
    model_overrides: o.model_overrides && typeof o.model_overrides === 'object' ? (o.model_overrides as Record<string, string>) : {},
  }
}

function ProfileRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="group flex flex-col gap-1 border-b border-slate-100 py-3 last:border-b-0 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <span className="shrink-0 text-sm font-medium text-slate-500">{label}</span>
      <div className="min-w-0 flex-1 text-sm text-navy-900 sm:text-right">{children}</div>
    </div>
  )
}

function AnalysisField({
  id,
  label,
  helpText,
  suffix,
  value,
  onChange,
  onBlur,
  inputMode,
  step,
  disabled,
}: {
  id: string
  label: string
  helpText?: string
  suffix?: string
  value: string
  onChange: (v: string) => void
  onBlur: () => void
  inputMode?: React.HTMLAttributes<HTMLInputElement>['inputMode']
  step?: string
  disabled?: boolean
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-slate-700">
        {label}
      </label>
      {helpText ? <p className="text-xs leading-relaxed text-slate-400">{helpText}</p> : null}
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="number"
          inputMode={inputMode}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          onKeyDown={(e) => {
            if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
          }}
          className={clsx(
            'w-full max-w-xs rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 shadow-sm outline-none transition',
            'ring-slate-900/5 focus:border-navy-400 focus:ring-2 focus:ring-navy-200',
            disabled && 'cursor-not-allowed opacity-60',
          )}
        />
        {suffix ? <span className="text-sm text-slate-500">{suffix}</span> : null}
      </div>
    </div>
  )
}

export default function OrganizationPage() {
  const navigate = useNavigate()
  const profileQuery = useOrgProfile()
  const connectionsQuery = useConnections()
  const settingsQuery = useOrgSettings()
  const updateSettings = useUpdateOrgSettings()
  const reanalyze = useReanalyze()
  const modelCatalogQuery = useModelCatalog()
  const mapSettingsQuery = useProcessMapSettings()
  const updateMapSettings = useUpdateProcessMapSettings()

  const updateProfile = useUpdateOrgProfile()
  const startResearch = useStartResearch()
  const [researchPolling, setResearchPolling] = useState(true)
  const researchStatusQuery = useResearchStatus(researchPolling)
  const researchLatestQuery = useResearchLatest()
  const [reanalyzeBanner, setReanalyzeBanner] = useState<string | null>(null)

  const profile = useMemo(() => parseProfile(profileQuery.data), [profileQuery.data])
  const company = useMemo(() => readCompanyFromSettings(profile.settings_json), [profile.settings_json])

  const displayCompanyName = company.company_name?.trim() || profile.name || '—'
  const displayIndustry = company.industry?.trim() || '—'

  // Domain editing
  const [domainDraft, setDomainDraft] = useState('')
  const domainInputRef = useRef<HTMLInputElement>(null)

  const addDomain = useCallback(() => {
    const raw = domainDraft.trim().replace(/^https?:\/\//, '').replace(/\/+$/, '')
    if (!raw) return
    if (company.domains.includes(raw)) { setDomainDraft(''); return }
    updateProfile.mutate({ domains: [...company.domains, raw] })
    setDomainDraft('')
    domainInputRef.current?.focus()
  }, [domainDraft, company.domains, updateProfile])

  const removeDomain = useCallback((d: string) => {
    updateProfile.mutate({ domains: company.domains.filter((x) => x !== d) })
  }, [company.domains, updateProfile])

  // Research / Enrich
  const researchStatus = researchStatusQuery.data as { status?: string; phase?: string | null; progress?: number; message?: string | null; error?: string | null } | undefined
  const isResearchRunning = researchStatus?.status === 'running'

  useEffect(() => {
    if (researchStatus?.status === 'completed' || researchStatus?.status === 'failed') {
      setResearchPolling(false)
      if (researchStatus.status === 'completed') {
        void researchLatestQuery.refetch()
        void profileQuery.refetch()
      }
    }
  }, [researchStatus?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  const onEnrich = useCallback(() => {
    setResearchPolling(true)
    startResearch.mutate(undefined, {
      onSuccess: () => {
        setResearchPolling(true)
      },
    })
  }, [startResearch])

  const connections = connectionsQuery.data?.items ?? []

  const aggregateSpend = useMemo(() => {
    let sum = 0
    let any = false
    for (const c of connections) {
      const n = connectionEstimatedSpend(c)
      if (n != null) {
        sum += n
        any = true
      }
    }
    return any ? sum : null
  }, [connections])

  const settings = settingsQuery.data
  const analysis = useMemo(() => normalizeAnalysisSettings(settings), [settings])

  const [velocityDraft, setVelocityDraft] = useState('')
  const [minVecDraft, setMinVecDraft] = useState('')

  useEffect(() => {
    if (!analysis) return
    setVelocityDraft(String(analysis.velocity_window_days))
    setMinVecDraft(String(analysis.min_records_for_vectorization))
  }, [analysis])

  const patchSetting = useCallback(
    (payload: Record<string, unknown>) => {
      updateSettings.mutate(payload)
    },
    [updateSettings],
  )

  const saveVelocity = useCallback(() => {
    const n = parseInt(velocityDraft, 10)
    if (Number.isNaN(n) || n < 1) {
      if (analysis) setVelocityDraft(String(analysis.velocity_window_days))
      return
    }
    if (analysis && n === analysis.velocity_window_days) return
    patchSetting({ velocity_window_days: n })
  }, [velocityDraft, analysis, patchSetting])

  const saveMinVec = useCallback(() => {
    const n = parseInt(minVecDraft, 10)
    if (Number.isNaN(n) || n < 0) {
      if (analysis) setMinVecDraft(String(analysis.min_records_for_vectorization))
      return
    }
    if (analysis && n === analysis.min_records_for_vectorization) return
    patchSetting({ min_records_for_vectorization: n })
  }, [minVecDraft, analysis, patchSetting])

  const onReanalyze = () => {
    setReanalyzeBanner(null)
    reanalyze.mutate(undefined, {
      onSuccess: (raw) => {
        const data = raw as { objects_reclassified?: number }
        const count = typeof data.objects_reclassified === 'number' ? data.objects_reclassified : 0
        setReanalyzeBanner(`Complete — ${count} object${count === 1 ? '' : 's'} reclassified`)
        window.setTimeout(() => setReanalyzeBanner(null), 4500)
      },
    })
  }

  const catalog = modelCatalogQuery.data as ModelCatalog | undefined

  const onModelOverrideChange = useCallback(
    (operationId: string, value: string) => {
      const current = analysis?.model_overrides ?? {}
      const next = { ...current }
      if (!value || value === 'default') {
        delete next[operationId]
      } else {
        next[operationId] = value
      }
      patchSetting({ model_overrides: next })
    },
    [analysis, patchSetting],
  )

  const operationsByGroup = useMemo(() => {
    if (!catalog?.operations) return new Map<string, ModelOperation[]>()
    const m = new Map<string, ModelOperation[]>()
    for (const op of catalog.operations) {
      const key = op.group_label || op.group
      if (!m.has(key)) m.set(key, [])
      m.get(key)!.push(op)
    }
    return m
  }, [catalog])

  return (
    <div className="mx-auto max-w-5xl space-y-10 px-4 py-8 sm:px-6 lg:px-8">
      <header>
        <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Organization</h1>
        <p className="mt-1 text-sm text-slate-600">Company intelligence, connected platforms, and analysis configuration.</p>
      </header>

      {/* Section 1: Company profile */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-navy-900">Company profile</h2>
          {isResearchRunning ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200/80 bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-800 ring-1 ring-indigo-900/5">
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              Enriching…
            </span>
          ) : researchStatus?.status === 'completed' ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200/80 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-emerald-900/5">
              <CheckCircle2 className="h-3 w-3" aria-hidden />
              Enriched
            </span>
          ) : researchStatus?.status === 'failed' ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-red-200/80 bg-red-50 px-2.5 py-0.5 text-xs font-medium text-red-800 ring-1 ring-red-900/5">
              <XCircle className="h-3 w-3" aria-hidden />
              Enrichment failed
            </span>
          ) : null}
        </div>
        {profileQuery.isError ? (
          <ErrorState message="Could not load organization profile." />
        ) : profileQuery.isPending ? (
          <div className={cardClass}>
            <LoadingState message="Loading profile…" />
          </div>
        ) : (
          <div className={clsx(cardClass, 'transition-shadow duration-200')}>
            <div className="mb-4 flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-navy-50 text-navy-800 ring-1 ring-navy-900/5">
                <Building2 className="h-5 w-5" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-base font-semibold text-navy-900">{displayCompanyName}</p>
                {profile.plan_tier ? <p className="text-xs text-slate-500">Plan: {profile.plan_tier}</p> : null}
              </div>
            </div>

            <div className="divide-y divide-slate-100 rounded-lg border border-slate-100 bg-slate-50/40 px-4">
              <ProfileRow label="Company name">{displayCompanyName}</ProfileRow>
              <ProfileRow label="Domains / websites">
                <div className="flex flex-col items-end gap-2">
                  {company.domains.length > 0 && (
                    <div className="flex flex-wrap justify-end gap-1.5">
                      {company.domains.map((d) => (
                        <span
                          key={d}
                          className="group/chip inline-flex max-w-full items-center gap-1 truncate rounded-full bg-white px-2.5 py-0.5 text-xs font-medium text-navy-800 ring-1 ring-slate-200/80"
                        >
                          <Globe className="h-3 w-3 shrink-0 text-slate-400" aria-hidden />
                          {d}
                          <button
                            type="button"
                            onClick={() => removeDomain(d)}
                            className="ml-0.5 rounded-full p-0.5 text-red-500 hover:bg-red-50 hover:text-red-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-red-400"
                            aria-label={`Remove ${d}`}
                          >
                            <X className="h-2.5 w-2.5" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}
                  <form
                    className="flex w-full items-center gap-1.5 sm:max-w-sm sm:justify-end"
                    onSubmit={(e) => { e.preventDefault(); addDomain() }}
                  >
                    <input
                      ref={domainInputRef}
                      type="text"
                      value={domainDraft}
                      onChange={(e) => setDomainDraft(e.target.value)}
                      placeholder="acme.com"
                      className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-navy-900 shadow-sm outline-none ring-slate-900/5 transition placeholder:text-slate-400 focus:border-navy-400 focus:ring-2 focus:ring-navy-200"
                    />
                    <button
                      type="submit"
                      disabled={!domainDraft.trim() || updateProfile.isPending}
                      className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-navy-700 px-2.5 py-1.5 text-xs font-medium text-white shadow-sm ring-1 ring-navy-900/10 hover:bg-navy-800 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Plus className="h-3 w-3" aria-hidden />
                      Add
                    </button>
                  </form>
                </div>
              </ProfileRow>
              <ProfileRow label="Industry">{displayIndustry}</ProfileRow>
              <ProfileRow label="Estimated headcount">
                {company.headcount != null ? (
                  <span className="tabular-nums">{new Intl.NumberFormat('en-US').format(company.headcount)}</span>
                ) : (
                  <span className="text-slate-400">—</span>
                )}
              </ProfileRow>
              <ProfileRow label="Estimated annual revenue">
                {company.annual_revenue != null ? (
                  <span className="tabular-nums">{formatUsd(company.annual_revenue)}</span>
                ) : (
                  <span className="text-slate-400">—</span>
                )}
              </ProfileRow>
            </div>

            {/* Enrich / Research section */}
            <div className="mt-5 flex flex-col gap-3 border-t border-slate-100 pt-5">
              {isResearchRunning ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-indigo-700">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    {researchStatus?.message || `Running: ${researchStatus?.phase ?? 'initializing'}…`}
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-all duration-500 ease-out"
                      style={{ width: `${Math.max(2, (researchStatus?.progress ?? 0) * 100)}%` }}
                    />
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={onEnrich}
                    disabled={company.domains.length === 0 || startResearch.isPending}
                    className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm ring-1 ring-indigo-700/10 hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {startResearch.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <Search className="h-4 w-4" aria-hidden />
                    )}
                    Enrich Organization
                  </button>
                  {company.domains.length === 0 && (
                    <p className="text-xs text-slate-500">Add at least one domain to enable enrichment.</p>
                  )}
                  {startResearch.isError && (
                    <p className="text-xs text-red-600">
                      {(startResearch.error as Error)?.message?.includes('409')
                        ? 'Enrichment already running.'
                        : 'Could not start enrichment. Try again.'}
                    </p>
                  )}
                  {researchStatus?.status === 'failed' && researchStatus?.error && (
                    <p className="text-xs text-red-600">{researchStatus.error}</p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* Section 1b: Enrichment Intelligence */}
      {researchLatestQuery.data ? (
        <EnrichmentProfile data={researchLatestQuery.data as Record<string, unknown>} />
      ) : null}

      {/* Section 2: Connected platforms */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Connected platforms</h2>
            <p className="text-sm text-slate-600">Open a platform for licensing, adoption, and technical detail.</p>
          </div>
          <div className="rounded-lg border border-slate-200/80 bg-white px-4 py-2 shadow-sm ring-1 ring-slate-900/5">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Aggregate est. spend</p>
            <p className="text-lg font-bold tabular-nums text-navy-900">{aggregateSpend != null ? formatUsd(aggregateSpend) : '—'}</p>
          </div>
        </div>
        {connectionsQuery.isError ? (
          <ErrorState message="Could not load connections." />
        ) : connectionsQuery.isPending ? (
          <div className={cardClass}>
            <LoadingState message="Loading connections…" />
          </div>
        ) : connections.length === 0 ? (
          <EmptyState
            title="No platforms connected"
            description="Connect a platform to see it here and drill into environment details."
            icon={<Plug className="h-10 w-10" />}
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {connections.map((c) => {
              const rawType = c.platform_type ?? c.platform
              const label = c.label?.trim() || platformTypeToLabel(typeof rawType === 'string' ? rawType : undefined)
              const Icon = platformTypeToIcon(typeof rawType === 'string' ? rawType : undefined)
              const spend = connectionEstimatedSpend(c)
              const badgeStatus = connectionBadgeStatus(String(c.status))
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => navigate(`/platforms/${c.id}`)}
                  className={clsx(
                    cardClass,
                    'cursor-pointer text-left transition',
                    'hover:border-navy-200 hover:shadow-md hover:ring-navy-900/10',
                    'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-500',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-navy-50 text-navy-800">
                        <Icon className="h-4 w-4" aria-hidden />
                      </span>
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-navy-900">{label}</p>
                        <p className="truncate text-xs text-slate-500">{platformTypeToLabel(typeof rawType === 'string' ? rawType : undefined)}</p>
                      </div>
                    </div>
                    <StatusBadge status={badgeStatus} />
                  </div>
                  <dl className="mt-4 space-y-2 text-xs">
                    <div className="flex justify-between gap-2 text-slate-600">
                      <dt>Last sync</dt>
                      <dd className="font-medium text-navy-900">{formatTimestamp(c.last_sync_at)}</dd>
                    </div>
                    <div className="flex justify-between gap-2 text-slate-600">
                      <dt>Est. annual spend</dt>
                      <dd className="font-medium tabular-nums text-navy-900">{spend != null ? formatUsd(spend) : '—'}</dd>
                    </div>
                  </dl>
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* Section 3: Analysis settings */}
      <section className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold text-navy-900">Analysis settings</h2>
          <p className="text-sm text-slate-600">Values apply org-wide. Changes save when you leave a field or press Enter.</p>
        </div>
        {settingsQuery.isError ? (
          <ErrorState message="Could not load analysis settings." />
        ) : settingsQuery.isPending ? (
          <div className={cardClass}>
            <LoadingState message="Loading settings…" />
          </div>
        ) : !analysis ? (
          <ErrorState message="Analysis settings response was invalid." />
        ) : (
          <div className={clsx(cardClass, 'space-y-6')}>
            <div className="grid gap-6 sm:grid-cols-1 md:grid-cols-2">
              <AnalysisField
                id="velocity-window"
                label="Velocity window"
                helpText="Number of days to look back when measuring object modification activity. Higher values smooth out spikes."
                suffix="days"
                value={velocityDraft}
                onChange={setVelocityDraft}
                onBlur={saveVelocity}
                disabled={updateSettings.isPending}
              />
              <AnalysisField
                id="min-vectorization"
                label="Min records for vectorization"
                helpText="Objects with fewer records than this are skipped during vectorization. Set to 0 to vectorize all objects."
                value={minVecDraft}
                onChange={setMinVecDraft}
                onBlur={saveMinVec}
                disabled={updateSettings.isPending}
              />
            </div>
            {updateSettings.isError ? <p className="text-sm text-red-600">Could not save settings. Check values and try again.</p> : null}
            <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
              <button
                type="button"
                onClick={onReanalyze}
                disabled={reanalyze.isPending}
                className="rounded-lg bg-navy-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm ring-1 ring-navy-900/10 hover:bg-navy-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {reanalyze.isPending ? (
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    Re-analyzing…
                  </span>
                ) : (
                  'Re-analyze'
                )}
              </button>
              {reanalyzeBanner ? (
                <span className="text-sm font-medium text-emerald-700 transition-opacity duration-300">{reanalyzeBanner}</span>
              ) : null}
              {reanalyze.isError ? <span className="text-sm text-red-600">Re-analyze failed. Try again.</span> : null}
            </div>
          </div>
        )}
      </section>

      {/* Section: Process Map settings */}
      <section className="space-y-3">
        <div className="flex items-start gap-2">
          <MapIcon className="mt-0.5 h-5 w-5 shrink-0 text-slate-500" aria-hidden />
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Process Map</h2>
            <p className="text-sm text-slate-600">Default layout options for the domain process map.</p>
          </div>
        </div>
        {mapSettingsQuery.isError ? (
          <ErrorState message="Could not load process map settings." />
        ) : mapSettingsQuery.isPending ? (
          <div className={cardClass}>
            <LoadingState message="Loading settings…" />
          </div>
        ) : (
          <div className={clsx(cardClass, 'space-y-6')}>
            <div className="grid gap-6 sm:grid-cols-1 md:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="map-direction" className="text-sm font-medium text-slate-700">
                  Flow direction
                </label>
                <p className="text-xs leading-relaxed text-slate-400">
                  Layout orientation for the process map. Left-to-right or top-to-bottom.
                </p>
                <select
                  id="map-direction"
                  value={mapSettingsQuery.data?.process_map_direction ?? 'TB'}
                  disabled={updateMapSettings.isPending}
                  onChange={(e) =>
                    updateMapSettings.mutate({
                      process_map_direction: e.target.value as 'LR' | 'TB',
                      process_map_default_state: mapSettingsQuery.data?.process_map_default_state ?? 'collapsed',
                    })
                  }
                  className={clsx(
                    'w-full max-w-xs rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 shadow-sm outline-none transition',
                    'ring-slate-900/5 focus:border-navy-400 focus:ring-2 focus:ring-navy-200',
                    updateMapSettings.isPending && 'cursor-not-allowed opacity-60',
                  )}
                >
                  <option value="TB">Top to bottom</option>
                  <option value="LR">Left to right</option>
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="map-default-state" className="text-sm font-medium text-slate-700">
                  Default state
                </label>
                <p className="text-xs leading-relaxed text-slate-400">
                  Whether process containers start expanded or collapsed when opening a domain map.
                </p>
                <select
                  id="map-default-state"
                  value={mapSettingsQuery.data?.process_map_default_state ?? 'collapsed'}
                  disabled={updateMapSettings.isPending}
                  onChange={(e) =>
                    updateMapSettings.mutate({
                      process_map_direction: mapSettingsQuery.data?.process_map_direction ?? 'TB',
                      process_map_default_state: e.target.value as 'expanded' | 'collapsed',
                    })
                  }
                  className={clsx(
                    'w-full max-w-xs rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 shadow-sm outline-none transition',
                    'ring-slate-900/5 focus:border-navy-400 focus:ring-2 focus:ring-navy-200',
                    updateMapSettings.isPending && 'cursor-not-allowed opacity-60',
                  )}
                >
                  <option value="collapsed">Collapsed</option>
                  <option value="expanded">Expanded</option>
                </select>
              </div>
            </div>
            {updateMapSettings.isError ? (
              <p className="text-sm text-red-600">Could not save process map settings.</p>
            ) : null}
          </div>
        )}
      </section>

      {/* Section 4: Model configuration */}
      <section className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold text-navy-900">Model configuration</h2>
          <p className="text-sm text-slate-600">
            Choose which AI model powers each pipeline stage. Defaults come from platform environment settings.
          </p>
        </div>
        {modelCatalogQuery.isError ? (
          <ErrorState message="Could not load model catalog." />
        ) : modelCatalogQuery.isPending || !catalog ? (
          <div className={cardClass}>
            <LoadingState message="Loading models…" />
          </div>
        ) : catalog.providers.length === 0 ? (
          <div className={clsx(cardClass, 'text-sm text-slate-500')}>
            No AI provider API keys are configured. Set at least one provider key (Gemini, Anthropic, or OpenAI) to enable model selection.
          </div>
        ) : (
          <div className={clsx(cardClass, 'space-y-6')}>
            {[...operationsByGroup.entries()].map(([groupLabel, ops]) => (
              <div key={groupLabel}>
                <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{groupLabel}</h3>
                <div className="grid gap-4 sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                  {ops.map((op) => {
                    const isEmbedding = op.id === 'embedding'
                    const currentOverride = analysis?.model_overrides?.[op.id] ?? ''
                    return (
                      <div key={op.id} className="flex flex-col gap-1.5">
                        <label htmlFor={`model-${op.id}`} className="text-sm font-medium text-slate-700">
                          {op.label}
                          {op.thinking_budget > 0 && (
                            <span className="ml-1.5 text-[10px] font-normal text-indigo-500" title={`${op.thinking_budget.toLocaleString()} thinking tokens allocated`}>
                              reasoning
                            </span>
                          )}
                          {op.output_format === 'json' && (
                            <span className="ml-1.5 text-[10px] font-normal text-emerald-600" title="Structured JSON output enforced at API level">
                              structured
                            </span>
                          )}
                        </label>
                        <p className="text-xs leading-relaxed text-slate-400">{op.description}</p>
                        {isEmbedding ? (
                          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                            {op.effective_model.split('/').pop()}
                          </div>
                        ) : (
                          <select
                            id={`model-${op.id}`}
                            value={currentOverride}
                            disabled={updateSettings.isPending}
                            onChange={(e) => onModelOverrideChange(op.id, e.target.value)}
                            className={clsx(
                              'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 shadow-sm outline-none transition',
                              'ring-slate-900/5 focus:border-navy-400 focus:ring-2 focus:ring-navy-200',
                              updateSettings.isPending && 'cursor-not-allowed opacity-60',
                            )}
                          >
                            <option value="">
                              Platform default ({op.effective_model.split('/').pop()})
                            </option>
                            {catalog.providers.map((provider) => (
                              <optgroup key={provider.id} label={provider.name}>
                                {provider.models.map((m) => (
                                  <option key={m.id} value={m.id}>
                                    {m.label}
                                  </option>
                                ))}
                              </optgroup>
                            ))}
                          </select>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Prompt Management</h2>
        <p className="mb-6 text-sm text-slate-500">
          Customize the prompts used by each AI operation. Locked blocks maintain system integrity.
        </p>
        <PromptsSection />
      </section>
    </div>
  )
}
