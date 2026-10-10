import { describe, expect, it } from 'vitest'

import { eventPose, frameUrl, phasePose, POSES, resolvePose, type PoseInput } from '@/stage/poses'
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
    expect(POSES).toHaveLength(16)
    expect(frameUrl('idle', 'https://host/api/v1/plugin/file/agentpetying/frontend/dist/assets/x.js')).toBe(
      'https://host/api/v1/plugin/file/agentpetying/frontend/dist/assets/ying/idle.webp',
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
    expect(resolvePose({ ...base, dozing: true })).toBe('doze')
    expect(resolvePose({ ...base, blinking: true })).toBe('blink')
  })

  it('clamps settings into the supported range', () => {
    expect(normalizeSettings({ scale: 9, speed: 'x' })).toEqual({
      scale: 1.6,
      speed: 1,
    })
    expect(normalizeSettings(null)).toEqual({ scale: 1, speed: 1 })
  })
})
