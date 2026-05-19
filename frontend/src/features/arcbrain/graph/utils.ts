import type { ArcbrainLens, ArcbrainNode } from '@/types'

const NODE_TYPE_LAYER: Record<string, string> = {
  business_domain: 'operations',
  business_process: 'operations',
  process_step: 'operations',
  handoff: 'operations',
  actor: 'people',
  team: 'people',
  metadata_object: 'platform',
  metadata_field: 'platform',
  automation: 'platform',
  code_project: 'code',
  code_file: 'code',
  code_folder: 'code',
  code_module: 'code',
  code_route: 'code',
  code_function: 'code',
  code_class: 'code',
  code_type: 'code',
  code_symbol: 'code',
  code_section: 'code',
  apex_class: 'platform',
  permission: 'controls',
  control: 'controls',
  risk: 'controls',
  document: 'evidence',
  document_chunk: 'evidence',
  evidence_claim: 'evidence',
  recommendation: 'replacement',
  replacement_decision: 'replacement',
  agent_action: 'replacement',
  agent_design_package: 'replacement',
  blocker: 'replacement',
}

export function nodeLayer(node: ArcbrainNode): string {
  return node.layer || NODE_TYPE_LAYER[String(node.node_type)] || 'other'
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return 'n/a'
  const normalized = value > 1 ? value : value * 100
  return `${Math.round(normalized)}%`
}

export function formatCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return 'n/a'
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    notation: Math.abs(value) >= 1_000_000 ? 'compact' : 'standard',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'n/a'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function compactLabel(label: string, max = 28): string {
  if (label.length <= max) return label
  const head = Math.max(8, Math.floor(max * 0.62))
  const tail = Math.max(5, max - head - 1)
  return `${label.slice(0, head).trim()}...${label.slice(-tail).trim()}`
}

export function getNodeHeat(node: ArcbrainNode, lens: ArcbrainLens): number {
  if (lens === 'replacement_heat') {
    return clamp01(node.replaceability_score ?? numberFromMetric(node, 'replaceability_score') ?? 0)
  }
  if (lens === 'trust') {
    const confidence = node.confidence ?? numberFromMetric(node, 'confidence') ?? 0
    const evidenceCoverage = numberFromMetric(node, 'evidence_coverage') ?? confidence
    return clamp01((confidence + evidenceCoverage) / 2)
  }
  if (lens === 'blast_radius') {
    return clamp01((node.risk_level === 'high' || node.risk_level === 'critical' ? 0.9 : 0.35) + (node.economic_value ? 0.15 : 0))
  }
  return clamp01((node.confidence ?? 0.45) * 0.5 + (node.replaceability_score ?? 0.25) * 0.35 + (node.economic_value ? 0.15 : 0))
}

export function numberFromMetric(node: ArcbrainNode, key: string): number | null {
  const value = node.metrics_json?.[key] ?? node.metadata_json?.[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value)
  return null
}

export function seededUnit(input: string): number {
  let hash = 2166136261
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return ((hash >>> 0) % 10000) / 10000
}

export function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0
  return Math.max(0, Math.min(1, value))
}
