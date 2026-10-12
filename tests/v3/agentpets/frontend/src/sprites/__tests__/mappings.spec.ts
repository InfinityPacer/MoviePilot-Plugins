import { describe, expect, it } from 'vitest'
import { buildCodexPetPack, resolveAction, validatePack, withCodexStageActions } from '@/sprites/schema'
import { nativeChoices, stageAction } from '@/sprites/mappings'

function pack(version: 'v1' | 'v2' = 'v1') {
  return validatePack(buildCodexPetPack('Rem', 1536, version === 'v1' ? 1872 : 2288).pack).pack!
}
describe('native animations and independent mappings', () => {
  it('keeps nine native animations while preserving aliases and v2 directions', () => {
    const v1 = pack()
    expect(nativeChoices(v1)).toHaveLength(9)
    expect(v1.actions.success.frames).toEqual(v1.actions.jumping.frames)
    const v2 = pack('v2')
    expect(nativeChoices(v2)).toHaveLength(10) // nine native rows plus scan
    expect(Object.keys(v2.actions).filter(key => key.startsWith('look-'))).toHaveLength(16)
    expect(v2.frames[v2.actions['look-337-5'].frames[0]]).toBe(87)
  })
  it('applies per-trigger overrides but bypasses them for native previews and reset drafts', () => {
    const original = pack()
    original.action_mappings = { 'stage.think': 'review', 'action.wave': 'failed', 'intent.thinking': 'running' }
    expect(resolveAction(original, 'thinking', 'idle', false, { mappingKey: 'stage.think' }).key).toBe('review')
    expect(resolveAction(original, 'wave', 'idle', false).key).toBe('failed')
    expect(resolveAction(original, null, 'thinking', false).key).toBe('running')
    expect(
      resolveAction(original, 'thinking', 'idle', false, { mappingKey: 'stage.think', nativeAction: 'waiting' }).key,
    ).toBe('waiting')
    expect(resolveAction(original, 'thinking', 'idle', false, { mappingKey: 'stage.think', mappings: {} }).key).toBe(
      'thinking',
    )
    expect(original.actions.thinking.frames).toEqual(original.actions.waiting.frames)
  })
  it('preserves custom actions when completing legacy packs and routes movement by direction', () => {
    const original = pack('v2')
    original.actions.wave = { frames: ['idle'], frame_ms: 500, loop: false }
    const completed = withCodexStageActions(original)
    expect(completed.actions.wave).toEqual(original.actions.wave)
    expect(completed.actions.waving.frames).toHaveLength(4)
    expect(stageAction('walk2', true)).toEqual({ key: 'stage.walk-left', action: 'running-left' })
    expect(stageAction('held', false).key).toBe('stage.held')
  })
})
