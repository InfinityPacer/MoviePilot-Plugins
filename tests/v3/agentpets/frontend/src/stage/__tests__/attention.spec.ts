import { describe, expect, it } from 'vitest'
import { GazeTracker, ProximityTracker, supportsLookDirections, ATTENTION_DWELL_MS } from '@/stage/attention'
import { buildCodexPetPack, withCodexStageActions } from '@/sprites/schema'

const box = { x: 100, y: 100, width: 80, height: 120 }

describe('nearby pointer dwell', () => {
  it('uses a 350ms dwell instead of responding to each pointer move', () => {
    expect(ATTENTION_DWELL_MS).toBe(350)
    const tracker = new ProximityTracker()
    expect(tracker.sample({ x: 200, y: 160 }, box)).toBe('arm')
    expect(tracker.sample({ x: 205, y: 160 }, box)).toBe('near')
    expect(tracker.sample({ x: 209, y: 160 }, box)).toBe('arm')
    tracker.consume()
    expect(tracker.sample({ x: 220, y: 170 }, box)).toBe('near')
  })

  it('responds once per entry and rearms after leaving the hysteresis zone', () => {
    const tracker = new ProximityTracker()
    expect(tracker.sample({ x: 230, y: 160 }, box)).toBe('arm')
    tracker.consume()
    expect(tracker.sample({ x: 255, y: 160 }, box)).toBe('near')
    expect(tracker.sample({ x: 257, y: 160 }, box)).toBe('leave')
    expect(tracker.sample({ x: 230, y: 160 }, box)).toBe('arm')
  })

  it('can dwell on proximity alone while retaining stationary dwell for fallback responses', () => {
    const tracker = new ProximityTracker()
    expect(tracker.sample({ x: 200, y: 160 }, box, false)).toBe('arm')
    expect(tracker.sample({ x: 220, y: 180 }, box, false)).toBe('near')
    expect(tracker.sample({ x: 230, y: 140 }, box, false)).toBe('near')
    expect(tracker.sample({ x: 400, y: 160 }, box, false)).toBe('leave')
    expect(tracker.sample({ x: 200, y: 160 }, box, false)).toBe('arm')
  })

  it('bounds the radius for very small and large characters', () => {
    const tiny = { x: 100, y: 100, width: 10, height: 10 }
    const huge = { x: 100, y: 100, width: 400, height: 400 }
    expect(new ProximityTracker().sample({ x: 158, y: 105 }, tiny)).toBe('arm')
    expect(new ProximityTracker().sample({ x: 159, y: 105 }, tiny)).toBe('leave')
    expect(new ProximityTracker().sample({ x: 596, y: 300 }, huge)).toBe('arm')
    expect(new ProximityTracker().sample({ x: 597, y: 300 }, huge)).toBe('leave')
  })

  it('checks Euclidean distance around corners rather than a square margin', () => {
    const tracker = new ProximityTracker()
    expect(tracker.sample({ x: 225, y: 55 }, box)).toBe('leave')
    expect(tracker.sample({ x: 220, y: 60 }, box)).toBe('arm')
    tracker.reset()
    expect(tracker.sample({ x: 220, y: 160 }, box)).toBe('arm')
  })
})

describe('clockwise Codex v2 gaze', () => {
  const origin = { x: 100, y: 100 }

  it.each([
    [{ x: 100, y: 0 }, 'look-000'],
    [{ x: 200, y: 100 }, 'look-090'],
    [{ x: 100, y: 200 }, 'look-180'],
    [{ x: 0, y: 100 }, 'look-270'],
    [{ x: 200, y: 0 }, 'look-045'],
    [{ x: 200, y: 200 }, 'look-135'],
    [{ x: 0, y: 200 }, 'look-225'],
    [{ x: 0, y: 0 }, 'look-315'],
  ])('uses screen coordinates for %j', (target, action) => {
    expect(new GazeTracker().select(target, origin, 0)).toBe(action)
  })

  it('keeps the center dead zone neutral and the current gaze stable', () => {
    const tracker = new GazeTracker()
    expect(tracker.select({ x: 111, y: 100 }, origin, 0)).toBeNull()
    expect(tracker.select({ x: 112, y: 100 }, origin, 0)).toBe('look-090')
    expect(tracker.select(origin, origin, 200)).toBe('look-090')
    tracker.reset()
    expect(tracker.select(origin, origin, 300)).toBeNull()
  })

  it('changes direction only at or after the 120ms interval', () => {
    const tracker = new GazeTracker()
    expect(tracker.remainingDelay(0)).toBe(0)
    expect(tracker.select({ x: 100, y: 0 }, origin, 0)).toBe('look-000')
    expect(tracker.select({ x: 200, y: 100 }, origin, 119)).toBe('look-000')
    expect(tracker.remainingDelay(119)).toBe(1)
    expect(tracker.select({ x: 200, y: 100 }, origin, 120)).toBe('look-090')
    expect(tracker.remainingDelay(240)).toBe(0)
    tracker.reset()
    expect(tracker.remainingDelay(240)).toBe(0)
  })

  it('adds angular hysteresis including the 337.5 to 000 seam', () => {
    const point = (angle: number) => ({
      x: origin.x + Math.sin((angle * Math.PI) / 180) * 100,
      y: origin.y - Math.cos((angle * Math.PI) / 180) * 100,
    })
    const tracker = new GazeTracker()
    expect(tracker.select(point(0), origin, 0)).toBe('look-000')
    expect(tracker.select(point(14), origin, 200)).toBe('look-000')
    expect(tracker.select(point(18), origin, 400)).toBe('look-022-5')
    tracker.reset()
    expect(tracker.select(point(337.5), origin, 0)).toBe('look-337-5')
    expect(tracker.select(point(351), origin, 200)).toBe('look-337-5')
    expect(tracker.select(point(356), origin, 400)).toBe('look-000')
  })
})

describe('direction capability', () => {
  it('accepts standard v2 and its remapped legacy frame names, not v1', () => {
    const v2 = buildCodexPetPack('v2.png', 1536, 2288).pack
    expect(supportsLookDirections(v2)).toBe(true)
    expect(supportsLookDirections(buildCodexPetPack('v1.png', 1536, 1872).pack)).toBe(false)
    const legacy = { ...v2, frames: { idle: 0 }, actions: { idle: v2.actions.idle } }
    expect(supportsLookDirections(withCodexStageActions(legacy))).toBe(true)
  })

  it('rejects a missing, looping, multi-frame or invalid directional action', () => {
    for (const variant of ['missing', 'looping', 'multi-frame', 'invalid-frame'] as const) {
      const pack = buildCodexPetPack('v2.png', 1536, 2288).pack
      const action = pack.actions['look-090']
      if (variant === 'missing') delete pack.actions['look-090']
      if (variant === 'looping') action.loop = true
      if (variant === 'multi-frame') action.frames.push('idle')
      if (variant === 'invalid-frame') action.frames[0] = 'missing'
      expect(supportsLookDirections(pack)).toBe(false)
    }
  })
})
