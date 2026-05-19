import { useCallback, useEffect, useRef } from 'react'
import { OrbitControls } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import * as THREE from 'three'
import type { PositionedArcbrainNode } from '../graph/model'

export const CAMERA_FAR_PLANE = 500000

const MIN_CAMERA_DISTANCE = 90
const MAX_CAMERA_DISTANCE = 220000

export type CameraViewMode = 'focus' | 'fit' | 'wide'

interface CameraRigProps {
  nodes: PositionedArcbrainNode[]
  focusIds: string[]
  focusSignal: number
  viewMode: CameraViewMode
  viewSignal: number
  orbiting: boolean
  onUserControl: () => void
}

export function CameraRig({
  nodes,
  focusIds,
  focusSignal,
  viewMode,
  viewSignal,
  orbiting,
  onUserControl,
}: CameraRigProps) {
  const { camera } = useThree()
  const controlsRef = useRef<OrbitControlsImpl | null>(null)
  const targetRef = useRef<{ cameraPosition: THREE.Vector3; lookAt: THREE.Vector3 } | null>(null)
  const nodesRef = useRef(nodes)
  const initializedRef = useRef(false)

  useEffect(() => {
    nodesRef.current = nodes
  }, [nodes])

  useEffect(() => {
    if (initializedRef.current || nodes.length === 0) return
    const target = cameraTargetForNodes(nodes, new Set(), 'fit')
    if (target) targetRef.current = target
    initializedRef.current = true
  }, [nodes])

  useEffect(() => {
    const target = cameraTargetForNodes(nodesRef.current, new Set(), viewMode)
    if (target) targetRef.current = target
  }, [viewMode, viewSignal])

  useEffect(() => {
    if (focusIds.length === 0) return
    const target = cameraTargetForNodes(nodesRef.current, new Set(focusIds), 'focus')
    if (target) targetRef.current = target
  }, [focusIds, focusSignal])

  const handleControlsStart = useCallback(() => {
    targetRef.current = null
    onUserControl()
  }, [onUserControl])

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
      zoomToCursor
      autoRotate={orbiting}
      autoRotateSpeed={0.35}
      onStart={handleControlsStart}
      makeDefault
    />
  )
}

function cameraTargetForNodes(nodes: PositionedArcbrainNode[], ids: Set<string>, mode: CameraViewMode) {
  const selected = ids.size > 0 ? nodes.filter((node) => ids.has(node.id)) : []
  const targets = selected.length > 0 ? selected : nodes
  if (targets.length === 0) return null

  const bounds = targets.reduce(
    (acc, node) => ({
      minX: Math.min(acc.minX, node.x - node.radius),
      maxX: Math.max(acc.maxX, node.x + node.radius),
      minY: Math.min(acc.minY, node.y - node.radius),
      maxY: Math.max(acc.maxY, node.y + node.radius),
      minZ: Math.min(acc.minZ, node.z - node.radius),
      maxZ: Math.max(acc.maxZ, node.z + node.radius),
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
  const center = new THREE.Vector3(
    (bounds.minX + bounds.maxX) / 2,
    (bounds.minY + bounds.maxY) / 2,
    (bounds.minZ + bounds.maxZ) / 2,
  )
  const diagonal = Math.hypot(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY, bounds.maxZ - bounds.minZ)
  const spread = Math.max(
    diagonal / 2,
    targets.reduce((max, node) => Math.max(max, center.distanceTo(new THREE.Vector3(node.x, node.y, node.z)) + node.radius), 0),
  )
  const selectedFocus = selected.length > 0
  const multiplier = mode === 'wide' ? 6.2 : selectedFocus ? 2.25 : 2.32
  const minimumDistance = selectedFocus ? (targets.length <= 2 ? 360 : 720) : mode === 'wide' ? 7200 : 980
  const distance = clamp(Math.max(minimumDistance, spread * multiplier), MIN_CAMERA_DISTANCE * 3.5, MAX_CAMERA_DISTANCE * 0.92)
  const direction = new THREE.Vector3(0.42, 0.12, 1).normalize()

  return {
    lookAt: center,
    cameraPosition: new THREE.Vector3(
      center.x + direction.x * distance,
      center.y + direction.y * distance,
      center.z + direction.z * distance,
    ),
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}
