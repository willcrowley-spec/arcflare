import { useCallback, useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { BarChart3, FileSpreadsheet, KeyRound, Link2, RefreshCw, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { StatusBadge } from '@/components/StatusBadge'
import { ConnectPlatformModal } from '@/components/ConnectPlatformModal'
import { EmptyState, ErrorState, LoadingState } from '@/components/EmptyState'
import { SyncProgressModal } from '@/components/SyncProgressModal'
import {
  useConnections,
  useDeleteConnection,
  useInitiateSalesforce,
  useReauthConnection,
  useSyncConnection,
} from '@/hooks/useApi'
import { useSyncEventStream } from '@/hooks/useSyncEventStream'
import type { PlatformConnection } from '@/types'

function platformTypeToKey(raw: string | undefined): string {
  return (raw ?? '').toUpperCase()
}

function platformLabelFromType(raw: string | undefined): string {
  const key = platformTypeToKey(raw)
  const labels: Record<string, string> = {
    SALESFORCE: 'Salesforce',
    HUBSPOT: 'HubSpot',
    NETSUITE: 'NetSuite',
    MULESOFT: 'MuleSoft',
    CONFLUENCE: 'Confluence',
  }
  if (labels[key]) return labels[key]
  if (!raw) return 'Salesforce'
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase()
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

function formatUnknownError(error: unknown, fallback: string): string {
  if (error instanceof Error) return error.message
  return fallback
}

export default function AnalysisPage() {
  const navigate = useNavigate()
  const [syncingId, setSyncingId] = useState<string | null>(null)
  const [activeSyncId, setActiveSyncId] = useState<string | null>(null)
  const [showSyncModal, setShowSyncModal] = useState(false)
  const [showConnectModal, setShowConnectModal] = useState(false)
  const { events: syncEvents, status: syncStreamStatus, reset: resetSyncStream } = useSyncEventStream(activeSyncId)
  const qc = useQueryClient()

  const connectionsQuery = useConnections()
  const initiateSalesforce = useInitiateSalesforce()
  const syncConnection = useSyncConnection()
  const deleteConnection = useDeleteConnection()
  const reauthConnection = useReauthConnection()

  const connections = connectionsQuery.data?.items ?? []

  useEffect(() => {
    if (!activeSyncId && connections.length > 0) {
      const active = connections.find((c) => {
        const s = String(c.status).toLowerCase()
        return s === 'syncing' || s === 'pending'
      })
      if (active) {
        setActiveSyncId(String(active.id))
      }
    }
  }, [connections, activeSyncId])

  useEffect(() => {
    if (syncStreamStatus === 'completed' || syncStreamStatus === 'failed') {
      void qc.invalidateQueries({ queryKey: ['connections'] })
      void qc.invalidateQueries({ queryKey: ['metadata'] })
      void qc.invalidateQueries({ queryKey: ['organization'] })
    }
  }, [syncStreamStatus, qc])

  const hasConnections = connections.length > 0

  const onSelectPlatform = useCallback(
    (platformId: string) => {
      if (platformId === 'salesforce') {
        initiateSalesforce.mutate(undefined, {
          onSuccess: (data) => {
            window.location.href = data.authorization_url
          },
        })
      }
      setShowConnectModal(false)
    },
    [initiateSalesforce],
  )

  const onReauth = useCallback(
    (id: string) => {
      reauthConnection.mutate(id)
    },
    [reauthConnection],
  )

  const onSync = useCallback(
    (id: string) => {
      resetSyncStream()
      setSyncingId(id)
      setActiveSyncId(id)
      setShowSyncModal(true)
      syncConnection.mutate(id, {
        onSettled: () => setSyncingId(null),
      })
    },
    [syncConnection, resetSyncStream],
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

  const pageLoading = connectionsQuery.isLoading && !connectionsQuery.data
  const pageError = connectionsQuery.isError
  const pageErrorMessage = formatUnknownError(
    connectionsQuery.isError ? (connectionsQuery as { error?: unknown }).error : undefined,
    'Request failed',
  )

  const connectButton = (
    <button
      type="button"
      disabled={initiateSalesforce.isPending}
      onClick={() => setShowConnectModal(true)}
      className="inline-flex items-center justify-center gap-2 self-start rounded-lg bg-navy-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm ring-1 ring-navy-900/10 hover:bg-navy-800 disabled:opacity-60"
    >
      <Link2 className="h-4 w-4" />
      {initiateSalesforce.isPending ? 'Connecting…' : '+ Add Connection'}
    </button>
  )

  if (pageLoading) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Analysis</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Unified visibility across metadata, operational records, and business documentation with live platform
            health.
          </p>
        </div>
        <LoadingState message="Loading connections…" />
      </div>
    )
  }

  if (pageError) {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Analysis</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Unified visibility across metadata, operational records, and business documentation with live platform
            health.
          </p>
        </div>
        <ErrorState message={pageErrorMessage} />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-navy-900">Analysis</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Unified visibility across metadata, operational records, and business documentation with live platform
            health.
          </p>
        </div>
        {connectButton}
      </div>

      <ConnectPlatformModal
        open={showConnectModal}
        onClose={() => setShowConnectModal(false)}
        onSelectPlatform={onSelectPlatform}
        connecting={initiateSalesforce.isPending}
      />

      {initiateSalesforce.isError && (
        <p className="text-sm text-red-600">
          {initiateSalesforce.error instanceof Error ? initiateSalesforce.error.message : 'Could not start OAuth.'}
        </p>
      )}

      <SyncProgressModal
        open={showSyncModal && !!activeSyncId}
        onClose={() => setShowSyncModal(false)}
        events={syncEvents}
        streamStatus={syncStreamStatus}
        platformLabel={
          activeSyncId
            ? platformLabelFromType(
                connections.find((c) => String(c.id) === activeSyncId)?.platform_type ??
                  (connections.find((c) => String(c.id) === activeSyncId)?.platform as string | undefined),
              )
            : undefined
        }
      />

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
              icon={<Link2 className="mx-auto h-10 w-10" />}
              title="Connect your first platform to get started"
              description="Link Salesforce to index org metadata, then run a sync from the platform card below."
              action={connectButton}
            />
          </div>
        ) : (
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {connections.map((c: PlatformConnection) => {
              const label = platformLabelFromType(c.platform_type ?? (c.platform as string | undefined))
              const badge = connectionBadgeStatus(String(c.status))
              const syncingThis = syncingId === String(c.id) && syncConnection.isPending
              return (
                <div
                  key={String(c.id)}
                  role="link"
                  tabIndex={0}
                  onClick={() => navigate(`/platforms/${String(c.id)}`)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      navigate(`/platforms/${String(c.id)}`)
                    }
                  }}
                  className="cursor-pointer rounded-lg border border-slate-100 bg-slate-50/60 p-4 ring-1 ring-slate-900/5 transition-colors hover:border-navy-200"
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
                  <div className="mt-4 flex flex-wrap gap-2" onClick={(e) => e.stopPropagation()}>
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
                      disabled={reauthConnection.isPending}
                      onClick={() => onReauth(String(c.id))}
                      className="inline-flex items-center gap-1.5 rounded-md bg-white px-2.5 py-1.5 text-xs font-semibold text-amber-800 ring-1 ring-amber-200 hover:bg-amber-50 disabled:opacity-50"
                    >
                      <KeyRound className="h-3.5 w-3.5" />
                      Re-authenticate
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

      <section className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 p-8 text-center">
        <BarChart3 className="mx-auto h-10 w-10 text-slate-300" />
        <h3 className="mt-3 text-sm font-semibold text-navy-900">Cross-platform ecosystem analysis</h3>
        <p className="mt-1 text-sm text-slate-500">
          Higher-level metrics and insights across all connected platforms will appear here as they become available.
        </p>
      </section>
    </div>
  )
}
