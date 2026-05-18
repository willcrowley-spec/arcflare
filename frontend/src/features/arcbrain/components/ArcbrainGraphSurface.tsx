import { useMemo } from 'react'
import type { ArcbrainLens } from '@/types'
import type { ArcbrainBlastRadius, ArcbrainReplacementHeat, ArcbrainSearchResult } from '@/types'
import { ArcbrainConstellation } from './ArcbrainConstellation'
import { ThreeArcbrainConstellation } from './ThreeArcbrainConstellation'
import type { ArcbrainGraphModel } from '../graph/model'
import { getArcbrainRendererKind } from '../renderers/registry'

interface ArcbrainGraphSurfaceProps {
  graph: ArcbrainGraphModel
  lens: ArcbrainLens
  selectedNodeId: string | null
  onSelectNode: (nodeId: string) => void
  searchResult?: ArcbrainSearchResult | null
  blastRadius?: ArcbrainBlastRadius | null
  replacementHeat?: ArcbrainReplacementHeat | null
}

export function ArcbrainGraphSurface(props: ArcbrainGraphSurfaceProps) {
  const renderer = getArcbrainRendererKind(import.meta.env.VITE_ARCBRAIN_RENDERER)
  const webglAvailable = useMemo(hasWebgl, [])

  if (renderer === 'canvas' || !webglAvailable) {
    return <ArcbrainConstellation {...props} />
  }

  return <ThreeArcbrainConstellation {...props} />
}

function hasWebgl() {
  if (typeof window === 'undefined') return false
  const canvas = document.createElement('canvas')
  return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
}
