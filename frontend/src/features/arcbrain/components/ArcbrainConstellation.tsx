import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import clsx from 'clsx'
import { Maximize2, MousePointer2, RotateCcw } from 'lucide-react'
import type { ArcbrainLens } from '@/types'
import {
  buildArcbrainScene,
  compactLabel,
  type ArcbrainGraphModel,
  type ArcbrainScene,
  type PositionedArcbrainNode,
} from '../graph/model'
import type { ArcbrainBlastRadius, ArcbrainReplacementHeat, ArcbrainSearchResult } from '@/types'

interface ArcbrainConstellationProps {
  graph: ArcbrainGraphModel
  lens: ArcbrainLens
  selectedNodeId: string | null
  onSelectNode: (nodeId: string) => void
  searchResult?: ArcbrainSearchResult | null
  blastRadius?: ArcbrainBlastRadius | null
  replacementHeat?: ArcbrainReplacementHeat | null
}

interface ProjectedNode extends PositionedArcbrainNode {
  sx: number
  sy: number
  scale: number
}

const LENS_LABEL: Record<ArcbrainLens, string> = {
  overview: 'Overview',
  replacement_heat: 'Replacement Heat',
  blast_radius: 'Blast Radius',
  trust: 'Trust',
}

const LAYER_COLOR: Record<string, string> = {
  process: '#f8fafc',
  operations: '#f8fafc',
  people: '#bfdbfe',
  metadata: '#c7d2fe',
  platform: '#c7d2fe',
  controls: '#fecaca',
  evidence: '#fde68a',
  replacement: '#fdba74',
  other: '#d1d5db',
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return reduced
}

export function ArcbrainConstellation({
  graph,
  lens,
  selectedNodeId,
  onSelectNode,
  searchResult,
  blastRadius,
  replacementHeat,
}: ArcbrainConstellationProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const projectedRef = useRef<ProjectedNode[]>([])
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [size, setSize] = useState({ width: 320, height: 520 })
  const reducedMotion = useReducedMotion()

  const scene = useMemo(
    () => buildArcbrainScene(graph, lens, selectedNodeId, searchResult, blastRadius, replacementHeat),
    [graph, lens, selectedNodeId, searchResult, blastRadius, replacementHeat],
  )

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const resize = () => {
      const rect = el.getBoundingClientRect()
      setSize({ width: Math.max(320, rect.width), height: Math.max(420, rect.height) })
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const draw = useCallback(
    (rotation: number) => {
      const canvas = canvasRef.current
      if (!canvas) return
      const dpr = window.devicePixelRatio || 1
      canvas.width = Math.floor(size.width * dpr)
      canvas.height = Math.floor(size.height * dpr)
      canvas.style.width = `${size.width}px`
      canvas.style.height = `${size.height}px`
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      paintScene(ctx, scene, size.width, size.height, rotation, selectedNodeId, hoveredNodeId)
      projectedRef.current = projectNodes(scene.nodes, size.width, size.height, rotation)
    },
    [hoveredNodeId, scene, selectedNodeId, size.height, size.width],
  )

  useEffect(() => {
    let frame = 0
    let start = performance.now()
    const tick = (now: number) => {
      const rotation = reducedMotion ? 0.28 : 0.28 + ((now - start) / 28000)
      draw(rotation)
      if (!reducedMotion) frame = window.requestAnimationFrame(tick)
    }
    frame = window.requestAnimationFrame(tick)
    return () => {
      start = 0
      window.cancelAnimationFrame(frame)
    }
  }, [draw, reducedMotion])

  const handlePointerMove = (event: PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    const hit = hitTest(projectedRef.current, x, y)
    setHoveredNodeId(hit?.id ?? null)
  }

  const handleClick = () => {
    if (hoveredNodeId) onSelectNode(hoveredNodeId)
  }

  const selected = selectedNodeId ? graph.nodes.find((n) => n.id === selectedNodeId) : null
  const hovered = hoveredNodeId ? graph.nodes.find((n) => n.id === hoveredNodeId) : null

  return (
    <section className="flex min-h-[520px] min-w-0 flex-col overflow-hidden rounded-xl border border-navy-900 bg-navy-900 shadow-sm ring-1 ring-slate-900/10">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white">Executive Constellation</p>
          <p className="text-xs text-slate-400">{LENS_LABEL[lens]} lens / {graph.nodes.length} nodes / {graph.edges.length} edges</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-300">
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/8 px-2.5 py-1.5 ring-1 ring-white/10">
            <MousePointer2 className="h-3.5 w-3.5 text-orange-300" />
            Select a node
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/8 px-2.5 py-1.5 ring-1 ring-white/10">
            {reducedMotion ? <Maximize2 className="h-3.5 w-3.5" /> : <RotateCcw className="h-3.5 w-3.5" />}
            {reducedMotion ? 'Static' : 'Reduced drift'}
          </span>
        </div>
      </div>

      <div ref={containerRef} className="relative min-h-[460px] flex-1">
        <canvas
          ref={canvasRef}
          className={clsx('block h-full w-full touch-none', hoveredNodeId ? 'cursor-pointer' : 'cursor-crosshair')}
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHoveredNodeId(null)}
          onClick={handleClick}
          aria-label="Arcbrain constellation graph"
        />
        {(hovered || selected) && (
          <div className="pointer-events-none absolute left-4 top-4 max-w-[min(320px,calc(100%-2rem))] rounded-lg border border-white/10 bg-navy-800/95 p-3 text-white shadow-xl">
            <p className="truncate text-sm font-semibold">{hovered?.label ?? selected?.label}</p>
            <p className="mt-1 text-xs text-slate-300">{String((hovered ?? selected)?.node_type).replace(/_/g, ' ')}</p>
            {(hovered ?? selected)?.summary ? (
              <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-slate-300">{(hovered ?? selected)?.summary}</p>
            ) : null}
          </div>
        )}
      </div>
    </section>
  )
}

function paintScene(
  ctx: CanvasRenderingContext2D,
  scene: ArcbrainScene,
  width: number,
  height: number,
  rotation: number,
  selectedNodeId: string | null,
  hoveredNodeId: string | null,
) {
  const grd = ctx.createLinearGradient(0, 0, width, height)
  grd.addColorStop(0, '#0f1736')
  grd.addColorStop(0.58, '#111827')
  grd.addColorStop(1, '#1f2937')
  ctx.fillStyle = grd
  ctx.fillRect(0, 0, width, height)

  drawGrid(ctx, width, height)

  const projected = projectNodes(scene.nodes, width, height, rotation)
  const projectedById = new Map(projected.map((n) => [n.id, n]))

  scene.edges.forEach((edge) => {
    const source = projectedById.get(edge.source_node_id)
    const target = projectedById.get(edge.target_node_id)
    if (!source || !target) return
    const highlighted = scene.highlightedEdgeIds.has(edge.id) || scene.highlightedNodeIds.has(source.id) || scene.highlightedNodeIds.has(target.id)
    ctx.beginPath()
    ctx.moveTo(source.sx, source.sy)
    ctx.lineTo(target.sx, target.sy)
    ctx.strokeStyle = highlighted ? 'rgba(251, 146, 60, 0.76)' : 'rgba(148, 163, 184, 0.18)'
    ctx.lineWidth = highlighted ? 1.6 : 0.8
    ctx.stroke()
  })

  projected
    .sort((a, b) => a.scale - b.scale)
    .forEach((node) => {
      const highlighted = scene.highlightedNodeIds.has(node.id)
      const active = selectedNodeId === node.id || hoveredNodeId === node.id
      const color = colorForNode(node)
      const radius = Math.max(3.5, node.radius * node.scale)

      if (highlighted || active) {
        ctx.beginPath()
        ctx.arc(node.sx, node.sy, radius + 8, 0, Math.PI * 2)
        ctx.fillStyle = active ? 'rgba(251, 146, 60, 0.18)' : 'rgba(251, 146, 60, 0.11)'
        ctx.fill()
      }

      ctx.beginPath()
      ctx.arc(node.sx, node.sy, radius, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()
      ctx.lineWidth = active ? 2 : 1
      ctx.strokeStyle = active ? '#fb923c' : highlighted ? 'rgba(251, 146, 60, 0.8)' : 'rgba(255, 255, 255, 0.28)'
      ctx.stroke()

      if (active || highlighted || node.radius > 9) {
        drawNodeLabel(ctx, node, radius, active)
      }
    })
}

function projectNodes(nodes: PositionedArcbrainNode[], width: number, height: number, rotation: number): ProjectedNode[] {
  const cx = width / 2
  const cy = height / 2
  const scaleBase = Math.min(width, height) / 600
  return nodes.map((node) => {
    const cos = Math.cos(rotation)
    const sin = Math.sin(rotation)
    const rx = node.x * cos - node.z * sin
    const rz = node.x * sin + node.z * cos
    const perspective = 520 / (520 + rz)
    return {
      ...node,
      sx: cx + rx * perspective * scaleBase,
      sy: cy + node.y * perspective * scaleBase * 0.86,
      scale: Math.max(0.52, Math.min(1.5, perspective)),
    }
  })
}

function hitTest(nodes: ProjectedNode[], x: number, y: number): ProjectedNode | null {
  let best: ProjectedNode | null = null
  let bestDistance = Number.POSITIVE_INFINITY
  nodes.forEach((node) => {
    const radius = Math.max(10, node.radius * node.scale + 4)
    const distance = Math.hypot(node.sx - x, node.sy - y)
    if (distance <= radius && distance < bestDistance) {
      best = node
      bestDistance = distance
    }
  })
  return best
}

function drawGrid(ctx: CanvasRenderingContext2D, width: number, height: number) {
  ctx.save()
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.08)'
  ctx.lineWidth = 1
  const gap = 48
  for (let x = -gap; x < width + gap; x += gap) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x + width * 0.12, height)
    ctx.stroke()
  }
  for (let y = gap; y < height; y += gap) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(width, y)
    ctx.stroke()
  }
  ctx.restore()
}

function colorForNode(node: PositionedArcbrainNode): string {
  if (node.heat >= 0.78) return '#fb923c'
  if (node.risk_level === 'high' || node.risk_level === 'critical') return '#f87171'
  const layer = node.layer || layerFromType(String(node.node_type))
  return LAYER_COLOR[layer] ?? LAYER_COLOR.other
}

function layerFromType(nodeType: string) {
  if (nodeType.includes('process') || nodeType.includes('handoff')) return 'operations'
  if (nodeType.includes('team') || nodeType.includes('actor')) return 'people'
  if (nodeType.includes('metadata') || nodeType.includes('automation') || nodeType.includes('apex')) return 'platform'
  if (nodeType.includes('evidence') || nodeType.includes('document')) return 'evidence'
  if (nodeType.includes('recommendation') || nodeType.includes('replacement') || nodeType.includes('agent')) return 'replacement'
  if (nodeType.includes('risk') || nodeType.includes('control') || nodeType.includes('permission')) return 'controls'
  return 'other'
}

function drawNodeLabel(ctx: CanvasRenderingContext2D, node: ProjectedNode, radius: number, active: boolean) {
  const label = compactLabel(node.label, active ? 36 : 24)
  ctx.font = `${active ? 600 : 500} 11px Inter, system-ui, sans-serif`
  const width = Math.min(ctx.measureText(label).width + 14, 220)
  const x = node.sx + radius + 8
  const y = node.sy - 11
  ctx.fillStyle = active ? 'rgba(15, 23, 42, 0.88)' : 'rgba(15, 23, 42, 0.68)'
  roundRect(ctx, x, y, width, 22, 6)
  ctx.fill()
  ctx.fillStyle = active ? '#fff7ed' : '#e2e8f0'
  ctx.fillText(label, x + 7, y + 15, width - 14)
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.arcTo(x + width, y, x + width, y + height, radius)
  ctx.arcTo(x + width, y + height, x, y + height, radius)
  ctx.arcTo(x, y + height, x, y, radius)
  ctx.arcTo(x, y, x + width, y, radius)
  ctx.closePath()
}
