import { describe, expect, it } from 'vitest'

import {
  blockedSpan,
  checkSupport,
  computeLanding,
  coversAny,
  effectiveScale,
  freeBounds,
  hopVelocity,
  nearestEdge,
  intersectionArea,
  pickClearX,
  pickShelterDepth,
  pickFreeTarget,
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

  it('treats more than 10% overlap with a control as covering', () => {
    const pet = { x: 100, y: 100, width: 100, height: 100 }
    expect(intersectionArea(pet, { x: 150, y: 150, width: 100, height: 100 })).toBe(2500)
    expect(intersectionArea(pet, { x: 200, y: 100, width: 50, height: 50 })).toBe(0)
    // 侧栏菜单项从她身后穿过：交集 100x20，正好 20%。
    expect(coversAny(pet, [{ x: 0, y: 160, width: 300, height: 20 }])).toBe(true)
    // 只擦到一点边：交集 10x50，5%。
    expect(coversAny(pet, [{ x: 190, y: 120, width: 80, height: 50 }])).toBe(false)
    expect(coversAny(pet, [])).toBe(false)
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

describe('cover rules and shelter helpers', () => {
  const pet = { x: 100, y: 100, width: 100, height: 120 }

  it('counts a small icon fully covered by her even though it is a tiny part of her body', () => {
    const icon = { x: 140, y: 150, width: 24, height: 24 }
    // 交集 576，只占身体 4.8%，但占图标 100%。
    expect(coversAny(pet, [icon])).toBe(true)
    // 只盖住图标一小角：交集占图标 25%、占身体 1.2%，不算。
    expect(coversAny(pet, [{ x: 188, y: 100, width: 24, height: 24 }])).toBe(false)
  })

  it('measures the body ratio against the full body while sunk', () => {
    const visible = { x: 0, y: 758, width: 100, height: 10 }
    const band = { x: 0, y: 600, width: 1000, height: 168 }
    expect(coversAny(visible, [band])).toBe(true)
    expect(coversAny(visible, [band], 100 * 120)).toBe(false)
  })

  it('sinks only as deep as needed and falls back to the deepest level', () => {
    expect(pickShelterDepth(depth => depth >= 0.65)).toBe(0.65)
    expect(pickShelterDepth(() => false)).toBe(0.92)
  })

  it('retreats to the nearest side', () => {
    expect(nearestEdge(100, [0, 900])).toBe(0)
    expect(nearestEdge(600, [0, 900])).toBe(900)
  })

  it('hops along an arc that lands exactly on the target, including higher surfaces', () => {
    for (const to of [
      { x: 500, y: 180 },
      { x: 50, y: 650 },
    ]) {
      const from = { x: 300, y: 648 }
      const { vx, vy } = hopVelocity(from, to, 2600, 60)
      expect(vy).toBeLessThan(0)
      // 用解析解检验：在下降段到达目标高度时，水平位置正好是目标 x。
      const apexTime = -vy / 2600
      const apexY = from.y + vy * apexTime + 0.5 * 2600 * apexTime ** 2
      expect(apexY).toBeLessThan(Math.min(from.y, to.y))
      const landTime = apexTime + Math.sqrt((2 * (to.y - apexY)) / 2600)
      expect(from.x + vx * landTime).toBeCloseTo(to.x)
    }
  })
})
