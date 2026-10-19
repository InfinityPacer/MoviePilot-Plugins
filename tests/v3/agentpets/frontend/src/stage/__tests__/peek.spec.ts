import { describe, expect, it } from 'vitest'
import type { AgentRect } from '@/host'
import { dropPeekEdge, isPeekEdge, peekHome, peekLayout, peekPanelShift, PEEK_TUCK, PEEK_TILT } from '@/stage/peek'
import type { StageViewport } from '@/stage/geometry'
import { calibrationEye, parseCalibration } from '@/sprites/calibration'

const view: StageViewport = {
  width: 390,
  height: 800,
  keyboardInset: 0,
  safeArea: { left: 12, right: 12, top: 24, bottom: 32 },
}
const size = { width: 100, height: 120 }
const eye = { x: 0.35, y: 0.3 }

function inside(rect: AgentRect, viewport = view) {
  expect(rect.x).toBeGreaterThanOrEqual(viewport.safeArea.left - 1e-8)
  expect(rect.y).toBeGreaterThanOrEqual(viewport.safeArea.top - 1e-8)
  expect(rect.x + rect.width).toBeLessThanOrEqual(viewport.width - viewport.safeArea.right + 1e-8)
  expect(rect.y + rect.height).toBeLessThanOrEqual(viewport.height - viewport.safeArea.bottom + 1e-8)
}

function projectedEye(layout: ReturnType<typeof peekLayout>, x: number) {
  const { artwork } = layout
  const radians = (artwork.rotation * Math.PI) / 180
  const dx = (x - 0.5) * artwork.width
  const dy = (eye.y - 0.5) * artwork.height
  return {
    x: artwork.x + artwork.width / 2 + dx * Math.cos(radians) - dy * Math.sin(radians),
    y: artwork.y + artwork.height / 2 + dx * Math.sin(radians) + dy * Math.cos(radians),
  }
}

describe('single-eye bottom-corner geometry', () => {
  it.each(['bottom', 'left', 'right'] as const)(
    'uses actual eye separation and the head marker for %s peeking',
    edge => {
      const face = calibrationEye(
        parseCalibration({
          left_eye_x: 0.35,
          left_eye_y: 0.29,
          right_eye_x: 0.62,
          right_eye_y: 0.31,
          head_top_x: 0.48,
          head_top_y: 0.08,
        }),
      )!
      const home = peekHome({ x: 12, y: 590 }, view, size, edge)
      const hidden = peekLayout(home, size, view, edge, PEEK_TUCK, face, false)
      expect(edge === 'bottom' ? hidden.visible.height : hidden.visible.width).toBe(0)
      const result = peekLayout(home, size, view, edge, 1, face, true, 1, PEEK_TILT)
      const a = result.artwork,
        radians = (a.rotation * Math.PI) / 180
      const projected = face.eyes!.map(point => ({
        x:
          a.x +
          a.width / 2 +
          (point.x - 0.5) * a.width * Math.cos(radians) -
          (point.y - 0.5) * a.height * Math.sin(radians),
        y:
          a.y +
          a.height / 2 +
          (point.x - 0.5) * a.width * Math.sin(radians) +
          (point.y - 0.5) * a.height * Math.cos(radians),
      }))
      const visible = projected.filter(point =>
        edge === 'bottom' ? point.y < 768 : edge === 'left' ? point.x > 12 : point.x < 378,
      )
      expect(visible).toHaveLength(1)
      inside(result.visible)
      inside(result.hit)
      if (edge === 'bottom') {
        const movedTop = peekLayout(
          home,
          size,
          view,
          edge,
          1,
          { ...face, headTop: { x: 0.2, y: 0.08 } },
          true,
          1,
          PEEK_TILT,
        )
        expect(movedTop.artwork.x).not.toBeCloseTo(result.artwork.x)
      }
    },
  )
  it('clears fractional panel overlap without moving away from the chosen edge', () => {
    const desktop = { ...view, width: 1280 }
    const rect = { x: 799.8176, y: 720, width: 100.7457, height: 48 }
    const shift = peekPanelShift(rect, { x: 900, y: 0, width: 380, height: 800 }, desktop)!
    expect(shift.y).toBe(0)
    expect(rect.x + shift.x + rect.width).toBeLessThan(900)
  })
  it('reverses only the bottom tilt and keeps the head close to its corner', () => {
    for (const corner of [
      { x: 0, y: 0 },
      { x: 390, y: 800 },
    ]) {
      const home = peekHome(corner, view, size)
      const layout = peekLayout(home, size, view, 'bottom', 1, eye, true, 1, PEEK_TILT)
      inside(layout.visible)
      inside(layout.hit)
      expect(layout.hit.width).toBeGreaterThanOrEqual(48)
      expect(layout.hit.height).toBeGreaterThanOrEqual(48)
      expect(layout.eye!.x).toBeGreaterThan(layout.visible.x)
      expect(layout.eye!.x).toBeLessThan(layout.visible.x + layout.visible.width)
      expect(layout.eye!.y).toBeGreaterThan(layout.visible.y)
      expect(layout.eye!.y).toBeGreaterThan(layout.visible.y + layout.visible.height)
      expect(layout.visible.y + layout.visible.height).toBeCloseTo(768)
      expect(layout.artwork.rotation).toBe(corner.x === 0 ? -PEEK_TILT : PEEK_TILT)
      expect(layout.eye!.x).toBeCloseTo(corner.x === 0 ? 49 : 341)
      const eyes = [projectedEye(layout, eye.x - 0.12), projectedEye(layout, eye.x + 0.12)]
      const visible = eyes.filter(point => point.y < 768)
      expect(visible).toHaveLength(1)
      expect(visible[0]).toEqual(eyes[corner.x === 0 ? 1 : 0])
      expect(visible[0].x).toBeGreaterThan(layout.visible.x)
      expect(visible[0].x).toBeLessThan(layout.visible.x + layout.visible.width)
      expect(Math.min(...eyes.map(point => point.y))).toBeLessThan(765)
      expect(Math.max(...eyes.map(point => point.y))).toBeGreaterThan(771)
    }
  })

  it.each([0.6, 1, 1.6])('adds eight CSS pixels of bottom-corner head clearance at scale %s', scale => {
    const face = calibrationEye(
      parseCalibration({
        left_eye_x: 0.35,
        left_eye_y: 0.29,
        right_eye_x: 0.62,
        right_eye_y: 0.31,
        head_top_x: 0.48,
        head_top_y: 0.08,
      }),
    )!
    const dimensions = { width: size.width * scale, height: size.height * scale }
    for (const width of [390, 1280]) {
      const viewport = { ...view, width }
      for (const onLeft of [true, false]) {
        const home = peekHome({ x: onLeft ? 0 : width, y: 0 }, viewport, dimensions)
        const legacy = peekLayout(home, dimensions, viewport, 'bottom', 1, eye)
        const boundary = onLeft ? home.x : home.x + dimensions.width
        const legacyGap = onLeft ? legacy.eye!.x - boundary : boundary - legacy.eye!.x
        expect(legacyGap).toBeCloseTo(dimensions.width * 0.25 + 4 + 8)
        const calibrated = peekLayout(home, dimensions, viewport, 'bottom', 1, face)
        const a = calibrated.artwork
        const radians = (a.rotation * Math.PI) / 180
        const xs = [...face.eyes!, face.headTop!].map(
          point =>
            a.x +
            a.width / 2 +
            (point.x - 0.5) * a.width * Math.cos(radians) -
            (point.y - 0.5) * a.height * Math.sin(radians),
        )
        const gap = onLeft ? Math.min(...xs) - boundary : boundary - Math.max(...xs)
        const padding = Math.max(4, (Math.abs(face.eyes![1].x - face.eyes![0].x) * a.width) / 2)
        expect(gap).toBeCloseTo(padding + 8)
        expect(calibrated.artwork.rotation).toBe(legacy.artwork.rotation)
        inside(calibrated.hit, viewport)
      }
    }
  })

  it('still follows a bottom-edge panel avoidance shift instead of pinning the head to the corner', () => {
    const home = peekHome({ x: 12, y: 0 }, view, size)
    const before = peekLayout(home, size, view, 'bottom', 1, eye)
    const moved = peekLayout({ ...home, x: home.x + 80 }, size, view, 'bottom', 1, eye)
    expect(moved.eye!.x - before.eye!.x).toBeCloseTo(80)
    expect(moved.eye!.y).toBeCloseTo(before.eye!.y)
    expect(moved.artwork.rotation).toBe(before.artwork.rotation)
  })

  it('keeps hit targets inside a small viewport throughout the transition', () => {
    const tiny = { ...view, width: 180, height: 240 }
    const wide = { width: 320, height: 160 }
    for (const progress of [0, 0.25, 0.5, 0.75, 1, PEEK_TUCK, 1.03]) {
      const home = peekHome({ x: 0, y: 0 }, tiny, wide)
      const layout = peekLayout(home, wide, tiny, 'bottom', progress, eye)
      inside(layout.visible, tiny)
      inside(layout.hit, tiny)
      expect(layout.hit.width * layout.hit.height).toBeGreaterThan(0)
      if (progress === PEEK_TUCK) expect(layout.visible.height).toBe(0)
    }
  })

  it('keeps the body upright throughout the initial descent', () => {
    const home = peekHome({ x: 120, y: 200 }, view, size)
    for (const tuck of [0, 0.25, 0.5, 1, PEEK_TUCK]) {
      expect(peekLayout(home, size, view, 'bottom', tuck, eye, false).artwork.rotation).toBe(0)
    }
  })

  it.each([20, PEEK_TILT])('finishes the bottom tilt at %s degrees out of view and then rises vertically', angle => {
    const home = peekHome({ x: 120, y: 200 }, view, size)
    const tucked = peekLayout(home, size, view, 'bottom', PEEK_TUCK, eye, false, 1, angle)
    expect(tucked.artwork.y).toBeGreaterThanOrEqual(768)
    expect(tucked.visible.height).toBe(0)
    expect(tucked.hit.height).toBe(48)
    expect(peekLayout(home, size, view, 'bottom', PEEK_TUCK, eye, true, 0, angle)).toEqual(tucked)
    let previousTilt = 0
    for (const turn of [0.25, 0.5, 0.75, 1]) {
      const turning = peekLayout(home, size, view, 'bottom', PEEK_TUCK, eye, true, turn, angle)
      expect(turning.visible.height).toBe(0)
      expect(Math.abs(turning.artwork.rotation)).toBeGreaterThan(previousTilt)
      previousTilt = Math.abs(turning.artwork.rotation)
    }
    const tilted = peekLayout(home, size, view, 'bottom', PEEK_TUCK, eye, true, 1, angle)
    let previousTop = tilted.artwork.y
    for (const progress of [1.05, 1.04, 1.03, 1.02, 1.01, 1]) {
      const looking = peekLayout(home, size, view, 'bottom', progress, eye, true, 1, angle)
      expect(looking.artwork.y).toBeLessThan(previousTop)
      expect(looking.artwork.x).toBeCloseTo(tilted.artwork.x)
      expect(looking.artwork.rotation).toBe(tilted.artwork.rotation)
      expect(looking.artwork.width).toBe(tilted.artwork.width)
      expect(looking.artwork.height).toBe(tilted.artwork.height)
      previousTop = looking.artwork.y
    }
  })

  it.each([false, true])('keeps both bottom corners vertical with three-point calibration %s', calibrated => {
    const face = calibrated
      ? calibrationEye(
          parseCalibration({
            left_eye_x: 0.35,
            left_eye_y: 0.29,
            right_eye_x: 0.62,
            right_eye_y: 0.31,
            head_top_x: 0.48,
            head_top_y: 0.08,
          }),
        )
      : eye
    for (const x of [12, 278]) {
      const home = peekHome({ x, y: 590 }, view, size)
      const start = peekLayout(home, size, view, 'bottom', PEEK_TUCK, face)
      for (const progress of [1.05, 1.03, 1.01, 1]) {
        const current = peekLayout(home, size, view, 'bottom', progress, face)
        expect(current.artwork.x).toBeCloseTo(start.artwork.x)
        expect(current.artwork.rotation).toBe(start.artwork.rotation)
        expect(current.artwork.y).toBeLessThan(start.artwork.y)
      }
    }
  })

  it('does not pretend that an uncalibrated head has a known eye', () => {
    const layout = peekLayout(peekHome({ x: 0, y: 0 }, view, size), size, view, 'bottom', 1, null)
    expect(layout.eye).toBeNull()
    expect(layout.visible.height).toBeGreaterThan(0)
    expect(layout.artwork.rotation).toBe(0)
  })

  it('defaults to upright bottom peeking and preserves vertical rise without changing side defaults', () => {
    const home = peekHome({ x: 0, y: 0 }, view, size)
    const tucked = peekLayout(home, size, view, 'bottom', PEEK_TUCK, eye)
    for (const progress of [1.05, 1.03, 1.01, 1]) {
      const current = peekLayout(home, size, view, 'bottom', progress, eye)
      expect(current.artwork.rotation).toBe(0)
      expect(current.artwork.x).toBeCloseTo(tucked.artwork.x)
      expect(current.artwork.width).toBe(tucked.artwork.width)
      expect(current.artwork.height).toBe(tucked.artwork.height)
      expect(current.artwork.y).toBeLessThan(tucked.artwork.y)
    }
    for (const edge of ['left', 'right'] as const) {
      expect(Math.abs(peekLayout(home, size, view, edge, 1, eye).artwork.rotation)).toBe(PEEK_TILT)
    }
  })

  it.each(['left', 'right'] as const)('fully hides beyond the %s side before exposing only one eye', edge => {
    const home = peekHome({ x: 150, y: 590 }, view, size, edge)
    const tucked = peekLayout(home, size, view, edge, PEEK_TUCK, eye, false)
    expect(tucked.visible.width).toBe(0)
    expect(tucked.hit.width).toBe(48)
    expect(tucked.artwork.rotation).toBe(0)
    expect(peekLayout(home, size, view, edge, PEEK_TUCK, eye)).toEqual(tucked)
    const boundary = edge === 'left' ? 12 : 378
    if (edge === 'left') expect(tucked.artwork.x + tucked.artwork.width).toBeLessThan(boundary)
    else expect(tucked.artwork.x).toBeGreaterThan(boundary)
    const looking = peekLayout(home, size, view, edge, 1, eye)
    inside(looking.visible)
    inside(looking.hit)
    expect(looking.artwork.rotation).toBe(edge === 'left' ? PEEK_TILT : -PEEK_TILT)
    const eyes = [projectedEye(looking, eye.x - 0.12), projectedEye(looking, eye.x + 0.12)]
    expect(eyes.filter(point => (edge === 'left' ? point.x > boundary : point.x < boundary))).toHaveLength(1)
    if (edge === 'left') expect(looking.visible.x).toBeCloseTo(boundary)
    else expect(looking.visible.x + looking.visible.width).toBeCloseTo(boundary)
    expect(looking.visible.height).toBeGreaterThan(0)
  })

  it.each(['left', 'right'] as const)('keeps %s-side touch targets inside a tiny viewport', edge => {
    const tiny = { ...view, width: 180, height: 240 }
    const tall = { width: 160, height: 320 }
    const home = peekHome({ x: 90, y: 150 }, tiny, tall, edge)
    for (const progress of [0, 0.5, 1, 1.03, PEEK_TUCK]) {
      const layout = peekLayout(home, tall, tiny, edge, progress, eye)
      inside(layout.visible, tiny)
      inside(layout.hit, tiny)
      expect(layout.hit.width).toBeGreaterThanOrEqual(48)
      expect(layout.hit.height).toBeGreaterThanOrEqual(48)
    }
  })

  it('slides along the side only while a lower-corner gap remains', () => {
    const rect = { x: 12, y: 600, width: 40, height: 100 }
    const shift = peekPanelShift(rect, { x: 0, y: 680, width: 80, height: 88 }, view, 'left')!
    expect(shift.x).toBe(0)
    expect(rect.y + shift.y + rect.height).toBeLessThan(680)
    expect(peekPanelShift(rect, { x: 0, y: 500, width: 80, height: 268 }, view, 'left')).toBeNull()
  })

  it('accepts lower side corners, prefers the nearest edge, and rejects upper sides', () => {
    expect(dropPeekEdge({ x: 12, y: 648 }, view, size)).toBe('bottom')
    expect(dropPeekEdge({ x: 278, y: 648 }, view, size)).toBe('bottom')
    expect(dropPeekEdge({ x: 150, y: 648 }, view, size)).toBeNull()
    expect(dropPeekEdge({ x: 12, y: 24 }, view, size)).toBeNull()
    expect(dropPeekEdge({ x: 12, y: 200 }, view, size)).toBeNull()
    expect(dropPeekEdge({ x: 278, y: 200 }, view, size)).toBeNull()
    expect(dropPeekEdge({ x: 150, y: 200 }, view, size)).toBeNull()
    expect(dropPeekEdge({ x: 12, y: 590 }, view, size)).toBe('left')
    expect(dropPeekEdge({ x: 278, y: 590 }, view, size)).toBe('right')
    expect(dropPeekEdge({ x: 12, y: 527 }, view, size)).toBeNull()
    expect(dropPeekEdge({ x: 278, y: 527 }, view, size)).toBeNull()
    expect(dropPeekEdge({ x: 13, y: 640 }, view, size)).toBe('left')
    expect(dropPeekEdge({ x: 20, y: 647 }, view, size)).toBe('bottom')
    expect(dropPeekEdge({ x: 20, y: 640 }, view, size)).toBe('bottom')
    expect(isPeekEdge('bottom')).toBe(true)
    expect(isPeekEdge('left')).toBe(true)
    expect(isPeekEdge('right')).toBe(true)
    expect(isPeekEdge('top')).toBe(false)
  })
})
