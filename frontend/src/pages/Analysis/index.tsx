import { useCallback, useMemo, useState } from 'react'
import {
  Database,
  FileSpreadsheet,
  FileText,
  Layers,
  Link2,
  RefreshCw,
  Search as SearchIcon,
  Trash2,
} from 'lucide-react'
import clsx from 'clsx'
import { DataTable, type ColumnDef } from '@/components/DataTable'
import { SearchBar } from '@/components/SearchBar'
import { StatusBadge } from '@/components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import {
  useConnections,
  useDeleteConnection,
  useInitiateSalesforce,
  useMetadataObjects,
  useSyncConnection,
} from '@/hooks/useApi'
import type { MetadataObject, PlatformConnection } from '@/types'

type SourceFilter = 'ALL' | 'SALESFORCE' | 'HUBSPOT' | 'NETSUITE' | 'MULESOFT' | 'CONFLUENCE'

type TabKey = 'ALL' | 'Metadata' | 'DATA' | 'DOCS'

type AnalysisRow = MetadataObject & {
  kind: 'Metadata' | 'Data Record' | 'Business Doc'
  platformLabel: string
  rowStatus: string
  lastUpdatedLabel: string
}

const platformStyles: Record<string, string> = {
  Salesforce: 'bg-sky-50 text-sky-900 ring-sky-200',
  HubSpot: 'bg-orange-50 text-orange-900 ring-orange-200',
  NetSuite: 'bg-emerald-50 text-emerald-900 ring-emerald-200',
  MuleSoft: 'bg-violet-50 text-violet-900 ring-violet-200',
  Confluence: 'bg-blue-50 text-blue-900 ring-blue-200',
}

function platformTypeToSourceKey(raw: string | undefined): SourceFilter {
  const u = (raw ?? '').toUpperCase()
  const map: Record<string, SourceFilter> = {
    SALESFORCE: 'SALESFORCE',
    HUBSPOT: 'HUBSPOT',
    NETSUITE: 'NETSUITE',
    MULESOFT: 'MULESOFT',
    CONFLUENCE: 'CONFLUENCE',
  }
  return map[u] ?? 'SALESFORCE'
}

function platformLabelFromType(raw: string | undefined): string {
  const key = platformTypeToSourceKey(raw)
  const labels: Record<SourceFilter, string> = {
    ALL: 'Platform',
    SALESFORCE: 'Salesforce',
    HUBSPOT: 'HubSpot',
    NETSUITE: 'NetSuite',
    MULESOFT: 'MuleSoft',
    CONFLUENCE: 'Confluence',
  }
  return labels[key] ?? (raw ? raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase() : 'Salesforce')
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

function relativeOrAbsolute(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const diffMs = Date.now() - d.getTime()
  const mins = Math.round(diffMs / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins} min${mins === 1 ? '' : 's'} ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 48) return `${hrs} hr${hrs === 1 ? '' : 's'} ago`
  return formatTimestamp(iso)
}

function rowKind(row: MetadataObject): AnalysisRow['kind'] {
  if (row.type === 'DATA_RECORD') return 'Data Record'
  if (row.type === 'BUSINESS_DOC') return 'Business Doc'
  if (row.record_count > 0) return 'Data Record'
  return 'Metadata'
}

function tabMatches(tab: TabKey, kind: AnalysisRow['kind']): boolean {
  if (tab === 'ALL') return true
  if (tab === 'Metadata') return kind === 'Metadata'
  if (tab === 'DATA') return kind === 'Data Record'
  if (tab === 'DOCS') return kind === 'Business Doc'
  return true
}

function connectionIdsForSource(connections: PlatformConnection[], source: SourceFilter): string[] | null {
  if (source === 'ALL') return null
  return connections
    .filter((c) => platformTypeToSourceKey(c.platform_type ?? c.platform) === source)
    .map((c) => String(c.id))
}

function formatUnknownError(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message
  return fallback
}

function KindIcon({ kind }: { kind: AnalysisRow['kind'] }) {
  if (kind === 'Metadata') return <Layers className="h-4 w-4 text-navy-600" />
  if (kind === 'Data Record') return <Database className="h-4 w-4 text-emerald-600" />
  return <FileText className="h-4 w-4 text-orange-600" />
}

function useAnalysisRows(
  items: MetadataObject[] | undefined,
  connections: PlatformConnection[] | undefined,
): AnalysisRow[] {
  return useMemo(() => {
    const connList = connections ?? []
    const connPlatform = new Map<string, string>()
    for (const c of connList) {
      connPlatform.set(String(c.id), c.platform_type ?? (c.platform as string | undefined) ?? 'salesforce')
    }

    return (items ?? []).map((obj) => {
      const kind = rowKind(obj)
      const cid = obj.connection_id ? String(obj.connection_id) : ''
      const pt = cid ? connPlatform.get(cid) : undefined
      const platformLabel =
        obj.platform != null ? platformLabelFromType(String(obj.platform)) : platformLabelFromType(pt)

      const rowStatus =
        obj.status ??
        (obj.record_count > 0 && (obj.field_count ?? 0) > 0 ? 'CLEAN' : obj.record_count > 0 ? 'ANALYZING' : 'PENDING')

      const lastIso = obj.last_synced_at ?? obj.last_updated_at
      const lastUpdatedLabel = relativeOrAbsolute(lastIso)

      return {
        ...obj,
        field_count: obj.field_count ?? 0,
        record_count: obj.record_count ?? 0,
        is_custom: obj.is_custom ?? false,
        has_triggers: obj.has_triggers ?? false,
        has_flows: obj.has_flows ?? false,
        has_validation_rules: obj.has_validation_rules ?? false,
        kind,
        platformLabel,
        rowStatus,
        lastUpdatedLabel,
      }
    })
  }, [connections, items])
}

export default function AnalysisPage() {
  const [tab, setTab] = useState<TabKey>('ALL')
  const [source, setSource] = useState<SourceFilter>('ALL')
  const [q, setQ] = useState('')
  const [syncingId, setSyncingId] = useState<string | null>(null)

  const connectionsQuery = useConnections()
  const initiateSalesforce = useInitiateSalesforce()
  const syncConnection = useSyncConnection()
  const deleteConnection = useDeleteConnection()

  const connections = connectionsQuery.data?.items ?? []
  const hasConnections = connections.length > 0

  const metadataQuery = useMetadataObjects({
    page: 1,
    page_size: 200,
    q: q.trim() || undefined,
  })

  const analysisRows = useAnalysisRows(metadataQuery.data?.items, connections)

  const filtered = useMemo(() => {
    const allowedConnIds = connectionIdsForSource(connections, source)
    return analysisRows.filter((r) => {
      if (!tabMatches(tab, r.kind)) return false
      if (allowedConnIds && allowedConnIds.length > 0) {
        if (!r.connection_id || !allowedConnIds.includes(String(r.connection_id))) return false
      }
      if (allowedConnIds && allowedConnIds.length === 0 && source !== 'ALL') return false
      return true
    })
  }, [analysisRows, connections, source, tab])

  const anySyncInFlight = useMemo(() => {
    return connections.some((c) => {
      const s = String(c.status).toLowerCase()
      return s === 'pending' || s === 'syncing'
    })
  }, [connections])

  const onConnectSalesforce = useCallback(() => {
    initiateSalesforce.mutate(undefined, {
      onSuccess: (data) => {
        window.location.href = data.authorization_url
      },
    })
  }, [initiateSalesforce])

  const onSync = useCallback(
    (id: string) => {
      setSyncingId(id)
      syncConnection.mutate(id, {
        onSettled: () => setSyncingId(null),
      })
    },
    [syncConnection],
  )

  const onDelete = useCallback(
    (id: string) => {
      if (!window.confirm('Remove this connection? Indexed metadata for this org may be cleared on next sync.')) {
        return
      }
      deleteConnection.mutate(id)
    },
    [deleteConnection],
  )

  const columns: ColumnDef<AnalysisRow>[] = useMemo(
    () => [
      {
        id: 'name',
        header: 'Entity / Document',
        sortValue: (r) => r.api_name,
        cell: (r) => (
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-50 ring-1 ring-slate-200/80">
              <KindIcon kind={r.kind} />
            </span>
            <div>
              <p className="font-medium text-slate-900">{r.label || r.api_name}</p>
              <p className="font-mono text-xs text-slate-500">{r.api_name}</p>
              <p className="text-xs text-slate-500">{r.kind}</p>
            </div>
          </div>
        ),
      },
      {
        id: 'type',
        header: 'Type',
        sortValue: (r) => r.object_type ?? r.kind,
        cell: (r) => (
          <span className="text-slate-700">
            {r.object_type ?? r.kind}
            {r.is_custom ? <span className="ml-1 text-xs text-slate-400">(custom)</span> : null}
          </span>
        ),
      },
      {
        id: 'platform',
        header: 'Platform',
        sortValue: (r) => r.platformLabel,
        cell: (r) => (
          <span
            className={clsx(
              'inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset',
              platformStyles[r.platformLabel] ?? 'bg-slate-50 text-slate-800 ring-slate-200',
            )}
          >
            {r.platformLabel}
          </span>
        ),
      },
      {
        id: 'counts',
        header: 'Fields / Records',
        sortValue: (r) => r.field_count + r.record_count,
        cell: (r) => (
          <span className="text-slate-700">
            {r.field_count.toLocaleString()} fields · {r.record_count.toLocaleString()} records
          </span>
        ),
      },
      {
        id: 'automation',
        header: 'Automation',
        sortValue: (r) => Number(r.has_triggers) + Number(r.has_flows) + Number(r.has_validation_rules),
        cell: (r) => {
          const bits = [
            r.has_triggers ? 'Triggers' : '',
            r.has_flows ? 'Flows' : '',
            r.has_validation_rules ? 'Validation rules' : '',
          ].filter(Boolean)
          return <span className="text-xs text-slate-600">{bits.length ? bits.join(' · ') : '—'}</span>
        },
      },
      {
        id: 'status',
        header: 'Status',
        sortValue: (r) => r.rowStatus,
        cell: (r) => <StatusBadge status={r.rowStatus} />,
      },
      {
        id: 'updated',
        header: 'Last sync',
        sortValue: (r) => r.last_synced_at ?? r.last_updated_at ?? '',
        cell: (r) => <span className="text-slate-600">{r.lastUpdatedLabel}</span>,
      },
    ],
    [],
  )

  const pageLoading = connectionsQuery.isLoading || (hasConnections && metadataQuery.isLoading)
  const pageError = connectionsQuery.isError || metadataQuery.isError
  const pageErrorMessage = formatUnknownError(
    connectionsQuery.isError
      ? (connectionsQuery as { error?: unknown }).error
      : (metadataQuery as { error?: unknown }).error,
    'Request failed',
  )

  if (pageLoading && !connectionsQuery.data && !metadataQuery.data) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Analysis</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Unified visibility across metadata, operational records, and business documentation with live platform
            health.
          </p>
        </div>
        <LoadingState message="Loading connections and metadata…" />
      </div>
    )
  }

  if (pageError) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Analysis</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Unified visibility across metadata, operational records, and business documentation with live platform
            health.
          </p>
        </div>
        <ErrorState message={pageErrorMessage} />
      </div>
    )
  }

  const connectButton = (
    <button
      type="button"
      disabled={initiateSalesforce.isPending}
      onClick={onConnectSalesforce}
      className="inline-flex items-center justify-center gap-2 self-start rounded-lg bg-navy-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm ring-1 ring-navy-900/10 hover:bg-navy-800 disabled:opacity-60"
    >
      <Link2 className="h-4 w-4" />
      {initiateSalesforce.isPending ? 'Connecting…' : '+ Connect Salesforce'}
    </button>
  )

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-navy-900">Analysis</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Unified visibility across metadata, operational records, and business documentation with live platform
            health.
          </p>
        </div>
        {connectButton}
      </div>

      {initiateSalesforce.isError && (
        <p className="text-sm text-red-600">
          {initiateSalesforce.error instanceof Error ? initiateSalesforce.error.message : 'Could not start OAuth.'}
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {(
            [
              ['ALL', 'All'],
              ['Metadata', 'Metadata'],
              ['DATA', 'Data Records'],
              ['DOCS', 'Business Docs'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={clsx(
                'rounded-full px-4 py-1.5 text-sm font-medium ring-1 ring-inset transition-colors',
                tab === key
                  ? 'bg-navy-800 text-white ring-navy-800'
                  : 'bg-white text-slate-700 ring-slate-200 hover:bg-slate-50',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
          <SearchBar value={q} onChange={setQ} placeholder="Search objects by API name or label…" className="flex-1" />
          <div className="flex items-center gap-2 sm:min-w-[200px]">
            <SearchIcon className="hidden h-4 w-4 text-slate-400 sm:block" aria-hidden />
            <label className="sr-only" htmlFor="source-filter">
              Source filter
            </label>
            <select
              id="source-filter"
              value={source}
              onChange={(e) => setSource(e.target.value as SourceFilter)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-navy-400 focus:outline-none focus:ring-2 focus:ring-navy-200"
            >
              <option value="ALL">All sources</option>
              <option value="SALESFORCE">Salesforce</option>
              <option value="HUBSPOT">HubSpot</option>
              <option value="NETSUITE">NetSuite</option>
              <option value="MULESOFT">MuleSoft</option>
              <option value="CONFLUENCE">Confluence</option>
            </select>
          </div>
        </div>
      </div>

      {!hasConnections ? (
        <EmptyState
          icon={<Link2 className="mx-auto h-10 w-10" />}
          title="Connect your first platform to get started"
          description="Link Salesforce to index org metadata, then run a sync from the platform card below."
          action={connectButton}
        />
      ) : metadataQuery.isLoading ? (
        <div className="rounded-xl border border-slate-200/80 bg-white p-8 shadow-sm ring-1 ring-slate-900/5">
          <LoadingState message="Loading metadata objects…" />
        </div>
      ) : metadataQuery.isError ? (
        <ErrorState
          message={formatUnknownError((metadataQuery as { error?: unknown }).error, 'Failed to load metadata.')}
        />
      ) : filtered.length === 0 && anySyncInFlight ? (
        <div className="rounded-xl border border-amber-200/80 bg-amber-50/40 p-8 shadow-sm ring-1 ring-amber-900/10">
          <LoadingState message="Metadata sync is running — objects will appear here when indexing completes." />
        </div>
      ) : filtered.length === 0 && (metadataQuery.data?.items?.length ?? 0) === 0 ? (
        <div className="rounded-xl border border-slate-200/80 bg-white p-8 text-center shadow-sm ring-1 ring-slate-900/5">
          <p className="text-sm font-medium text-navy-900">No metadata indexed yet</p>
          <p className="mt-1 text-sm text-slate-600">Run Sync on your Salesforce connection to pull describe metadata into Arcflare.</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-slate-200/80 bg-white p-8 text-center shadow-sm ring-1 ring-slate-900/5">
          <p className="text-sm font-medium text-navy-900">No metadata objects match your filters</p>
          <p className="mt-1 text-sm text-slate-600">Try another search, tab, or source — or run Sync on your connection.</p>
        </div>
      ) : (
        <DataTable columns={columns} rows={filtered} rowKey={(r) => r.id} pageSize={8} />
      )}

      <section className="rounded-xl border border-slate-200/80 bg-white p-6 shadow-sm ring-1 ring-slate-900/5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-navy-900">Platform Sources</h2>
            <p className="text-sm text-slate-600">Live connection inventory and entity coverage</p>
          </div>
          <FileSpreadsheet className="h-8 w-8 text-slate-300" aria-hidden />
        </div>

        {connectionsQuery.isLoading ? (
          <div className="mt-6">
            <LoadingState message="Loading connections…" />
          </div>
        ) : connectionsQuery.isError ? (
          <div className="mt-6">
            <ErrorState
              message={formatUnknownError((connectionsQuery as { error?: unknown }).error, 'Failed to load connections.')}
            />
          </div>
        ) : !hasConnections ? (
          <div className="mt-6">
            <EmptyState
              title="No connections yet"
              description="Connect Salesforce to populate this inventory."
              action={connectButton}
            />
          </div>
        ) : (
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {connections.map((c) => {
              const label = platformLabelFromType(c.platform_type ?? (c.platform as string | undefined))
              const badge = connectionBadgeStatus(String(c.status))
              const syncingThis = syncingId === String(c.id) && syncConnection.isPending
              return (
                <div
                  key={String(c.id)}
                  className="rounded-lg border border-slate-100 bg-slate-50/60 p-4 ring-1 ring-slate-900/5"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-navy-900">{c.label ?? label}</p>
                      <p className="mt-0.5 text-xs font-medium text-slate-500">{label}</p>
                      {c.instance_url ? (
                        <p className="mt-1 truncate text-xs text-slate-500" title={c.instance_url}>
                          {c.instance_url}
                        </p>
                      ) : null}
                      <p className="mt-2 text-xs text-slate-500">
                        {(c.entity_count ?? 0).toLocaleString()} entities indexed
                      </p>
                      <p className="mt-0.5 text-xs text-slate-400">
                        Last sync: {relativeOrAbsolute(c.last_sync_at ?? null)}
                      </p>
                    </div>
                    <StatusBadge status={badge} />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={syncConnection.isPending}
                      onClick={() => onSync(String(c.id))}
                      className="inline-flex items-center gap-1.5 rounded-md bg-white px-2.5 py-1.5 text-xs font-semibold text-navy-800 ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-50"
                    >
                      <RefreshCw className={clsx('h-3.5 w-3.5', syncingThis && 'animate-spin')} />
                      {syncingThis ? 'Syncing…' : 'Sync'}
                    </button>
                    <button
                      type="button"
                      disabled={deleteConnection.isPending}
                      onClick={() => onDelete(String(c.id))}
                      className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold text-red-700 ring-1 ring-red-200 hover:bg-red-50 disabled:opacity-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Remove
                    </button>
                  </div>
                  {syncConnection.isError && syncingId === String(c.id) ? (
                    <p className="mt-2 text-xs text-red-600">
                      {syncConnection.error instanceof Error ? syncConnection.error.message : 'Sync failed'}
                    </p>
                  ) : null}
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
