import { describe, expect, it } from 'vitest'

import {
  blockedSpan,
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
