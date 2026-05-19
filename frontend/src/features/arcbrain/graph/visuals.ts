import type { ArcbrainCommunity } from '@/types'
import type { PositionedArcbrainNode } from './types'
import { nodeLayer } from './utils'

const FOCUS_ORANGE = '#fb923c'
const MUTED_NODE = '#475569'

const LAYER_ORDER = ['operations', 'people', 'platform', 'code', 'controls', 'evidence', 'replacement', 'other']

export interface ArcbrainLayerVisual {
  layer: string
  label: string
  color: string
  softColor: string
  edgeColor: string
}

export interface ArcbrainNodeVisual extends ArcbrainLayerVisual {
  opacity: number
}

export interface ArcbrainVisualState {
  active?: boolean
  conversation?: boolean
  highlighted?: boolean
  muted?: boolean
}

export interface ArcbrainLayerSummary extends ArcbrainLayerVisual {
  count: number
}

export interface ArcbrainCommunityBeacon {
  id: string
  label: string
  count: number
  dominantLayer: string
  averageHeat: number
  color: string
  center: { x: number; y: number; z: number }
  radius: number
}

export interface ArcbrainSceneBounds {
  center: { x: number; y: number; z: number }
  size: { x: number; y: number; z: number }
  radius: number
}

export const LAYER_VISUALS: Record<string, ArcbrainLayerVisual> = {
  operations: {
    layer: 'operations',
    label: 'Operations',
    color: '#e5eefc',
    softColor: '#31405f',
    edgeColor: '#93a4c7',
  },
  people: {
    layer: 'people',
    label: 'People',
    color: '#bdebd6',
    softColor: '#244b43',
    edgeColor: '#83c8ad',
  },
  platform: {
    layer: 'platform',
    label: 'Platform',
    color: '#c5cffd',
    softColor: '#303660',
    edgeColor: '#9caaf0',
  },
  code: {
    layer: 'code',
    label: 'Code',
    color: '#a8d3f1',
    softColor: '#294963',
    edgeColor: '#7fb8dc',
  },
  controls: {
    layer: 'controls',
    label: 'Controls',
    color: '#f4b8ba',
    softColor: '#593033',
    edgeColor: '#da8e92',
  },
  evidence: {
    layer: 'evidence',
    label: 'Evidence',
    color: '#f3d787',
    softColor: '#584822',
    edgeColor: '#dabf6f',
  },
  replacement: {
    layer: 'replacement',
    label: 'Replacement',
    color: '#fdba74',
    softColor: '#604022',
    edgeColor: '#f59e0b',
  },
  other: {
    layer: 'other',
    label: 'Other',
    color: '#cbd5e1',
    softColor: '#334155',
    edgeColor: '#94a3b8',
  },
}

export function layerVisualForNode(node: PositionedArcbrainNode, state: ArcbrainVisualState = {}): ArcbrainNodeVisual {
  const visual = LAYER_VISUALS[nodeLayer(node)] ?? LAYER_VISUALS.other
  if (state.active || state.conversation) {
    return { ...visual, color: FOCUS_ORANGE, edgeColor: FOCUS_ORANGE, opacity: 1 }
  }
  if (state.highlighted) {
    return { ...visual, color: '#ffb168', edgeColor: FOCUS_ORANGE, opacity: 0.98 }
  }
  if (state.muted) {
    return { ...visual, color: MUTED_NODE, opacity: 0.34 }
  }
  return { ...visual, opacity: 0.86 }
}

export function summarizeSceneLayers(nodes: PositionedArcbrainNode[]): ArcbrainLayerSummary[] {
  const counts = new Map<string, number>()
  nodes.forEach((node) => {
    const layer = nodeLayer(node)
    counts.set(layer, (counts.get(layer) ?? 0) + 1)
  })

  const sortedLayers = [...counts.keys()].sort((a, b) => {
    const aIndex = LAYER_ORDER.indexOf(a)
    const bIndex = LAYER_ORDER.indexOf(b)
    return (aIndex === -1 ? LAYER_ORDER.length : aIndex) - (bIndex === -1 ? LAYER_ORDER.length : bIndex) || a.localeCompare(b)
  })

  return sortedLayers.map((layer) => ({
    ...(LAYER_VISUALS[layer] ?? LAYER_VISUALS.other),
    layer,
    label: LAYER_VISUALS[layer]?.label ?? humanizeLayer(layer),
    count: counts.get(layer) ?? 0,
  }))
}

export function summarizeSceneCommunities(
  nodes: PositionedArcbrainNode[],
  communities: ArcbrainCommunity[],
  limit = 8,
): ArcbrainCommunityBeacon[] {
  const communityLabelById = new Map(communities.map((community) => [community.id, community.label || humanizeLayer(community.id)]))
  const buckets = new Map<string, PositionedArcbrainNode[]>()
  nodes.forEach((node) => {
    const key = node.community_id || nodeLayer(node)
    const bucket = buckets.get(key) ?? []
    bucket.push(node)
    buckets.set(key, bucket)
  })

  return [...buckets.entries()]
    .map(([id, bucket]) => {
      const center = bucket.reduce(
        (acc, node) => ({
          x: acc.x + node.x / bucket.length,
          y: acc.y + node.y / bucket.length,
          z: acc.z + node.z / bucket.length,
        }),
        { x: 0, y: 0, z: 0 },
      )
      const dominantLayer = dominantLayerForNodes(bucket)
      const visual = LAYER_VISUALS[dominantLayer] ?? LAYER_VISUALS.other
      const radius = bucket.reduce((max, node) => {
        const distance = Math.hypot(node.x - center.x, node.y - center.y, node.z - center.z) + node.radius
        return Math.max(max, distance)
      }, 120)
      return {
        id,
        label: communityLabelById.get(id) ?? humanizeLayer(id),
        count: bucket.length,
        dominantLayer,
        averageHeat: bucket.reduce((sum, node) => sum + node.heat, 0) / bucket.length,
        color: visual.color,
        center,
        radius,
      }
    })
    .sort((a, b) => b.count - a.count || b.averageHeat - a.averageHeat || a.label.localeCompare(b.label))
    .slice(0, limit)
}

export function sceneBounds(nodes: PositionedArcbrainNode[]): ArcbrainSceneBounds {
  if (nodes.length === 0) {
    return {
      center: { x: 0, y: 0, z: 0 },
      size: { x: 1, y: 1, z: 1 },
      radius: 1,
    }
  }

  const bounds = nodes.reduce(
    (acc, node) => ({
      minX: Math.min(acc.minX, node.x),
      maxX: Math.max(acc.maxX, node.x),
      minY: Math.min(acc.minY, node.y),
      maxY: Math.max(acc.maxY, node.y),
      minZ: Math.min(acc.minZ, node.z),
      maxZ: Math.max(acc.maxZ, node.z),
      maxRadius: Math.max(acc.maxRadius, node.radius),
    }),
    {
      minX: Number.POSITIVE_INFINITY,
      maxX: Number.NEGATIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
      minZ: Number.POSITIVE_INFINITY,
      maxZ: Number.NEGATIVE_INFINITY,
      maxRadius: 0,
    },
  )
  const center = {
    x: (bounds.minX + bounds.maxX) / 2,
    y: (bounds.minY + bounds.maxY) / 2,
    z: (bounds.minZ + bounds.maxZ) / 2,
  }
  const size = {
    x: bounds.maxX - bounds.minX + bounds.maxRadius * 2,
    y: bounds.maxY - bounds.minY + bounds.maxRadius * 2,
    z: bounds.maxZ - bounds.minZ + bounds.maxRadius * 2,
  }

  return {
    center,
    size,
    radius: Math.hypot(size.x, size.y, size.z) / 2,
  }
}

function dominantLayerForNodes(nodes: PositionedArcbrainNode[]): string {
  const counts = new Map<string, number>()
  nodes.forEach((node) => {
    const layer = nodeLayer(node)
    counts.set(layer, (counts.get(layer) ?? 0) + 1)
  })
  return [...counts.entries()].sort((a, b) => {
    const countDelta = b[1] - a[1]
    if (countDelta !== 0) return countDelta
    return layerOrder(a[0]) - layerOrder(b[0]) || a[0].localeCompare(b[0])
  })[0]?.[0] ?? 'other'
}

function layerOrder(layer: string): number {
  const index = LAYER_ORDER.indexOf(layer)
  return index === -1 ? LAYER_ORDER.length : index
}

function humanizeLayer(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}
