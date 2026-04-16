import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Building2, CreditCard, GitBranch, Globe, HelpCircle, Landmark, Shield, TrendingUp, Users } from 'lucide-react'
import clsx from 'clsx'
import {
  useCostModel,
  useOrgEntities,
  useOrgHierarchy,
  useOrgLicensing,
  useOrgProfile,
  useUserVelocity,
} from '@/hooks/useApi'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'

type HierarchyNode = {
  id: string
  name: string
  entity_type?: string | null
  children?: HierarchyNode[]
}

type OrgProfileData = {
  name?: string
  plan_tier?: string
  settings_json?: Record<string, unknown>
}

type CostModelData = {
  annual_cost_deflection?: number | null
  hires_deflected?: number | null
  assumptions?: Record<string, unknown>
}

type EntityRow = {
  headcount?: number
}

function getHttpStatus(err: unknown): number | undefined {
  if (err && typeof err === 'object' && 'status' in err) {
    const s = (err as { status: unknown }).status
    return typeof s === 'number' ? s : undefined
  }
  return undefined
}

function parseHierarchyRoots(data: unknown): HierarchyNode[] {
  if (!data || typeof data !== 'object') return []
  const o = data as { roots?: unknown; nodes?: unknown }
  const raw = Array.isArray(o.roots) ? o.roots : Array.isArray(o.nodes) ? o.nodes : []
  return raw.filter((n): n is HierarchyNode => {
    if (!n || typeof n !== 'object') return false
    const x = n as { id?: unknown; name?: unknown }
    return typeof x.id === 'string' && typeof x.name === 'string'
  })
}

function formatUsdCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function formatNumberCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
}

function formatInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value)
}

function pickString(obj: Record<string, unknown> | undefined, keys: string[]): string | undefined {
  if (!obj) return undefined
  for (const k of keys) {
    const v = obj[k]
    if (typeof v === 'string' && v.trim()) return v.trim()
  }
  return undefined
}

function TreeNode({ node, depth = 0 }: { node: HierarchyNode; depth?: number }) {
  const subtitle = node.entity_type?.trim() || '—'
  return (
    <li className="space-y-2">
      <div
        className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm"
        style={{ marginLeft: depth * 16 }}
      >
        <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-md bg-navy-50 text-navy-800">
          <Users className="h-4 w-4" />
        </div>
        <div>
          <p className="text-sm font-semibold text-navy-900">{node.name}</p>
          <p className="text-xs text-slate-500">{subtitle}</p>
        </div>
      </div>
      {node.children?.length ? (
        <ul className="space-y-2 border-l border-dashed border-slate-200 pl-4">
          {node.children.map((c) => (
            <TreeNode key={c.id} node={c} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

type LicenseRow = { type: string; key?: string; category?: string; total: number; used: number; status: string }
type PslRow = { name: string; developer_name?: string; total: number; used: number }
type LicData = {
  edition?: string
  is_sandbox?: boolean
  licenses_json?: LicenseRow[]
  package_licenses_json?: { namespace: string; total: number; used: number }[]
  psl_json?: PslRow[]
  limits_json?: Record<string, unknown>
  estimated_annual_spend?: number | null
}

const LICENSE_TABS = ['internal', 'external', 'feature'] as const
type LicTab = (typeof LICENSE_TABS)[number]
const TAB_LABELS: Record<LicTab, string> = { internal: 'Core (Internal)', external: 'External (Community)', feature: 'Feature / Entitlement' }

function LicenseBar({ label, used, total }: { label: string; used: number; total: number }) {
  const pct = total > 0 ? Math.round((used / total) * 100) : 0
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-40 truncate text-slate-700" title={label}>{label}</span>
      <div className="h-2 flex-1 rounded-full bg-slate-100">
        <div
          className={`h-2 rounded-full ${pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-amber-400' : 'bg-emerald-500'}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="w-16 text-right tabular-nums text-slate-600">{used}/{total}</span>
    </div>
  )
}

function LicensingSection({ licensingQuery, experienceSites }: {
  licensingQuery: { data?: unknown }
  experienceSites: { name: string; status: string; url_prefix: string }[]
}) {
  const [tab, setTab] = useState<LicTab>('internal')
  const [showMethodology, setShowMethodology] = useState(false)

  if (!licensingQuery.data) return null
  const lic = licensingQuery.data as LicData
  const licenses = lic.licenses_json ?? []
  const pslList = lic.psl_json ?? []

  const internal = licenses.filter((l) => l.total > 0 && (l.category === 'internal' || !l.category))
  const external = licenses.filter((l) => l.total > 0 && l.category === 'external')
  const identity = licenses.filter((l) => l.total > 0 && l.category === 'identity')
  const featureItems = [...identity, ...pslList.filter((p) => p.total > 0).map((p) => ({ type: p.name, total: p.total, used: p.used, status: '', category: 'feature' as const, key: p.developer_name ?? '' }))]

  const currentList = tab === 'internal' ? internal : tab === 'external' ? external : featureItems

  const totalLic = licenses.reduce((s, l) => s + (l.total || 0), 0)
  const usedLic = licenses.reduce((s, l) => s + (l.used || 0), 0)
  const pkgCount = (lic.package_licenses_json ?? []).length

  const limitsJson = (lic.limits_json ?? {}) as Record<string, { Max?: number; Remaining?: number }>
  const storage = limitsJson.DataStorageMB as { Max?: number; Remaining?: number } | undefined
  const apiLimits = limitsJson.DailyApiRequests as { Max?: number; Remaining?: number } | undefined
  const methodology = typeof limitsJson.cost_methodology === 'string' ? limitsJson.cost_methodology : null

  const liveSites = experienceSites.filter((s) => s.status === 'Live' || s.status === 'Active')

  return (
    <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
      <div className="flex items-center gap-3">
        <CreditCard className="h-6 w-6 text-navy-700" />
        <div>
          <h2 className="text-lg font-semibold text-navy-900">Salesforce Licensing</h2>
          <p className="text-sm text-slate-600">License utilization and estimated platform spend</p>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-navy-100 px-3 py-1 text-xs font-semibold text-navy-800">
              {lic.edition || 'Unknown Edition'}
            </span>
            {lic.is_sandbox && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">Sandbox</span>
            )}
          </div>
          <div className="relative">
            <div className="flex items-center gap-1.5">
              <p className="text-xs uppercase tracking-wide text-slate-500">Estimated Annual Spend</p>
              {methodology && (
                <button
                  type="button"
                  className="text-slate-400 hover:text-slate-600"
                  onClick={() => setShowMethodology((v) => !v)}
                  aria-label="Cost methodology"
                >
                  <HelpCircle className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <p className="mt-1 text-3xl font-bold text-navy-900">
              {lic.estimated_annual_spend
                ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 0 }).format(lic.estimated_annual_spend)
                : '—'}
            </p>
            {showMethodology && methodology && (
              <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs leading-relaxed text-slate-600">
                {methodology}
              </div>
            )}
          </div>
          <div className="flex gap-4 text-sm">
            <div>
              <span className="text-slate-500">Licenses: </span>
              <span className="font-semibold text-slate-900">{usedLic}/{totalLic}</span>
            </div>
            <div>
              <span className="text-slate-500">Packages: </span>
              <span className="font-semibold text-slate-900">{pkgCount}</span>
            </div>
          </div>
          {storage && (
            <p className="text-xs text-slate-500">
              Storage:{' '}
              {storage.Remaining != null && storage.Max != null
                ? `${((storage.Max - storage.Remaining) / 1024).toFixed(1)} / ${(storage.Max / 1024).toFixed(1)} GB`
                : '—'}
            </p>
          )}
          {apiLimits && (
            <p className="text-xs text-slate-500">
              Daily API:{' '}
              {apiLimits.Remaining != null && apiLimits.Max != null
                ? `${(apiLimits.Max - apiLimits.Remaining).toLocaleString()} / ${apiLimits.Max.toLocaleString()} used`
                : '—'}
            </p>
          )}
        </div>

        <div className="space-y-3 lg:col-span-2">
          <div className="flex items-center gap-1 border-b border-slate-100">
            {LICENSE_TABS.map((t) => (
              <button
                key={t}
                type="button"
                className={clsx(
                  'px-3 py-1.5 text-xs font-medium transition-colors',
                  t === tab ? 'border-b-2 border-navy-700 text-navy-800' : 'text-slate-500 hover:text-slate-700',
                )}
                onClick={() => setTab(t)}
              >
                {TAB_LABELS[t]}
                <span className="ml-1.5 tabular-nums text-slate-400">
                  ({(t === 'internal' ? internal : t === 'external' ? external : featureItems).length})
                </span>
              </button>
            ))}
          </div>
          <div className="max-h-[220px] space-y-1.5 overflow-auto pr-2">
            {currentList.length === 0 ? (
              <p className="py-4 text-center text-xs text-slate-400">No licenses in this category</p>
            ) : (
              currentList.map((l) => (
                <LicenseBar key={l.type} label={l.type} used={l.used} total={l.total} />
              ))
            )}
          </div>
        </div>
      </div>

      {liveSites.length > 0 && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-navy-700" />
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Experience Cloud Sites</p>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {liveSites.map((s) => (
              <span key={s.name} className="inline-flex items-center gap-1.5 rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-medium text-teal-800">
                <span className="h-1.5 w-1.5 rounded-full bg-teal-500" />
                {s.name}
                {s.url_prefix && <span className="text-teal-600">/{s.url_prefix}</span>}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

type VelocitySnap = {
  snapshot_at: string
  active_user_count: number
  internal_active_count?: number
  external_active_count?: number
  new_users_this_month: number
  deactivated_this_month: number
  by_role_json: Record<string, number>
  by_profile_json: Record<string, number>
}

function VelocitySection({ velocityQuery }: { velocityQuery: { data?: unknown } }) {
  if (!velocityQuery.data || !Array.isArray(velocityQuery.data) || velocityQuery.data.length === 0) return null

  const snapshots = (velocityQuery.data as VelocitySnap[]).slice().reverse()
  const chartData = snapshots.map((s) => ({
    date: new Date(s.snapshot_at).toLocaleDateString(undefined, { month: 'short', year: '2-digit' }),
    internal: s.internal_active_count ?? s.active_user_count,
    external: s.external_active_count ?? 0,
    new: s.new_users_this_month,
    deactivated: s.deactivated_this_month,
  }))

  const latestSnap = snapshots[snapshots.length - 1]
  const internalCount = latestSnap?.internal_active_count ?? latestSnap?.active_user_count ?? 0
  const externalCount = latestSnap?.external_active_count ?? 0
  const roleEntries = Object.entries(latestSnap?.by_role_json ?? {}).sort((a, b) => b[1] - a[1])
  const profileEntries = Object.entries(latestSnap?.by_profile_json ?? {}).sort((a, b) => b[1] - a[1])

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center gap-3">
          <TrendingUp className="h-6 w-6 text-navy-700" />
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Platform Adoption</h2>
            <p className="text-sm text-slate-600">Internal vs external active users</p>
          </div>
        </div>
        <div className="mt-4 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="internalGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#1e3a5f" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#1e3a5f" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="externalGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0d9488" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#0d9488" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Area type="monotone" dataKey="internal" name="Internal" stroke="#1e3a5f" fill="url(#internalGrad)" strokeWidth={2} />
              <Area type="monotone" dataKey="external" name="External" stroke="#0d9488" fill="url(#externalGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        {chartData.length > 0 && (
          <div className="mt-3 flex gap-6 text-xs text-slate-600">
            <span>Internal: <strong className="text-navy-900">{internalCount}</strong></span>
            <span>External: <strong className="text-teal-700">{externalCount}</strong></span>
            <span>New this month: <strong className="text-emerald-700">+{latestSnap?.new_users_this_month ?? 0}</strong></span>
            <span>Deactivated: <strong className="text-red-600">-{latestSnap?.deactivated_this_month ?? 0}</strong></span>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center gap-3">
          <Shield className="h-6 w-6 text-navy-700" />
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Role & Profile Distribution</h2>
            <p className="text-sm text-slate-600">Internal users by role and profile</p>
          </div>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">By Role</p>
            <div className="max-h-[180px] space-y-1 overflow-auto pr-1">
              {roleEntries.length === 0 ? (
                <p className="text-xs text-slate-400">No role data</p>
              ) : (
                roleEntries.map(([name, count]) => (
                  <div key={name} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-slate-700">{name}</span>
                    <span className="font-semibold text-slate-900">{count}</span>
                  </div>
                ))
              )}
            </div>
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">By Profile</p>
            <div className="max-h-[180px] space-y-1 overflow-auto pr-1">
              {profileEntries.length === 0 ? (
                <p className="text-xs text-slate-400">No profile data</p>
              ) : (
                profileEntries.map(([name, count]) => (
                  <div key={name} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate text-slate-700">{name}</span>
                    <span className="font-semibold text-slate-900">{count}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

export default function OrganizationPage() {
  const profileQuery = useOrgProfile()
  const hierarchyQuery = useOrgHierarchy()
  const licensingQuery = useOrgLicensing()
  const velocityQuery = useUserVelocity()
  const costModelQuery = useCostModel()
  const entitiesQuery = useOrgEntities({ page: 1, page_size: 200 })

  const roots = useMemo(() => parseHierarchyRoots(hierarchyQuery.data), [hierarchyQuery.data])

  const profile = profileQuery.data as OrgProfileData | undefined
  const cost = costModelQuery.data as CostModelData | undefined

  const settings = profile?.settings_json
  const sfOrgName = pickString(settings, ['sf_org_name']) || profile?.name
  const edition = pickString(settings, ['edition'])
  const isSandbox = settings?.is_sandbox === true
  const instanceUrl = pickString(settings, ['instance_url'])
  const activeUsers = typeof settings?.active_users === 'number' ? settings.active_users : null
  const internalUsers = typeof settings?.internal_users === 'number' ? settings.internal_users : null
  const externalUsers = typeof settings?.external_users === 'number' ? settings.external_users : null
  const annualSpend = typeof settings?.estimated_annual_spend === 'number' ? settings.estimated_annual_spend : null
  const licenseSummary = settings?.license_summary as {
    total?: number; used?: number;
    internal_total?: number; internal_used?: number;
    external_total?: number; external_used?: number;
  } | undefined
  const experienceSites = Array.isArray(settings?.experience_sites) ? (settings.experience_sites as { name: string; status: string; url_prefix: string }[]) : []
  const roleCount = typeof settings?.role_count === 'number' ? settings.role_count : null
  const profileCount = typeof settings?.profile_count === 'number' ? settings.profile_count : null
  const topPackages = Array.isArray(settings?.top_packages) ? (settings.top_packages as string[]) : []

  const entityItems = (entitiesQuery.data?.items ?? []) as EntityRow[]
  const entityTotal = entitiesQuery.data?.total ?? 0
  const headcountListed = entityItems.reduce((acc, e) => acc + (Number(e.headcount) || 0), 0)
  const employeesDisplay =
    entityTotal === 0
      ? (activeUsers != null ? formatInt(activeUsers) : '—')
      : entityItems.length >= entityTotal
        ? formatInt(headcountListed)
        : `${formatInt(headcountListed)}+`

  const modelNote =
    typeof cost?.assumptions?.model === 'string' && cost.assumptions.model
      ? String(cost.assumptions.model)
      : 'Entity-linked cost signals'

  const profileLoading = profileQuery.isLoading
  const profileError = profileQuery.isError && getHttpStatus(profileQuery.error) !== 404

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Organization</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Business entity profiling, operating structure, and human-capital cost modeling across connected systems.
        </p>
      </div>

      {profileLoading ? (
        <LoadingState message="Loading organization data..." />
      ) : profileError ? (
        <ErrorState message={profileQuery.error instanceof Error ? profileQuery.error.message : undefined} />
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-3">
            <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5 lg:col-span-1">
              <div className="flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-navy-800 text-white shadow">
                  <Building2 className="h-6 w-6" />
                </span>
                <div>
                  <h2 className="text-lg font-semibold text-navy-900">Business Profile</h2>
                  <p className="text-xs text-slate-500">Synced from Salesforce</p>
                </div>
              </div>
              <dl className="mt-6 space-y-4 text-sm">
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Company</dt>
                  <dd className="font-medium text-slate-900">{sfOrgName ?? '—'}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Edition</dt>
                  <dd className="font-medium text-slate-900">
                    {edition || '—'}
                    {isSandbox && <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">Sandbox</span>}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Internal Users</dt>
                  <dd className="font-medium text-slate-900">{internalUsers != null ? formatInt(internalUsers) : employeesDisplay}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">External Users</dt>
                  <dd className="font-medium text-slate-900">{externalUsers != null ? formatInt(externalUsers) : '—'}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Roles / Profiles</dt>
                  <dd className="font-medium text-slate-900">
                    {roleCount != null ? roleCount : '—'} / {profileCount != null ? profileCount : '—'}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Est. Annual Spend</dt>
                  <dd className="font-medium text-slate-900">{annualSpend ? formatUsdCompact(annualSpend) : '—'}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Licenses</dt>
                  <dd className="font-medium text-slate-900">
                    {licenseSummary ? `${formatInt(licenseSummary.used)} / ${formatInt(licenseSummary.total)}` : '—'}
                  </dd>
                </div>
                {instanceUrl && (
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-slate-500">Instance</dt>
                    <dd className="font-medium text-slate-900 truncate max-w-[180px]">
                      <a href={instanceUrl} target="_blank" rel="noreferrer" className="text-sky-700 hover:underline">
                        {pickString(settings, ['instance_name']) || instanceUrl.replace('https://', '')}
                      </a>
                    </dd>
                  </div>
                )}
              </dl>
              {topPackages.length > 0 && (
                <div className="mt-5 border-t border-slate-100 pt-4">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Installed Packages</p>
                  <div className="flex flex-wrap gap-1.5">
                    {topPackages.slice(0, 12).map((pkg) => (
                      <span key={pkg} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">{pkg}</span>
                    ))}
                    {topPackages.length > 12 && (
                      <span className="text-xs text-slate-400">+{topPackages.length - 12} more</span>
                    )}
                  </div>
                </div>
              )}
            </section>

            <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5 lg:col-span-2">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <GitBranch className="h-6 w-6 text-navy-700" />
                  <div>
                    <h2 className="text-lg font-semibold text-navy-900">Org hierarchy</h2>
                    <p className="text-sm text-slate-600">Leadership tree with key operational pillars</p>
                  </div>
                </div>
              </div>
              <div className="mt-6 max-h-[420px] overflow-auto pr-2">
                {roots.length === 0 ? (
                  <p className="text-sm text-slate-500">No hierarchy nodes yet. Import entities or sync from Salesforce.</p>
                ) : (
                  <ul className="space-y-3">
                    {roots.map((n) => (
                      <TreeNode key={n.id} node={n} />
                    ))}
                  </ul>
                )}
              </div>
            </section>
          </div>

          <LicensingSection licensingQuery={licensingQuery} experienceSites={experienceSites} />

          <VelocitySection velocityQuery={velocityQuery} />

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-xl border border-slate-200/80 bg-navy-800 p-6 text-white shadow-md ring-1 ring-black/10">
              <div className="flex items-center gap-3">
                <Landmark className="h-6 w-6 text-orange-300" />
                <div>
                  <h2 className="text-lg font-semibold">Cost modeling</h2>
                  <p className="text-sm text-slate-200">Annualized IT + labor baseline</p>
                </div>
              </div>
              <div className="mt-6 grid gap-4 sm:grid-cols-3">
                <div className="rounded-lg bg-white/5 p-4 ring-1 ring-white/10">
                  <p className="text-xs uppercase tracking-wide text-slate-300">Annual cost deflection</p>
                  <p className="mt-2 text-2xl font-semibold">
                    {formatUsdCompact(cost?.annual_cost_deflection ?? null)}
                  </p>
                  <p className="mt-1 text-xs text-slate-200">From modeled entity cost signals</p>
                </div>
                <div className="rounded-lg bg-white/5 p-4 ring-1 ring-white/10">
                  <p className="text-xs uppercase tracking-wide text-slate-300">Hires deflected (est.)</p>
                  <p className="mt-2 text-2xl font-semibold">
                    {formatNumberCompact(cost?.hires_deflected ?? null)}
                  </p>
                  <p className="mt-1 text-xs text-slate-200">FTE-equivalent from headcount model</p>
                </div>
                <div className="rounded-lg bg-white/5 p-4 ring-1 ring-white/10">
                  <p className="text-xs uppercase tracking-wide text-slate-300">Entities modeled</p>
                  <p className="mt-2 text-2xl font-semibold">{formatInt(entityTotal)}</p>
                  <p className="mt-1 text-xs text-orange-200">Synced org records</p>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
              <h2 className="text-lg font-semibold text-navy-900">Human capital cost deflection</h2>
              <p className="mt-1 text-sm text-slate-600">
                Modeled deflection from synced entity costs and headcount signals.
              </p>
              <div className="mt-6 grid gap-4 sm:grid-cols-2">
                <div className="rounded-lg border border-emerald-100 bg-emerald-50/60 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Annual deflection</p>
                  <p className="mt-2 text-3xl font-semibold text-emerald-900">
                    {formatUsdCompact(cost?.annual_cost_deflection ?? null)}
                  </p>
                  <p className="mt-1 text-xs text-emerald-800/90">Roll-up from entity cost_data</p>
                </div>
                <div className="rounded-lg border border-sky-100 bg-sky-50/60 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-sky-900">Hires deflected</p>
                  <p className="mt-2 text-3xl font-semibold text-sky-900">
                    {formatNumberCompact(cost?.hires_deflected ?? null)}
                  </p>
                  <p className="mt-1 text-xs text-sky-800/90">{modelNote}</p>
                </div>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
