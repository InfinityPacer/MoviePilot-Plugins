import { describe, expect, it } from 'vitest'

import { BUILTIN_PACKS, buildCodexPetPack, type PackAction } from '@/sprites/schema'
import {
  actionDuration,
  airborneFramePhase,
  MAX_ACTION_CYCLE_MS,
  NOMINAL_WALK_HEIGHTS_PER_SECOND,
  phaseFrame,
  resolveStageAction,
  stageCycleDuration,
  travelFrame,
} from '@/stage/playback'

const action: PackAction = { frames: ['a', 'b', 'c'], frame_ms: 100, frame_durations: [100, 200, 300], loop: true }
const travel = (ms: number) => (ms / 1000) * NOMINAL_WALK_HEIGHTS_PER_SECOND

describe('stage sprite playback', () => {
  it('uses traveled height rather than a timer and preserves unequal frame durations', () => {
    expect(actionDuration(action)).toBe(600)
    expect([0, 99, 100, 299, 301, 599, 601].map(ms => travelFrame(action, travel(ms)))).toEqual([0, 0, 1, 1, 2, 2, 0])
    expect(travelFrame(action, -1)).toBe(0)
    expect(travelFrame(action, NaN)).toBe(0)
  })

  it('uses every frame in long walking sequences instead of limiting them to four poses', () => {
    const long: PackAction = {
      frames: Array.from({ length: 8 }, (_, index) => String(index)),
      frame_ms: 100,
      loop: true,
    }
    expect(Array.from({ length: 8 }, (_, index) => travelFrame(long, travel(index * 100 + 1)))).toEqual([
      0, 1, 2, 3, 4, 5, 6, 7,
    ])
  })

  it('bounds physical phases and divides a shared native jump into ascent and descent', () => {
    expect([-1, 0, 0.34, 0.99, 1, 2].map(phase => phaseFrame(action, phase))).toEqual([0, 0, 1, 2, 2, 2])
    expect(airborneFramePhase('jumping', 'jump', 0)).toBe(0)
    expect(airborneFramePhase('jumping', 'jump', 1)).toBe(0.5)
    expect(airborneFramePhase('jumping', 'fall', 0)).toBe(0.5)
    expect(airborneFramePhase('jumping', 'fall', 1)).toBe(1)
    expect(airborneFramePhase('fall', 'fall', 0.4)).toBe(0.4)
    expect(airborneFramePhase('wave', 'jump', 0.4)).toBeUndefined()
  })

  it.each(['builtin-chibiterasu', 'builtin-nailong', 'builtin-kurisu'])(
    'uses existing jump, fall and landing sequences for %s without altering the pack',
    key => {
      const pack = BUILTIN_PACKS[key]
      const before = JSON.stringify(pack)
      expect(resolveStageAction(pack, 'jump').key).toBe('jump')
      expect(resolveStageAction(pack, 'fall').key).toBe('fall')
      expect(resolveStageAction(pack, 'sit').key).toBe('land')
      expect(JSON.stringify(pack)).toBe(before)
      expect(resolveStageAction(pack, 'sit', false, false, { 'stage.sit': 'idle' }).key).toBe('idle')
    },
  )

  it('retains standard Codex native actions and caps unusually long cycles', () => {
    const pack = buildCodexPetPack('fixture.png', 1536, 2288).pack
    expect(resolveStageAction(pack, 'jump').key).toBe('jumping')
    expect(resolveStageAction(pack, 'fall').key).toBe('jumping')
    expect(stageCycleDuration(pack, 'wave')).toBeGreaterThan(0)
    expect(stageCycleDuration(pack, 'wave', { 'stage.wave': 'idle' })).toBeUndefined()
    const slow = { ...pack, actions: { ...pack.actions, wave: { ...action, frame_ms: MAX_ACTION_CYCLE_MS } } }
    delete slow.actions.wave.frame_durations
    expect(stageCycleDuration(slow, 'wave')).toBeUndefined()
  })
})
