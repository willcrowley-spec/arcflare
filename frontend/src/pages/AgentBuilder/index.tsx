import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import clsx from 'clsx'
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  Code2,
  Download,
  FileCode2,
  FlaskConical,
  GitBranch,
  Loader2,
  Lock,
  Play,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react'
import {
  useAgentGeneration,
  useApproveAgentDesign,
  useDownloadAgentSource,
  useGenerateAgentSource,
  useRegenerateAgentDesign,
  useValidateAgentSource,
} from '@/hooks/useApi'
import type { AgentGenerationRun, AgentSourceFile } from '@/types'

const STAGES = [
  { key: 'scope', label: 'Scope', icon: GitBranch },
  { key: 'design', label: 'Design', icon: ShieldCheck },
  { key: 'source', label: 'Source', icon: FileCode2 },
  { key: 'validation', label: 'Validation', icon: FlaskConical },
]

function asArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((x) => x && typeof x === 'object') as Record<string, unknown>[] : []
}

function text(value: unknown, fallback = '-'): string {
  if (value == null || value === '') return fallback
  return String(value)
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : []
}

function formatBlocker(blocker: string): string {
  if (blocker.startsWith('unresolved_metadata_binding:')) {
    return `Unresolved metadata binding: ${blocker.replace('unresolved_metadata_binding:', '')}`
  }
  if (blocker.startsWith('suggested_metadata_binding:')) {
    return `Suggested metadata binding needs validation: ${blocker.replace('suggested_metadata_binding:', '')}`
  }
  if (blocker.startsWith('legacy_binding_requires_review:')) {
    return `Legacy mapping suggestion needs review: ${blocker.replace('legacy_binding_requires_review:', '')}`
  }
  if (blocker.startsWith('unresolved_data_requirement:')) {
    return `Unmapped data requirement: ${blocker.replace('unresolved_data_requirement:', '')}`
  }
  if (blocker.startsWith('unknown_salesforce_object:')) {
    return `Unknown Salesforce object: ${blocker.replace('unknown_salesforce_object:', '')}`
  }
  if (blocker.startsWith('missing_permission_requirement:')) {
    return `Missing permission requirement: ${blocker.replace('missing_permission_requirement:', '')}`
  }
  if (blocker.startsWith('missing_action_permissions:')) {
    return `Missing action permissions: ${blocker.replace('missing_action_permissions:', '')}`
  }
  return blocker.replace(/_/g, ' ')
}

function fileLabel(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] || path
}

function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function RunHeader({ run }: { run: AgentGenerationRun }) {
  const design = run.design_package?.package_json ?? {}
  const agent = design.agent && typeof design.agent === 'object' ? design.agent as Record<string, unknown> : {}
  const rawBlockers = (run.design_package?.validation_json ?? {}).blockers
  const blockers = Array.isArray(rawBlockers) ? rawBlockers.map(String) : []
  const blockerCount = blockers.length

  return (
    <header className="border-b border-slate-200 bg-white px-5 py-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <Link
            to="/recommendations?status=accepted"
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-navy-900"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            Recommendations
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h1 className="font-display text-2xl font-bold text-navy-900">{text(agent.name, 'Generated Agent')}</h1>
            <span className="rounded-full bg-navy-50 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-navy-900 ring-1 ring-navy-200">
              {run.status.replace(/_/g, ' ')}
            </span>
            {blockerCount > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200">
                <AlertTriangle className="h-3 w-3" />
                {blockerCount} blocker{blockerCount === 1 ? '' : 's'}
              </span>
            ) : null}
          </div>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">{text(agent.summary, 'Review the generated design package before creating Salesforce source artifacts.')}</p>
        </div>
        <div className="grid min-w-[280px] grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <div className="font-semibold text-slate-500">Trigger</div>
            <div className="mt-1 font-medium text-navy-900">{text(agent.trigger)}</div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <div className="font-semibold text-slate-500">Runtime shape</div>
            <div className="mt-1 font-medium capitalize text-navy-900">{text(agent.type, 'hybrid')}</div>
          </div>
        </div>
      </div>
      {blockers.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {blockers.map((blocker) => (
            <span key={blocker} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900 ring-1 ring-amber-200">
              {formatBlocker(blocker)}
            </span>
          ))}
        </div>
      ) : null}
    </header>
  )
}

function StageRail({ current }: { current: string | null }) {
  const currentIndex = Math.max(0, STAGES.findIndex((s) => s.key === current))
  return (
    <aside className="border-b border-slate-200 bg-white px-5 py-3 lg:w-64 lg:border-b-0 lg:border-r">
      <div className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
        {STAGES.map((stage, index) => {
          const Icon = stage.icon
          const done = index < currentIndex
          const active = stage.key === current
          return (
            <div
              key={stage.key}
              className={clsx(
                'flex min-w-fit items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold',
                active ? 'bg-navy-50 text-navy-900 ring-1 ring-navy-200' : 'text-slate-600',
              )}
            >
              <Icon className={clsx('h-4 w-4', done ? 'text-emerald-600' : active ? 'text-navy-700' : 'text-slate-400')} />
              {stage.label}
              {done ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : null}
            </div>
          )
        })}
      </div>
    </aside>
  )
}

function ScopePanel({ run }: { run: AgentGenerationRun }) {
  const scope = run.stage_results.scope && typeof run.stage_results.scope === 'object'
    ? run.stage_results.scope as Record<string, unknown>
    : {}
  const evidence = run.design_package?.package_json.source_evidence
  const sourceEvidence = evidence && typeof evidence === 'object' ? evidence as Record<string, unknown> : {}
  const processes = asArray(sourceEvidence.processes)
  return (
    <section className="space-y-4">
      <h2 className="text-sm font-bold uppercase tracking-wide text-navy-900">Scoped Evidence</h2>
      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="Linked processes" value={text(scope.process_count, '0')} />
        <Metric label="Metadata objects scanned" value={text(scope.metadata_object_count, '0')} />
        <Metric label="Recommendation" value={run.recommendation_id.slice(0, 8)} />
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Process</th>
              <th className="px-4 py-2">Level</th>
              <th className="px-4 py-2">Automation</th>
              <th className="px-4 py-2">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {processes.length > 0 ? processes.map((p) => (
              <tr key={text(p.id)} className="border-t border-slate-100">
                <td className="px-4 py-3 font-medium text-navy-900">{text(p.name)}</td>
                <td className="px-4 py-3 text-slate-600">{text(p.level)}</td>
                <td className="px-4 py-3 text-slate-600">{text(p.automation_potential)}</td>
                <td className="px-4 py-3 text-slate-600">{text(p.confidence_score)}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-sm text-slate-500">No linked process evidence was attached to this design package.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-bold text-navy-900">{value}</div>
    </div>
  )
}

function DesignPanel({ run }: { run: AgentGenerationRun }) {
  const approve = useApproveAgentDesign()
  const regenerate = useRegenerateAgentDesign()
  const design = run.design_package
  const pkg = design?.package_json ?? {}
  const validation = design?.validation_json ?? {}
  const topics = asArray(pkg.topics)
  const actions = asArray(pkg.action_contracts)
  const permissions = asArray(pkg.permission_requirements)
  const grounding = pkg.metadata_grounding && typeof pkg.metadata_grounding === 'object' ? pkg.metadata_grounding as Record<string, unknown> : {}
  const mappedObjects = asArray(grounding.mapped)
  const unresolvedObjects = asArray(grounding.unresolved)
  const legacySuggestions = asArray(grounding.legacy_suggestions)
  const groundingWarnings = Array.isArray(grounding.warnings) ? grounding.warnings.map(String) : []
  const legacyAdapterUsed = grounding.legacy_adapter_used === true
  const blockers = Array.isArray(validation.blockers) ? validation.blockers as string[] : []
  const canApprove = design?.status === 'draft' && blockers.length === 0
  const canRegenerate = !!design && ['blocked', 'draft'].includes(design.status) && !run.source_bundle

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wide text-navy-900">Design Package</h2>
          <p className="mt-1 text-sm text-slate-600">Review topics, action contracts, permissions, and tests before source generation.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canRegenerate ? (
            <button
              type="button"
              disabled={regenerate.isPending || !design}
              onClick={() => design && regenerate.mutate(run.id)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw className={clsx('h-3.5 w-3.5', regenerate.isPending && 'animate-spin')} />
              Regenerate design
            </button>
          ) : null}
          <button
            type="button"
            disabled={!canApprove || approve.isPending || !design}
            onClick={() => design && approve.mutate(design.id)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Lock className="h-3.5 w-3.5" />
            {design?.status === 'approved' || design?.status === 'source_generated' ? 'Approved' : 'Approve design'}
          </button>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <Panel title="Topics">
            <div className="space-y-3">
              {topics.map((topic) => (
                <div key={text(topic.name)} className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold text-navy-900">{text(topic.name)}</h3>
                    <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200">
                      {text(topic.reasoning_type, 'hybrid')}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-slate-600">{text(topic.description)}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(Array.isArray(topic.actions) ? topic.actions : []).map((a) => (
                      <span key={String(a)} className="rounded-md bg-white px-2 py-1 text-xs font-medium text-navy-800 ring-1 ring-slate-200">
                        {String(a)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Action Contracts">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="text-xs font-bold uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="border-b border-slate-200 py-2 pr-4">Action</th>
                    <th className="border-b border-slate-200 py-2 pr-4">Target</th>
                    <th className="border-b border-slate-200 py-2 pr-4">Objects</th>
                    <th className="border-b border-slate-200 py-2">I/O</th>
                  </tr>
                </thead>
                <tbody>
                  {actions.map((action) => (
                    <tr key={text(action.name)} className="border-b border-slate-100 last:border-0">
                      <td className="py-3 pr-4 font-medium text-navy-900">{text(action.name)}</td>
                      <td className="py-3 pr-4 text-slate-600">{text(action.target_type)}</td>
                      <td className="py-3 pr-4 text-slate-600">{(Array.isArray(action.salesforce_objects) ? action.salesforce_objects : []).join(', ') || '-'}</td>
                      <td className="py-3 text-slate-600">
                        {(Array.isArray(action.inputs) ? action.inputs.length : 0)} in / {(Array.isArray(action.outputs) ? action.outputs.length : 0)} out
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title="Metadata Grounding">
            <div className="space-y-3">
              {legacyAdapterUsed ? (
                <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm ring-1 ring-amber-200">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                    <div>
                      <div className="font-semibold text-amber-950">Legacy mapping mode</div>
                      <div className="mt-0.5 text-xs leading-5 text-amber-800">
                        These are review suggestions from old recommendation text. They cannot generate Apex or Agentforce dependencies until backed by process touchpoints or a user-approved mapping.
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}
              {mappedObjects.length > 0 ? (
                <div className="space-y-2">
                  {mappedObjects.map((item) => (
                    <div key={`${text(item.raw)}-${text(item.api_name)}`} className="rounded-lg bg-emerald-50 px-3 py-2 text-sm ring-1 ring-emerald-100">
                      <div className="font-semibold text-emerald-950">{text(item.api_name)}</div>
                      <div className="mt-0.5 text-xs text-emerald-800">
                        Validated {text(item.label)} from {text(item.source, 'metadata evidence')}.
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-600">No validated Salesforce metadata bindings are available for source generation.</p>
              )}
              {legacySuggestions.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Review suggestions</div>
                  {legacySuggestions.map((item) => (
                    <div key={`${text(item.raw)}-${text(item.api_name)}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm ring-1 ring-slate-200">
                      <div className="font-semibold text-navy-900">{text(item.api_name)}</div>
                      <div className="mt-0.5 text-xs leading-5 text-slate-600">
                        Suggested from "{text(item.raw)}". Confirm this against process evidence before using it in generated source.
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {unresolvedObjects.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Mapping tasks</div>
                  {unresolvedObjects.map((item) => (
                    <div key={`${text(item.raw)}-${text(item.reason)}`} className="rounded-lg bg-amber-50 px-3 py-2 text-sm ring-1 ring-amber-100">
                      <div className="font-semibold text-amber-950">{text(item.raw)}</div>
                      <div className="mt-0.5 text-xs text-amber-800">
                        {text(item.ref_type, 'Metadata')} binding needs evidence before this design can be approved.
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {groundingWarnings.length > 0 ? (
                <div className="space-y-1 text-xs leading-5 text-slate-500">
                  {groundingWarnings.map((warning) => <div key={warning}>{warning}</div>)}
                </div>
              ) : null}
            </div>
          </Panel>
          <Panel title="Permission Requirements">
            {permissions.length > 0 ? (
              <div className="space-y-2">
                {permissions.map((perm) => (
                  <div key={text(perm.object)} className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
                    <div className="font-semibold text-navy-900">{text(perm.object)}</div>
                    <div className="text-xs text-slate-600">{stringArray(perm.operations).join(', ')}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-600">No permissions generated because no validated Salesforce object bindings are available.</p>
            )}
          </Panel>
          <Panel title="Readiness">
            {blockers.length > 0 ? (
              <ul className="space-y-2 text-sm text-amber-900">
                {blockers.map((b) => <li key={b}>{formatBlocker(b)}</li>)}
              </ul>
            ) : (
              <p className="text-sm text-slate-600">No blockers. Approval locks this package for source generation.</p>
            )}
          </Panel>
        </div>
      </div>
    </section>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-xs font-bold uppercase tracking-wide text-navy-900">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  )
}

function SourcePanel({ run }: { run: AgentGenerationRun }) {
  const generate = useGenerateAgentSource()
  const download = useDownloadAgentSource()
  const source = run.source_bundle
  const design = run.design_package
  const files = source?.source_tree_json.files ?? []
  const [selected, setSelected] = useState<string | null>(files[0]?.path ?? null)
  const selectedFile = files.find((f) => f.path === selected) ?? files[0]
  const canGenerate = design?.status === 'approved'

  const handleDownload = () => {
    if (!source) return
    download.mutate(source.id, {
      onSuccess: (blob) => downloadBlob(blob, `${source.source_tree_json.bundle_name ?? 'arcflare-agent-source'}.zip`),
    })
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wide text-navy-900">Source Artifacts</h2>
          <p className="mt-1 text-sm text-slate-600">Generated Salesforce DX source from the approved design package.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!canGenerate || generate.isPending}
            onClick={() => design && generate.mutate(design.id)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-navy-800 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-navy-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generate.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Code2 className="h-3.5 w-3.5" />}
            Generate source
          </button>
          <button
            type="button"
            disabled={!source || download.isPending}
            onClick={handleDownload}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-navy-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            Download zip
          </button>
        </div>
      </div>

      {files.length > 0 ? (
        <div className="grid min-h-[520px] overflow-hidden rounded-lg border border-slate-200 bg-white lg:grid-cols-[340px_minmax(0,1fr)]">
          <div className="border-b border-slate-200 bg-slate-50 lg:border-b-0 lg:border-r">
            {files.map((file) => (
              <button
                key={file.path}
                type="button"
                onClick={() => setSelected(file.path)}
                className={clsx(
                  'flex w-full items-start gap-2 border-b border-slate-100 px-4 py-3 text-left text-sm hover:bg-white',
                  selectedFile?.path === file.path && 'bg-white text-navy-900',
                )}
              >
                <FileCode2 className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                <span className="min-w-0">
                  <span className="block truncate font-semibold">{fileLabel(file.path)}</span>
                  <span className="block truncate text-xs text-slate-500">{file.path}</span>
                </span>
              </button>
            ))}
          </div>
          <pre className="overflow-auto bg-slate-950 p-4 text-xs leading-5 text-slate-100">
            <code>{selectedFile?.content ?? ''}</code>
          </pre>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-5 py-10 text-center text-sm text-slate-600">
          Approve the design package, then generate source artifacts.
        </div>
      )}
    </section>
  )
}

function ValidationPanel({ run }: { run: AgentGenerationRun }) {
  const validate = useValidateAgentSource()
  const source = run.source_bundle
  const latest = run.validation_runs[0]
  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wide text-navy-900">Scratch Org Validation</h2>
          <p className="mt-1 text-sm text-slate-600">Optional validation lane for deploy/test/preview once server-side Dev Hub auth is enabled.</p>
        </div>
        <button
          type="button"
          disabled={!source || validate.isPending}
          onClick={() => source && validate.mutate(source.id)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-orange-300 bg-orange-50 px-3.5 py-2 text-xs font-semibold text-orange-900 shadow-sm hover:bg-orange-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" />
          Validate in lab
        </button>
      </div>
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        {latest ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold capitalize text-navy-900 ring-1 ring-slate-200">
                {latest.status.replace(/_/g, ' ')}
              </span>
              <span className="text-xs text-slate-500">Dev Hub: {latest.devhub_alias ?? 'not configured'}</span>
            </div>
            {latest.error ? <p className="text-sm text-amber-900">{latest.error}</p> : null}
          </div>
        ) : (
          <p className="text-sm text-slate-600">No validation run yet. Source artifacts can still be reviewed and downloaded without a scratch org.</p>
        )}
      </div>
    </section>
  )
}

export default function AgentBuilderPage() {
  const { runId } = useParams()
  const { data: run, isLoading, isError, error } = useAgentGeneration(runId)
  const currentStage = run?.current_stage ?? 'design'
  const content = useMemo(() => {
    if (!run) return null
    return (
      <div className="space-y-8">
        <ScopePanel run={run} />
        <DesignPanel run={run} />
        <SourcePanel run={run} />
        <ValidationPanel run={run} />
      </div>
    )
  }, [run])

  if (isLoading) {
    return (
      <div className="flex min-h-[420px] items-center justify-center text-sm text-slate-600">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading agent generation run...
      </div>
    )
  }

  if (isError || !run) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-900">
        {error instanceof Error ? error.message : 'Agent generation run could not be loaded.'}
      </div>
    )
  }

  return (
    <div className="-m-6 min-h-[calc(100vh-4rem)] bg-slate-50">
      <RunHeader run={run} />
      <div className="flex flex-col lg:flex-row">
        <StageRail current={currentStage} />
        <main className="min-w-0 flex-1 px-5 py-5">{content}</main>
      </div>
    </div>
  )
}
