import { describe, expect, it } from 'vitest'
import { checkSupport, effectiveScale, surfaceXBounds, type StageViewport } from '@/stage/geometry'

describe('fractional surface support', () => {
  it.each([375, 390, 393, 414, 428, 430, 440])('retains clamped edges at viewport width %s', width => {
    const view: StageViewport = {
      width,
      height: 935,
      keyboardInset: 0,
      safeArea: { top: 59, right: 0, bottom: 113, left: 0 },
    }
    for (const scale of [0.6, 1, 1.3, 1.5, 1.6]) {
      const height = 120 * effectiveScale(scale, true)
      const charWidth = height * (198 / 240)
      for (const card of [
        { left: 16, right: width - 16, top: 563 },
        { left: 100.125, right: width - 100.125, top: 563 },
      ]) {
        for (const x of surfaceXBounds(card, view, charWidth)) {
          expect(checkSupport(card, card, x + charWidth / 2, view, height, null, charWidth).kind).toBe('follow')
        }
      }
    }
  })

  it('still rejects real subpixel exits, missing support and offscreen surfaces', () => {
    const view: StageViewport = {
      width: 430,
      height: 935,
      keyboardInset: 0,
      safeArea: { top: 59, right: 0, bottom: 113, left: 0 },
    }
    const height = 120 * effectiveScale(1.5, true)
    const width = height * (198 / 240)
    for (const card of [
      { left: 16, right: 414, top: 563 },
      { left: 100, right: 330, top: 563 },
    ]) {
      const [left, right] = surfaceXBounds(card, view, width)
      for (const x of [left - 0.01, right + 0.01]) {
        expect(checkSupport(card, card, x + width / 2, view, height, null, width).kind).toBe('fall')
      }
      expect(checkSupport(card, null, 215, view, height, null, width).kind).toBe('fall')
      expect(checkSupport(card, { ...card, top: 58 }, 215, view, height, null, width).kind).toBe('fall')
    }
  })
})
