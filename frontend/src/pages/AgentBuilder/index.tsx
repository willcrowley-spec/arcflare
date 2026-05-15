import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import clsx from 'clsx'
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  Code2,
  Download,
  FileText,
  FileCode2,
  FlaskConical,
  GitBranch,
  Loader2,
  Lock,
  Play,
  RefreshCw,
  Search,
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
import type { AgentGenerationRun, AgentSourceArtifactGroup, AgentSourceFile } from '@/types'

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
  if (blocker.startsWith('upstream_metadata_evidence_missing:')) {
    return `Upstream metadata evidence missing: ${blocker.replace('upstream_metadata_evidence_missing:', '')}`
  }
  if (blocker.startsWith('external_dependency_contract_missing:')) {
    return `External dependency contract missing: ${blocker.replace('external_dependency_contract_missing:', '')}`
  }
  if (blocker.startsWith('unresolved_metadata_binding:')) {
    return `Upstream metadata evidence missing: ${blocker.replace('unresolved_metadata_binding:', '')}`
  }
  if (blocker.startsWith('suggested_metadata_binding:')) {
    return `Advisory metadata hint ignored: ${blocker.replace('suggested_metadata_binding:', '')}`
  }
  if (blocker.startsWith('legacy_binding_requires_review:')) {
    return `Legacy recommendation needs rerun: ${blocker.replace('legacy_binding_requires_review:', '')}`
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

const SOURCE_TAB_LABELS: Record<string, string> = {
  contract: 'Contract',
  dependencies: 'Dependencies',
  apex_class: 'Apex Class',
  apex_meta: 'Meta XML',
  apex_test: 'Test',
  apex_test_meta: 'Test Meta',
  agent_script: 'Agent Script',
  permission_set: 'Permission Set',
  manifest: 'Manifest',
  sfdx_project: 'Project JSON',
  scratch_def: 'Scratch Def',
  readme: 'README',
}

function sourceKindLabel(kind: string): string {
  return kind.replace(/_/g, ' ')
}

function sourceBadgeClass(status: unknown): string {
  const value = String(status || '').toLowerCase()
  if (value === 'scaffold') return 'bg-amber-50 text-amber-900 ring-amber-200'
  if (value === 'deployable_candidate' || value === 'bounded_implementation') return 'bg-emerald-50 text-emerald-900 ring-emerald-200'
  return 'bg-slate-100 text-slate-700 ring-slate-200'
}

function humanizeIdentifier(value: string): string {
  return value
    .replace(/Action(Test)?$/, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .trim()
}

function buildFallbackArtifactGroups(files: AgentSourceFile[]): AgentSourceArtifactGroup[] {
  const groups: AgentSourceArtifactGroup[] = []
  const actionGroups = new Map<string, AgentSourceArtifactGroup>()
  const used = new Set<string>()

  for (const file of files) {
    const match = file.path.match(/\/classes\/([^/]+?)(Test)?\.cls(-meta\.xml)?$/)
    if (!match) continue
    const classBase = match[1]
    const isTest = Boolean(match[2])
    const isMeta = Boolean(match[3])
    const actionName = classBase.replace(/Action$/, '')
    const groupId = `action:${actionName}`
    const existing = actionGroups.get(groupId) ?? {
      id: groupId,
      kind: 'action_contract',
      display_name: humanizeIdentifier(classBase),
      common_name: humanizeIdentifier(classBase),
      action_name: actionName,
      target_type: 'apex',
      target_name: classBase,
      capability_type: 'action',
      implementation_status: 'scaffold',
      files: {},
    }
    const fileKey = isTest ? (isMeta ? 'apex_test_meta' : 'apex_test') : (isMeta ? 'apex_meta' : 'apex_class')
    existing.files = { ...(existing.files ?? {}), [fileKey]: file.path }
    actionGroups.set(groupId, existing)
    used.add(file.path)
  }

  const specialGroups: AgentSourceArtifactGroup[] = []
  for (const file of files) {
    if (used.has(file.path)) continue
    if (file.kind === 'agent_script') {
      specialGroups.push({
        id: 'agent_script',
        kind: 'agent_script',
        display_name: fileLabel(file.path).replace('.agent', ' Agent Script'),
        common_name: fileLabel(file.path).replace('.agent', ' Agent Script'),
        files: { agent_script: file.path },
      })
      used.add(file.path)
    } else if (file.kind === 'permission_set') {
      specialGroups.push({
        id: 'permissions',
        kind: 'permission_set',
        display_name: 'Permission set',
        common_name: 'Permission set',
        files: { permission_set: file.path },
      })
      used.add(file.path)
    } else if (['manifest', 'project_config', 'scratch_org_definition'].includes(file.kind)) {
      let configGroup = specialGroups.find((group) => group.id === 'project_config')
      if (!configGroup) {
        configGroup = {
          id: 'project_config',
          kind: 'project_config',
          display_name: 'Salesforce DX project config',
          common_name: 'Salesforce DX project config',
          files: {},
        }
        specialGroups.push(configGroup)
      }
      const key = file.kind === 'manifest' ? 'manifest' : file.kind === 'scratch_org_definition' ? 'scratch_def' : 'sfdx_project'
      configGroup.files = { ...(configGroup.files ?? {}), [key]: file.path }
      used.add(file.path)
    } else if (file.kind === 'readme') {
      specialGroups.push({
        id: 'readme',
        kind: 'documentation',
        display_name: 'Review README',
        common_name: 'Review README',
        files: { readme: file.path },
      })
      used.add(file.path)
    }
  }

  groups.push(...specialGroups)
  groups.push(...Array.from(actionGroups.values()).sort((a, b) => (a.common_name ?? '').localeCompare(b.common_name ?? '')))
  for (const file of files) {
    if (!used.has(file.path)) {
      groups.push({
        id: file.path,
        kind: file.kind || 'source_file',
        display_name: fileLabel(file.path),
        common_name: fileLabel(file.path),
        files: { source: file.path },
      })
    }
  }
  return groups
}

function groupSearchText(group: AgentSourceArtifactGroup): string {
  return [
    group.display_name,
    group.common_name,
    group.action_name,
    group.target_name,
    group.kind,
    group.capability_type,
    ...(group.salesforce_objects ?? []),
    ...(group.source_topics ?? []),
    ...Object.values(group.files ?? {}),
  ].filter(Boolean).join(' ').toLowerCase()
}

function filesByPath(files: AgentSourceFile[]): Record<string, AgentSourceFile> {
  return Object.fromEntries(files.map((file) => [file.path, file]))
}

function sourceTabs(
  group: AgentSourceArtifactGroup | undefined,
  lookup: Record<string, AgentSourceFile>,
): { key: string; label: string; type: 'contract' | 'dependencies' | 'file'; file?: AgentSourceFile }[] {
  if (!group) return []
  const tabs: { key: string; label: string; type: 'contract' | 'dependencies' | 'file'; file?: AgentSourceFile }[] = []
  if (group.contract) {
    tabs.push({ key: 'contract', label: SOURCE_TAB_LABELS.contract, type: 'contract' })
  }
  const preferredOrder = [
    'apex_class',
    'apex_meta',
    'apex_test',
    'apex_test_meta',
    'agent_script',
    'permission_set',
    'manifest',
    'sfdx_project',
    'scratch_def',
    'readme',
    'source',
  ]
  const groupFiles = group.files ?? {}
  const keys = [
    ...preferredOrder.filter((key) => groupFiles[key]),
    ...Object.keys(groupFiles).filter((key) => !preferredOrder.includes(key)).sort(),
  ]
  for (const key of keys) {
    const file = lookup[groupFiles[key]]
    if (file) {
      tabs.push({ key, label: SOURCE_TAB_LABELS[key] ?? fileLabel(file.path), type: 'file', file })
    }
  }
  tabs.push({ key: 'dependencies', label: SOURCE_TAB_LABELS.dependencies, type: 'dependencies' })
  return tabs
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
  const validatedDependencies = asArray(grounding.validated_dependencies)
  const upstreamDefects = asArray(grounding.upstream_defects)
  const externalDependencies = asArray(grounding.external_dependencies)
  const advisorySuggestions = asArray(grounding.advisory_suggestions)
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
          <Panel title="Evidence Check">
            <div className="space-y-3">
              {legacyAdapterUsed ? (
                <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm ring-1 ring-amber-200">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                    <div>
                      <div className="font-semibold text-amber-950">Legacy recommendation mode</div>
                      <div className="mt-0.5 text-xs leading-5 text-amber-800">
                        This recommendation predates typed evidence. Rerun the assessment or recommendation pipeline so Arcflare can rebuild validated dependencies from Salesforce metadata.
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
                        Object access validated from {text(item.source, 'process evidence')}.
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-600">No validated Salesforce dependencies are available for source generation.</p>
              )}
              {validatedDependencies.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Validated automations</div>
                  {validatedDependencies.map((item) => (
                    <div key={`${text(item.ref_type)}-${text(item.api_name)}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm ring-1 ring-slate-200">
                      <div className="font-semibold text-navy-900">{text(item.api_name)}</div>
                      <div className="mt-0.5 text-xs leading-5 text-slate-600">
                        {text(item.ref_type, 'Metadata')} dependency validated from {text(item.source, 'process evidence')}.
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {legacySuggestions.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Legacy diagnostics</div>
                  {legacySuggestions.map((item) => (
                    <div key={`${text(item.raw)}-${text(item.api_name)}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm ring-1 ring-slate-200">
                      <div className="font-semibold text-navy-900">{text(item.api_name)}</div>
                      <div className="mt-0.5 text-xs leading-5 text-slate-600">
                        Suggested from old recommendation text. It is diagnostic only; generated source requires a fresh typed assessment.
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {upstreamDefects.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Upstream evidence incomplete</div>
                  {upstreamDefects.map((item) => (
                    <div key={`${text(item.raw)}-${text(item.reason)}`} className="rounded-lg bg-amber-50 px-3 py-2 text-sm ring-1 ring-amber-100">
                      <div className="font-semibold text-amber-950">{text(item.raw)}</div>
                      <div className="mt-0.5 text-xs text-amber-800">
                        Arcflare found this in process evidence, but it was not validated in the Salesforce metadata inventory. Rerun metadata sync or assessment before generating source.
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {externalDependencies.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-500">External contracts needed</div>
                  {externalDependencies.map((item) => (
                    <div key={`${text(item.raw)}-${text(item.reason)}`} className="rounded-lg bg-orange-50 px-3 py-2 text-sm ring-1 ring-orange-100">
                      <div className="font-semibold text-orange-950">{text(item.raw)}</div>
                      <div className="mt-0.5 text-xs text-orange-800">
                        External dependencies need an Apex/API contract before Arcflare can generate deployable Agentforce actions.
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {advisorySuggestions.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Advisory signals</div>
                  {advisorySuggestions.map((item) => (
                    <div key={`${text(item.raw)}-${text(item.ref_type)}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm ring-1 ring-slate-200">
                      <div className="font-semibold text-navy-900">{text(item.raw)}</div>
                      <div className="mt-0.5 text-xs leading-5 text-slate-600">
                        This came from AI analysis and is not used as a source dependency unless future process evidence validates it.
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {unresolvedObjects.length > 0 ? (
                <div className="space-y-2">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Legacy unresolved evidence</div>
                  {unresolvedObjects.map((item) => (
                    <div key={`${text(item.raw)}-${text(item.reason)}`} className="rounded-lg bg-amber-50 px-3 py-2 text-sm ring-1 ring-amber-100">
                      <div className="font-semibold text-amber-950">{text(item.raw)}</div>
                      <div className="mt-0.5 text-xs text-amber-800">
                        This old design package should be regenerated after rerunning the recommendation pipeline.
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
  const lookup = useMemo(() => filesByPath(files), [files])
  const groups = useMemo(() => {
    const existing = source?.source_tree_json.artifact_groups
    return existing && existing.length > 0 ? existing : buildFallbackArtifactGroups(files)
  }, [files, source?.source_tree_json.artifact_groups])
  const [query, setQuery] = useState('')
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(groups[0]?.id ?? null)
  const [selectedTabKey, setSelectedTabKey] = useState<string>('contract')
  const filteredGroups = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return groups
    return groups.filter((group) => groupSearchText(group).includes(needle))
  }, [groups, query])
  const selectedGroup = groups.find((group) => group.id === selectedGroupId) ?? filteredGroups[0] ?? groups[0]
  const tabs = useMemo(() => sourceTabs(selectedGroup, lookup), [lookup, selectedGroup])
  const selectedTab = tabs.find((tab) => tab.key === selectedTabKey) ?? tabs[0]
  const canGenerate = design?.status === 'approved'

  useEffect(() => {
    if (!selectedGroup || selectedGroup.id !== selectedGroupId) {
      setSelectedGroupId(selectedGroup?.id ?? null)
    }
  }, [selectedGroup, selectedGroupId])

  useEffect(() => {
    if (tabs.length > 0 && !tabs.some((tab) => tab.key === selectedTabKey)) {
      setSelectedTabKey(tabs[0].key)
    }
  }, [selectedTabKey, tabs])

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
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                <span className="font-semibold text-navy-900">{groups.length} artifact groups</span>
                <span>{files.length} source files</span>
                <span>{source?.source_tree_json.compiler_version ?? 'compiler unknown'}</span>
              </div>
              <label className="relative block w-full lg:w-80">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search action, class, object, topic..."
                  className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-navy-900 outline-none ring-orange-300 placeholder:text-slate-400 focus:border-orange-300 focus:ring-2"
                />
              </label>
            </div>
          </div>
          <div className="grid min-h-[560px] lg:grid-cols-[360px_minmax(0,1fr)]">
            <div className="max-h-[680px] overflow-auto border-b border-slate-200 bg-white lg:border-b-0 lg:border-r">
              {filteredGroups.length > 0 ? filteredGroups.map((group) => {
                const active = selectedGroup?.id === group.id
                return (
                  <button
                    key={group.id}
                    type="button"
                    onClick={() => {
                      setSelectedGroupId(group.id)
                      setSelectedTabKey(group.contract ? 'contract' : Object.keys(group.files ?? {})[0] ?? 'dependencies')
                    }}
                    className={clsx(
                      'flex w-full items-start gap-3 border-b border-slate-100 px-4 py-3 text-left text-sm hover:bg-slate-50',
                      active && 'bg-navy-50 text-navy-900 ring-1 ring-inset ring-navy-200',
                    )}
                  >
                    {group.kind === 'action_contract' ? (
                      <Code2 className="mt-0.5 h-4 w-4 shrink-0 text-navy-700" />
                    ) : (
                      <FileText className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold">{group.common_name ?? group.display_name ?? group.id}</span>
                      <span className="mt-0.5 block truncate text-xs text-slate-500">
                        {group.target_name ?? sourceKindLabel(group.kind)}
                      </span>
                      <span className="mt-2 flex flex-wrap gap-1.5">
                        {group.capability_type ? (
                          <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold capitalize text-slate-600 ring-1 ring-slate-200">
                            {sourceKindLabel(group.capability_type)}
                          </span>
                        ) : null}
                        {group.implementation_status ? (
                          <span className={clsx('rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize ring-1', sourceBadgeClass(group.implementation_status))}>
                            {sourceKindLabel(group.implementation_status)}
                          </span>
                        ) : null}
                        {(group.salesforce_objects ?? []).slice(0, 2).map((objectName) => (
                          <span key={objectName} className="rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200">
                            {objectName}
                          </span>
                        ))}
                      </span>
                    </span>
                  </button>
                )
              }) : (
                <div className="px-4 py-8 text-sm text-slate-500">No source artifacts match that search.</div>
              )}
            </div>
            <div className="min-w-0 bg-white">
              {selectedGroup ? (
                <div className="flex h-full min-h-[560px] flex-col">
                  <div className="border-b border-slate-200 px-4 py-3">
                    <div className="flex flex-col gap-2 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0">
                        <h3 className="truncate text-sm font-bold text-navy-900">
                          {selectedGroup.common_name ?? selectedGroup.display_name ?? selectedGroup.id}
                        </h3>
                        <p className="mt-1 truncate text-xs text-slate-500">
                          {selectedGroup.target_name ?? sourceKindLabel(selectedGroup.kind)}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {(selectedGroup.source_topics ?? []).slice(0, 3).map((topic) => (
                          <span key={topic} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200">
                            {topic}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="mt-3 flex gap-1 overflow-x-auto">
                      {tabs.map((tab) => (
                        <button
                          key={tab.key}
                          type="button"
                          onClick={() => setSelectedTabKey(tab.key)}
                          className={clsx(
                            'whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-semibold',
                            selectedTab?.key === tab.key
                              ? 'bg-navy-900 text-white'
                              : 'text-slate-600 hover:bg-slate-100 hover:text-navy-900',
                          )}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="min-h-0 flex-1 overflow-auto">
                    {selectedTab?.type === 'contract' ? (
                      <ContractSummary group={selectedGroup} />
                    ) : selectedTab?.type === 'dependencies' ? (
                      <DependencySummary group={selectedGroup} />
                    ) : (
                      <div className="h-full">
                        <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-500">
                          {selectedTab?.file?.path}
                        </div>
                        <pre className="min-h-[500px] overflow-auto bg-slate-950 p-4 text-xs leading-5 text-slate-100">
                          <code>{selectedTab?.file?.content ?? ''}</code>
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="px-4 py-8 text-sm text-slate-500">Select an artifact group to review its contract and source files.</div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-5 py-10 text-center text-sm text-slate-600">
          Approve the design package, then generate source artifacts.
        </div>
      )}
    </section>
  )
}

function ContractSummary({ group }: { group: AgentSourceArtifactGroup }) {
  const contract = group.contract ?? {}
  const inputs = asArray(contract.inputs)
  const outputs = asArray(contract.outputs)
  const operations = asArray(contract.operations)
  const permissions = stringArray(contract.permissions)
  return (
    <div className="space-y-5 p-4">
      <div>
        <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Purpose</div>
        <p className="mt-1 max-w-4xl text-sm leading-6 text-navy-900">{text(contract.purpose ?? contract.description, 'Review this action contract before using the generated source.')}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="Target" value={text(group.target_name ?? contract.target_name)} />
        <Metric label="Capability" value={sourceKindLabel(text(group.capability_type ?? contract.capability_type, 'action'))} />
        <Metric label="Status" value={sourceKindLabel(text(group.implementation_status ?? contract.implementation_status, 'scaffold'))} />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <ContractTable title="Inputs" rows={inputs} />
        <ContractTable title="Outputs" rows={outputs} />
      </div>
      <div>
        <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Operations</div>
        {operations.length > 0 ? (
          <div className="mt-2 overflow-hidden rounded-lg border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Object</th>
                  <th className="px-3 py-2">Field</th>
                  <th className="px-3 py-2">Operation</th>
                  <th className="px-3 py-2">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {operations.map((operation, index) => (
                  <tr key={`${text(operation.object_api_name)}-${text(operation.field_api_name)}-${index}`} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-medium text-navy-900">{text(operation.object_api_name)}</td>
                    <td className="px-3 py-2 text-slate-600">{text(operation.field_api_name)}</td>
                    <td className="px-3 py-2 text-slate-600">{text(operation.operation)}</td>
                    <td className="px-3 py-2 text-slate-500">{stringArray(operation.evidence_ids).join(', ') || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-600">No field-level operations were attached to this artifact.</p>
        )}
      </div>
      {permissions.length > 0 ? (
        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Permissions</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {permissions.map((permission) => (
              <span key={permission} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-navy-900 ring-1 ring-slate-200">
                {permission}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function ContractTable({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  return (
    <div>
      <div className="text-xs font-bold uppercase tracking-wide text-slate-500">{title}</div>
      <div className="mt-2 overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Required</th>
            </tr>
          </thead>
          <tbody>
            {rows.length > 0 ? rows.map((row) => (
              <tr key={text(row.name)} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium text-navy-900">{text(row.name)}</td>
                <td className="px-3 py-2 text-slate-600">{text(row.type)}</td>
                <td className="px-3 py-2 text-slate-600">{row.required === false ? 'No' : 'Yes'}</td>
              </tr>
            )) : (
              <tr>
                <td colSpan={3} className="px-3 py-4 text-sm text-slate-500">No {title.toLowerCase()} declared.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DependencySummary({ group }: { group: AgentSourceArtifactGroup }) {
  const contract = group.contract ?? {}
  const sourceProcesses = asArray(contract.source_processes)
  const files = group.files ?? {}
  return (
    <div className="space-y-5 p-4">
      <div>
        <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Salesforce Dependencies</div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(group.salesforce_objects ?? []).length > 0 ? group.salesforce_objects?.map((objectName) => (
            <span key={objectName} className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-navy-900 ring-1 ring-slate-200">
              {objectName}
            </span>
          )) : <span className="text-sm text-slate-600">No Salesforce objects attached.</span>}
        </div>
      </div>
      <div>
        <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Source Topics</div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(group.source_topics ?? []).length > 0 ? group.source_topics?.map((topic) => (
            <span key={topic} className="rounded-full bg-navy-50 px-2.5 py-1 text-xs font-semibold text-navy-900 ring-1 ring-navy-200">
              {topic}
            </span>
          )) : <span className="text-sm text-slate-600">No source topics attached.</span>}
        </div>
      </div>
      <div>
        <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Linked Processes</div>
        {sourceProcesses.length > 0 ? (
          <div className="mt-2 space-y-2">
            {sourceProcesses.map((process) => (
              <div key={text(process.process_id)} className="rounded-lg bg-slate-50 px-3 py-2 text-sm ring-1 ring-slate-200">
                <div className="font-semibold text-navy-900">{text(process.process_name, 'Linked process')}</div>
                <div className="mt-0.5 text-xs text-slate-500">{text(process.process_id)}</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-600">No linked processes attached.</p>
        )}
      </div>
      <div>
        <div className="text-xs font-bold uppercase tracking-wide text-slate-500">Files In This Group</div>
        <div className="mt-2 overflow-hidden rounded-lg border border-slate-200">
          {Object.entries(files).map(([key, path]) => (
            <div key={`${key}-${path}`} className="border-t border-slate-100 px-3 py-2 first:border-t-0">
              <div className="text-xs font-semibold text-slate-500">{SOURCE_TAB_LABELS[key] ?? key}</div>
              <div className="break-all text-sm font-medium text-navy-900">{path}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
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
