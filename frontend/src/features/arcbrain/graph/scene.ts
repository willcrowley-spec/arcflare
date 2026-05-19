import type { ArcbrainBlastRadius, ArcbrainEdge, ArcbrainLens, ArcbrainNode, ArcbrainReplacementHeat, ArcbrainSearchResult } from '@/types'
import { positionNodes } from './layout'
import type { ArcbrainGraphModel, ArcbrainScene, ArcbrainSceneEdge } from './types'
import { clamp01, getNodeHeat } from './utils'

const MAX_VISIBLE_SCENE_NODES = 1400

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

  const sceneGraph = limitGraphForScene(graph, heatScores, highlightedNodeIds, lens)
  const nodes = positionNodes(sceneGraph, lens, heatScores)

  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  const edges = sceneGraph.edges.reduce<ArcbrainSceneEdge[]>((acc, edge) => {
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

function limitGraphForScene(
  graph: ArcbrainGraphModel,
  heatScores: Map<string, number>,
  protectedNodeIds: Set<string>,
  lens: ArcbrainLens,
): ArcbrainGraphModel {
  if (graph.nodes.length <= MAX_VISIBLE_SCENE_NODES) return graph

  const selected = selectSceneNodeIds(graph.nodes, graph.edges, heatScores, protectedNodeIds, lens)
  const nodes = graph.nodes.filter((node) => selected.has(node.id))
  const edges = graph.edges.filter((edge) => selected.has(edge.source_node_id) && selected.has(edge.target_node_id))
  const communities = graph.communities.map((community) => ({
    ...community,
    member_node_ids: community.member_node_ids?.filter((id) => selected.has(id)),
  }))
  return { ...graph, nodes, edges, communities }
}

function selectSceneNodeIds(
  nodes: ArcbrainNode[],
  edges: ArcbrainEdge[],
  heatScores: Map<string, number>,
  protectedNodeIds: Set<string>,
  lens: ArcbrainLens,
): Set<string> {
  const degreeByNodeId = new Map<string, number>()
  nodes.forEach((node) => degreeByNodeId.set(node.id, 0))
  edges.forEach((edge) => {
    if (degreeByNodeId.has(edge.source_node_id)) {
      degreeByNodeId.set(edge.source_node_id, (degreeByNodeId.get(edge.source_node_id) ?? 0) + 1)
    }
    if (degreeByNodeId.has(edge.target_node_id)) {
      degreeByNodeId.set(edge.target_node_id, (degreeByNodeId.get(edge.target_node_id) ?? 0) + 1)
    }
  })

  const selected = new Set(nodes.filter((node) => protectedNodeIds.has(node.id)).map((node) => node.id))
  nodes
    .map((node) => ({
      node,
      score:
        (heatScores.get(node.id) ?? getNodeHeat(node, lens)) * 4 +
        (node.confidence ?? 0.45) +
        Math.min(2, (degreeByNodeId.get(node.id) ?? 0) / 8) +
        (node.economic_value ? 0.65 : 0) +
        (node.risk_level === 'high' || node.risk_level === 'critical' ? 0.4 : 0),
    }))
    .sort((a, b) => b.score - a.score || a.node.id.localeCompare(b.node.id))
    .forEach(({ node }) => {
      if (selected.size < MAX_VISIBLE_SCENE_NODES) selected.add(node.id)
    })

  return selected
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
