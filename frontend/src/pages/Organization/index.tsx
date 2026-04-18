import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Building2,
  Cloud,
  Database,
  FileSpreadsheet,
  Globe,
  Landmark,
  Layers,
  Loader2,
  Plug,
  Sparkles,
  Users,
  Wrench,
} from 'lucide-react'
import clsx from 'clsx'
import { useConnections, useModelCatalog, useOrgProfile, useOrgSettings, useReanalyze, useUpdateOrgSettings } from '@/hooks/useApi'
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
  const company_name = typeof settings?.company_name === 'string' ? settings.company_name : undefined
  const domains = Array.isArray(settings?.domains)
    ? (settings.domains as unknown[]).filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
    : []
  const industry = typeof settings?.industry === 'string' ? settings.industry : undefined
  const headcount = readNumber(settings, ['headcount', 'estimated_headcount'])
  const annual_revenue = readNumber(settings, ['annual_revenue', 'estimated_annual_revenue'])
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
  const threshold = typeof o.classification_threshold === 'number' ? o.classification_threshold : 0.1
  const minVec = typeof o.min_records_for_vectorization === 'number' ? o.min_records_for_vectorization : 1
  return {
    velocity_window_days: velocity,
    classification_threshold: threshold,
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

  const [reanalyzeBanner, setReanalyzeBanner] = useState<string | null>(null)

  const profile = useMemo(() => parseProfile(profileQuery.data), [profileQuery.data])
  const company = useMemo(() => readCompanyFromSettings(profile.settings_json), [profile.settings_json])

  const displayCompanyName = company.company_name?.trim() || profile.name || '—'
  const displayIndustry = company.industry?.trim() || '—'

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
  const [thresholdDraft, setThresholdDraft] = useState('')
  const [minVecDraft, setMinVecDraft] = useState('')

  useEffect(() => {
    if (!analysis) return
    setVelocityDraft(String(analysis.velocity_window_days))
    setThresholdDraft(String(analysis.classification_threshold))
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

  const saveThreshold = useCallback(() => {
    const n = parseFloat(thresholdDraft)
    if (Number.isNaN(n) || n < 0) {
      if (analysis) setThresholdDraft(String(analysis.classification_threshold))
      return
    }
    if (analysis && n === analysis.classification_threshold) return
    patchSetting({ classification_threshold: n })
  }, [thresholdDraft, analysis, patchSetting])

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
          <span
            className="inline-flex items-center gap-1 rounded-full border border-amber-200/80 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-900 ring-1 ring-amber-900/5"
            title="Inline editing will be available when profile updates are supported."
          >
            <Sparkles className="h-3 w-3" aria-hidden />
            Editing coming soon
          </span>
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
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Read-only</p>
                <p className="text-base font-semibold text-navy-900">{displayCompanyName}</p>
                {profile.plan_tier ? <p className="text-xs text-slate-500">Plan: {profile.plan_tier}</p> : null}
              </div>
            </div>
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-100 bg-slate-50/40 px-4">
              <ProfileRow label="Company name">{displayCompanyName}</ProfileRow>
              <ProfileRow label="Domains / websites">
                {company.domains.length ? (
                  <div className="flex flex-wrap justify-end gap-1.5 sm:justify-end">
                    {company.domains.map((d) => (
                      <span
                        key={d}
                        className="inline-flex max-w-full items-center gap-1 truncate rounded-full bg-white px-2.5 py-0.5 text-xs font-medium text-navy-800 ring-1 ring-slate-200/80"
                      >
                        <Globe className="h-3 w-3 shrink-0 text-slate-400" aria-hidden />
                        {d}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-slate-400">—</span>
                )}
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
          </div>
        )}
      </section>

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
            <div className="grid gap-6 sm:grid-cols-1 md:grid-cols-3">
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
                id="classification-threshold"
                label="Classification threshold"
                helpText="Velocity-to-record ratio above which an object is classified as operational vs configuration. Lower values classify more objects as operational."
                value={thresholdDraft}
                onChange={setThresholdDraft}
                onBlur={saveThreshold}
                step="0.01"
                inputMode="decimal"
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
                    const currentOverride = analysis?.model_overrides?.[op.id] ?? ''
                    return (
                      <div key={op.id} className="flex flex-col gap-1.5">
                        <label htmlFor={`model-${op.id}`} className="text-sm font-medium text-slate-700">
                          {op.label}
                        </label>
                        <p className="text-xs leading-relaxed text-slate-400">{op.description}</p>
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
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
