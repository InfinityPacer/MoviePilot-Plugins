import { describe, expect, it } from 'vitest'

import {
  blockedSpan,
  checkSupport,
  computeLanding,
  effectiveScale,
  freeBounds,
  pickClearX,
  pickFreeTarget,
  probePoints,
  standable,
  surfaceXBounds,
  escapeSpan,
  groundTop,
  pickWalkTarget,
  ratioToX,
  sameRect,
  xBounds,
  xToRatio,
  type StageViewport,
} from '@/stage/geometry'

const viewport: StageViewport = {
  width: 1000,
  height: 800,
  keyboardInset: 0,
  safeArea: { top: 0, right: 0, bottom: 20, left: 0 },
}

describe('stage geometry', () => {
  it('places the ground above the safe area and the soft keyboard', () => {
    expect(groundTop(viewport, 120)).toBe(660)
    expect(groundTop({ ...viewport, keyboardInset: 300 }, 120)).toBe(360)
  })

  it('round-trips the remembered horizontal ratio across viewport sizes', () => {
    const wide = xBounds(viewport, 100)
    const narrow = xBounds({ ...viewport, width: 400 }, 100)
    const ratio = xToRatio(450, wide)
    expect(ratio).toBeCloseTo(0.5)
    expect(ratioToX(ratio, narrow)).toBeCloseTo(150)
  })

  it('only blocks the ground band when the panel reaches it', () => {
    const panel = { x: 600, y: 100, width: 380, height: 680 }
    expect(blockedSpan(panel, 660, 100)).toEqual([500, 980])
    expect(blockedSpan({ ...panel, height: 300 }, 660, 100)).toBeNull()
    expect(blockedSpan(null, 660, 100)).toBeNull()
  })

  it('never picks a walk target on the far side of the panel', () => {
    const values = [0.1, 0.9, 0.5]
    let index = 0
    const random = () => values[index++ % values.length]
    for (let round = 0; round < 10; round += 1) {
      const target = pickWalkTarget(random, 100, [0, 900], [500, 980])
      expect(target === null || target <= 500).toBe(true)
    }
  })

  it('moves a blocked character to the nearer side of the panel', () => {
    expect(escapeSpan(560, [500, 980], [0, 900])).toBe(500)
    expect(escapeSpan(300, [500, 980], [0, 900])).toBe(300)
  })

  it('compares anchors at pixel precision', () => {
    expect(sameRect({ x: 1.2, y: 2, width: 3, height: 4 }, { x: 1.4, y: 2, width: 3, height: 4 })).toBe(true)
    expect(sameRect({ x: 1, y: 2, width: 3, height: 4 }, null)).toBe(false)
  })
})

describe('roam landing', () => {
  const size = { width: 100, height: 120 }
  const card = { left: 200, top: 400, right: 600 }
  const dialog = { left: 300, top: 250, right: 700 }

  it('floor mode always lands on the bottom edge', () => {
    const landing = computeLanding('floor', [card], { x: 300, y: 50 }, viewport, size)
    expect(landing).toEqual({ y: 660, surface: null })
  })

  it('free mode stops where it was released, clamped to the viewport', () => {
    expect(computeLanding('free', [card], { x: 300, y: 50 }, viewport, size)).toEqual({ y: 50, surface: null })
    expect(computeLanding('free', [card], { x: 300, y: 900 }, viewport, size).y).toBe(660)
  })

  it('surfaces mode lands on the nearest surface below the feet', () => {
    const landing = computeLanding('surfaces', [card, dialog], { x: 350, y: 50 }, viewport, size)
    expect(landing.surface).toBe(dialog)
    expect(landing.y).toBe(130)
    const belowDialog = computeLanding('surfaces', [card, dialog], { x: 350, y: 200 }, viewport, size)
    expect(belowDialog.surface).toBe(card)
    const offSurface = computeLanding('surfaces', [card], { x: 700, y: 50 }, viewport, size)
    expect(offSurface).toEqual({ y: 660, surface: null })
  })

  it('only accepts wide, visible surfaces with headroom outside the panel', () => {
    expect(standable(card, viewport, 120, null)).toBe(true)
    expect(standable({ ...card, right: card.left + 100 }, viewport, 120, null)).toBe(false)
    expect(standable({ ...card, top: 80 }, viewport, 120, null)).toBe(false)
    expect(standable({ ...card, top: 790 }, viewport, 120, null)).toBe(false)
    expect(standable(card, viewport, 120, { x: 150, y: 300, width: 500, height: 400 })).toBe(false)
  })

  it('falls when the surface disappears, shrinks away or scrolls out', () => {
    expect(checkSupport(card, null, 400, viewport, 120, null)).toEqual({ kind: 'fall' })
    expect(checkSupport(card, { ...card, right: 300 }, 400, viewport, 120, null)).toEqual({ kind: 'fall' })
    expect(checkSupport(card, { ...card, top: 60 }, 400, viewport, 120, null)).toEqual({ kind: 'fall' })
  })

  it('follows a surface that moves', () => {
    expect(checkSupport(card, { left: 230, top: 350, right: 630 }, 400, viewport, 120, null)).toEqual({
      kind: 'follow',
      dx: 30,
      y: 230,
    })
  })

  it('keeps the center on the surface while walking and finds free targets inside the viewport', () => {
    expect(surfaceXBounds(card, viewport, 100)).toEqual([150, 550])
    const target = pickFreeTarget(() => 0.9, { x: 0, y: 0 }, freeBounds(viewport, 100, 120))
    expect(target).toEqual({ x: 810, y: 594 })
    expect(blockedSpan({ x: 600, y: 100, width: 200, height: 200 }, 660, 100, 120)).toBeNull()
  })
})

describe('control clearance', () => {
  it('shrinks on mobile on top of the user scale', () => {
    expect(effectiveScale(1.5, false)).toBe(1.5)
    expect(effectiveScale(1.5, true)).toBeCloseTo(1.2)
  })

  it('probes the center and both sides of the lower half', () => {
    expect(probePoints({ x: 100, y: 200, width: 80, height: 120 })).toEqual([
      { x: 140, y: 260 },
      { x: 120, y: 290 },
      { x: 160, y: 290 },
    ])
  })

  it('walks to the nearest clear position on the current surface', () => {
    const blocked = (x: number) => x >= 500 && x <= 700
    expect(pickClearX(600, [0, 900], x => !blocked(x), 50)).toBe(450)
    expect(pickClearX(690, [0, 900], x => !blocked(x), 50)).toBe(740)
    // 只能往一侧走时贴着范围边界停下。
    expect(pickClearX(880, [0, 900], x => x < 820, 50)).toBe(780)
  })

  it('reports no position when the whole surface is covered', () => {
    expect(pickClearX(300, [200, 500], () => false, 50)).toBeNull()
  })
})
