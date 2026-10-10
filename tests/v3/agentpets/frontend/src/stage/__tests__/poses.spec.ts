import { describe, expect, it } from 'vitest'

import {
  eventPose,
  frameUrl,
  phasePose,
  POSES,
  resolvePose,
  WALK_CYCLE,
  walkFrame,
  type PoseInput,
} from '@/stage/poses'
import { normalizeSettings } from '@/stage/settings'

const base: PoseInput = {
  motion: 'idle',
  walkPhase: 0,
  transient: null,
  sustained: null,
  dozing: false,
  blinking: false,
}

describe('ying poses', () => {
  it('declares every frame named by the contract', () => {
    expect(POSES).toHaveLength(18)
    expect(POSES).toEqual(expect.arrayContaining(['walk1', 'walk2', 'walk3', 'walk4']))
    expect(frameUrl('idle', 'https://host/api/v1/plugin/file/agentpets/frontend/dist/assets/x.js')).toBe(
      'https://host/api/v1/plugin/file/agentpets/frontend/dist/assets/ying/idle.webp',
    )
  })

  it('maps host phases and events to actions', () => {
    expect(phasePose('thinking')).toBe('think')
    expect(phasePose('tool')).toBe('busy')
    expect(phasePose('awaiting')).toBe('alert')
    expect(phasePose('done')).toBeNull()
    expect(eventPose('agent.done')?.pose).toBe('victory')
    expect(eventPose('agent.error')?.pose).toBe('confused')
    expect(eventPose('agent.preview')?.pose).toBe('talk')
    expect(eventPose('agent.bubble')?.pose).toBe('talk')
    expect(eventPose('agent.tool.start')).toBeNull()
  })

  it('lets physical state win over event actions', () => {
    expect(resolvePose({ ...base, motion: 'drag', transient: 'victory' })).toBe('held')
    expect(resolvePose({ ...base, motion: 'fall' })).toBe('fall')
    expect(resolvePose({ ...base, transient: 'talk', sustained: 'think' })).toBe('talk')
    expect(resolvePose({ ...base, sustained: 'think', dozing: true })).toBe('think')
    expect(resolvePose({ ...base, motion: 'walk', walkPhase: 1 })).toBe('walk2')
    expect(resolvePose({ ...base, motion: 'walk', walkPhase: 3 })).toBe('walk4')
    expect(resolvePose({ ...base, motion: 'fall', rising: true })).toBe('jump')
    expect(resolvePose({ ...base, dozing: true })).toBe('doze')
    expect(resolvePose({ ...base, blinking: true })).toBe('blink')
  })

  it('clamps settings into the supported range', () => {
    expect(normalizeSettings({ scale: 9, speed: 'x', roam: 'moon' })).toEqual({
      scale: 1.6,
      speed: 1,
      roam: 'surfaces',
    })
    expect(normalizeSettings({ roam: 'free' }).roam).toBe('free')
    expect(normalizeSettings(null)).toEqual({ scale: 1, speed: 1, roam: 'surfaces' })
  })

  it('advances the four-frame walk cycle by distance, not time', () => {
    expect(WALK_CYCLE).toEqual(['walk1', 'walk2', 'walk3', 'walk4'])
    // 身高 100 时每帧 14px：同样走 56px，无论用时多久都恰好走完一个循环。
    expect([0, 13, 14, 28, 42, 56].map(distance => walkFrame(distance, 100))).toEqual([0, 0, 1, 2, 3, 0])
    // 角色变大步子变大，同样距离推进的帧更少。
    expect(walkFrame(28, 200)).toBe(1)
  })
})
