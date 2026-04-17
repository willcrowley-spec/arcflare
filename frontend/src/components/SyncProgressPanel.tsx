import { useEffect, useRef, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import clsx from 'clsx'

interface PhaseInfo {
  status: string
  count: number
}

interface SyncProgressData {
  status: string
  started_at: string | null
  completed_at: string | null
  error: string | null
  phases?: Record<string, PhaseInfo>
}

const PHASE_LABELS: Record<string, string> = {
  objects: 'Data Objects',
  automations: 'Automations',
  code: 'Code',
  permissions: 'Permissions',
  ui_components: 'UI Components',
  installed_packages: 'Packages',
  licensing: 'Licensing',
  user_velocity: 'User Velocity',
  entities: 'Org Hierarchy',
  classification: 'Classification',
  vectorization: 'Vectorization',
}

const PHASE_ORDER = Object.keys(PHASE_LABELS)

function PhaseChip({ name, info }: { name: string; info: PhaseInfo }) {
  const label = PHASE_LABELS[name] ?? name
  const isWaiting = info.status === 'waiting'
  const isPulling = info.status === 'pulling'
  const isDone = info.status === 'done'

  return (
    <div
      className={clsx(
        'flex min-w-0 items-center gap-1.5 overflow-hidden rounded-lg border px-2.5 py-2 text-xs transition-all duration-300',
        isWaiting && 'border-slate-200 bg-slate-50 text-slate-400',
        isPulling && 'border-sky-300 bg-sky-50 text-sky-800 shadow-sm',
        isDone && 'border-emerald-200 bg-emerald-50 text-emerald-800',
      )}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">
        {isWaiting && <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />}
        {isPulling && <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-600" />}
        {isDone && <Check className="h-3.5 w-3.5 text-emerald-600" />}
      </span>
      <span className="truncate font-medium">{label}</span>
      {isDone && info.count > 0 && (
        <span className="ml-auto shrink-0 tabular-nums font-semibold">{info.count.toLocaleString()}</span>
      )}
    </div>
  )
}

export function SyncProgressPanel({
  data,
  isActive = false,
  onDismiss,
}: {
  data: SyncProgressData | undefined
  isActive?: boolean
  onDismiss?: () => void
}) {
  const [dismissed, setDismissed] = useState(false)
  const completedAtRef = useRef<number | null>(null)

  const isRunning = data?.status === 'running'
  const isCompleted = data?.status === 'completed'
  const isFailed = data?.status === 'failed'
  const isLoading = isActive && (!data || data.status === 'idle')

  useEffect(() => {
    if (isCompleted && !completedAtRef.current) {
      completedAtRef.current = Date.now()
      const timer = setTimeout(() => {
        setDismissed(true)
        onDismiss?.()
      }, 4000)
      return () => clearTimeout(timer)
    }
    if (isRunning || isLoading) {
      completedAtRef.current = null
      setDismissed(false)
    }
  }, [isCompleted, isRunning, isLoading, onDismiss])

  if (dismissed) return null
  if (!isActive && (!data || data.status === 'idle')) return null
  if (!data) {
    return (
      <div className="rounded-xl border border-sky-200 bg-gradient-to-br from-sky-50/80 to-white p-5 shadow-sm">
        <p className="text-sm font-medium text-sky-800">Preparing sync…</p>
      </div>
    )
  }

  const phases = data.phases ?? {}
  const doneCount = PHASE_ORDER.filter((p) => phases[p]?.status === 'done').length
  const totalPhases = PHASE_ORDER.length

  return (
    <div
      className={clsx(
        'rounded-xl border p-5 transition-all duration-500',
        (isRunning || isLoading) && 'border-sky-200 bg-gradient-to-br from-sky-50/80 to-white shadow-sm',
        isCompleted && 'border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white shadow-sm',
        isFailed && 'border-red-200 bg-gradient-to-br from-red-50/80 to-white shadow-sm',
      )}
    >
      <div className="mb-4 flex items-center justify-between">
        <div aria-live="polite">
          <p className="text-sm font-semibold text-slate-800">
            {isLoading && 'Preparing sync\u2026'}
            {isRunning && 'Syncing metadata\u2026'}
            {isCompleted && 'Sync complete'}
            {isFailed && 'Sync failed'}
          </p>
          <p className="text-xs text-slate-500">
            {isLoading && 'Initializing sync pipeline'}
            {isRunning && `${doneCount} of ${totalPhases} phases complete`}
            {isCompleted && `All ${totalPhases} phases complete`}
            {isFailed && (data?.error || 'An error occurred during sync')}
          </p>
        </div>
        {(isRunning || isLoading) && (
          <div className="flex items-center gap-2">
            <div
              className="h-2 w-24 overflow-hidden rounded-full bg-slate-200"
              role="progressbar"
              aria-valuenow={Math.round((doneCount / totalPhases) * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Sync progress"
            >
              <div
                className="h-full rounded-full bg-sky-500 transition-all duration-500"
                style={{ width: `${(doneCount / totalPhases) * 100}%` }}
              />
            </div>
            <span className="text-xs tabular-nums text-slate-500">
              {Math.round((doneCount / totalPhases) * 100)}%
            </span>
          </div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {PHASE_ORDER.map((phase) => (
          <PhaseChip
            key={phase}
            name={phase}
            info={phases[phase] ?? { status: 'waiting', count: 0 }}
          />
        ))}
      </div>
    </div>
  )
}
