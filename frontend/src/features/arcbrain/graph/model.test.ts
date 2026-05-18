import { describe, expect, it } from 'vitest'
import type { ArcbrainGraphModel } from './model'
import { buildArcbrainScene } from './model'
import type { ArcbrainEdge, ArcbrainNode, ArcbrainSearchResult } from '@/types'

function node(id: string, overrides: Partial<ArcbrainNode> = {}): ArcbrainNode {
  return {
    id,
    label: id,
    node_type: 'business_process',
    layer: 'process',
    source_type: 'test',
    source_ref: id,
    confidence: 0.7,
    freshness: 'current',
    risk_level: 'low',
    replaceability_score: 0.4,
    economic_value: 0,
    evidence_refs: [`evidence:${id}`],
    metrics_json: {},
    metadata_json: {},
    community_id: 'service',
    ...overrides,
  }
}

function edge(id: string, source: string, target: string): ArcbrainEdge {
  return {
    id,
    source_node_id: source,
    target_node_id: target,
    edge_type: 'depends_on',
    weight: 1,
    confidence: 0.8,
    evidence_refs: [`evidence:${id}`],
    metrics_json: {},
    metadata_json: {},
  }
}

describe('buildArcbrainScene', () => {
  it('adds conversation focus sets and pulse order from search paths', () => {
    const graph: ArcbrainGraphModel = {
      nodes: [node('case'), node('flow'), node('process'), node('account')],
      edges: [
        edge('edge-flow-case', 'flow', 'case'),
        edge('edge-process-flow', 'process', 'flow'),
        edge('edge-account-case', 'account', 'case'),
      ],
      communities: [{ id: 'service', label: 'Service', member_node_ids: ['case', 'flow', 'process'] }],
      summary: {},
    }
    const searchResult: ArcbrainSearchResult = {
      answer: 'Arcbrain consulted the case path.',
      confidence: 0.82,
      nodes: [graph.nodes[0], graph.nodes[1], graph.nodes[2]],
      edges: [graph.edges[0], graph.edges[1]],
      paths: [['case', 'flow', 'process']],
      suggested_next_questions: [],
    }

    const scene = buildArcbrainScene(graph, 'overview', 'case', searchResult)

    expect([...scene.conversationNodeIds]).toEqual(['case', 'flow', 'process'])
    expect(scene.pulseOrderByNodeId.get('case')).toBe(0)
    expect(scene.pulseOrderByNodeId.get('process')).toBe(2)
    expect(scene.highlightedEdgeIds.has('edge-flow-case')).toBe(true)
    expect(scene.highlightedEdgeIds.has('edge-process-flow')).toBe(true)
    expect(scene.mutedNodeIds.has('account')).toBe(true)
  })

  it('keeps dense same-community nodes separated enough for default rendering', () => {
    const nodes = Array.from({ length: 24 }, (_, index) => node(`service-${index}`))
    const graph: ArcbrainGraphModel = {
      nodes,
      edges: nodes.slice(1).map((item, index) => edge(`edge-${index}`, nodes[index].id, item.id)),
      communities: [{ id: 'service', label: 'Service', member_node_ids: nodes.map((item) => item.id) }],
      summary: {},
    }

    const scene = buildArcbrainScene(graph, 'overview')
    const minimumDistance = scene.nodes.reduce((min, source, sourceIndex) => {
      return scene.nodes.slice(sourceIndex + 1).reduce((innerMin, target) => {
        const distance = Math.hypot(source.x - target.x, source.y - target.y)
        return Math.min(innerMin, distance)
      }, min)
    }, Number.POSITIVE_INFINITY)

    expect(minimumDistance).toBeGreaterThanOrEqual(28)
  })
})
