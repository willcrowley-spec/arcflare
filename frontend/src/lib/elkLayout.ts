import ELK from 'elkjs/lib/elk.bundled.js'
import type { Node, Edge } from '@xyflow/react'
import type { DomainGraphNode, DomainGraphEdge } from '@/types'

const elk = new ELK()

interface LayoutOptions {
  direction: 'RIGHT' | 'DOWN'
  collapsedIds: Set<string>
}

interface ContainerNodeData extends Record<string, unknown> {
  label: string
  leafCount: number
  depth: number
  isCollapsed: boolean
  processId: string
}

interface StepNodeData extends Record<string, unknown> {
  title: string
  subtitle: string
  variant: 'process' | 'doc' | 'record'
  processId: string
}

type MapNodeData = ContainerNodeData | StepNodeData

const STEP_WIDTH = 240
const STEP_HEIGHT = 80
const COLLAPSED_WIDTH = 260
const COLLAPSED_HEIGHT = 50
const CONTAINER_PADDING = 40

interface ElkNode {
  id: string
  width?: number
  height?: number
  children?: ElkNode[]
  layoutOptions?: Record<string, string>
}

function flattenVisible(
  nodes: DomainGraphNode[],
  collapsedIds: Set<string>,
  depth: number,
  parentId: string | null,
): { elkNodes: ElkNode[]; rfMeta: Map<string, { depth: number; parentId: string | null; node: DomainGraphNode }> } {
  const elkNodes: ElkNode[] = []
  const rfMeta = new Map<string, { depth: number; parentId: string | null; node: DomainGraphNode }>()

  for (const n of nodes) {
    rfMeta.set(n.id, { depth, parentId, node: n })

    if (n.is_leaf) {
      elkNodes.push({
        id: n.id,
        width: STEP_WIDTH,
        height: STEP_HEIGHT,
      })
    } else if (collapsedIds.has(n.id)) {
      elkNodes.push({
        id: n.id,
        width: COLLAPSED_WIDTH,
        height: COLLAPSED_HEIGHT,
      })
    } else {
      const childResult = flattenVisible(n.children, collapsedIds, depth + 1, n.id)
      childResult.rfMeta.forEach((v, k) => rfMeta.set(k, v))
      elkNodes.push({
        id: n.id,
        children: childResult.elkNodes,
        layoutOptions: {
          'elk.padding': `[top=${CONTAINER_PADDING + 30},left=${CONTAINER_PADDING},bottom=${CONTAINER_PADDING},right=${CONTAINER_PADDING}]`,
        },
      })
    }
  }

  return { elkNodes, rfMeta }
}

function collectLeafIds(node: DomainGraphNode): string[] {
  if (node.is_leaf) return [node.id]
  return node.children.flatMap(collectLeafIds)
}

function buildCollapsedEdgeMap(
  hierarchy: DomainGraphNode[],
  collapsedIds: Set<string>,
): Map<string, string> {
  const leafToCollapsed = new Map<string, string>()

  function walk(nodes: DomainGraphNode[]) {
    for (const n of nodes) {
      if (!n.is_leaf && collapsedIds.has(n.id)) {
        const leafIds = collectLeafIds(n)
        for (const lid of leafIds) {
          leafToCollapsed.set(lid, n.id)
        }
      } else if (!n.is_leaf) {
        walk(n.children)
      }
    }
  }
  walk(hierarchy)
  return leafToCollapsed
}

export async function computeElkLayout(
  hierarchy: DomainGraphNode[],
  edges: DomainGraphEdge[],
  options: LayoutOptions,
): Promise<{ nodes: Node<MapNodeData>[]; edges: Edge[] }> {
  const { elkNodes, rfMeta } = flattenVisible(hierarchy, options.collapsedIds, 1, null)

  const leafToCollapsed = buildCollapsedEdgeMap(hierarchy, options.collapsedIds)

  const elkEdges: { id: string; sources: string[]; targets: string[] }[] = []
  const seenEdges = new Set<string>()

  for (const e of edges) {
    const src = leafToCollapsed.get(e.source_id) ?? e.source_id
    const tgt = leafToCollapsed.get(e.target_id) ?? e.target_id
    if (src === tgt) continue
    if (!rfMeta.has(src) || !rfMeta.has(tgt)) continue
    const key = `${src}->${tgt}`
    if (seenEdges.has(key)) continue
    seenEdges.add(key)
    elkEdges.push({ id: e.id, sources: [src], targets: [tgt] })
  }

  const elkGraph = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': options.direction,
      'elk.layered.spacing.nodeNodeBetweenLayers': '80',
      'elk.spacing.nodeNode': '40',
      'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
    },
    children: elkNodes,
    edges: elkEdges,
  }

  const layoutResult = await elk.layout(elkGraph)

  const rfNodes: Node<MapNodeData>[] = []

  function extractNodes(elkChildren: typeof layoutResult.children, rfParentId?: string) {
    if (!elkChildren) return
    for (const en of elkChildren) {
      const meta = rfMeta.get(en.id)
      if (!meta) continue
      const { depth, node: graphNode } = meta

      const position = { x: en.x ?? 0, y: en.y ?? 0 }

      if (graphNode.is_leaf) {
        rfNodes.push({
          id: en.id,
          type: 'stepNode',
          position,
          parentId: rfParentId,
          extent: rfParentId ? 'parent' : undefined,
          data: {
            title: graphNode.name,
            subtitle: graphNode.description ?? '',
            variant: 'process',
            processId: graphNode.id,
          } as StepNodeData,
        })
      } else if (options.collapsedIds.has(en.id)) {
        rfNodes.push({
          id: en.id,
          type: 'collapsedContainer',
          position,
          parentId: rfParentId,
          extent: rfParentId ? 'parent' : undefined,
          data: {
            label: graphNode.name,
            leafCount: graphNode.leaf_count,
            depth,
            isCollapsed: true,
            processId: graphNode.id,
          } as ContainerNodeData,
        })
      } else {
        rfNodes.push({
          id: en.id,
          type: 'containerNode',
          position,
          parentId: rfParentId,
          extent: rfParentId ? 'parent' : undefined,
          style: {
            width: en.width ?? 300,
            height: en.height ?? 200,
          },
          data: {
            label: graphNode.name,
            leafCount: graphNode.leaf_count,
            depth,
            isCollapsed: false,
            processId: graphNode.id,
          } as ContainerNodeData,
        })
        extractNodes(en.children, en.id)
      }
    }
  }

  extractNodes(layoutResult.children)

  const rfEdges: Edge[] = []
  for (const e of edges) {
    const src = leafToCollapsed.get(e.source_id) ?? e.source_id
    const tgt = leafToCollapsed.get(e.target_id) ?? e.target_id
    if (src === tgt) continue
    if (!rfMeta.has(src) || !rfMeta.has(tgt)) continue
    const isAggregate = leafToCollapsed.has(e.source_id) || leafToCollapsed.has(e.target_id)
    rfEdges.push({
      id: e.id + (isAggregate ? '-agg' : ''),
      source: src,
      target: tgt,
      type: 'handoff',
      style: {
        stroke: e.is_gap ? '#fca5a5' : isAggregate ? '#94a3b8' : '#cbd5e1',
        strokeWidth: e.is_gap ? 2 : 1.5,
        strokeDasharray: isAggregate ? '6 3' : undefined,
      },
      data: {
        label: e.label,
        description: e.description,
        isGap: e.is_gap,
        isAggregate,
      },
    })
  }

  return { nodes: rfNodes, edges: rfEdges }
}
