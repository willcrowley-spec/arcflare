import type { ArcbrainLens, ArcbrainNode } from '@/types'
import type { ArcbrainGraphModel, PositionedArcbrainNode } from './types'
import { clamp01, getNodeHeat, nodeLayer, seededUnit } from './utils'

export function positionNodes(
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
  const depthByNodeId = dependencyDepthByNodeId(graph)

  const nodes = communityKeys.flatMap((communityKey, communityOrder) => {
    const bucket = [...(nodesByCommunity.get(communityKey) ?? [])].sort((a, b) => {
      const aHeat = heatScores.get(a.id) ?? getNodeHeat(a, lens)
      const bHeat = heatScores.get(b.id) ?? getNodeHeat(b, lens)
      return bHeat - aHeat || String(a.label).localeCompare(String(b.label)) || a.id.localeCompare(b.id)
    })
    const anchor = communityAnchor(communityKey, communityOrder, communityCount)
    const sameLayerBucket = new Set(bucket.map((node) => nodeLayer(node))).size <= 1

    return bucket.map((node, index) => {
      const heat = heatScores.get(node.id) ?? getNodeHeat(node, lens)
      const importance = clamp01((node.confidence ?? 0.45) * 0.45 + heat * 0.4 + (node.economic_value ? 0.15 : 0))
      const radius = 4.5 + importance * 7
      const local = volumetricOffset(node, index, bucket.length, communityKey)
      const depthZ = layerDepth(node) + (depthByNodeId.get(node.id) ?? 0) * 24
      const x = anchor.x + local.x
      const y = anchor.y + local.y
      const z = anchor.z + depthZ + local.z * (sameLayerBucket ? 1 : 0.24)
      return { ...node, x, y, z, radius, heat }
    })
  })

  return centerNodes(relaxCollisions(nodes))
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
        const dz = b.z - a.z
        const distance = Math.max(0.001, Math.hypot(dx, dy, dz))
        const minimum = a.radius + b.radius + 24
        if (distance >= minimum) continue
        const push = (minimum - distance) / 2
        const nx = dx / distance
        const ny = dy / distance
        const nz = dz / distance
        a.x -= nx * push
        a.y -= ny * push
        a.z -= nz * push
        b.x += nx * push
        b.y += ny * push
        b.z += nz * push
      }
    }
  }
  return relaxed
}

function centerNodes(nodes: PositionedArcbrainNode[]): PositionedArcbrainNode[] {
  if (nodes.length === 0) return nodes
  const bounds = nodes.reduce(
    (acc, node) => ({
      minX: Math.min(acc.minX, node.x),
      maxX: Math.max(acc.maxX, node.x),
      minY: Math.min(acc.minY, node.y),
      maxY: Math.max(acc.maxY, node.y),
      minZ: Math.min(acc.minZ, node.z),
      maxZ: Math.max(acc.maxZ, node.z),
    }),
    {
      minX: Number.POSITIVE_INFINITY,
      maxX: Number.NEGATIVE_INFINITY,
      minY: Number.POSITIVE_INFINITY,
      maxY: Number.NEGATIVE_INFINITY,
      minZ: Number.POSITIVE_INFINITY,
      maxZ: Number.NEGATIVE_INFINITY,
    },
  )
  const centerX = (bounds.minX + bounds.maxX) / 2
  const centerY = (bounds.minY + bounds.maxY) / 2
  const centerZ = (bounds.minZ + bounds.maxZ) / 2
  return nodes.map((node) => ({
    ...node,
    x: node.x - centerX,
    y: node.y - centerY,
    z: node.z - centerZ,
  }))
}

function volumetricOffset(
  node: ArcbrainNode,
  index: number,
  count: number,
  communityKey: string,
): { x: number; y: number; z: number } {
  if (count <= 1) return { x: 0, y: 0, z: 0 }

  const seed = seededUnit(`${communityKey}:${node.id}:volume`)
  const sample = index + 0.5 + seed * 0.72
  const normalized = sample / count
  const goldenAngle = Math.PI * (3 - Math.sqrt(5))
  const zUnit = 1 - 2 * normalized
  const radiusAtZ = Math.sqrt(Math.max(0, 1 - zUnit * zUnit))
  const angle = sample * goldenAngle + seed * Math.PI * 2
  const directionX = Math.cos(angle) * radiusAtZ
  const directionY = Math.sin(angle) * radiusAtZ
  const directionZ = zUnit
  const shell = Math.cbrt(Math.min(1, (index + 1 + seed) / count))
  const spread = 150 + Math.min(460, Math.cbrt(count) * 54)
  const jitter = (axis: string) => (seededUnit(`${node.id}:${axis}`) - 0.5) * 18

  return {
    x: directionX * spread * shell + jitter('x'),
    y: directionY * spread * shell * 0.9 + jitter('y'),
    z: directionZ * spread * shell + jitter('z'),
  }
}

function communityAnchor(communityKey: string, index: number, count: number): { x: number; y: number; z: number } {
  if (count <= 1) return { x: 0, y: 0, z: 0 }
  const radius = 280 + Math.min(220, count * 18)
  const goldenAngle = Math.PI * (3 - Math.sqrt(5))
  const yUnit = 1 - (2 * (index + 0.5)) / count
  const ringRadius = Math.sqrt(Math.max(0, 1 - yUnit * yUnit))
  const angle = index * goldenAngle + seededUnit(communityKey) * 0.35
  return {
    x: Math.cos(angle) * ringRadius * radius,
    y: yUnit * radius * 0.72,
    z: Math.sin(angle) * ringRadius * radius,
  }
}

function layerDepth(node: ArcbrainNode): number {
  const layer = nodeLayer(node)
  if (layer === 'process' || layer === 'operations') return -170
  if (layer === 'people') return -90
  if (layer === 'metadata' || layer === 'platform') return -20
  if (layer === 'code') return 38
  if (layer === 'controls') return 52
  if (layer === 'evidence') return 125
  if (layer === 'replacement') return 255
  return 0
}

function dependencyDepthByNodeId(graph: ArcbrainGraphModel): Map<string, number> {
  const nodeIds = new Set(graph.nodes.map((node) => node.id))
  const inbound = new Map<string, number>()
  const outbound = new Map<string, string[]>()
  nodeIds.forEach((id) => {
    inbound.set(id, 0)
    outbound.set(id, [])
  })
  graph.edges.forEach((edge) => {
    if (!nodeIds.has(edge.source_node_id) || !nodeIds.has(edge.target_node_id)) return
    inbound.set(edge.target_node_id, (inbound.get(edge.target_node_id) ?? 0) + 1)
    outbound.get(edge.source_node_id)?.push(edge.target_node_id)
  })
  const queue = [...nodeIds].filter((id) => (inbound.get(id) ?? 0) === 0).sort()
  const depth = new Map(queue.map((id) => [id, 0]))
  while (queue.length > 0) {
    const id = queue.shift()!
    const baseDepth = depth.get(id) ?? 0
    for (const nextId of outbound.get(id) ?? []) {
      const nextDepth = Math.max(depth.get(nextId) ?? 0, baseDepth + 1)
      depth.set(nextId, nextDepth)
      inbound.set(nextId, Math.max(0, (inbound.get(nextId) ?? 0) - 1))
      if (inbound.get(nextId) === 0) queue.push(nextId)
    }
  }
  nodeIds.forEach((id) => {
    if (!depth.has(id)) depth.set(id, 0)
  })
  return depth
}
