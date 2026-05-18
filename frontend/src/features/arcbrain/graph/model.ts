import type {
  ArcbrainBlastRadius,
  ArcbrainCommunity,
  ArcbrainEdge,
  ArcbrainLens,
  ArcbrainNode,
  ArcbrainReplacementHeat,
  ArcbrainSearchResult,
  ArcbrainSnapshotResponse,
  ArcbrainSummary,
} from '@/types'

export interface ArcbrainGraphModel {
  nodes: ArcbrainNode[]
  edges: ArcbrainEdge[]
  communities: ArcbrainCommunity[]
  summary: ArcbrainSummary
}

export interface PositionedArcbrainNode extends ArcbrainNode {
  x: number
  y: number
  z: number
  radius: number
  heat: number
}

export interface ArcbrainSceneEdge extends ArcbrainEdge {
  source: PositionedArcbrainNode
  target: PositionedArcbrainNode
}

export interface ArcbrainScene {
  nodes: PositionedArcbrainNode[]
  edges: ArcbrainSceneEdge[]
  highlightedNodeIds: Set<string>
  highlightedEdgeIds: Set<string>
}

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

export function normalizeArcbrainSnapshot(raw: ArcbrainSnapshotResponse | null | undefined): ArcbrainGraphModel {
  const nodes = Array.isArray(raw?.nodes) ? raw.nodes.filter((n) => n?.id && n?.label) : []
  const nodeIds = new Set(nodes.map((n) => n.id))
  const edges = Array.isArray(raw?.edges)
    ? raw.edges.filter((e) => e?.id && nodeIds.has(e.source_node_id) && nodeIds.has(e.target_node_id))
    : []
  const communities = Array.isArray(raw?.communities) ? raw.communities.filter((c) => c?.id) : []
  const summaryFromSnapshot =
    raw?.snapshot?.summary_json && !Array.isArray(raw.snapshot.summary_json)
      ? (raw.snapshot.summary_json as ArcbrainSummary)
      : {}
  const summary: ArcbrainSummary = {
    ...summaryFromSnapshot,
    ...(raw?.summary ?? {}),
    node_count: raw?.summary?.node_count ?? raw?.snapshot?.node_count ?? nodes.length,
    edge_count: raw?.summary?.edge_count ?? raw?.snapshot?.edge_count ?? edges.length,
    community_count: raw?.summary?.community_count ?? communities.length,
    avg_confidence: raw?.summary?.avg_confidence ?? raw?.summary?.average_confidence ?? null,
    replacement_value:
      raw?.summary?.replacement_value ?? raw?.summary?.replacement_value_total ?? null,
    staleness_status: raw?.summary?.staleness_status ?? raw?.snapshot?.staleness_status ?? null,
    projection_status: raw?.summary?.projection_status ?? raw?.snapshot?.projection_status ?? null,
    generated_at: raw?.summary?.generated_at ?? raw?.snapshot?.created_at ?? null,
  }
  return { nodes, edges, communities, summary }
}

export function normalizeSearchResult(raw: ArcbrainSearchResult | null | undefined): ArcbrainSearchResult | null {
  if (!raw) return null
  return {
    ...raw,
    nodes: Array.isArray(raw.nodes) ? raw.nodes : [],
    edges: Array.isArray(raw.edges) ? raw.edges : [],
    paths: Array.isArray(raw.paths) ? raw.paths : [],
    supporting_claims: Array.isArray(raw.supporting_claims) ? raw.supporting_claims : [],
    assumptions: Array.isArray(raw.assumptions) ? raw.assumptions : [],
    missing_evidence: Array.isArray(raw.missing_evidence) ? raw.missing_evidence : [],
    suggested_next_questions: Array.isArray(raw.suggested_next_questions) ? raw.suggested_next_questions : [],
  }
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

export function buildArcbrainScene(
  graph: ArcbrainGraphModel,
  lens: ArcbrainLens,
  selectedNodeId?: string | null,
  searchResult?: ArcbrainSearchResult | null,
  blastRadius?: ArcbrainBlastRadius | null,
  replacementHeat?: ArcbrainReplacementHeat | null,
): ArcbrainScene {
  const highlightedNodeIds = new Set<string>()
  const highlightedEdgeIds = new Set<string>()

  if (selectedNodeId) highlightedNodeIds.add(selectedNodeId)
  searchResult?.nodes.forEach((n) => highlightedNodeIds.add(n.id))
  searchResult?.edges.forEach((e) => highlightedEdgeIds.add(e.id))
  searchResult?.paths?.flat().forEach((id) => highlightedNodeIds.add(id))

  if (blastRadius) {
    blastRadius.upstream_nodes.forEach((n) => highlightedNodeIds.add(n.id))
    blastRadius.downstream_nodes.forEach((n) => highlightedNodeIds.add(n.id))
    ;(blastRadius.related_nodes ?? []).forEach((n) => highlightedNodeIds.add(n.id))
    ;(blastRadius.affected_processes ?? []).forEach((n) => highlightedNodeIds.add(n.id))
    ;(blastRadius.affected_teams ?? []).forEach((n) => highlightedNodeIds.add(n.id))
    ;(blastRadius.affected_edges ?? blastRadius.edges ?? []).forEach((e) => highlightedEdgeIds.add(e.id))
  }

  const heatScores = new Map<string, number>()
  const heatItems =
    replacementHeat?.items ??
    replacementHeat?.nodes?.map((node) => ({
      node,
      replaceability_score: node.replaceability_score ?? null,
      economic_value: node.economic_value ?? null,
      confidence: node.confidence ?? null,
      risk_level: node.risk_level ?? null,
    })) ??
    []

  heatItems.forEach((item) => {
    heatScores.set(item.node.id, clamp01(item.replaceability_score ?? item.node.replaceability_score ?? 0))
  })

  const communityIndex = new Map<string, number>()
  graph.communities.forEach((c, i) => communityIndex.set(c.id, i))
  const fallbackCommunities = new Map<string, number>()

  const nodes = graph.nodes.map((node, i) => {
    const communityKey = node.community_id || nodeLayer(node)
    if (!fallbackCommunities.has(communityKey)) fallbackCommunities.set(communityKey, fallbackCommunities.size)
    const community = communityIndex.get(communityKey) ?? fallbackCommunities.get(communityKey) ?? 0
    const communityCount = Math.max(graph.communities.length, fallbackCommunities.size, 1)
    const orbit = (Math.PI * 2 * community) / communityCount
    const local = seededUnit(node.id)
    const ring = 150 + (community % 3) * 42
    const spread = 46 + ((i % 5) * 8)
    const heat = heatScores.get(node.id) ?? getNodeHeat(node, lens)
    const importance = clamp01((node.confidence ?? 0.45) * 0.45 + heat * 0.4 + (node.economic_value ? 0.15 : 0))
    const radius = 4.5 + importance * 7
    const x = Math.cos(orbit) * ring + Math.cos(local * Math.PI * 2) * spread
    const y = Math.sin(orbit) * ring + Math.sin(local * Math.PI * 2) * spread
    const z = ((seededUnit(`${node.id}:z`) - 0.5) * 180) + (nodeLayer(node) === 'replacement' ? 44 : 0)
    return { ...node, x, y, z, radius, heat }
  })

  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  const edges = graph.edges.reduce<ArcbrainSceneEdge[]>((acc, edge) => {
    const source = nodeById.get(edge.source_node_id)
    const target = nodeById.get(edge.target_node_id)
    if (source && target) acc.push({ ...edge, source, target })
    return acc
  }, [])

  if (selectedNodeId && highlightedNodeIds.size === 1) {
    edges.forEach((edge) => {
      if (edge.source_node_id === selectedNodeId || edge.target_node_id === selectedNodeId) {
        highlightedEdgeIds.add(edge.id)
        highlightedNodeIds.add(edge.source_node_id)
        highlightedNodeIds.add(edge.target_node_id)
      }
    })
  }

  return { nodes, edges, highlightedNodeIds, highlightedEdgeIds }
}

function numberFromMetric(node: ArcbrainNode, key: string): number | null {
  const value = node.metrics_json?.[key] ?? node.metadata_json?.[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value)
  return null
}

function seededUnit(input: string): number {
  let hash = 2166136261
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return ((hash >>> 0) % 10000) / 10000
}

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0
  return Math.max(0, Math.min(1, value))
}
