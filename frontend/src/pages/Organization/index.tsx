import { useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Building2, CreditCard, GitBranch, Landmark, Shield, TrendingUp, Users } from 'lucide-react'
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
  const annualSpend = typeof settings?.estimated_annual_spend === 'number' ? settings.estimated_annual_spend : null
  const licenseSummary = settings?.license_summary as { total?: number; used?: number } | undefined
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
                  <dt className="text-slate-500">Active Users</dt>
                  <dd className="font-medium text-slate-900">{employeesDisplay}</dd>
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

          {licensingQuery.data &&
            (() => {
              const lic = licensingQuery.data as {
                edition?: string
                is_sandbox?: boolean
                licenses_json?: { type: string; total: number; used: number; status: string }[]
                package_licenses_json?: { namespace: string; total: number; used: number }[]
                psl_json?: { name: string; total: number; used: number }[]
                limits_json?: Record<string, { Max?: number; Remaining?: number }>
                estimated_annual_spend?: number | null
              }
              const licenses = lic.licenses_json ?? []
              const activeLicenses = licenses.filter((l) => l.total > 0)
              const totalLic = licenses.reduce((s, l) => s + (l.total || 0), 0)
              const usedLic = licenses.reduce((s, l) => s + (l.used || 0), 0)
              const pkgCount = (lic.package_licenses_json ?? []).length
              const storage = lic.limits_json?.DataStorageMB
              const apiLimits = lic.limits_json?.DailyApiRequests

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
                          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                            Sandbox
                          </span>
                        )}
                      </div>
                      <div>
                        <p className="text-xs uppercase tracking-wide text-slate-500">Estimated Annual Spend</p>
                        <p className="mt-1 text-3xl font-bold text-navy-900">
                          {lic.estimated_annual_spend
                            ? new Intl.NumberFormat('en-US', {
                                style: 'currency',
                                currency: 'USD',
                                notation: 'compact',
                                maximumFractionDigits: 0,
                              }).format(lic.estimated_annual_spend)
                            : '—'}
                        </p>
                      </div>
                      <div className="flex gap-4 text-sm">
                        <div>
                          <span className="text-slate-500">Licenses: </span>
                          <span className="font-semibold text-slate-900">
                            {usedLic}/{totalLic}
                          </span>
                        </div>
                        <div>
                          <span className="text-slate-500">Packages: </span>
                          <span className="font-semibold text-slate-900">{pkgCount}</span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2 lg:col-span-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">License Utilization</p>
                      <div className="max-h-[200px] space-y-1.5 overflow-auto pr-2">
                        {activeLicenses.map((l) => {
                          const pct = l.total > 0 ? Math.round((l.used / l.total) * 100) : 0
                          return (
                            <div key={l.type} className="flex items-center gap-3 text-xs">
                              <span className="w-36 truncate text-slate-700" title={l.type}>
                                {l.type}
                              </span>
                              <div className="h-2 flex-1 rounded-full bg-slate-100">
                                <div
                                  className={`h-2 rounded-full ${pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                                  style={{ width: `${Math.min(pct, 100)}%` }}
                                />
                              </div>
                              <span className="w-16 text-right text-slate-600">
                                {l.used}/{l.total}
                              </span>
                            </div>
                          )
                        })}
                      </div>
                      {storage && (
                        <p className="mt-2 text-xs text-slate-500">
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
                  </div>
                </section>
              )
            })()}

          {velocityQuery.data &&
            Array.isArray(velocityQuery.data) &&
            velocityQuery.data.length > 0 &&
            (() => {
              const snapshots = (
                velocityQuery.data as {
                  snapshot_at: string
                  active_user_count: number
                  new_users_this_month: number
                  deactivated_this_month: number
                  by_role_json: Record<string, number>
                  by_profile_json: Record<string, number>
                }[]
              )
                .slice()
                .reverse()

              const chartData = snapshots.map((s) => ({
                date: new Date(s.snapshot_at).toLocaleDateString(undefined, { month: 'short', year: '2-digit' }),
                active: s.active_user_count,
                new: s.new_users_this_month,
                deactivated: s.deactivated_this_month,
                net: s.new_users_this_month - s.deactivated_this_month,
              }))

              const latestSnap = snapshots[snapshots.length - 1]
              const roleEntries = Object.entries(latestSnap?.by_role_json ?? {}).sort((a, b) => b[1] - a[1])
              const profileEntries = Object.entries(latestSnap?.by_profile_json ?? {}).sort((a, b) => b[1] - a[1])

              return (
                <div className="grid gap-6 lg:grid-cols-2">
                  <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
                    <div className="flex items-center gap-3">
                      <TrendingUp className="h-6 w-6 text-navy-700" />
                      <div>
                        <h2 className="text-lg font-semibold text-navy-900">Platform Adoption Trend</h2>
                        <p className="text-sm text-slate-600">Net platform user change over time</p>
                      </div>
                    </div>
                    <div className="mt-4 h-56">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                          <defs>
                            <linearGradient id="activeGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#1e3a5f" stopOpacity={0.15} />
                              <stop offset="95%" stopColor="#1e3a5f" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                          <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                          <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
                          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                          <Area
                            type="monotone"
                            dataKey="active"
                            name="Active Users"
                            stroke="#1e3a5f"
                            fill="url(#activeGrad)"
                            strokeWidth={2}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                    {chartData.length > 0 && (
                      <div className="mt-3 flex gap-6 text-xs text-slate-600">
                        <span>
                          Active: <strong className="text-slate-900">{latestSnap?.active_user_count ?? 0}</strong>
                        </span>
                        <span>
                          New this month:{' '}
                          <strong className="text-emerald-700">+{latestSnap?.new_users_this_month ?? 0}</strong>
                        </span>
                        <span>
                          Deactivated:{' '}
                          <strong className="text-red-600">-{latestSnap?.deactivated_this_month ?? 0}</strong>
                        </span>
                      </div>
                    )}
                  </section>

                  <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
                    <div className="flex items-center gap-3">
                      <Shield className="h-6 w-6 text-navy-700" />
                      <div>
                        <h2 className="text-lg font-semibold text-navy-900">Role & Profile Distribution</h2>
                        <p className="text-sm text-slate-600">Active users by role and profile</p>
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
            })()}

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
