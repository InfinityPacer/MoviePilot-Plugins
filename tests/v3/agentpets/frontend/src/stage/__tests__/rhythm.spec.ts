import { describe, expect, it } from 'vitest'

import { BUILTIN_PACK, BUILTIN_PACKS, type SpritePack } from '@/sprites/schema'
import { ActivityPolicy, activityRadius, type ActivityArea } from '@/stage/activity'
import { builtinRhythm, RhythmPolicy } from '@/stage/rhythm'

const z256 = 'builtin-kurisu' + '-z256'
const keys = ['builtin-nailong', 'builtin-chibiterasu', 'builtin-kurisu', z256]

describe('built-in rhythm profiles', () => {
  it.each(keys)('uses existing, distinct artwork for %s without mutating its pack', key => {
    const pack = BUILTIN_PACKS[key]
    const original = JSON.stringify(pack)
    const profile = builtinRhythm(pack)!
    expect(profile.id).toBe(key)
    expect(profile.walkWeight).toBeGreaterThan(profile.actions.reduce((sum, action) => sum + action.weight, 0))
    expect(profile.actions.length).toBeGreaterThan(0)
    for (const action of profile.actions) {
      expect(pack.actions[action.key]).toBeDefined()
      expect(action.duration).toBeGreaterThan(0)
      expect(action.duration).toBeLessThanOrEqual(6000)
      expect(action.cooldown).toBeGreaterThan(profile.interval[1])
    }
    expect(JSON.stringify(pack)).toBe(original)
  })

  it('gives each character a different default cadence and curated repertoire', () => {
    const profiles = keys.map(key => builtinRhythm(BUILTIN_PACKS[key])!)
    expect(new Set(profiles.map(profile => profile.interval.join(','))).size).toBe(4)
    expect(profiles.map(profile => profile.actions.map(action => action.key))).toEqual([
      ['cheer'],
      ['relaxed-sit', 'lie'],
      ['look-up', 'relaxed-sit'],
      ['wave', 'scan'],
    ])
  })

  it('does not apply stage rhythm to Ying, the host-controlled cat or imported packs', () => {
    expect(builtinRhythm(BUILTIN_PACK)).toBeNull()
    expect(builtinRhythm({ ...BUILTIN_PACKS[z256], id: 'imported-pet' })).toBeNull()
    expect(builtinRhythm({ ...BUILTIN_PACKS[z256], id: 'ying' })).toBeNull()
  })

  it('holds duplicate-frame still poses briefly instead of calling them long animations', () => {
    const profile = builtinRhythm(BUILTIN_PACKS['builtin-chibiterasu'])!
    expect(profile.actions.map(action => [action.key, action.cycle, action.duration])).toEqual([
      ['relaxed-sit', null, 2200],
      ['lie', null, 2800],
    ])
    expect(builtinRhythm(BUILTIN_PACKS['builtin-kurisu'])!.actions[0].cycle).toBe(3894)
    expect(builtinRhythm(BUILTIN_PACKS[z256])!.actions[1].cycle).toBe(960)
  })

  it('respects saved or draft mappings and skips idle-only mapped artwork', () => {
    const pack = BUILTIN_PACKS[z256]
    const mapped = { ...pack, action_mappings: { 'stage.think': 'idle', 'stage.wave': 'happy-jump' } }
    expect(builtinRhythm(mapped)!.actions.map(action => action.key)).toEqual(['happy-jump'])
    expect(
      builtinRhythm(mapped, { 'stage.think': 'scan', 'stage.wave': 'idle' })!.actions.map(action => action.key),
    ).toEqual(['scan'])
  })

  it('deduplicates alias sequences and ignores absent or too-long animations', () => {
    const pack = BUILTIN_PACKS[z256]
    const mapped = { 'stage.think': 'wave' }
    expect(builtinRhythm(pack, mapped)!.actions.map(action => action.key)).toEqual(['wave'])
    const invalid: SpritePack = {
      ...pack,
      actions: { ...pack.actions, wave: { ...pack.actions.wave, frame_ms: 5000 } },
    }
    delete invalid.actions.scan
    expect(builtinRhythm(invalid)!.actions).toEqual([])
    const malformed = { ...pack, actions: { ...pack.actions, scan: { ...pack.actions.scan, frames: ['absent'] } } }
    expect(builtinRhythm(malformed)!.actions.map(action => action.key)).toEqual(['wave'])
  })

  it('keeps short episode and interaction continuations regardless of character interval', () => {
    const activity = new ActivityPolicy()
    const profile = builtinRhythm(BUILTIN_PACKS['builtin-kurisu'])!
    expect(activity.delay(0, () => 0.5, profile.interval)).toBe(12_000)
    activity.begin(0, () => 0.5)
    expect(activity.delay(0, () => 0.5, profile.interval)).toBe(1300)
    activity.interact({ x: 200, y: 200 }, 30_000)
    expect(activity.delay(30_000, () => 0.5, profile.interval)).toBe(1300)
    activity.reset()
    expect(activity.delay(100_000, () => 0.5)).toBe(10_000)
  })

  it('bounds small-character routes even when the random sample would normally choose a distant target', () => {
    const profile = builtinRhythm(BUILTIN_PACKS['builtin-chibiterasu'])!
    const activity = new ActivityPolicy()
    const area: ActivityArea = {
      current: { x: 500, y: 400 },
      bounds: { x: [0, 1000], y: [0, 800] },
      free: true,
      height: 120,
      mobile: false,
      radiusScale: profile.radiusScale,
      span: null,
      allowed: () => true,
    }
    const point = activity.target(area, 0, () => 0.99)!
    const radius = activityRadius(120, false, profile.radiusScale)
    expect(point).not.toBeNull()
    expect(Math.abs(point.x - 500)).toBeLessThanOrEqual(radius)
    expect(Math.abs(point.y - 400)).toBeLessThanOrEqual(radius)
    expect(radius).toBeLessThan(activityRadius(120, false))
  })
})

describe('memory-only weighted rhythm policy', () => {
  it('keeps movement as a real weighted choice', () => {
    const profile = builtinRhythm(BUILTIN_PACKS[z256])!
    const policy = new RhythmPolicy()
    expect(policy.pick(profile, 0, () => 0)).toBeNull()
    expect(policy.pick(profile, 0, () => 0.7)?.key).toBe('wave')
  })

  it('requires an actual move, enforces cooldowns and avoids an eligible repeated action', () => {
    const profile = builtinRhythm(BUILTIN_PACKS[z256])!
    const policy = new RhythmPolicy()
    expect(policy.pick(profile, 0, () => 0.99)?.key).toBe('scan')
    expect(policy.pick(profile, 100_000, () => 0.99)).toBeNull()
    policy.walked()
    expect(policy.pick(profile, 100_000, () => 0.99)?.key).toBe('wave')
    policy.walked()
    expect(policy.pick(profile, 100_001, () => 0.99)?.key).toBe('scan')
    policy.walked()
    expect(policy.pick(profile, 100_002, () => 0.99)).toBeNull()
    expect(policy.pick(profile, 128_001, () => 0.99)?.key).toBe('scan')
  })

  it('allows a sole curated action again only after movement and its cooldown', () => {
    const profile = builtinRhythm(BUILTIN_PACKS['builtin-nailong'])!
    const policy = new RhythmPolicy()
    expect(policy.pick(profile, 0, () => 0.99)?.key).toBe('cheer')
    policy.walked()
    expect(policy.pick(profile, 35_999, () => 0.99)).toBeNull()
    expect(policy.pick(profile, 36_000, () => 0.99)?.key).toBe('cheer')
    policy.reset()
    expect(policy.pick(profile, 0, () => 0.99)?.key).toBe('cheer')
  })

  it('does not age into silence when there has been no interaction for hours', () => {
    const profile = builtinRhythm(BUILTIN_PACKS[z256])!
    const policy = new RhythmPolicy()
    expect(policy.pick(profile, 10 * 60 * 60 * 1000, () => 0.99)?.key).toBe('scan')
    policy.walked()
    expect(policy.pick(profile, 20 * 60 * 60 * 1000, () => 0.99)?.key).toBe('wave')
  })
})
