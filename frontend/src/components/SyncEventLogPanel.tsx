import { useEffect, useRef, useState, useMemo } from 'react'
import { Check, ChevronDown, ChevronUp, Loader2, AlertTriangle, XCircle } from 'lucide-react'
import clsx from 'clsx'
import type { SyncEvent } from '@/types'
import type { SyncStreamStatus } from '@/hooks/useSyncEventStream'

const PHASE_LABELS: Record<string, string> = {
  objects: 'Data Objects',
  mdapi_retrieve: 'Metadata Retrieve',
  mdapi_parse: 'Metadata Parse',
  automations: 'Automations',
  code: 'Code Assets',
  permissions: 'Security',
  ui_components: 'UI Components',
  installed_packages: 'Packages',
  custom_metadata_types: 'Custom Metadata',
  licensing: 'Licensing',
  user_velocity: 'Adoption',
  entities: 'Org Hierarchy',
  graph_build: 'Dependency Graph',
  classification: 'Classification',
  vectorization: 'Vectorization',
}

const PHASE_ORDER = Object.keys(PHASE_LABELS)

interface PhaseState {
  status: 'waiting' | 'running' | 'done' | 'error'
  count?: number
}

function derivePhaseStates(events: SyncEvent[]): Record<string, PhaseState> {
  const states: Record<string, PhaseState> = {}
  for (const phase of PHASE_ORDER) {
    states[phase] = { status: 'waiting' }
  }
  for (const e of events) {
    if (!e.phase) continue
    if (e.event_type === 'phase_start') {
      states[e.phase] = { status: 'running' }
    } else if (e.event_type === 'phase_complete') {
      const count = (e.detail?.count ??
        e.detail?.file_count ??
        e.detail?.edge_count ??
        e.detail?.classified_count ??
        e.detail?.chunk_count ??
        0) as number
      states[e.phase] = { status: 'done', count }
    } else if (e.event_type === 'error') {
      states[e.phase] = { status: 'error' }
    }
  }
  return states
}

function PhaseChip({ name, state }: { name: string; state: PhaseState }) {
  const label = PHASE_LABELS[name] ?? name

  return (
    <div
      className={clsx(
        'flex min-w-0 items-center gap-1.5 overflow-hidden rounded-lg border px-2.5 py-2 text-xs transition-all duration-300',
        state.status === 'waiting' && 'border-slate-200 bg-slate-50 text-slate-400',
        state.status === 'running' && 'border-sky-300 bg-sky-50 text-sky-800 shadow-sm',
        state.status === 'done' && 'border-emerald-200 bg-emerald-50 text-emerald-800',
        state.status === 'error' && 'border-red-200 bg-red-50 text-red-800',
      )}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">
        {state.status === 'waiting' && <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />}
        {state.status === 'running' && <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-600" />}
        {state.status === 'done' && <Check className="h-3.5 w-3.5 text-emerald-600" />}
        {state.status === 'error' && <XCircle className="h-3.5 w-3.5 text-red-500" />}
      </span>
      <span className="truncate font-medium">{label}</span>
      {state.status === 'done' && state.count != null && state.count > 0 && (
        <span className="ml-auto shrink-0 tabular-nums font-semibold">
          {state.count.toLocaleString()}
        </span>
      )}
    </div>
  )
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

interface Props {
  events: SyncEvent[]
  status: SyncStreamStatus
  onDismiss?: () => void
}

export function SyncEventLogPanel({ events, status, onDismiss: _onDismiss }: Props) {
  const [logOpen, setLogOpen] = useState(true)
  const logRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const prevEventCount = useRef(0)

  const phaseStates = useMemo(() => derivePhaseStates(events), [events])
  const doneCount = PHASE_ORDER.filter((p) => phaseStates[p]?.status === 'done').length
  const totalPhases = PHASE_ORDER.length
  const pct = totalPhases > 0 ? Math.round((doneCount / totalPhases) * 100) : 0

  const isRunning = status === 'running' || status === 'connecting'
  const isCompleted = status === 'completed'
  const isFailed = status === 'failed'
  const isIdle = status === 'idle'

  const elapsed = useMemo(() => {
    const start = events.find((e) => e.event_type === 'run_start')
    if (!start?.created_at) return null
    const end = [...events].reverse().find(
      (e) => e.event_type === 'run_complete' || (e.event_type === 'error' && e.severity === 'error'),
    )
    const endTime = end?.created_at ? new Date(end.created_at).getTime() : Date.now()
    const ms = endTime - new Date(start.created_at).getTime()
    if (ms < 60_000) return `${Math.round(ms / 1000)}s`
    return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
  }, [events, status])

  useEffect(() => {
    if (events.length > prevEventCount.current && autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
    prevEventCount.current = events.length
  }, [events.length, autoScroll])

  const handleLogScroll = () => {
    if (!logRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = logRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
  }

  if (isIdle && events.length === 0) return null

  return (
    <div
      className={clsx(
        'rounded-xl border transition-all duration-500 overflow-hidden',
        isRunning && 'border-sky-200 bg-gradient-to-br from-sky-50/80 to-white shadow-sm',
        isCompleted && 'border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white shadow-sm',
        isFailed && 'border-red-200 bg-gradient-to-br from-red-50/80 to-white shadow-sm',
        isIdle && 'border-slate-200 bg-white',
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {isRunning && 'Syncing metadata…'}
            {isCompleted && 'Sync complete'}
            {isFailed && 'Sync failed'}
            {isIdle && 'Sync Log'}
          </p>
          <p className="text-xs text-slate-500">
            {isRunning && `${doneCount} of ${totalPhases} phases complete`}
            {isCompleted && `All ${totalPhases} phases complete`}
            {isFailed && 'An error occurred during sync'}
            {elapsed && ` · ${elapsed}`}
          </p>
        </div>
        {isRunning && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full bg-sky-500 transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs tabular-nums text-slate-500">{pct}%</span>
          </div>
        )}
      </div>

      {/* Phase pills */}
      <div className="grid grid-cols-2 gap-2 px-5 pb-3 sm:grid-cols-3 lg:grid-cols-5">
        {PHASE_ORDER.map((phase) => (
          <PhaseChip key={phase} name={phase} state={phaseStates[phase]} />
        ))}
      </div>

      {/* Sync Log */}
      <div className="border-t border-slate-200/60">
        <button
          type="button"
          onClick={() => setLogOpen(!logOpen)}
          className="flex w-full items-center justify-between px-5 py-2.5 text-xs font-medium text-slate-500 hover:bg-slate-50"
        >
          <span>Sync Log</span>
          {logOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>

        {logOpen && (
          <div className="relative">
            <div
              ref={logRef}
              onScroll={handleLogScroll}
              className="max-h-72 overflow-y-auto bg-slate-900 px-4 py-3 font-mono text-xs leading-relaxed text-slate-300"
            >
              {events.map((e, i) => {
                if (e.event_type === 'phase_start' || e.event_type === 'phase_complete') {
                  return (
                    <div key={i} className="my-1">
                      <span className="text-slate-500">{formatTimestamp(e.created_at)}  </span>
                      <span
                        className={clsx(
                          'font-semibold',
                          e.event_type === 'phase_complete' ? 'text-emerald-400' : 'text-sky-400',
                        )}
                      >
                        {e.message}
                      </span>
                    </div>
                  )
                }
                if (e.event_type === 'item') {
                  return (
                    <div key={i} className="ml-4 text-slate-500">
                      <span className="text-slate-600">{formatTimestamp(e.created_at)}  </span>
                      <span className="text-slate-400">{'▸ '}{e.message}</span>
                    </div>
                  )
                }
                if (e.event_type === 'warning') {
                  return (
                    <div key={i} className="my-0.5 flex items-start gap-1.5">
                      <span className="text-slate-500">{formatTimestamp(e.created_at)}  </span>
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" />
                      <span className="text-amber-400">{e.message}</span>
                    </div>
                  )
                }
                if (e.event_type === 'error') {
                  return (
                    <div key={i} className="my-0.5 flex items-start gap-1.5">
                      <span className="text-slate-500">{formatTimestamp(e.created_at)}  </span>
                      <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-red-400" />
                      <span className="text-red-400">{e.message}</span>
                    </div>
                  )
                }
                return (
                  <div key={i} className="my-0.5">
                    <span className="text-slate-500">{formatTimestamp(e.created_at)}  </span>
                    <span>{e.message}</span>
                  </div>
                )
              })}
              {isRunning && (
                <div className="my-1 flex items-center gap-1.5">
                  <Loader2 className="h-3 w-3 animate-spin text-sky-400" />
                </div>
              )}
            </div>
            {!autoScroll && (
              <button
                type="button"
                onClick={() => {
                  setAutoScroll(true)
                  logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
                }}
                className="absolute bottom-2 right-4 rounded-md bg-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-600"
              >
                Jump to bottom
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
