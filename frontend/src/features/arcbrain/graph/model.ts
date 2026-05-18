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
  conversationNodeIds: Set<string>
  mutedNodeIds: Set<string>
  pulseOrderByNodeId: Map<string, number>
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
  const conversationNodeIds = conversationIds(searchResult)
  const pulseOrderByNodeId = new Map<string, number>()

  if (selectedNodeId) highlightedNodeIds.add(selectedNodeId)
  conversationNodeIds.forEach((id) => {
    highlightedNodeIds.add(id)
    if (!pulseOrderByNodeId.has(id)) pulseOrderByNodeId.set(id, pulseOrderByNodeId.size)
  })
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

  const nodes = positionNodes(graph, lens, heatScores)

  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  const edges = graph.edges.reduce<ArcbrainSceneEdge[]>((acc, edge) => {
    const source = nodeById.get(edge.source_node_id)
    const target = nodeById.get(edge.target_node_id)
    if (source && target) acc.push({ ...edge, source, target })
    return acc
  }, [])

  searchResult?.paths?.forEach((path) => {
    pathEdges(path, edges).forEach((edgeId) => highlightedEdgeIds.add(edgeId))
  })

  if (selectedNodeId && highlightedNodeIds.size === 1) {
    edges.forEach((edge) => {
      if (edge.source_node_id === selectedNodeId || edge.target_node_id === selectedNodeId) {
        highlightedEdgeIds.add(edge.id)
        highlightedNodeIds.add(edge.source_node_id)
        highlightedNodeIds.add(edge.target_node_id)
      }
    })
  }

  const mutedNodeIds = new Set<string>()
  if (searchResult || blastRadius || replacementHeat) {
    nodes.forEach((node) => {
      if (!highlightedNodeIds.has(node.id)) mutedNodeIds.add(node.id)
    })
  }

  return { nodes, edges, highlightedNodeIds, highlightedEdgeIds, conversationNodeIds, mutedNodeIds, pulseOrderByNodeId }
}

function positionNodes(
  graph: ArcbrainGraphModel,
  lens: ArcbrainLens,
  heatScores: Map<string, number>,
): PositionedArcbrainNode[] {
  const communityIndex = new Map<string, number>()
  graph.communities.forEach((community, index) => communityIndex.set(community.id, index))
  const fallbackCommunities = new Map<string, number>()
  const nodesByCommunity = new Map<string, ArcbrainNode[]>()

  graph.nodes.forEach((node) => {
    const communityKey = node.community_id || nodeLayer(node)
    if (!fallbackCommunities.has(communityKey)) fallbackCommunities.set(communityKey, fallbackCommunities.size)
    const bucket = nodesByCommunity.get(communityKey) ?? []
    bucket.push(node)
    nodesByCommunity.set(communityKey, bucket)
  })

  const communityKeys = [...nodesByCommunity.keys()].sort((a, b) => {
    const aIndex = communityIndex.get(a) ?? fallbackCommunities.get(a) ?? 0
    const bIndex = communityIndex.get(b) ?? fallbackCommunities.get(b) ?? 0
    return aIndex - bIndex || a.localeCompare(b)
  })
  const communityCount = Math.max(communityKeys.length, 1)

  const nodes = communityKeys.flatMap((communityKey, communityOrder) => {
    const bucket = [...(nodesByCommunity.get(communityKey) ?? [])].sort((a, b) => {
      const aHeat = heatScores.get(a.id) ?? getNodeHeat(a, lens)
      const bHeat = heatScores.get(b.id) ?? getNodeHeat(b, lens)
      return bHeat - aHeat || String(a.label).localeCompare(String(b.label)) || a.id.localeCompare(b.id)
    })
    const orbit = (Math.PI * 2 * communityOrder) / communityCount
    const clusterRadius = communityCount === 1 ? 0 : 230 + Math.min(120, communityCount * 10)
    const centerX = Math.cos(orbit) * clusterRadius
    const centerY = Math.sin(orbit) * clusterRadius * 0.74
    const centerZ = ((seededUnit(`${communityKey}:z`) - 0.5) * 90)

    return bucket.map((node, index) => {
      const heat = heatScores.get(node.id) ?? getNodeHeat(node, lens)
      const importance = clamp01((node.confidence ?? 0.45) * 0.45 + heat * 0.4 + (node.economic_value ? 0.15 : 0))
      const radius = 4.5 + importance * 7
      const localAngle = index * 2.399963 + seededUnit(node.id) * 0.35
      const localRadius = index === 0 ? 0 : Math.sqrt(index) * 42
      const x = centerX + Math.cos(localAngle) * localRadius
      const y = centerY + Math.sin(localAngle) * localRadius * 0.86
      const z = centerZ + ((seededUnit(`${node.id}:z`) - 0.5) * 150) + (nodeLayer(node) === 'replacement' ? 44 : 0)
      return { ...node, x, y, z, radius, heat }
    })
  })

  return relaxCollisions(nodes)
}

function relaxCollisions(nodes: PositionedArcbrainNode[]): PositionedArcbrainNode[] {
  const relaxed = nodes.map((node) => ({ ...node }))
  for (let iteration = 0; iteration < 18; iteration += 1) {
    for (let i = 0; i < relaxed.length; i += 1) {
      for (let j = i + 1; j < relaxed.length; j += 1) {
        const a = relaxed[i]
        const b = relaxed[j]
        const dx = b.x - a.x
        const dy = b.y - a.y
        const distance = Math.max(0.001, Math.hypot(dx, dy))
        const minimum = a.radius + b.radius + 22
        if (distance >= minimum) continue
        const push = (minimum - distance) / 2
        const nx = dx / distance
        const ny = dy / distance
        a.x -= nx * push
        a.y -= ny * push
        b.x += nx * push
        b.y += ny * push
      }
    }
  }
  return relaxed
}

function conversationIds(searchResult?: ArcbrainSearchResult | null): Set<string> {
  const ids = new Set<string>()
  searchResult?.paths?.forEach((path) => path.forEach((id) => ids.add(id)))
  searchResult?.nodes.forEach((node) => ids.add(node.id))
  return ids
}

function pathEdges(path: string[], edges: ArcbrainSceneEdge[]): string[] {
  const edgeByPair = new Map<string, string>()
  edges.forEach((edge) => {
    edgeByPair.set(`${edge.source_node_id}->${edge.target_node_id}`, edge.id)
    edgeByPair.set(`${edge.target_node_id}->${edge.source_node_id}`, edge.id)
  })
  return path.flatMap((sourceId, index) => {
    const targetId = path[index + 1]
    if (!targetId) return []
    return edgeByPair.get(`${sourceId}->${targetId}`) ?? []
  })
}

/*
 * The cluster layout intentionally avoids a force simulation at render time. Arcbrain needs stable positions
 * across questions, so nodes can animate and executives do not lose their mental map.
 */

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
