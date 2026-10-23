import { describe, expect, it, vi } from 'vitest'

import { ActivityPolicy, supportsRest, type ActivityArea } from '@/stage/activity'
import { buildCodexPetPack, BUILTIN_PACK } from '@/sprites/schema'

const area = (overrides: Partial<ActivityArea> = {}): ActivityArea => ({
  current: { x: 400, y: 400 },
  bounds: { x: [0, 900], y: [0, 700] },
  free: false,
  height: 120,
  mobile: false,
  span: null,
  allowed: () => true,
  ...overrides,
})

describe('finite autonomous activity', () => {
  it('does not promise sleep artwork for standard Codex layouts or idle aliases', () => {
    for (const height of [1872, 2288]) {
      const pack = buildCodexPetPack('pet.png', 1536, height).pack
      expect(supportsRest(pack)).toBe(false)
      pack.actions.sleep = { ...pack.actions.idle }
      expect(supportsRest(pack)).toBe(false)
      pack.actions.sleep = { frames: [pack.actions.idle.frames[0]], frame_ms: 160, loop: false }
      expect(supportsRest(pack)).toBe(false)
    }
    expect(supportsRest(BUILTIN_PACK)).toBe(true)
    expect(supportsRest(BUILTIN_PACK, { 'stage.doze': 'idle' })).toBe(false)
    expect(supportsRest(BUILTIN_PACK, { 'stage.doze': 'sleep' })).toBe(true)
  })
  it('continues two or three steps then returns to a normal episode interval', () => {
    for (const random of [() => 0.2, () => 0.8]) {
      const policy = new ActivityPolicy()
      expect(policy.delay(0, random)).toBeGreaterThanOrEqual(6000)
      policy.begin(0, random)
      const steps = random() < 0.5 ? 2 : 3
      for (let step = 0; step < steps; step++) {
        expect(policy.continuing(step * 1000)).toBe(true)
        expect(policy.delay(step * 1000, random)).toBeLessThan(2000)
        policy.arrived({ x: step * 100, y: 0 }, { x: (step + 1) * 100, y: 0 }, step * 1000)
      }
      expect(policy.continuing(steps * 1000)).toBe(false)
      expect(policy.delay(steps * 1000, random)).toBeGreaterThanOrEqual(6000)
    }
  })

  it('expires a delayed episode instead of replaying its remaining steps', () => {
    const policy = new ActivityPolicy()
    policy.begin(0, () => 0.8)
    expect(policy.remainingTime(0)).toBe(25_000)
    expect(policy.continuing(25_000)).toBe(false)
    expect(policy.remainingTime(25_000)).toBe(0)
    expect(policy.delay(25_000, () => 0.5)).toBe(10_000)
  })

  it('allows an occasional long first exploration and never mutates its input bounds', () => {
    const policy = new ActivityPolicy()
    const input = area({ span: [800, 950] })
    policy.begin(0, () => 0.8)
    expect(policy.target(input, 0, () => 0.95)!.x).toBeGreaterThan(616)
    expect(input.bounds.x).toEqual([0, 900])
  })

  it('does not turn a brief interaction boost into unlimited short-interval episodes', () => {
    const policy = new ActivityPolicy()
    policy.interact({ x: 400, y: 400 }, 0)
    policy.begin(0, () => 0.5)
    for (let step = 0; step < 3; step++)
      policy.arrived({ x: step * 100, y: 0 }, { x: (step + 1) * 100, y: 0 }, step * 100)
    expect(policy.delay(301, () => 0.5)).toBe(10_000)
  })

  it('keeps post-interaction exploration nearby only for a bounded window', () => {
    const policy = new ActivityPolicy()
    policy.interact({ x: 400, y: 400 }, 100)
    expect(policy.delay(100, () => 0.5)).toBe(1300)
    const target = policy.target(area(), 100, () => 0.95)!
    expect(Math.abs(target.x - 400)).toBeLessThanOrEqual(216)
    expect(policy.excited(16_100)).toBe(false)
    expect(policy.delay(16_100, () => 0.5)).toBe(10_000)
  })

  it('prefers a new nearby point over returning to the prior departure', () => {
    const policy = new ActivityPolicy()
    policy.arrived({ x: 184, y: 400 }, { x: 400, y: 400 }, 0)
    const target = policy.target(area(), 100, () => 0.5)
    expect(target).toEqual({ x: 616, y: 400 })
    policy.reset()
    expect(policy.target(area(), 100, () => 0.5)).toEqual({ x: 184, y: 400 })
  })

  it('forgets old route preferences without persisting or growing state', () => {
    const policy = new ActivityPolicy()
    for (let step = 0; step < 20; step++) policy.arrived({ x: 184, y: 400 }, { x: 400, y: 400 }, step)
    expect(policy.target(area(), 44_000, () => 0.5)?.x).toBe(616)
    expect(policy.target(area(), 45_020, () => 0.5)?.x).toBe(184)
  })

  it('cancels excitement and continuation but keeps recently reached route preferences', () => {
    const policy = new ActivityPolicy()
    policy.interact({ x: 400, y: 400 }, 0)
    policy.begin(0, () => 0.8)
    policy.arrived({ x: 184, y: 400 }, { x: 400, y: 400 }, 100)
    policy.cancel()
    expect(policy.continuing(101)).toBe(false)
    expect(policy.excited(101)).toBe(false)
    expect(policy.target(area(), 101, () => 0.5)?.x).toBe(616)
  })

  it('uses at most eight unique safety candidates and never forces a blocked move', () => {
    const allowed = vi.fn(() => false)
    const policy = new ActivityPolicy()
    expect(policy.target(area({ free: true, allowed }), 0, () => 0.5)).toBeNull()
    expect(allowed.mock.calls.length).toBeLessThanOrEqual(8)
  })

  it('picks only nearby higher surfaces with a shorter mobile rise limit', () => {
    const policy = new ActivityPolicy()
    const close = { x: 400, y: 200, surface: 'nearby' }
    const tooHigh = { x: 400, y: 120, surface: 'high' }
    const tooFar = { x: 700, y: 300, surface: 'far' }
    const sameLevel = { x: 400, y: 400, surface: 'same-level' }
    expect(policy.upwardTarget(area(), [tooHigh, tooFar, sameLevel, close], 0)).toBe(close)
    expect(policy.upwardTarget(area({ mobile: true }), [close], 0)).toBeNull()
    expect(policy.upwardTarget(area({ free: true }), [close], 0)).toBeNull()
    expect(policy.upwardTarget(area(), [], 0)).toBeNull()
  })

  it('reuses bounded route preferences for hops and forgets expired destinations', () => {
    const policy = new ActivityPolicy()
    const first = { x: 400, y: 300, surface: 'visited' }
    const alternative = { x: 500, y: 300, surface: 'new' }
    policy.arrived({ x: 400, y: 400 }, first, 0)
    expect(policy.upwardTarget(area(), [first, alternative], 100)).toBe(alternative)
    expect(policy.upwardTarget(area(), [first, alternative], 45_001)).toBe(first)
  })

  it('does not let a hop escape the accepted interaction neighborhood', () => {
    const policy = new ActivityPolicy()
    policy.interact({ x: 400, y: 400 }, 0)
    const escaped = { x: 650, y: 300 }
    const local = { x: 500, y: 300 }
    expect(policy.upwardTarget(area({ current: { x: 550, y: 400 } }), [escaped, local], 100)).toBe(local)
  })

  it('stays on the same side of a panel and respects narrow mobile bounds', () => {
    const policy = new ActivityPolicy()
    const target = policy.target(
      area({ current: { x: 150, y: 400 }, bounds: { x: [10, 280], y: [100, 450] }, span: [200, 250], mobile: true }),
      0,
      () => 0.8,
    )!
    expect(target.x).toBeLessThan(200)
    expect(Math.abs(target.x - 150)).toBeLessThanOrEqual(108)
    expect(policy.target(area({ bounds: { x: [400, 400], y: [400, 400] } }), 0, () => 0.5)).toBeNull()
  })
})
