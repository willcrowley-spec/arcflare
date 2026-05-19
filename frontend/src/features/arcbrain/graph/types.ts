import type { ArcbrainCommunity, ArcbrainEdge, ArcbrainNode, ArcbrainSummary } from '@/types'

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
