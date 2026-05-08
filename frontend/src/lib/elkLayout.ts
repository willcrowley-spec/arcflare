import ELK from 'elkjs/lib/elk.bundled.js'
import type { Node, Edge } from '@xyflow/react'
import type { DomainGraphNode, DomainGraphEdge, ProcessMapLens } from '@/types'

const elk = new ELK()

interface LayoutOptions {
  direction: 'RIGHT' | 'DOWN'
  collapsedIds: Set<string>
  positions?: Record<string, { x: number; y: number }>
  lens?: ProcessMapLens
  highlightedIds?: Set<string>
}

interface ContainerNodeData extends Record<string, unknown> {
  label: string
  leafCount: number
  depth: number
  isCollapsed: boolean
  processId: string
  isDimmed?: boolean
  isHighlighted?: boolean
}

interface StepNodeData extends Record<string, unknown> {
  title: string
  subtitle: string
  variant: 'process' | 'doc' | 'record'
  processId: string
  level: string
  status: string
  confidenceScore?: number | null
  needsReview?: boolean
  automationPotential?: string | null
  valueClassification?: string | null
  actorLabels?: string[]
  touchpointLabels?: string[]
  evidenceCount?: number
  searchText?: string
  isDimmed?: boolean
  isHighlighted?: boolean
}

type MapNodeData = ContainerNodeData | StepNodeData

const STEP_WIDTH = 260
const STEP_HEIGHT = 132
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

function textValue(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number') return String(value)
  return null
}

function recordLabel(value: unknown, keys: string[]): string | null {
  if (typeof value === 'string') return textValue(value)
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  for (const key of keys) {
    const label = textValue(record[key])
    if (label) return label
  }
  return null
}

function compactLabels(values: unknown[] | undefined, keys: string[], limit = 3): string[] {
  return (values ?? [])
    .map((value) => recordLabel(value, keys))
    .filter((value): value is string => Boolean(value))
    .slice(0, limit)
}

function evidenceCount(node: DomainGraphNode): number {
  return Array.isArray(node.evidence_sources) ? node.evidence_sources.length : 0
}

function nodeHasAutomationSignal(node: DomainGraphNode): boolean {
  const potential = node.automation_potential?.toLowerCase()
  return potential === 'high' || potential === 'medium'
}

function nodeHasEvidenceSignal(node: DomainGraphNode): boolean {
  return evidenceCount(node) > 0 || typeof node.confidence_score === 'number'
}

function nodeSearchText(node: DomainGraphNode, actorLabels: string[], touchpointLabels: string[]): string {
  const evidenceLabels = compactLabels(node.evidence_sources, ['api_name', 'document_name', 'name', 'type'], 5)
  return [
    node.name,
    node.description,
    node.status,
    node.value_classification,
    node.automation_potential,
    ...actorLabels,
    ...touchpointLabels,
    ...evidenceLabels,
  ].filter(Boolean).join(' ').toLowerCase()
}

function nodeLensState(
  node: DomainGraphNode,
  visibleEdgeEndpoints: Set<string>,
  options: LayoutOptions,
): { isDimmed: boolean; isHighlighted: boolean } {
  const lens = options.lens ?? 'structure'
  const explicit = options.highlightedIds?.has(node.id) ?? false
  let lensMatch = true

  if (lens === 'handoffs') {
    lensMatch = visibleEdgeEndpoints.has(node.id)
  } else if (lens === 'evidence') {
    lensMatch = nodeHasEvidenceSignal(node)
  } else if (lens === 'automation') {
    lensMatch = nodeHasAutomationSignal(node)
  }

  return {
    isDimmed: lens !== 'structure' && !lensMatch && !explicit,
    isHighlighted: explicit || (lens !== 'structure' && lensMatch),
  }
}

function edgeLensState(edge: DomainGraphEdge, options: LayoutOptions): { isDimmed: boolean; isHighlighted: boolean } {
  const lens = options.lens ?? 'structure'
  const explicit = options.highlightedIds?.has(edge.id) ?? false
  let lensMatch = true

  if (lens === 'handoffs') {
    lensMatch = edge.kind !== 'sequence' || edge.is_gap
  } else if (lens === 'evidence') {
    lensMatch = Boolean(edge.evidence_sources?.length) || typeof edge.confidence_score === 'number'
  } else if (lens === 'automation') {
    lensMatch = false
  }

  return {
    isDimmed: lens !== 'structure' && !lensMatch && !explicit,
    isHighlighted: explicit || (lens !== 'structure' && lensMatch),
  }
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
  const visibleEdgeEndpoints = new Set<string>()

  for (const e of edges) {
    const src = leafToCollapsed.get(e.source_id) ?? e.source_id
    const tgt = leafToCollapsed.get(e.target_id) ?? e.target_id
    if (src === tgt) continue
    if (!rfMeta.has(src) || !rfMeta.has(tgt)) continue
    visibleEdgeEndpoints.add(src)
    visibleEdgeEndpoints.add(tgt)
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

      const savedPosition = options.positions?.[en.id]
      const position = savedPosition ?? { x: en.x ?? 0, y: en.y ?? 0 }
      const lensState = nodeLensState(graphNode, visibleEdgeEndpoints, options)

      if (graphNode.is_leaf) {
        const actorLabels = compactLabels(graphNode.actors, ['name', 'role', 'type'])
        const touchpointLabels = compactLabels(graphNode.system_touchpoints, [
          'object_api_name',
          'api_name',
          'name',
          'system',
          'metadata_type',
        ])
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
            level: graphNode.level,
            status: graphNode.status,
            confidenceScore: graphNode.confidence_score,
            needsReview: graphNode.needs_review,
            automationPotential: graphNode.automation_potential,
            valueClassification: graphNode.value_classification,
            actorLabels,
            touchpointLabels,
            evidenceCount: evidenceCount(graphNode),
            searchText: nodeSearchText(graphNode, actorLabels, touchpointLabels),
            ...lensState,
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
            ...lensState,
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
            ...lensState,
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
    const lensState = edgeLensState(e, {
      ...options,
      highlightedIds: new Set([
        ...(options.highlightedIds ?? new Set<string>()),
        ...(options.highlightedIds?.has(src) || options.highlightedIds?.has(tgt) ? [e.id] : []),
      ]),
    })
    const opacity = lensState.isDimmed ? 0.25 : 1
    rfEdges.push({
      id: e.id + (isAggregate ? '-agg' : ''),
      source: src,
      target: tgt,
      type: 'handoff',
      style: {
        stroke: e.is_gap ? '#fca5a5' : isAggregate ? '#94a3b8' : '#cbd5e1',
        strokeWidth: e.is_gap ? 2 : 1.5,
        strokeDasharray: isAggregate ? '6 3' : undefined,
        opacity,
      },
      data: {
        label: e.label,
        description: e.description,
        isGap: e.is_gap,
        isAggregate,
        kind: e.kind ?? 'handoff',
        confidenceScore: e.confidence_score,
        gapStatus: e.gap_status,
        needsReview: e.needs_review,
        evidenceSources: e.evidence_sources ?? [],
        dataTransferred: e.data_transferred ?? [],
        transferMechanism: e.transfer_mechanism,
        ...lensState,
      },
    })
  }

  return { nodes: rfNodes, edges: rfEdges }
}
