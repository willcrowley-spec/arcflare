import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Code,
  CreditCard,
  Database,
  Hash,
  KeyRound,
  Package,
  RefreshCw,
  Shield,
  TrendingUp,
  Zap,
} from 'lucide-react'
import clsx from 'clsx'
import { StatusBadge } from '@/components/StatusBadge'
import { SyncEventLogPanel } from '@/components/SyncEventLogPanel'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import {
  useConnections,
  useMetadataAutomation,
  useMetadataComponents,
  useMetadataObjects,
  useMetadataSummary,
  useOrgLicensing,
  useReauthConnection,
  useSyncConnection,
  useUserVelocity,
} from '@/hooks/useApi'
import { useSyncEventStream } from '@/hooks/useSyncEventStream'
import type { MetadataComponent, MetadataSummary } from '@/types'
import { DataObjectsTable } from './DataObjectsTable'

function platformTypeToLabel(raw: string | undefined): string {
  const u = (raw ?? '').toUpperCase()
  const labels: Record<string, string> = {
    SALESFORCE: 'Salesforce',
    HUBSPOT: 'HubSpot',
    NETSUITE: 'NetSuite',
    MULESOFT: 'MuleSoft',
    CONFLUENCE: 'Confluence',
  }
  return labels[u] ?? (raw ? raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase() : 'Connected platform')
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

function humanizeSlug(s: string): string {
  return s
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
}

function filterByConnectionId<T extends { connection_id?: string }>(rows: T[], connectionId: string): T[] {
  return rows.filter((r) => r.connection_id != null && String(r.connection_id) === connectionId)
}

type LicenseRow = { type: string; total: number; used: number; category?: string }

function LicenseUtilBar({ label, used, total }: { label: string; used: number; total: number }) {
  const pct = total > 0 ? Math.round((used / total) * 100) : 0
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-36 truncate text-slate-700" title={label}>
        {label}
      </span>
      <div className="h-2 flex-1 rounded-full bg-slate-100">
        <div
          className={clsx('h-2 rounded-full', pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-amber-400' : 'bg-emerald-500')}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="w-14 text-right tabular-nums text-slate-600">
        {used}/{total}
      </span>
    </div>
  )
}

type VelocitySnap = {
  snapshot_at: string
  active_user_count: number
  internal_active_count?: number
  external_active_count?: number
  system_user_count?: number
  new_users_this_month: number
  deactivated_this_month: number
  by_role_json: Record<string, number>
  by_profile_json: Record<string, number>
}

type LicData = {
  edition?: string
  licenses_json?: LicenseRow[]
  estimated_annual_spend?: number | null
}

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: typeof Database
  label: string
  value: string | number
  sub?: string
}) {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm ring-1 ring-slate-900/5">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-navy-50 text-navy-800">
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
          <p className="mt-0.5 text-2xl font-bold tabular-nums text-navy-900">{value}</p>
          {sub ? <p className="mt-1 text-xs text-slate-500">{sub}</p> : null}
        </div>
      </div>
    </div>
  )
}

export default function PlatformDetailPage() {
  const { connectionId } = useParams<{ connectionId: string }>()
  const navigate = useNavigate()
  const [syncingId, setSyncingId] = useState<string | null>(null)
  const [activeSyncId, setActiveSyncId] = useState<string | null>(null)
  const { events: syncEvents, status: syncStreamStatus, reset: resetSyncStream } = useSyncEventStream(activeSyncId)
  const qc = useQueryClient()

  const connectionsQuery = useConnections()
  const syncConnection = useSyncConnection()
  const reauthConnection = useReauthConnection()

  const connections = connectionsQuery.data?.items ?? []
  const connection = useMemo(
    () => connections.find((c) => String(c.id) === String(connectionId)),
    [connections, connectionId],
  )

  useEffect(() => {
    setActiveSyncId(null)
  }, [connectionId])

  useEffect(() => {
    if (connection?.status === 'syncing' && connectionId && !activeSyncId) {
      setActiveSyncId(connectionId)
    }
  }, [connection?.status, connectionId, activeSyncId])

  useEffect(() => {
    if (syncStreamStatus === 'completed' || syncStreamStatus === 'failed') {
      void qc.invalidateQueries({ queryKey: ['connections'] })
      void qc.invalidateQueries({ queryKey: ['metadata'] })
      void qc.invalidateQueries({ queryKey: ['organization'] })
    }
  }, [syncStreamStatus, qc])

  const hasConnection = !!connection && !!connectionId
  const cid = connectionId ?? ''

  const objectsQuery = useMetadataObjects({ page: 1, page_size: 200 }, { enabled: hasConnection })
  const automationQuery = useMetadataAutomation({ page: 1, page_size: 200 }, { enabled: hasConnection })
  const componentsQuery = useMetadataComponents({ page: 1, page_size: 200 }, { enabled: hasConnection })
  const summaryQuery = useMetadataSummary({ enabled: hasConnection })
  const licensingQuery = useOrgLicensing()
  const velocityQuery = useUserVelocity()

  const objectRows = useMemo(() => {
    const items = objectsQuery.data?.items ?? []
    return filterByConnectionId(items, cid)
  }, [objectsQuery.data?.items, cid])

  const automationRows = useMemo(() => {
    const items = automationQuery.data?.items ?? []
    return filterByConnectionId(items, cid)
  }, [automationQuery.data?.items, cid])

  const componentRows = useMemo(() => {
    const items = componentsQuery.data?.items ?? []
    return filterByConnectionId(items, cid)
  }, [componentsQuery.data?.items, cid])

  const packageRows = useMemo(
    () => componentRows.filter((c) => c.component_category === 'installed_package'),
    [componentRows],
  )

  const codeRows = useMemo(
    () => componentRows.filter((c) => c.component_category !== 'installed_package'),
    [componentRows],
  )

  const automationByType = useMemo(() => {
    const m: Record<string, number> = {}
    for (const a of automationRows) {
      const k = a.automation_type || 'other'
      m[k] = (m[k] ?? 0) + 1
    }
    return Object.entries(m).sort((a, b) => b[1] - a[1])
  }, [automationRows])

  const componentsByCategory = useMemo(() => {
    const m: Record<string, number> = {}
    for (const c of codeRows) {
      const k = c.component_category || 'other'
      m[k] = (m[k] ?? 0) + 1
    }
    return Object.entries(m).sort((a, b) => b[1] - a[1])
  }, [codeRows])

  const totalRecords = useMemo(
    () => objectRows.reduce((sum, o) => sum + (o.record_count ?? 0), 0),
    [objectRows],
  )

  const totalAutomationOnObjects = useMemo(
    () => objectRows.reduce((sum, o) => sum + (o.automation_count ?? 0), 0),
    [objectRows],
  )

  const summary = summaryQuery.data as MetadataSummary | undefined

  const onReauth = useCallback(() => {
    if (!connection) return
    reauthConnection.mutate(String(connection.id))
  }, [reauthConnection, connection])

  const onSync = useCallback(() => {
    if (!connection) return
    resetSyncStream()
    const cid = String(connection.id)
    setSyncingId(cid)
    setActiveSyncId(cid)
    syncConnection.mutate(cid, {
      onSettled: () => setSyncingId(null),
    })
  }, [syncConnection, connection, resetSyncStream])

  const platformLabel = connection ? platformTypeToLabel(connection.platform_type ?? connection.platform) : 'Platform'
  const instanceUrl = connection?.instance_url?.trim() || '—'
  const lastSync = connection?.last_sync_at ?? summary?.last_sync_at ?? null

  const velocitySnaps = useMemo(() => {
    const raw = velocityQuery.data
    if (!raw || !Array.isArray(raw) || raw.length === 0) return [] as VelocitySnap[]
    return (raw as VelocitySnap[]).slice().reverse()
  }, [velocityQuery.data])

  const latestVelocity = velocitySnaps.length > 0 ? velocitySnaps[velocitySnaps.length - 1] : undefined
  const roleTop = useMemo(
    () => Object.entries(latestVelocity?.by_role_json ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 8),
    [latestVelocity],
  )
  const profileTop = useMemo(
    () => Object.entries(latestVelocity?.by_profile_json ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 8),
    [latestVelocity],
  )

  const licData = licensingQuery.data as LicData | undefined
  const licenseBars = useMemo(() => {
    const rows = licData?.licenses_json ?? []
    return rows.filter((l) => l.total > 0 && (l.category === 'internal' || !l.category)).slice(0, 8)
  }, [licData])

  if (connectionsQuery.isLoading) {
    return <LoadingState message="Loading platform…" />
  }

  if (connectionsQuery.isError) {
    return <ErrorState message="Could not load connections." />
  }

  if (!connectionId) {
    return (
      <EmptyState
        title="Missing connection"
        description="No connection id in the URL."
        action={
          <Link to="/analysis" className="text-sm font-medium text-navy-700 hover:underline">
            Back to Analysis
          </Link>
        }
      />
    )
  }

  if (!connection) {
    return (
      <EmptyState
        title="Connection not found"
        description="This platform connection does not exist or was removed."
        action={
          <button
            type="button"
            className="text-sm font-medium text-navy-700 hover:underline"
            onClick={() => navigate('/analysis')}
          >
            Back to Analysis
          </button>
        }
      />
    )
  }

  const objectsLoading = objectsQuery.isLoading
  const headerLoading = objectsLoading && objectRows.length === 0

  return (
    <div className="space-y-8">
      <div>
        <Link
          to="/analysis"
          className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-navy-700 hover:text-navy-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Analysis
        </Link>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">{platformLabel}</h1>
              <StatusBadge status={connectionBadgeStatus(String(connection.status))} />
            </div>
            <p className="mt-2 break-all text-sm text-slate-600">
              <span className="font-medium text-slate-700">Instance: </span>
              {instanceUrl}
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Last sync: <span className="text-slate-700">{formatTimestamp(lastSync)}</span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onSync}
              disabled={syncConnection.isPending || syncingId === String(connection.id)}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw className={clsx('h-4 w-4', (syncConnection.isPending || syncingId === String(connection.id)) && 'animate-spin')} />
              Sync now
            </button>
            <button
              type="button"
              onClick={onReauth}
              disabled={reauthConnection.isPending}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:opacity-50"
            >
              <KeyRound className="h-4 w-4" />
              Re-authenticate
            </button>
          </div>
        </div>
      </div>

      {activeSyncId && (
        <SyncEventLogPanel
          events={syncEvents}
          status={syncStreamStatus}
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          icon={Database}
          label="Total data objects"
          value={headerLoading ? '…' : objectRows.length.toLocaleString()}
        />
        <KpiCard
          icon={Zap}
          label="Total automations"
          value={headerLoading ? '…' : totalAutomationOnObjects.toLocaleString()}
          sub={`${automationRows.length.toLocaleString()} automation assets indexed`}
        />
        <KpiCard
          icon={Code}
          label="Total code assets"
          value={headerLoading ? '…' : codeRows.length.toLocaleString()}
        />
        <KpiCard
          icon={Hash}
          label="Total records"
          value={headerLoading ? '…' : totalRecords.toLocaleString()}
        />
      </div>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-navy-900">Data objects</h2>
        {objectsQuery.isError ? (
          <ErrorState message="Could not load metadata objects." />
        ) : (
          <DataObjectsTable rows={objectRows} isLoading={objectsLoading && objectRows.length === 0} />
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <div className="flex items-center gap-3">
            <Zap className="h-6 w-6 text-navy-700" />
            <div>
              <h2 className="text-lg font-semibold text-navy-900">Automations summary</h2>
              <p className="text-sm text-slate-600">Counts by automation type for this connection</p>
            </div>
          </div>
          {automationQuery.isError ? (
            <p className="mt-4 text-sm text-red-600">Could not load automations.</p>
          ) : automationByType.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">No automations recorded for this connection.</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {automationByType.map(([type, count]) => (
                <li key={type} className="flex items-center justify-between text-sm">
                  <span className="text-slate-700">{humanizeSlug(type)}</span>
                  <span className="font-semibold tabular-nums text-navy-900">{count.toLocaleString()}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <div className="flex items-center gap-3">
            <Code className="h-6 w-6 text-navy-700" />
            <div>
              <h2 className="text-lg font-semibold text-navy-900">Code summary</h2>
              <p className="text-sm text-slate-600">Code-related metadata components (excludes installed packages)</p>
            </div>
          </div>
          {componentsQuery.isError ? (
            <p className="mt-4 text-sm text-red-600">Could not load components.</p>
          ) : (
            <>
              <p className="mt-4 text-3xl font-bold text-navy-900">{codeRows.length.toLocaleString()}</p>
              <p className="mt-1 text-xs text-slate-500">Total code assets</p>
              <ul className="mt-4 max-h-48 space-y-1.5 overflow-auto pr-1">
                {componentsByCategory.slice(0, 12).map(([cat, count]) => (
                  <li key={cat} className="flex items-center justify-between text-xs">
                    <span className="truncate text-slate-700">{humanizeSlug(cat)}</span>
                    <span className="font-semibold text-slate-900">{count}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>

      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center gap-3">
          <CreditCard className="h-6 w-6 text-navy-700" />
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Licensing</h2>
            <p className="text-sm text-slate-600">Org-level license utilization (simplified)</p>
          </div>
        </div>
        {licensingQuery.isError ? (
          <p className="mt-4 text-sm text-slate-500">Licensing data is not available.</p>
        ) : !licData ? (
          <p className="mt-4 text-sm text-slate-500">No licensing data loaded.</p>
        ) : (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-navy-100 px-3 py-1 text-xs font-semibold text-navy-800">
                {licData.edition ?? 'Edition unknown'}
              </span>
              {licData.estimated_annual_spend != null ? (
                <span className="text-sm text-slate-600">
                  Est. spend:{' '}
                  <span className="font-semibold text-navy-900">
                    {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 0 }).format(licData.estimated_annual_spend)}
                  </span>
                </span>
              ) : null}
            </div>
            <div className="max-h-52 space-y-2 overflow-auto pr-2">
              {licenseBars.length === 0 ? (
                <p className="text-xs text-slate-400">No core license rows to display.</p>
              ) : (
                licenseBars.map((l) => <LicenseUtilBar key={l.type} label={l.type} used={l.used} total={l.total} />)
              )}
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <div className="flex items-center gap-3">
            <TrendingUp className="h-6 w-6 text-navy-700" />
            <div>
              <h2 className="text-lg font-semibold text-navy-900">Platform adoption</h2>
              <p className="text-sm text-slate-600">Latest user snapshot (org-level)</p>
            </div>
          </div>
          {!latestVelocity ? (
            <p className="mt-4 text-sm text-slate-500">No velocity snapshots available.</p>
          ) : (
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Human / internal</dt>
                <dd className="text-lg font-semibold text-navy-900">
                  {(latestVelocity.internal_active_count ?? latestVelocity.active_user_count).toLocaleString()}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">System</dt>
                <dd className="text-lg font-semibold text-slate-700">{(latestVelocity.system_user_count ?? 0).toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">External</dt>
                <dd className="text-lg font-semibold text-teal-800">{(latestVelocity.external_active_count ?? 0).toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">New / deactivated (month)</dt>
                <dd className="text-lg font-semibold text-slate-800">
                  +{latestVelocity.new_users_this_month} / −{latestVelocity.deactivated_this_month}
                </dd>
              </div>
            </dl>
          )}
        </section>

        <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
          <div className="flex items-center gap-3">
            <Shield className="h-6 w-6 text-navy-700" />
            <div>
              <h2 className="text-lg font-semibold text-navy-900">Role &amp; profile distribution</h2>
              <p className="text-sm text-slate-600">From latest snapshot (org-level)</p>
            </div>
          </div>
          {!latestVelocity ? (
            <p className="mt-4 text-sm text-slate-500">No role or profile data.</p>
          ) : (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">By role</p>
                <ul className="max-h-40 space-y-1 overflow-auto text-xs">
                  {roleTop.length === 0 ? (
                    <li className="text-slate-400">No role data</li>
                  ) : (
                    roleTop.map(([name, count]) => (
                      <li key={name} className="flex justify-between gap-2">
                        <span className="truncate text-slate-700">{name}</span>
                        <span className="font-semibold text-slate-900">{count}</span>
                      </li>
                    ))
                  )}
                </ul>
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">By profile</p>
                <ul className="max-h-40 space-y-1 overflow-auto text-xs">
                  {profileTop.length === 0 ? (
                    <li className="text-slate-400">No profile data</li>
                  ) : (
                    profileTop.map(([name, count]) => (
                      <li key={name} className="flex justify-between gap-2">
                        <span className="truncate text-slate-700">{name}</span>
                        <span className="font-semibold text-slate-900">{count}</span>
                      </li>
                    ))
                  )}
                </ul>
              </div>
            </div>
          )}
        </section>
      </div>

      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center gap-3">
          <Package className="h-6 w-6 text-navy-700" />
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Installed packages</h2>
            <p className="text-sm text-slate-600">{packageRows.length.toLocaleString()} packages for this connection</p>
          </div>
        </div>
        {componentsQuery.isError ? (
          <p className="mt-4 text-sm text-red-600">Could not load packages.</p>
        ) : packageRows.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">No installed packages found for this connection.</p>
        ) : (
          <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {packageRows.map((p: MetadataComponent) => (
              <li
                key={p.id}
                className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-sm text-slate-800"
              >
                <span className="font-medium text-navy-900">{p.label?.trim() || p.api_name}</span>
                <p className="font-mono text-xs text-slate-500">{p.api_name}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
