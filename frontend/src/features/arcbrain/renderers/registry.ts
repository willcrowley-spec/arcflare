export type ArcbrainRendererKind = 'canvas' | 'three'

const RENDERER_KINDS = new Set<ArcbrainRendererKind>(['canvas', 'three'])

export function isArcbrainRendererKind(value: unknown): value is ArcbrainRendererKind {
  return typeof value === 'string' && RENDERER_KINDS.has(value as ArcbrainRendererKind)
}

export function getArcbrainRendererKind(value: unknown): ArcbrainRendererKind {
  return isArcbrainRendererKind(value) ? value : 'three'
}
