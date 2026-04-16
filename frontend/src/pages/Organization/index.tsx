import { useMemo } from 'react'
import { Building2, GitBranch, Landmark, Users } from 'lucide-react'
import { useCostModel, useOrgEntities, useOrgHierarchy, useOrgProfile } from '@/hooks/useApi'
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
  const costModelQuery = useCostModel()
  const entitiesQuery = useOrgEntities({ page: 1, page_size: 200 })

  const roots = useMemo(() => parseHierarchyRoots(hierarchyQuery.data), [hierarchyQuery.data])

  const profile = profileQuery.data as OrgProfileData | undefined
  const cost = costModelQuery.data as CostModelData | undefined

  const settings = profile?.settings_json
  const industry =
    pickString(settings, ['industry', 'sector', 'vertical']) ||
    (typeof profile?.plan_tier === 'string' && profile.plan_tier ? profile.plan_tier : undefined) ||
    'Not specified'

  const hq = pickString(settings, ['hq', 'headquarters', 'headquarter', 'city', 'address']) || '—'

  const entityItems = (entitiesQuery.data?.items ?? []) as EntityRow[]
  const entityTotal = entitiesQuery.data?.total ?? 0
  const headcountListed = entityItems.reduce((acc, e) => acc + (Number(e.headcount) || 0), 0)
  const employeesDisplay =
    entityTotal === 0
      ? '—'
      : entityItems.length >= entityTotal
        ? formatInt(headcountListed)
        : `${formatInt(headcountListed)}+`

  const modelNote =
    typeof cost?.assumptions?.model === 'string' && cost.assumptions.model
      ? String(cost.assumptions.model)
      : 'Entity-linked cost signals'

  const queries = [profileQuery, hierarchyQuery, costModelQuery, entitiesQuery] as const

  const loading = queries.some((q) => q.isLoading)
  const errored = queries.filter((q) => q.isError)
  const hasNon404Error = errored.some((q) => {
    const s = getHttpStatus(q.error)
    return s === undefined || s !== 404
  })
  const has404 = errored.some((q) => getHttpStatus(q.error) === 404)

  const settledEmptyOrg =
    !loading &&
    !hasNon404Error &&
    profileQuery.isSuccess &&
    hierarchyQuery.isSuccess &&
    entitiesQuery.isSuccess &&
    roots.length === 0 &&
    entityTotal === 0

  const showEmpty = has404 || settledEmptyOrg

  const firstErrorMessage = errored[0]?.error instanceof Error ? errored[0].error.message : undefined

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Organization</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Business entity profiling, operating structure, and human-capital cost modeling across connected systems.
        </p>
      </div>

      {loading ? (
        <LoadingState message="Loading organization data..." />
      ) : hasNon404Error ? (
        <ErrorState message={firstErrorMessage} />
      ) : showEmpty ? (
        <EmptyState
          icon={<Building2 className="h-10 w-10" />}
          title="No organization profile yet"
          description="Connect a platform or import a CSV to get started."
        />
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
                  <p className="text-xs text-slate-500">Synced snapshot</p>
                </div>
              </div>
              <dl className="mt-6 space-y-4 text-sm">
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Company</dt>
                  <dd className="font-medium text-slate-900">{profile?.name ?? '—'}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Industry</dt>
                  <dd className="font-medium text-slate-900">{industry}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-3">
                  <dt className="text-slate-500">Employees</dt>
                  <dd className="font-medium text-slate-900">{employeesDisplay}</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-slate-500">Headquarters</dt>
                  <dd className="font-medium text-slate-900">{hq}</dd>
                </div>
              </dl>
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
