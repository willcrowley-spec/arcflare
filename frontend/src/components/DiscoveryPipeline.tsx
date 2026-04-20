import { AlertCircle, Check, Loader2, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import type { DiscoveryPhase, DiscoveryProgressPhaseKey, DiscoveryStatus } from '@/types'
import { DISCOVERY_PHASE_LABELS } from '@/types'

type StageDef = {
  key: DiscoveryProgressPhaseKey
  label: string
  passNum: number
  /** If set, phase progress for this chip may come from these keys (older workers). */
  legacySourceKeys?: readonly DiscoveryProgressPhaseKey[]
}

const V2_PIPELINE_MARKERS = new Set([
  'evidence_assembly',
  'extraction',
  'verification',
])

const V1_PIPELINE_MARKERS = new Set([
  'structural_decomposition',
  'step_enrichment',
  'flow_analysis',
  'validation',
])

const V2_PIPELINE_STAGES: StageDef[] = [
  { key: 'context_gathering', label: DISCOVERY_PHASE_LABELS.context_gathering, passNum: 1 },
  { key: 'domain_discovery', label: DISCOVERY_PHASE_LABELS.domain_discovery, passNum: 2 },
  { key: 'evidence_assembly', label: DISCOVERY_PHASE_LABELS.evidence_assembly, passNum: 3 },
  { key: 'extraction', label: DISCOVERY_PHASE_LABELS.extraction, passNum: 4 },
  { key: 'verification', label: DISCOVERY_PHASE_LABELS.verification, passNum: 5 },
  { key: 'cross_domain_synthesis', label: DISCOVERY_PHASE_LABELS.cross_domain_synthesis, passNum: 6 },
  { key: 'quality_scoring', label: DISCOVERY_PHASE_LABELS.quality_scoring, passNum: 7 },
  { key: 'graph_generation', label: DISCOVERY_PHASE_LABELS.graph_generation, passNum: 8 },
]

const V1_PIPELINE_STAGES: StageDef[] = [
  { key: 'context_gathering', label: DISCOVERY_PHASE_LABELS.context_gathering, passNum: 1 },
  { key: 'domain_discovery', label: DISCOVERY_PHASE_LABELS.domain_discovery, passNum: 2 },
  {
    key: 'structural_decomposition',
    label: DISCOVERY_PHASE_LABELS.structural_decomposition,
    passNum: 3,
    legacySourceKeys: ['domain_decomposition'],
  },
  { key: 'step_enrichment', label: DISCOVERY_PHASE_LABELS.step_enrichment, passNum: 4 },
  { key: 'flow_analysis', label: DISCOVERY_PHASE_LABELS.flow_analysis, passNum: 5 },
  { key: 'validation', label: DISCOVERY_PHASE_LABELS.validation, passNum: 6 },
  { key: 'cross_domain_synthesis', label: DISCOVERY_PHASE_LABELS.cross_domain_synthesis, passNum: 7 },
  { key: 'quality_scoring', label: DISCOVERY_PHASE_LABELS.quality_scoring, passNum: 8 },
  { key: 'graph_generation', label: DISCOVERY_PHASE_LABELS.graph_generation, passNum: 9 },
]

/** Pre–7-stage workers typically only reported these three phases. */
const LEGACY_PIPELINE_STAGES: StageDef[] = [
  { key: 'domain_discovery', label: DISCOVERY_PHASE_LABELS.domain_discovery, passNum: 1 },
  {
    key: 'domain_decomposition',
    label: DISCOVERY_PHASE_LABELS.domain_decomposition,
    passNum: 2,
  },
  { key: 'cross_domain_synthesis', label: DISCOVERY_PHASE_LABELS.cross_domain_synthesis, passNum: 3 },
]

function pickStages(phases: Record<string, DiscoveryPhase | undefined>): StageDef[] {
  const keys = Object.keys(phases)
  if (keys.length === 0) return V2_PIPELINE_STAGES
  if (keys.some((k) => V2_PIPELINE_MARKERS.has(k))) return V2_PIPELINE_STAGES
  if (keys.some((k) => V1_PIPELINE_MARKERS.has(k))) return V1_PIPELINE_STAGES
  return LEGACY_PIPELINE_STAGES
}

function resolvePhase(
  phases: DiscoveryStatus['phases'],
  stage: StageDef,
): DiscoveryPhase | undefined {
  const direct = phases[stage.key]
  if (direct) return direct
  if (stage.legacySourceKeys) {
    for (const k of stage.legacySourceKeys) {
      const p = phases[k]
      if (p) return p
    }
  }
  return undefined
}

export type DiscoveryPipelineStageKey = DiscoveryProgressPhaseKey

function hasPriorDiscovery(data: DiscoveryStatus | undefined): boolean {
  if (!data) return false
  const rid = data.run_id?.trim()
  if (rid) return true
  if (data.started_at || data.completed_at) return true
  if (data.status && data.status !== 'idle') return true
  return Object.keys(data.phases ?? {}).length > 0
}

function StageChip({
  label,
  passNum,
  status,
  count,
  total,
  onRerun,
}: {
  label: string
  passNum: number
  status: string
  count: number
  total: number
  onRerun?: () => void
}) {
  const isWaiting = status === 'waiting' || !status
  const isRunning = status === 'pulling' || status === 'running' || status === 'gathering'
  const isDone = status === 'done'
  const isFailed = status === 'failed'

  const subtext =
    isRunning && total > 0
      ? `${count} of ${total}`
      : isDone && count > 0
        ? `${count} found`
        : undefined

  return (
    <div
      className={clsx(
        'flex min-w-0 items-center gap-2.5 rounded-lg border px-3 py-2.5 text-sm transition-all duration-300',
        isWaiting && 'border-slate-200 bg-slate-50 text-slate-400',
        isRunning && 'border-sky-300 bg-sky-50 text-sky-800 shadow-sm',
        isDone && 'border-emerald-200 bg-emerald-50 text-emerald-800',
        isFailed && 'border-red-200 bg-red-50 text-red-800',
      )}
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center">
        {isWaiting && <span className="h-2 w-2 rounded-full bg-slate-300" />}
        {isRunning && <Loader2 className="h-4 w-4 animate-spin text-sky-600" />}
        {isDone && <Check className="h-4 w-4 text-emerald-600" />}
        {isFailed && <AlertCircle className="h-4 w-4 text-red-600" />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">
          <span className="text-xs opacity-60">Pass {passNum}</span> {label}
        </p>
        {subtext ? <p className="text-xs opacity-70">{subtext}</p> : null}
      </div>
      {isDone && onRerun ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onRerun()
          }}
          className="shrink-0 rounded p-1 text-slate-400 hover:bg-white/60 hover:text-slate-600"
          title={`Re-run ${label}`}
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  )
}

export function DiscoveryPipeline({
  data,
  isActive,
  onRerunStage,
}: {
  data: DiscoveryStatus | undefined
  isActive: boolean
  onRerunStage?: (stageKey: DiscoveryPipelineStageKey) => void
}) {
  if (!isActive && (!data || (data.status === 'idle' && !hasPriorDiscovery(data)))) return null

  const phases = data?.phases ?? {}
  const overallStatus = data?.status ?? 'idle'
  const stages = pickStages(phases)

  return (
    <div
      className={clsx(
        'rounded-xl border p-4 transition-all duration-500',
        overallStatus === 'running' &&
          'border-sky-200 bg-gradient-to-br from-sky-50/80 to-white shadow-sm',
        overallStatus === 'completed' &&
          'border-emerald-200 bg-gradient-to-br from-emerald-50/80 to-white shadow-sm',
        overallStatus === 'failed' &&
          'border-red-200 bg-gradient-to-br from-red-50/80 to-white shadow-sm',
        overallStatus === 'idle' && 'border-slate-200 bg-slate-50',
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-800">
          {overallStatus === 'running' && 'Discovering processes…'}
          {overallStatus === 'completed' && 'Discovery complete'}
          {overallStatus === 'failed' && 'Discovery failed'}
          {overallStatus === 'idle' && 'Ready to discover'}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {stages.map((stage) => {
          const phase = resolvePhase(phases, stage)
          return (
            <StageChip
              key={stage.key}
              label={stage.label}
              passNum={stage.passNum}
              status={phase?.status ?? 'waiting'}
              count={phase?.count ?? 0}
              total={phase?.total ?? 0}
              onRerun={onRerunStage ? () => onRerunStage(stage.key) : undefined}
            />
          )
        })}
      </div>
      {overallStatus === 'failed' && data?.error ? (
        <div
          className="mt-3 flex gap-2 rounded-lg border border-red-200 bg-red-50/90 px-3 py-2.5 text-sm text-red-900"
          role="alert"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden />
          <p className="min-w-0 break-words leading-snug">{data.error}</p>
        </div>
      ) : null}
    </div>
  )
}
