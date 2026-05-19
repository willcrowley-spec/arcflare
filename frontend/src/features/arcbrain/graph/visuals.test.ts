import { describe, expect, it } from 'vitest'
import type { ArcbrainCommunity, ArcbrainNode } from '@/types'
import type { PositionedArcbrainNode } from './model'
import {
  layerVisualForNode,
  sceneBounds,
  summarizeSceneCommunities,
  summarizeSceneLayers,
} from './visuals'

function positionedNode(id: string, overrides: Partial<PositionedArcbrainNode> = {}): PositionedArcbrainNode {
  const base: ArcbrainNode = {
    id,
    label: id,
    node_type: 'business_process',
    layer: 'operations',
    source_type: 'test',
    source_ref: id,
    confidence: 0.7,
    freshness: 'current',
    risk_level: 'low',
    replaceability_score: 0.35,
    economic_value: 0,
    evidence_refs: [],
    metrics_json: {},
    metadata_json: {},
    community_id: 'service',
  }
  return {
    ...base,
    x: 0,
    y: 0,
    z: 0,
    radius: 6,
    heat: 0.4,
    ...overrides,
  }
}

describe('Arcbrain visual model', () => {
  it('uses distinct layer colors and reserves orange for focus/action', () => {
    const operations = positionedNode('process', { layer: 'operations' })
    const platform = positionedNode('flow', { layer: 'platform' })
    const evidence = positionedNode('evidence', { layer: 'evidence' })

    expect(layerVisualForNode(operations).color).not.toEqual(layerVisualForNode(platform).color)
    expect(layerVisualForNode(platform).color).not.toEqual(layerVisualForNode(evidence).color)
    expect(layerVisualForNode(operations, { conversation: true }).color).toBe('#fb923c')
    expect(layerVisualForNode(operations, { muted: true }).color).not.toBe(layerVisualForNode(operations).color)
  })

  it('summarizes visible layers by count with stable labels', () => {
    const summaries = summarizeSceneLayers([
      positionedNode('process-a', { layer: 'operations' }),
      positionedNode('process-b', { layer: 'operations' }),
      positionedNode('evidence-a', { layer: 'evidence' }),
      positionedNode('replacement-a', { layer: 'replacement' }),
    ])

    expect(summaries.map((summary) => `${summary.label}:${summary.count}`)).toEqual([
      'Operations:2',
      'Evidence:1',
      'Replacement:1',
    ])
  })

  it('builds top community beacons with centroid, layer, and heat context', () => {
    const communities: ArcbrainCommunity[] = [
      { id: 'service', label: 'Service', member_node_ids: ['case', 'flow', 'claim'] },
      { id: 'finance', label: 'Finance', member_node_ids: ['invoice'] },
    ]
    const summaries = summarizeSceneCommunities(
      [
        positionedNode('case', { community_id: 'service', x: 10, y: 20, z: 30, heat: 0.9, layer: 'operations' }),
        positionedNode('flow', { community_id: 'service', x: 20, y: 30, z: 40, heat: 0.3, layer: 'platform' }),
        positionedNode('claim', { community_id: 'service', x: 30, y: 40, z: 50, heat: 0.6, layer: 'evidence' }),
        positionedNode('invoice', { community_id: 'finance', x: 100, y: 200, z: 300, heat: 0.2, layer: 'replacement' }),
      ],
      communities,
      1,
    )

    expect(summaries).toHaveLength(1)
    expect(summaries[0]).toMatchObject({
      id: 'service',
      label: 'Service',
      count: 3,
      dominantLayer: 'operations',
    })
    expect(summaries[0].averageHeat).toBeCloseTo(0.6)
    expect(summaries[0].center).toEqual({ x: 20, y: 30, z: 40 })
  })

  it('calculates scene bounds for depth staging and camera overlays', () => {
    const bounds = sceneBounds([
      positionedNode('left', { x: -120, y: -20, z: -40, radius: 10 }),
      positionedNode('right', { x: 180, y: 60, z: 120, radius: 20 }),
    ])

    expect(bounds.center).toEqual({ x: 30, y: 20, z: 40 })
    expect(bounds.size.x).toBe(340)
    expect(bounds.size.y).toBe(120)
    expect(bounds.size.z).toBe(200)
    expect(bounds.radius).toBeGreaterThan(200)
  })
})
