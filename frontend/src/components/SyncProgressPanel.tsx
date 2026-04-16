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
  objects: 'Objects',
  fields: 'Fields',
  flows: 'Flows',
  triggers: 'Triggers',
  validation_rules: 'Validation Rules',
  apex_classes: 'Apex Classes',
  permissions: 'Permissions',
  ui_components: 'UI Components',
  reports: 'Reports & Dashboards',
  installed_packages: 'Packages',
  licensing: 'Licensing',
  user_velocity: 'User Velocity',
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
        'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-all duration-300',
        isWaiting && 'border-slate-200 bg-slate-50 text-slate-400',
        isPulling && 'border-sky-300 bg-sky-50 text-sky-800 shadow-sm',
        isDone && 'border-emerald-200 bg-emerald-50 text-emerald-800',
      )}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center">
        {isWaiting && <span className="h-2 w-2 rounded-full bg-slate-300" />}
        {isPulling && <Loader2 className="h-4 w-4 animate-spin text-sky-600" />}
        {isDone && <Check className="h-4 w-4 text-emerald-600" />}
      </span>
      <span className="font-medium">{label}</span>
      {isDone && info.count > 0 && (
        <span className="ml-auto tabular-nums text-xs font-semibold">{info.count.toLocaleString()}</span>
      )}
    </div>
  )
}

export function SyncProgressPanel({
  data,
  onDismiss,
}: {
  data: SyncProgressData | undefined
  onDismiss?: () => void
}) {
  const [dismissed, setDismissed] = useState(false)
  const completedAtRef = useRef<number | null>(null)

  const isRunning = data?.status === 'running'
  const isCompleted = data?.status === 'completed'
  const isFailed = data?.status === 'failed'

  useEffect(() => {
    if (isCompleted && !completedAtRef.current) {
      completedAtRef.current = Date.now()
      const timer = setTimeout(() => {
        setDismissed(true)
        onDismiss?.()
      }, 4000)
      return () => clearTimeout(timer)
    }
    if (isRunning) {
      completedAtRef.current = null
      setDismissed(false)
    }
  }, [isCompleted, isRunning, onDismiss])

  if (!data || data.status === 'idle' || dismissed) return null

  const phases = data.phases ?? {}
  const doneCount = PHASE_ORDER.filter((p) => phases[p]?.status === 'done').length
  const totalPhases = PHASE_ORDER.length

  return (
    <div
      className={clsx(
        'rounded-xl border p-5 transition-all duration-500',
        isRunning && 'border-sky-200 bg-gradient-to-br from-sky-50/80 to-white shadow-sm',
        isCompleted && 'border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white shadow-sm',
        isFailed && 'border-red-200 bg-gradient-to-br from-red-50/80 to-white shadow-sm',
      )}
    >
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {isRunning && 'Syncing metadata\u2026'}
            {isCompleted && 'Sync complete'}
            {isFailed && 'Sync failed'}
          </p>
          <p className="text-xs text-slate-500">
            {isRunning && `${doneCount} of ${totalPhases} phases complete`}
            {isCompleted && `All ${totalPhases} phases complete`}
            {isFailed && (data.error || 'An error occurred during sync')}
          </p>
        </div>
        {isRunning && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200">
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
