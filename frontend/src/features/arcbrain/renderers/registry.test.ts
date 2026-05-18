import { describe, expect, it } from 'vitest'
import { getArcbrainRendererKind, isArcbrainRendererKind } from './registry'

describe('Arcbrain renderer registry', () => {
  it('defaults to the true 3D renderer while preserving canvas fallback', () => {
    expect(getArcbrainRendererKind(undefined)).toBe('three')
    expect(getArcbrainRendererKind('')).toBe('three')
    expect(getArcbrainRendererKind('canvas')).toBe('canvas')
    expect(getArcbrainRendererKind('three')).toBe('three')
  })

  it('rejects unknown renderer names instead of silently creating a third path', () => {
    expect(isArcbrainRendererKind('canvas')).toBe(true)
    expect(isArcbrainRendererKind('three')).toBe(true)
    expect(isArcbrainRendererKind('webgl')).toBe(false)
  })
})
