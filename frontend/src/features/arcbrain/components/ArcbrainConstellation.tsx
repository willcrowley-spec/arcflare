import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent, type ReactNode } from 'react'
import clsx from 'clsx'
import { Crosshair, LocateFixed, Minus, MousePointer2, Pause, Play, RotateCcw, ScanSearch, ZoomIn } from 'lucide-react'
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

interface Camera {
  rotation: number
  zoom: number
  panX: number
  panY: number
  orbiting: boolean
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

const INITIAL_CAMERA: Camera = { rotation: 0.28, zoom: 1, panX: 0, panY: 0, orbiting: true }

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
  const cameraRef = useRef<Camera>(INITIAL_CAMERA)
  const canvasMetricsRef = useRef({ width: 0, height: 0, dpr: 0 })
  const dragRef = useRef<{ pointerId: number; x: number; y: number; mode: 'rotate' | 'pan' } | null>(null)
  const pointersRef = useRef(new Map<number, { x: number; y: number }>())
  const pinchRef = useRef<{ distance: number; zoom: number; panX: number; panY: number } | null>(null)
  const draggedRef = useRef(false)
  const [cameraUi, setCameraUi] = useState<Camera>(INITIAL_CAMERA)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [size, setSize] = useState({ width: 320, height: 560 })
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
      setSize({ width: Math.max(320, rect.width), height: Math.max(500, rect.height) })
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const draw = useCallback(
    (camera = cameraRef.current, now = performance.now()) => {
      const canvas = canvasRef.current
      if (!canvas) return
      const dpr = window.devicePixelRatio || 1
      const targetWidth = Math.floor(size.width * dpr)
      const targetHeight = Math.floor(size.height * dpr)
      const metrics = canvasMetricsRef.current
      if (metrics.width !== targetWidth || metrics.height !== targetHeight || metrics.dpr !== dpr) {
        canvas.width = targetWidth
        canvas.height = targetHeight
        canvas.style.width = `${size.width}px`
        canvas.style.height = `${size.height}px`
        canvasMetricsRef.current = { width: targetWidth, height: targetHeight, dpr }
      }
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      paintScene(ctx, scene, size.width, size.height, camera, selectedNodeId, hoveredNodeId, now, reducedMotion)
      projectedRef.current = projectNodes(scene.nodes, size.width, size.height, camera)
    },
    [hoveredNodeId, reducedMotion, scene, selectedNodeId, size.height, size.width],
  )

  const setCamera = useCallback(
    (updater: Camera | ((camera: Camera) => Camera)) => {
      const next = typeof updater === 'function' ? updater(cameraRef.current) : updater
      cameraRef.current = clampCamera(next)
      setCameraUi(cameraRef.current)
      draw(cameraRef.current)
    },
    [draw],
  )

  useEffect(() => {
    draw()
  }, [draw])

  useEffect(() => {
    let frame = 0
    let last = performance.now()
    const tick = (now: number) => {
      const delta = now - last
      last = now
      if (!reducedMotion && cameraRef.current.orbiting) {
        cameraRef.current = clampCamera({
          ...cameraRef.current,
          rotation: cameraRef.current.rotation + delta / 28000,
        })
      }
      draw(cameraRef.current, now)
      frame = window.requestAnimationFrame(tick)
    }
    frame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frame)
  }, [draw, reducedMotion])

  const updateHover = (event: PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    const hit = hitTest(projectedRef.current, x, y)
    setHoveredNodeId(hit?.id ?? null)
  }

  const handlePointerDown = (event: PointerEvent<HTMLCanvasElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    draggedRef.current = false
    if (pointersRef.current.size >= 2) {
      const points = [...pointersRef.current.values()]
      pinchRef.current = {
        distance: pointerDistance(points[0], points[1]),
        zoom: cameraRef.current.zoom,
        panX: cameraRef.current.panX,
        panY: cameraRef.current.panY,
      }
      return
    }
    dragRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      mode: event.button === 2 || event.shiftKey ? 'pan' : 'rotate',
    }
    setCamera((camera) => ({ ...camera, orbiting: false }))
  }

  const handlePointerMove = (event: PointerEvent<HTMLCanvasElement>) => {
    if (!pointersRef.current.has(event.pointerId)) {
      updateHover(event)
      return
    }
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY })
    if (pointersRef.current.size >= 2 && pinchRef.current) {
      const points = [...pointersRef.current.values()]
      const distance = pointerDistance(points[0], points[1])
      const ratio = distance / Math.max(1, pinchRef.current.distance)
      draggedRef.current = true
      setCamera((camera) => ({
        ...camera,
        zoom: pinchRef.current ? pinchRef.current.zoom * ratio : camera.zoom,
        panX: pinchRef.current?.panX ?? camera.panX,
        panY: pinchRef.current?.panY ?? camera.panY,
        orbiting: false,
      }))
      return
    }

    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const dx = event.clientX - drag.x
    const dy = event.clientY - drag.y
    if (Math.abs(dx) + Math.abs(dy) > 2) draggedRef.current = true
    dragRef.current = { ...drag, x: event.clientX, y: event.clientY }
    setCamera((camera) =>
      drag.mode === 'pan'
        ? { ...camera, panX: camera.panX + dx, panY: camera.panY + dy, orbiting: false }
        : { ...camera, rotation: camera.rotation + dx * 0.006, panY: camera.panY + dy * 0.18, orbiting: false },
    )
  }

  const handlePointerUp = (event: PointerEvent<HTMLCanvasElement>) => {
    pointersRef.current.delete(event.pointerId)
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null
    if (pointersRef.current.size < 2) pinchRef.current = null
  }

  const handleWheel = useCallback((event: WheelEvent) => {
    event.preventDefault()
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const x = event.clientX - rect.left - size.width / 2
    const y = event.clientY - rect.top - size.height / 2
    const factor = event.deltaY > 0 ? 0.9 : 1.1
    setCamera((camera) => {
      const nextZoom = clamp(camera.zoom * factor, 0.48, 2.6)
      const zoomRatio = nextZoom / camera.zoom
      return {
        ...camera,
        zoom: nextZoom,
        panX: x - (x - camera.panX) * zoomRatio,
        panY: y - (y - camera.panY) * zoomRatio,
        orbiting: false,
      }
    })
  }, [setCamera, size.height, size.width])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    canvas.addEventListener('wheel', handleWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', handleWheel)
  }, [handleWheel])

  const handleClick = () => {
    if (draggedRef.current) return
    if (hoveredNodeId) onSelectNode(hoveredNodeId)
  }

  const focusNode = useCallback(
    (nodeId: string | null | undefined) => {
      if (!nodeId) return
      const node = scene.nodes.find((item) => item.id === nodeId)
      if (!node) return
      const rotation = Math.atan2(node.x, node.z || 0.001)
      const scaleBase = Math.min(size.width, size.height) / 600
      setCamera({
        rotation,
        zoom: Math.max(1.12, cameraRef.current.zoom),
        panX: 0,
        panY: -node.y * scaleBase * 0.86,
        orbiting: false,
      })
      onSelectNode(node.id)
    },
    [onSelectNode, scene.nodes, setCamera, size.height, size.width],
  )

  const focusHighlighted = () => {
    const firstConversation = [...scene.conversationNodeIds][0]
    const firstHighlighted = [...scene.highlightedNodeIds][0]
    focusNode(firstConversation ?? selectedNodeId ?? firstHighlighted)
  }

  const resetCamera = () => {
    setCamera({ ...INITIAL_CAMERA, orbiting: !reducedMotion })
  }

  const selected = selectedNodeId ? graph.nodes.find((n) => n.id === selectedNodeId) : null
  const hovered = hoveredNodeId ? graph.nodes.find((n) => n.id === hoveredNodeId) : null
  const consultingCount = scene.conversationNodeIds.size
  const pathCount = searchResult?.paths?.length ?? 0
  const pathLabel = pathCount === 1 ? 'path' : 'paths'

  return (
    <section className="flex min-h-[620px] min-w-0 flex-col overflow-hidden rounded-xl border border-navy-900 bg-navy-900 shadow-sm ring-1 ring-slate-900/10">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white">Arcbrain Constellation</p>
          <p className="text-xs text-slate-400">
            {LENS_LABEL[lens]} / {graph.nodes.length} nodes / {graph.edges.length} edges
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-slate-300">
          {consultingCount > 0 ? (
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-orange-400/14 px-2.5 py-1.5 text-orange-100 ring-1 ring-orange-300/25">
              <ScanSearch className="h-3.5 w-3.5" />
              Consulting {consultingCount} nodes / {pathCount} {pathLabel}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/8 px-2.5 py-1.5 ring-1 ring-white/10">
              <MousePointer2 className="h-3.5 w-3.5 text-orange-300" />
              Drag rotate / wheel zoom / shift-drag pan
            </span>
          )}
        </div>
      </div>

      <div ref={containerRef} className="relative min-h-[560px] flex-1">
        <canvas
          ref={canvasRef}
          tabIndex={0}
          className={clsx('block h-full w-full touch-none outline-none focus-visible:ring-2 focus-visible:ring-orange-300/70', hoveredNodeId ? 'cursor-pointer' : 'cursor-grab')}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onPointerLeave={(event) => {
            handlePointerUp(event)
            setHoveredNodeId(null)
          }}
          onClick={handleClick}
          onContextMenu={(event) => event.preventDefault()}
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft') setCamera((camera) => ({ ...camera, rotation: camera.rotation - 0.1, orbiting: false }))
            if (event.key === 'ArrowRight') setCamera((camera) => ({ ...camera, rotation: camera.rotation + 0.1, orbiting: false }))
            if (event.key === '+' || event.key === '=') setCamera((camera) => ({ ...camera, zoom: camera.zoom * 1.12, orbiting: false }))
            if (event.key === '-' || event.key === '_') setCamera((camera) => ({ ...camera, zoom: camera.zoom * 0.9, orbiting: false }))
            if (event.key === 'Home') resetCamera()
          }}
          aria-label="Arcbrain constellation graph. Drag to rotate, use the mouse wheel to zoom, and shift-drag to pan."
        />

        <div className="absolute right-4 top-4 flex flex-col gap-2">
          <ControlButton label="Zoom in" onClick={() => setCamera((camera) => ({ ...camera, zoom: camera.zoom * 1.14, orbiting: false }))}>
            <ZoomIn className="h-4 w-4" />
          </ControlButton>
          <ControlButton label="Zoom out" onClick={() => setCamera((camera) => ({ ...camera, zoom: camera.zoom * 0.88, orbiting: false }))}>
            <Minus className="h-4 w-4" />
          </ControlButton>
          <ControlButton label="Focus selected node" onClick={() => focusNode(selectedNodeId)}>
            <LocateFixed className="h-4 w-4" />
          </ControlButton>
          <ControlButton label="Focus answer path" onClick={focusHighlighted}>
            <Crosshair className="h-4 w-4" />
          </ControlButton>
          <ControlButton label={cameraUi.orbiting && !reducedMotion ? 'Pause orbit' : 'Resume orbit'} onClick={() => setCamera((camera) => ({ ...camera, orbiting: !camera.orbiting }))}>
            {cameraUi.orbiting && !reducedMotion ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </ControlButton>
          <ControlButton label="Reset view" onClick={resetCamera}>
            <RotateCcw className="h-4 w-4" />
          </ControlButton>
        </div>

        <div className="absolute bottom-4 left-4 rounded-lg border border-white/10 bg-navy-800/90 px-3 py-2 text-xs font-medium text-slate-300 shadow-xl">
          Zoom {Math.round(cameraUi.zoom * 100)}%
        </div>

        {(hovered || selected) && (
          <div className="pointer-events-none absolute left-4 top-4 max-w-[min(320px,calc(100%-6rem))] rounded-lg border border-white/10 bg-navy-800/95 p-3 text-white shadow-xl">
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

function ControlButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-navy-800/92 text-slate-200 shadow-lg transition-colors hover:bg-navy-700 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-orange-300"
    >
      {children}
    </button>
  )
}

function paintScene(
  ctx: CanvasRenderingContext2D,
  scene: ArcbrainScene,
  width: number,
  height: number,
  camera: Camera,
  selectedNodeId: string | null,
  hoveredNodeId: string | null,
  now: number,
  reducedMotion: boolean,
) {
  const grd = ctx.createLinearGradient(0, 0, width, height)
  grd.addColorStop(0, '#101936')
  grd.addColorStop(0.64, '#111827')
  grd.addColorStop(1, '#182033')
  ctx.fillStyle = grd
  ctx.fillRect(0, 0, width, height)

  drawGrid(ctx, width, height, camera)

  const projected = projectNodes(scene.nodes, width, height, camera)
  const projectedById = new Map(projected.map((n) => [n.id, n]))

  scene.edges.forEach((edge) => {
    const source = projectedById.get(edge.source_node_id)
    const target = projectedById.get(edge.target_node_id)
    if (!source || !target) return
    const highlighted = scene.highlightedEdgeIds.has(edge.id)
    const muted = scene.mutedNodeIds.has(source.id) || scene.mutedNodeIds.has(target.id)
    ctx.beginPath()
    ctx.moveTo(source.sx, source.sy)
    ctx.lineTo(target.sx, target.sy)
    ctx.strokeStyle = highlighted ? 'rgba(251, 146, 60, 0.82)' : muted ? 'rgba(148, 163, 184, 0.055)' : 'rgba(148, 163, 184, 0.17)'
    ctx.lineWidth = highlighted ? 1.9 : 0.8
    ctx.stroke()
  })

  projected
    .sort((a, b) => a.scale - b.scale)
    .forEach((node) => {
      const highlighted = scene.highlightedNodeIds.has(node.id)
      const conversation = scene.conversationNodeIds.has(node.id)
      const muted = scene.mutedNodeIds.has(node.id)
      const active = selectedNodeId === node.id || hoveredNodeId === node.id
      const color = colorForNode(node)
      const radius = Math.max(3.5, node.radius * node.scale * Math.sqrt(camera.zoom))

      if (conversation || active) {
        const order = scene.pulseOrderByNodeId.get(node.id) ?? 0
        const phase = reducedMotion ? 0.35 : ((now / 900 - order * 0.28) % 1 + 1) % 1
        ctx.beginPath()
        ctx.arc(node.sx, node.sy, radius + 8 + phase * 18, 0, Math.PI * 2)
        ctx.strokeStyle = active ? 'rgba(251, 146, 60, 0.5)' : `rgba(251, 146, 60, ${0.32 * (1 - phase)})`
        ctx.lineWidth = active ? 2 : 1.2
        ctx.stroke()
      } else if (highlighted) {
        ctx.beginPath()
        ctx.arc(node.sx, node.sy, radius + 8, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(251, 146, 60, 0.11)'
        ctx.fill()
      }

      ctx.save()
      ctx.globalAlpha = muted && !active ? 0.28 : 1
      ctx.beginPath()
      ctx.arc(node.sx, node.sy, radius, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()
      ctx.lineWidth = active ? 2.2 : conversation ? 1.8 : 1
      ctx.strokeStyle = active ? '#fb923c' : conversation ? 'rgba(251, 146, 60, 0.9)' : highlighted ? 'rgba(251, 146, 60, 0.72)' : 'rgba(255, 255, 255, 0.26)'
      ctx.stroke()
      ctx.restore()

      const showLabel = active || conversation || (highlighted && camera.zoom >= 0.76) || (!muted && node.radius > 9.5 && camera.zoom > 1.05)
      if (showLabel) {
        drawNodeLabel(ctx, node, radius, active, width)
      }
    })
}

function projectNodes(nodes: PositionedArcbrainNode[], width: number, height: number, camera: Camera): ProjectedNode[] {
  const cx = width / 2 + camera.panX
  const cy = height / 2 + camera.panY
  const scaleBase = (Math.min(width, height) / 600) * camera.zoom
  return nodes.map((node) => {
    const cos = Math.cos(camera.rotation)
    const sin = Math.sin(camera.rotation)
    const rx = node.x * cos - node.z * sin
    const rz = node.x * sin + node.z * cos
    const perspective = 560 / (560 + rz)
    return {
      ...node,
      sx: cx + rx * perspective * scaleBase,
      sy: cy + node.y * perspective * scaleBase * 0.86,
      scale: Math.max(0.42, Math.min(1.7, perspective)),
    }
  })
}

function hitTest(nodes: ProjectedNode[], x: number, y: number): ProjectedNode | null {
  let best: ProjectedNode | null = null
  let bestDistance = Number.POSITIVE_INFINITY
  nodes.forEach((node) => {
    const radius = Math.max(10, node.radius * node.scale + 5)
    const distance = Math.hypot(node.sx - x, node.sy - y)
    if (distance <= radius && distance < bestDistance) {
      best = node
      bestDistance = distance
    }
  })
  return best
}

function drawGrid(ctx: CanvasRenderingContext2D, width: number, height: number, camera: Camera) {
  ctx.save()
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.065)'
  ctx.lineWidth = 1
  const gap = 52 * Math.max(0.7, Math.min(1.25, camera.zoom))
  const offsetX = camera.panX % gap
  const offsetY = camera.panY % gap
  for (let x = -gap + offsetX; x < width + gap; x += gap) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x + width * 0.1, height)
    ctx.stroke()
  }
  for (let y = gap + offsetY; y < height; y += gap) {
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

function drawNodeLabel(ctx: CanvasRenderingContext2D, node: ProjectedNode, radius: number, active: boolean, canvasWidth: number) {
  const label = compactLabel(node.label, active ? 36 : 24)
  ctx.font = `${active ? 600 : 500} 11px Inter, system-ui, sans-serif`
  const width = Math.min(ctx.measureText(label).width + 14, 220)
  const preferRight = node.sx + radius + 10 + width < canvasWidth - 12
  const x = preferRight ? node.sx + radius + 8 : node.sx - radius - width - 8
  const y = node.sy - 11
  ctx.fillStyle = active ? 'rgba(15, 23, 42, 0.9)' : 'rgba(15, 23, 42, 0.74)'
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

function pointerDistance(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function clampCamera(camera: Camera): Camera {
  return {
    rotation: camera.rotation,
    zoom: clamp(camera.zoom, 0.48, 2.6),
    panX: clamp(camera.panX, -800, 800),
    panY: clamp(camera.panY, -800, 800),
    orbiting: camera.orbiting,
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}
