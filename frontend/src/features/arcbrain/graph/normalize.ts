import type { ArcbrainSearchResult, ArcbrainSnapshotResponse, ArcbrainSummary } from '@/types'
import type { ArcbrainGraphModel } from './types'

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
