import { useMemo, useRef } from 'react'
import { Html } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { ArcbrainScene } from '../graph/model'
import { compactLabel } from '../graph/model'
import type { ArcbrainCommunityBeacon, ArcbrainLayerSummary, ArcbrainSceneBounds } from '../graph/visuals'

interface ArcbrainDepthStageProps {
  bounds: ArcbrainSceneBounds
}

interface ArcbrainCommunityBeaconsProps {
  beacons: ArcbrainCommunityBeacon[]
  reducedMotion: boolean
}

interface ArcbrainAnswerPathProps {
  scene: ArcbrainScene
  reducedMotion: boolean
}

interface ArcbrainLayerLegendProps {
  summaries: ArcbrainLayerSummary[]
  renderedCount: number
  totalCount: number
  communityCount: number
}

export function ArcbrainDepthStage({ bounds }: ArcbrainDepthStageProps) {
  const gridSize = Math.max(1600, Math.min(18000, bounds.radius * 2.45))
  const floorY = bounds.center.y - bounds.size.y * 0.58 - 140

  return (
    <group>
      <mesh position={[bounds.center.x, floorY - 8, bounds.center.z]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[gridSize * 0.54, 96]} />
        <meshBasicMaterial color="#0b1229" transparent opacity={0.48} depthWrite={false} side={THREE.DoubleSide} toneMapped={false} />
      </mesh>
      <group position={[bounds.center.x, floorY, bounds.center.z]}>
        <gridHelper args={[gridSize, 16, '#334155', '#17213d']} />
      </group>
      <mesh position={[bounds.center.x, bounds.center.y, bounds.center.z]}>
        <sphereGeometry args={[Math.max(600, bounds.radius * 1.18), 48, 24]} />
        <meshBasicMaterial color="#1e293b" transparent opacity={0.035} depthWrite={false} side={THREE.BackSide} toneMapped={false} />
      </mesh>
    </group>
  )
}

export function ArcbrainCommunityBeacons({ beacons, reducedMotion }: ArcbrainCommunityBeaconsProps) {
  return (
    <>
      {beacons.map((beacon, index) => (
        <CommunityBeacon key={beacon.id} beacon={beacon} index={index} reducedMotion={reducedMotion} />
      ))}
    </>
  )
}

function CommunityBeacon({
  beacon,
  index,
  reducedMotion,
}: {
  beacon: ArcbrainCommunityBeacon
  index: number
  reducedMotion: boolean
}) {
  const groupRef = useRef<THREE.Group>(null)
  const ringRadius = Math.max(90, Math.min(720, beacon.radius * 0.78))
  const markerScale = Math.max(7, Math.min(22, 6 + Math.sqrt(beacon.count) * 1.35))

  useFrame(({ clock }) => {
    if (reducedMotion || !groupRef.current) return
    const drift = Math.sin(clock.getElapsedTime() * 0.18 + index) * 0.035
    groupRef.current.rotation.y = drift
    groupRef.current.rotation.x = -drift * 0.6
  })

  return (
    <group ref={groupRef} position={[beacon.center.x, beacon.center.y, beacon.center.z]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[ringRadius, 1.4, 8, 112]} />
        <meshBasicMaterial color={beacon.color} transparent opacity={0.13} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh rotation={[0.72, 0.24, 0.12]}>
        <torusGeometry args={[ringRadius * 0.72, 1, 8, 96]} />
        <meshBasicMaterial color={beacon.color} transparent opacity={0.1} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh scale={markerScale}>
        <sphereGeometry args={[1, 18, 12]} />
        <meshBasicMaterial color={beacon.color} transparent opacity={0.42} depthWrite={false} toneMapped={false} />
      </mesh>
      {index < 6 ? (
        <Html position={[0, markerScale + 22, 0]} center distanceFactor={780}>
          <div className="pointer-events-none rounded-md border border-white/10 bg-navy-950/88 px-2.5 py-1.5 text-[11px] font-semibold leading-tight text-slate-100 shadow-xl">
            <span className="block max-w-40 truncate">{compactLabel(beacon.label, 26)}</span>
            <span className="mt-0.5 block text-[10px] font-medium text-slate-400">{beacon.count.toLocaleString()} nodes</span>
          </div>
        </Html>
      ) : null}
    </group>
  )
}

export function ArcbrainAnswerPath({ scene, reducedMotion }: ArcbrainAnswerPathProps) {
  const highlightedEdges = useMemo(
    () => scene.edges.filter((edge) => scene.highlightedEdgeIds.has(edge.id)).slice(0, 72),
    [scene.edges, scene.highlightedEdgeIds],
  )

  if (highlightedEdges.length === 0) return null

  return (
    <>
      {highlightedEdges.map((edge) => (
        <AnswerEdgeBeam key={edge.id} edge={edge} />
      ))}
      {!reducedMotion
        ? highlightedEdges.slice(0, 24).map((edge, index) => (
            <AnswerEdgeMarker key={`${edge.id}:marker`} edge={edge} index={index} />
          ))
        : null}
    </>
  )
}

function AnswerEdgeBeam({ edge }: { edge: ArcbrainScene['edges'][number] }) {
  const geometry = useMemo(() => {
    const graphGeometry = new THREE.BufferGeometry()
    graphGeometry.setFromPoints([
      new THREE.Vector3(edge.source.x, edge.source.y, edge.source.z),
      new THREE.Vector3(edge.target.x, edge.target.y, edge.target.z),
    ])
    return graphGeometry
  }, [edge.source.x, edge.source.y, edge.source.z, edge.target.x, edge.target.y, edge.target.z])

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#fb923c" transparent opacity={0.92} depthWrite={false} toneMapped={false} />
    </lineSegments>
  )
}

function AnswerEdgeMarker({ edge, index }: { edge: ArcbrainScene['edges'][number]; index: number }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const source = useMemo(() => new THREE.Vector3(edge.source.x, edge.source.y, edge.source.z), [edge.source.x, edge.source.y, edge.source.z])
  const target = useMemo(() => new THREE.Vector3(edge.target.x, edge.target.y, edge.target.z), [edge.target.x, edge.target.y, edge.target.z])
  const scratch = useMemo(() => new THREE.Vector3(), [])

  useFrame(({ clock }) => {
    if (!meshRef.current) return
    const t = (clock.getElapsedTime() * 0.22 + index * 0.09) % 1
    scratch.copy(source).lerp(target, t)
    meshRef.current.position.copy(scratch)
  })

  return (
    <mesh ref={meshRef} scale={5.5}>
      <sphereGeometry args={[1, 14, 10]} />
      <meshBasicMaterial color="#ffb168" transparent opacity={0.86} depthWrite={false} toneMapped={false} />
    </mesh>
  )
}

export function ArcbrainLayerLegend({ summaries, renderedCount, totalCount, communityCount }: ArcbrainLayerLegendProps) {
  return (
    <div className="pointer-events-none absolute bottom-4 left-4 max-w-[min(520px,calc(100%-2rem))] rounded-lg border border-white/10 bg-navy-950/88 p-3 text-slate-200 shadow-xl">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-semibold uppercase text-slate-400">
        <span>Semantic Layers</span>
        <span>
          {renderedCount.toLocaleString()} rendered
          {totalCount > renderedCount ? ` / ${totalCount.toLocaleString()} total` : ''}
        </span>
        <span>{communityCount.toLocaleString()} clusters</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {summaries.map((summary) => (
          <span key={summary.layer} className="inline-flex items-center gap-1.5 rounded-md bg-white/6 px-2 py-1 text-[11px] font-medium text-slate-200 ring-1 ring-white/8">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: summary.color }} />
            {summary.label}
            <span className="text-slate-400">{summary.count.toLocaleString()}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
