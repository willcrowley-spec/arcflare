import type { Edge, Node } from '@xyflow/react'
import type { ReactNode } from 'react'
import { AlertTriangle, Bot, Database, FileSearch, GitBranch, MousePointer2, Users } from 'lucide-react'
import clsx from 'clsx'

type InspectorNodeData = {
  title?: string
  subtitle?: string
  level?: string
  status?: string
  confidenceScore?: number | null
  needsReview?: boolean
  automationPotential?: string | null
  valueClassification?: string | null
  actorLabels?: string[]
  touchpointLabels?: string[]
  evidenceCount?: number
  label?: string
  leafCount?: number
}

type InspectorEdgeData = {
  label?: string
  description?: string | null
  kind?: string
  confidenceScore?: number | null
  isGap?: boolean
  gapStatus?: string | null
  needsReview?: boolean
  evidenceSources?: Record<string, unknown>[]
  dataTransferred?: Record<string, unknown>[]
  transferMechanism?: string | null
  isAggregate?: boolean
}

interface MapInspectorProps {
  selectedNode: Node | null
  selectedEdge: Edge | null
  nodeNameById: Map<string, string>
}

function titleCase(value?: string | null) {
  if (!value) return null
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function confidenceLabel(value?: number | null) {
  if (typeof value !== 'number') return 'Not scored'
  return `${Math.round(value * 100)}% confidence`
}

function recordLabel(value: unknown): string {
  if (typeof value === 'string') return value
  if (!value || typeof value !== 'object') return 'Evidence'
  const record = value as Record<string, unknown>
  const first =
    record.api_name ??
    record.object_api_name ??
    record.document_name ??
    record.name ??
    record.type ??
    record.object ??
    'Evidence'
  return String(first)
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-slate-200 py-4 first:border-t-0 first:pt-0">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  )
}

function Pill({ children, tone = 'slate' }: { children: ReactNode; tone?: 'slate' | 'amber' | 'green' | 'red' | 'blue' }) {
  const styles = {
    slate: 'border-slate-200 bg-slate-50 text-slate-600',
    amber: 'border-amber-200 bg-amber-50 text-amber-700',
    green: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    red: 'border-red-200 bg-red-50 text-red-700',
    blue: 'border-sky-200 bg-sky-50 text-sky-700',
  }
  return <span className={clsx('inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-semibold', styles[tone])}>{children}</span>
}

function CompactList({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p className="text-sm text-slate-500">{empty}</p>
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Pill key={item}>{item}</Pill>
      ))}
    </div>
  )
}

function RecordList({ items, empty }: { items: Record<string, unknown>[]; empty: string }) {
  if (!items.length) return <p className="text-sm text-slate-500">{empty}</p>
  return (
    <ul className="space-y-1.5 text-sm text-slate-700">
      {items.slice(0, 5).map((item, index) => (
        <li key={`${recordLabel(item)}-${index}`} className="rounded-md bg-slate-50 px-2 py-1.5">
          {recordLabel(item)}
        </li>
      ))}
    </ul>
  )
}

export function MapInspector({ selectedNode, selectedEdge, nodeNameById }: MapInspectorProps) {
  if (selectedEdge) {
    const data = (selectedEdge.data ?? {}) as InspectorEdgeData
    const sourceName = nodeNameById.get(selectedEdge.source) ?? selectedEdge.source
    const targetName = nodeNameById.get(selectedEdge.target) ?? selectedEdge.target
    return (
      <aside className="h-full rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-start gap-3">
          <span className={clsx('rounded-lg p-2', data.isGap ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-navy-800')}>
            {data.isGap ? <AlertTriangle className="h-4 w-4" /> : <GitBranch className="h-4 w-4" />}
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-navy-900">{data.label || 'Handoff'}</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              {sourceName} to {targetName}
            </p>
          </div>
        </div>

        <Section title="Status">
          <div className="flex flex-wrap gap-1.5">
            <Pill tone={data.isGap ? 'red' : 'slate'}>{data.isGap ? 'Gap' : titleCase(data.kind) || 'Handoff'}</Pill>
            {data.gapStatus ? <Pill tone="red">{titleCase(data.gapStatus)}</Pill> : null}
            {data.needsReview ? <Pill tone="amber">Needs review</Pill> : null}
            <Pill>{confidenceLabel(data.confidenceScore)}</Pill>
          </div>
        </Section>

        <Section title="Reasoning">
          <p className="text-sm leading-relaxed text-slate-700">{data.description || 'No handoff rationale captured yet.'}</p>
        </Section>

        <Section title="Evidence">
          <RecordList items={data.evidenceSources ?? []} empty="No source evidence linked." />
        </Section>

        <Section title="Data Moved">
          <RecordList items={data.dataTransferred ?? []} empty="No transferred data captured." />
          {data.transferMechanism ? <p className="mt-2 text-xs font-medium text-slate-500">Mechanism: {data.transferMechanism}</p> : null}
        </Section>
      </aside>
    )
  }

  if (selectedNode) {
    const data = (selectedNode.data ?? {}) as InspectorNodeData
    const title = data.title ?? data.label ?? 'Process'
    const isContainer = !data.title
    return (
      <aside className="h-full rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-start gap-3">
          <span className="rounded-lg bg-slate-100 p-2 text-navy-800">
            {isContainer ? <GitBranch className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-navy-900">{title}</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              {isContainer ? `${data.leafCount ?? 0} mapped steps` : data.subtitle || 'No description captured yet.'}
            </p>
          </div>
        </div>

        <Section title="Classification">
          <div className="flex flex-wrap gap-1.5">
            {data.automationPotential ? <Pill tone={data.automationPotential === 'high' ? 'green' : 'blue'}>{titleCase(data.automationPotential)}</Pill> : null}
            {data.valueClassification ? <Pill>{data.valueClassification.toUpperCase()}</Pill> : null}
            {data.needsReview ? <Pill tone="amber">Needs review</Pill> : null}
            <Pill>{confidenceLabel(data.confidenceScore)}</Pill>
          </div>
        </Section>

        <Section title="Actors">
          <CompactList items={data.actorLabels ?? []} empty="No actor evidence captured." />
        </Section>

        <Section title="System Touchpoints">
          <CompactList items={data.touchpointLabels ?? []} empty="No systems or metadata objects linked." />
        </Section>

        <Section title="Evidence">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-lg bg-slate-50 p-2">
              <Users className="mx-auto h-4 w-4 text-slate-400" />
              <p className="mt-1 text-sm font-semibold text-navy-900">{data.actorLabels?.length ?? 0}</p>
              <p className="text-[10px] font-medium text-slate-500">actors</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-2">
              <Database className="mx-auto h-4 w-4 text-slate-400" />
              <p className="mt-1 text-sm font-semibold text-navy-900">{data.touchpointLabels?.length ?? 0}</p>
              <p className="text-[10px] font-medium text-slate-500">systems</p>
            </div>
            <div className="rounded-lg bg-slate-50 p-2">
              <FileSearch className="mx-auto h-4 w-4 text-slate-400" />
              <p className="mt-1 text-sm font-semibold text-navy-900">{data.evidenceCount ?? 0}</p>
              <p className="text-[10px] font-medium text-slate-500">sources</p>
            </div>
          </div>
        </Section>
      </aside>
    )
  }

  return (
    <aside className="h-full rounded-lg border border-dashed border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex h-full min-h-[260px] flex-col items-center justify-center text-center">
        <span className="rounded-lg bg-slate-100 p-3 text-slate-500">
          <MousePointer2 className="h-5 w-5" />
        </span>
        <p className="mt-3 text-sm font-semibold text-navy-900">Select a process or handoff</p>
        <p className="mt-1 max-w-[18rem] text-sm leading-relaxed text-slate-500">
          The inspector shows evidence, actors, touchpoints, automation potential, and gap reasoning for the selected map item.
        </p>
      </div>
    </aside>
  )
}
