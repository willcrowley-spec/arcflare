import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, OrbitControls } from '@react-three/drei'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import * as THREE from 'three'
import { Crosshair, LocateFixed, MousePointer2, Pause, Play, RotateCcw, ScanSearch, ZoomIn } from 'lucide-react'
import type { ArcbrainBlastRadius, ArcbrainLens, ArcbrainReplacementHeat, ArcbrainSearchResult } from '@/types'
import {
  buildArcbrainScene,
  compactLabel,
  type ArcbrainGraphModel,
  type ArcbrainScene,
  type PositionedArcbrainNode,
} from '../graph/model'

interface ThreeArcbrainConstellationProps {
  graph: ArcbrainGraphModel
  lens: ArcbrainLens
  selectedNodeId: string | null
  onSelectNode: (nodeId: string) => void
  searchResult?: ArcbrainSearchResult | null
  blastRadius?: ArcbrainBlastRadius | null
  replacementHeat?: ArcbrainReplacementHeat | null
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
const GRAPH_VIEWPORT_HEIGHT = 'clamp(560px, 72vh, 840px)'
const DEFAULT_CAMERA_POSITION: [number, number, number] = [860, 520, 1850]
const CAMERA_FAR_PLANE = 60000
const MIN_CAMERA_DISTANCE = 90
const MAX_CAMERA_DISTANCE = 24000

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

export function ThreeArcbrainConstellation({
  graph,
  lens,
  selectedNodeId,
  onSelectNode,
  searchResult,
  blastRadius,
  replacementHeat,
}: ThreeArcbrainConstellationProps) {
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [orbiting, setOrbiting] = useState(true)
  const [focusIds, setFocusIds] = useState<string[]>([])
  const [focusSignal, setFocusSignal] = useState(0)
  const [resetSignal, setResetSignal] = useState(0)
  const reducedMotion = useReducedMotion()

  const scene = useMemo(
    () => buildArcbrainScene(graph, lens, selectedNodeId, searchResult, blastRadius, replacementHeat),
    [graph, lens, selectedNodeId, searchResult, blastRadius, replacementHeat],
  )

  const hovered = hoveredNodeId ? graph.nodes.find((node) => node.id === hoveredNodeId) : null
  const selected = selectedNodeId ? graph.nodes.find((node) => node.id === selectedNodeId) : null
  const consultingCount = scene.conversationNodeIds.size
  const pathCount = searchResult?.paths?.length ?? 0
  const pathLabel = pathCount === 1 ? 'path' : 'paths'

  const focusNode = useCallback(
    (nodeId: string | null | undefined) => {
      if (!nodeId) return
      setOrbiting(false)
      setFocusIds([nodeId])
      setFocusSignal((value) => value + 1)
      onSelectNode(nodeId)
    },
    [onSelectNode],
  )

  const focusHighlighted = () => {
    const ids = [...scene.conversationNodeIds]
    if (ids.length === 0 && selectedNodeId) ids.push(selectedNodeId)
    if (ids.length === 0) ids.push(...[...scene.highlightedNodeIds].slice(0, 8))
    setOrbiting(false)
    setFocusIds(ids)
    setFocusSignal((value) => value + 1)
  }

  const resetCamera = () => {
    setOrbiting(!reducedMotion)
    setFocusIds([])
    setResetSignal((value) => value + 1)
  }

  return (
    <section className="flex min-h-[620px] min-w-0 flex-col overflow-hidden rounded-xl border border-navy-900 bg-navy-900 shadow-sm ring-1 ring-slate-900/10">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white">Arcbrain Constellation</p>
          <p className="text-xs text-slate-400">
            {LENS_LABEL[lens]} / {graph.nodes.length} nodes / {graph.edges.length} edges
            {scene.nodes.length < graph.nodes.length ? ` / ${scene.nodes.length} rendered` : ''}
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
              Drag orbit / wheel zoom / right-drag pan
            </span>
          )}
        </div>
      </div>

      <div
        className="relative min-h-[560px] flex-1 bg-[radial-gradient(circle_at_50%_42%,rgba(251,146,60,0.08),transparent_34%),linear-gradient(135deg,#101936,#111827_58%,#182033)]"
        style={{ height: GRAPH_VIEWPORT_HEIGHT }}
      >
        <Canvas
          camera={{ position: DEFAULT_CAMERA_POSITION, fov: 50, near: 1, far: CAMERA_FAR_PLANE }}
          dpr={[1, 2]}
          gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
          className="w-full outline-none"
          style={{ height: GRAPH_VIEWPORT_HEIGHT, width: '100%' }}
          aria-label="Arcbrain true 3D constellation graph. Drag to orbit, use the mouse wheel to zoom, and right-drag to pan."
        >
          <ambientLight intensity={0.72} />
          <pointLight position={[360, 420, 540]} intensity={0.55} color="#fff7ed" />
          <ArcbrainSceneObjects
            scene={scene}
            selectedNodeId={selectedNodeId}
            hoveredNodeId={hoveredNodeId}
            onHover={setHoveredNodeId}
            onSelectNode={onSelectNode}
            reducedMotion={reducedMotion}
          />
          <CameraRig
            nodes={scene.nodes}
            focusIds={focusIds}
            focusSignal={focusSignal}
            resetSignal={resetSignal}
            orbiting={orbiting && !reducedMotion}
          />
        </Canvas>

        <div className="absolute right-4 top-4 flex flex-col gap-2">
          <ControlButton label="Focus selected node" onClick={() => focusNode(selectedNodeId)}>
            <LocateFixed className="h-4 w-4" />
          </ControlButton>
          <ControlButton label="Focus answer path" onClick={focusHighlighted}>
            <Crosshair className="h-4 w-4" />
          </ControlButton>
          <ControlButton label={orbiting && !reducedMotion ? 'Pause orbit' : 'Resume orbit'} onClick={() => setOrbiting((value) => !value)}>
            {orbiting && !reducedMotion ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </ControlButton>
          <ControlButton label="Reset view" onClick={resetCamera}>
            <RotateCcw className="h-4 w-4" />
          </ControlButton>
        </div>

        <div className="absolute bottom-4 left-4 rounded-lg border border-white/10 bg-navy-800/90 px-3 py-2 text-xs font-medium text-slate-300 shadow-xl">
          True 3D / WebGL
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

function ArcbrainSceneObjects({
  scene,
  selectedNodeId,
  hoveredNodeId,
  onHover,
  onSelectNode,
  reducedMotion,
}: {
  scene: ArcbrainScene
  selectedNodeId: string | null
  hoveredNodeId: string | null
  onHover: (nodeId: string | null) => void
  onSelectNode: (nodeId: string) => void
  reducedMotion: boolean
}) {
  return (
    <>
      <ArcbrainEdges scene={scene} />
      <ArcbrainNodes
        scene={scene}
        selectedNodeId={selectedNodeId}
        hoveredNodeId={hoveredNodeId}
        onHover={onHover}
        onSelectNode={onSelectNode}
        reducedMotion={reducedMotion}
      />
      <ArcbrainFocusNodes
        scene={scene}
        selectedNodeId={selectedNodeId}
        hoveredNodeId={hoveredNodeId}
        reducedMotion={reducedMotion}
      />
      <ArcbrainLabels scene={scene} selectedNodeId={selectedNodeId} hoveredNodeId={hoveredNodeId} />
    </>
  )
}

function ArcbrainNodes({
  scene,
  selectedNodeId,
  hoveredNodeId,
  onHover,
  onSelectNode,
  reducedMotion,
}: {
  scene: ArcbrainScene
  selectedNodeId: string | null
  hoveredNodeId: string | null
  onHover: (nodeId: string | null) => void
  onSelectNode: (nodeId: string) => void
  reducedMotion: boolean
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null)
  const tempObject = useMemo(() => new THREE.Object3D(), [])

  const nodeIds = useMemo(() => scene.nodes.map((node) => node.id), [scene.nodes])

  useLayoutEffect(() => {
    const mesh = meshRef.current
    if (!mesh) return
    scene.nodes.forEach((node, index) => {
      const active = selectedNodeId === node.id || hoveredNodeId === node.id
      const conversation = scene.conversationNodeIds.has(node.id)
      const highlighted = scene.highlightedNodeIds.has(node.id)
      const muted = scene.mutedNodeIds.has(node.id)
      const scale = nodeScale(node, active, conversation, highlighted, muted, 0, reducedMotion)
      tempObject.position.set(node.x, node.y, node.z)
      tempObject.scale.setScalar(scale)
      tempObject.updateMatrix()
      mesh.setMatrixAt(index, tempObject.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
    mesh.computeBoundingSphere()
  }, [hoveredNodeId, nodeIds, reducedMotion, scene, selectedNodeId, tempObject])

  useFrame(({ clock }) => {
    const mesh = meshRef.current
    if (!mesh || reducedMotion) return
    const elapsed = clock.getElapsedTime()
    scene.nodes.forEach((node, index) => {
      if (!scene.conversationNodeIds.has(node.id) && selectedNodeId !== node.id && hoveredNodeId !== node.id) return
      const active = selectedNodeId === node.id || hoveredNodeId === node.id
      const conversation = scene.conversationNodeIds.has(node.id)
      const highlighted = scene.highlightedNodeIds.has(node.id)
      const muted = scene.mutedNodeIds.has(node.id)
      const order = scene.pulseOrderByNodeId.get(node.id) ?? 0
      const scale = nodeScale(node, active, conversation, highlighted, muted, elapsed - order * 0.22, reducedMotion)
      tempObject.position.set(node.x, node.y, node.z)
      tempObject.scale.setScalar(scale)
      tempObject.updateMatrix()
      mesh.setMatrixAt(index, tempObject.matrix)
    })
    mesh.instanceMatrix.needsUpdate = true
  })

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, scene.nodes.length]}
      frustumCulled={false}
      onPointerOver={(event) => {
        event.stopPropagation()
        if (event.instanceId != null) onHover(scene.nodes[event.instanceId]?.id ?? null)
      }}
      onPointerOut={() => onHover(null)}
      onClick={(event) => {
        event.stopPropagation()
        const nodeId = event.instanceId != null ? scene.nodes[event.instanceId]?.id : null
        if (nodeId) onSelectNode(nodeId)
      }}
    >
      <sphereGeometry args={[1, 24, 16]} />
      <meshBasicMaterial color="#cbd5e1" transparent opacity={0.82} toneMapped={false} />
    </instancedMesh>
  )
}

function ArcbrainFocusNodes({
  scene,
  selectedNodeId,
  hoveredNodeId,
  reducedMotion,
}: {
  scene: ArcbrainScene
  selectedNodeId: string | null
  hoveredNodeId: string | null
  reducedMotion: boolean
}) {
  const focusedNodes = scene.nodes.filter((node) => {
    return (
      selectedNodeId === node.id ||
      hoveredNodeId === node.id ||
      scene.conversationNodeIds.has(node.id) ||
      scene.highlightedNodeIds.has(node.id)
    )
  }).slice(0, 48)

  return (
    <>
      {focusedNodes.map((node) => {
        const active = selectedNodeId === node.id || hoveredNodeId === node.id
        const conversation = scene.conversationNodeIds.has(node.id)
        const highlighted = scene.highlightedNodeIds.has(node.id)
        const muted = scene.mutedNodeIds.has(node.id)
        const scale = nodeScale(node, active, conversation, highlighted, muted, 0.2, reducedMotion)
        const color = active || conversation ? '#fb923c' : focusColorForNode(node)
        return (
          <group key={node.id} position={[node.x, node.y, node.z]}>
            <mesh scale={scale * 1.08}>
              <sphereGeometry args={[1, 28, 18]} />
              <meshBasicMaterial color={color} toneMapped={false} />
            </mesh>
            <mesh scale={scale * 2.25}>
              <sphereGeometry args={[1, 28, 18]} />
              <meshBasicMaterial color="#fb923c" transparent opacity={conversation || active ? 0.18 : 0.08} depthWrite={false} toneMapped={false} />
            </mesh>
          </group>
        )
      })}
    </>
  )
}

function ArcbrainEdges({ scene }: { scene: ArcbrainScene }) {
  const geometry = useMemo(() => {
    const positions = new Float32Array(scene.edges.length * 6)
    const colors = new Float32Array(scene.edges.length * 6)
    const color = new THREE.Color()
    scene.edges.forEach((edge, index) => {
      const highlighted = scene.highlightedEdgeIds.has(edge.id)
      const muted = scene.mutedNodeIds.has(edge.source_node_id) || scene.mutedNodeIds.has(edge.target_node_id)
      const edgeColor = highlighted ? '#fb923c' : muted ? '#475569' : '#64748b'
      const intensity = highlighted ? 1 : muted ? 0.18 : 0.34
      color.set(edgeColor).multiplyScalar(intensity)
      const offset = index * 6
      positions[offset] = edge.source.x
      positions[offset + 1] = edge.source.y
      positions[offset + 2] = edge.source.z
      positions[offset + 3] = edge.target.x
      positions[offset + 4] = edge.target.y
      positions[offset + 5] = edge.target.z
      colors[offset] = color.r
      colors[offset + 1] = color.g
      colors[offset + 2] = color.b
      colors[offset + 3] = color.r
      colors[offset + 4] = color.g
      colors[offset + 5] = color.b
    })
    const graphGeometry = new THREE.BufferGeometry()
    graphGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    graphGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    return graphGeometry
  }, [scene.edges, scene.highlightedEdgeIds, scene.mutedNodeIds])

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial vertexColors transparent opacity={0.92} depthWrite={false} toneMapped={false} />
    </lineSegments>
  )
}

function ArcbrainLabels({
  scene,
  selectedNodeId,
  hoveredNodeId,
}: {
  scene: ArcbrainScene
  selectedNodeId: string | null
  hoveredNodeId: string | null
}) {
  const labeledNodes = scene.nodes.filter((node) => {
    return (
      selectedNodeId === node.id ||
      hoveredNodeId === node.id ||
      scene.conversationNodeIds.has(node.id) ||
      (scene.highlightedNodeIds.has(node.id) && node.radius > 8.8)
    )
  }).slice(0, 18)

  return (
    <>
      {labeledNodes.map((node) => (
        <Html key={node.id} position={[node.x, node.y + node.radius + 8, node.z]} center distanceFactor={620}>
          <div className="pointer-events-none rounded-md bg-navy-950/88 px-2 py-1 text-[11px] font-semibold text-orange-50 shadow-xl ring-1 ring-white/10">
            {compactLabel(node.label, selectedNodeId === node.id ? 34 : 24)}
          </div>
        </Html>
      ))}
    </>
  )
}

function CameraRig({
  nodes,
  focusIds,
  focusSignal,
  resetSignal,
  orbiting,
}: {
  nodes: PositionedArcbrainNode[]
  focusIds: string[]
  focusSignal: number
  resetSignal: number
  orbiting: boolean
}) {
  const { camera } = useThree()
  const controlsRef = useRef<OrbitControlsImpl | null>(null)
  const targetRef = useRef<{ cameraPosition: THREE.Vector3; lookAt: THREE.Vector3 } | null>(null)

  useEffect(() => {
    camera.position.set(...DEFAULT_CAMERA_POSITION)
    controlsRef.current?.target.set(0, 0, 0)
    controlsRef.current?.update()
    targetRef.current = null
  }, [camera, resetSignal])

  useEffect(() => {
    const target = cameraTargetForNodes(nodes, new Set(focusIds))
    if (target) targetRef.current = target
  }, [focusIds, focusSignal, nodes])

  useFrame(() => {
    const target = targetRef.current
    if (!target) return
    camera.position.lerp(target.cameraPosition, 0.085)
    controlsRef.current?.target.lerp(target.lookAt, 0.12)
    controlsRef.current?.update()
    if (camera.position.distanceTo(target.cameraPosition) < 4) targetRef.current = null
  })

  return (
    <OrbitControls
      ref={controlsRef}
      enableDamping
      dampingFactor={0.08}
      rotateSpeed={0.58}
      zoomSpeed={1.1}
      panSpeed={0.72}
      minDistance={MIN_CAMERA_DISTANCE}
      maxDistance={MAX_CAMERA_DISTANCE}
      autoRotate={orbiting}
      autoRotateSpeed={0.35}
      makeDefault
    />
  )
}

function cameraTargetForNodes(nodes: PositionedArcbrainNode[], ids: Set<string>) {
  const selected = ids.size > 0 ? nodes.filter((node) => ids.has(node.id)) : []
  const targets = selected.length > 0 ? selected : nodes.slice(0, 20)
  if (targets.length === 0) return null
  const center = targets.reduce(
    (acc, node) => {
      acc.x += node.x
      acc.y += node.y
      acc.z += node.z
      return acc
    },
    new THREE.Vector3(),
  ).divideScalar(targets.length)
  const spread = targets.reduce((max, node) => Math.max(max, center.distanceTo(new THREE.Vector3(node.x, node.y, node.z))), 0)
  const distance = Math.max(targets.length <= 2 ? 320 : 520, spread * 2.7)
  return {
    lookAt: center,
    cameraPosition: new THREE.Vector3(center.x + distance * 0.26, center.y + distance * 0.18, center.z + distance),
  }
}

function nodeScale(
  node: PositionedArcbrainNode,
  active: boolean,
  conversation: boolean,
  highlighted: boolean,
  muted: boolean,
  phaseTime: number,
  reducedMotion: boolean,
) {
  const base = Math.max(3.2, node.radius * 0.72)
  const pulse = reducedMotion ? 0 : Math.sin(phaseTime * Math.PI * 2) * 0.16
  if (active) return base * 1.55
  if (conversation) return base * (1.32 + Math.max(0, pulse))
  if (highlighted) return base * 1.18
  if (muted) return base * 0.62
  return base
}

function focusColorForNode(node: PositionedArcbrainNode) {
  if (node.heat >= 0.78) return '#fb923c'
  if (node.risk_level === 'high' || node.risk_level === 'critical') return '#f87171'
  return LAYER_COLOR[node.layer || 'other'] ?? LAYER_COLOR.other
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
