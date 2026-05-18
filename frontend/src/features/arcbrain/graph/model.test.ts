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

  it('keeps dense same-community nodes separated enough in 3D space', () => {
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
        const distance = Math.hypot(source.x - target.x, source.y - target.y, source.z - target.z)
        return Math.min(innerMin, distance)
      }, min)
    }, Number.POSITIVE_INFINITY)

    expect(minimumDistance).toBeGreaterThanOrEqual(34)
  })

  it('uses meaningful z depth for operating layers instead of a flat ring', () => {
    const graph: ArcbrainGraphModel = {
      nodes: [
        node('process', { node_type: 'business_process', layer: 'process' }),
        node('metadata', { node_type: 'metadata_object', layer: 'metadata' }),
        node('evidence', { node_type: 'evidence_claim', layer: 'evidence' }),
        node('replacement', { node_type: 'recommendation', layer: 'replacement' }),
      ],
      edges: [
        edge('edge-process-metadata', 'process', 'metadata'),
        edge('edge-metadata-evidence', 'metadata', 'evidence'),
        edge('edge-evidence-replacement', 'evidence', 'replacement'),
      ],
      communities: [{ id: 'service', label: 'Service', member_node_ids: ['process', 'metadata', 'evidence', 'replacement'] }],
      summary: {},
    }

    const scene = buildArcbrainScene(graph, 'overview')
    const byId = new Map(scene.nodes.map((item) => [item.id, item]))
    const zValues = scene.nodes.map((item) => item.z)
    const zSpread = Math.max(...zValues) - Math.min(...zValues)

    expect(zSpread).toBeGreaterThanOrEqual(260)
    expect(byId.get('metadata')!.z).toBeGreaterThan(byId.get('process')!.z)
    expect(byId.get('evidence')!.z).toBeGreaterThan(byId.get('metadata')!.z)
    expect(byId.get('replacement')!.z).toBeGreaterThan(byId.get('evidence')!.z)
  })

  it('relaxes dense layouts in three dimensions, not only screen x/y', () => {
    const nodes = Array.from({ length: 36 }, (_, index) =>
      node(`dense-${index}`, {
        layer: index % 3 === 0 ? 'process' : index % 3 === 1 ? 'evidence' : 'replacement',
        node_type: index % 3 === 0 ? 'business_process' : index % 3 === 1 ? 'evidence_claim' : 'recommendation',
      }),
    )
    const graph: ArcbrainGraphModel = {
      nodes,
      edges: nodes.slice(1).map((item, index) => edge(`dense-edge-${index}`, nodes[index].id, item.id)),
      communities: [{ id: 'service', label: 'Service', member_node_ids: nodes.map((item) => item.id) }],
      summary: {},
    }

    const scene = buildArcbrainScene(graph, 'overview')
    const minimumDistance = scene.nodes.reduce((min, source, sourceIndex) => {
      return scene.nodes.slice(sourceIndex + 1).reduce((innerMin, target) => {
        const distance = Math.hypot(source.x - target.x, source.y - target.y, source.z - target.z)
        return Math.min(innerMin, distance)
      }, min)
    }, Number.POSITIVE_INFINITY)

    expect(minimumDistance).toBeGreaterThanOrEqual(34)
  })

  it('uses a volumetric cloud even when one community has one node layer', () => {
    const nodes = Array.from({ length: 96 }, (_, index) =>
      node(`same-layer-${index}`, {
        layer: 'evidence',
        node_type: 'evidence_claim',
        community_id: 'evidence',
        confidence: 0.55 + (index % 4) * 0.08,
      }),
    )
    const graph: ArcbrainGraphModel = {
      nodes,
      edges: [],
      communities: [{ id: 'evidence', label: 'Evidence', member_node_ids: nodes.map((item) => item.id) }],
      summary: {},
    }

    const scene = buildArcbrainScene(graph, 'overview')
    const xValues = scene.nodes.map((item) => item.x)
    const yValues = scene.nodes.map((item) => item.y)
    const zValues = scene.nodes.map((item) => item.z)
    const xSpread = Math.max(...xValues) - Math.min(...xValues)
    const ySpread = Math.max(...yValues) - Math.min(...yValues)
    const zSpread = Math.max(...zValues) - Math.min(...zValues)

    expect(zSpread).toBeGreaterThanOrEqual(260)
    expect(zSpread).toBeGreaterThanOrEqual(Math.min(xSpread, ySpread) * 0.45)
  })

  it('caps very large scenes without dropping selected or conversation nodes', () => {
    const nodes = Array.from({ length: 1505 }, (_, index) =>
      node(`large-${index}`, {
        community_id: `community-${index % 8}`,
        confidence: index % 5 === 0 ? 0.9 : 0.1,
        replaceability_score: index % 7 === 0 ? 0.9 : 0.1,
        economic_value: index % 11 === 0 ? 100000 : 0,
      }),
    )
    const selected = nodes[1503]
    const consulted = nodes[1504]
    const graph: ArcbrainGraphModel = {
      nodes,
      edges: [],
      communities: Array.from({ length: 8 }, (_, index) => ({ id: `community-${index}`, label: `Community ${index}` })),
      summary: {},
    }
    const searchResult: ArcbrainSearchResult = {
      answer: 'Arcbrain consulted the protected node.',
      confidence: 0.8,
      nodes: [consulted],
      edges: [],
      paths: [[consulted.id]],
    }

    const scene = buildArcbrainScene(graph, 'overview', selected.id, searchResult)
    const renderedIds = new Set(scene.nodes.map((item) => item.id))

    expect(scene.nodes.length).toBeLessThanOrEqual(1400)
    expect(renderedIds.has(selected.id)).toBe(true)
    expect(renderedIds.has(consulted.id)).toBe(true)
  })
})
