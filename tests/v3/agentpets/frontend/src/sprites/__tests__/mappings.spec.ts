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

  it.each([
    ['v1', 0],
    ['v2', 0],
  ] as const)('uses a neutral level-gaze peek for new %s imports', (version, frame) => {
    const imported = pack(version)
    expect(imported.frames[imported.actions.peek.frames[0]]).toBe(frame)
    expect(imported.actions.peek.frames).toHaveLength(1)
    expect(stageAction('alert', true, true)).toEqual(stageAction('alert', false, true))
  })

  it.each(['v1', 'v2'] as const)('repairs the old generated %s peek only in the display copy', version => {
    const original = pack(version)
    const oldFrame = version === 'v2' ? 'look-270' : original.actions.review.frames[0]
    original.actions.peek = { frames: [oldFrame], frame_ms: 160, loop: false }
    const snapshot = JSON.stringify(original)
    const completed = withCodexStageActions(original)
    expect(completed.frames[completed.actions.peek.frames[0]]).toBe(0)
    expect(JSON.stringify(original)).toBe(snapshot)
  })

  it('replaces the interim upward-gaze alias without changing explicit gaze mappings', () => {
    const original = pack('v2')
    original.actions.peek = { frames: ['look-000'], frame_ms: 160, loop: false }
    const completed = withCodexStageActions(original)
    expect(completed.frames[completed.actions.peek.frames[0]]).toBe(0)
    expect(original.actions.peek.frames).toEqual(['look-000'])
    expect(
      resolveAction(completed, 'peek', 'idle', false, {
        mappingKey: 'stage.peek',
        mappings: { 'stage.peek': 'look-000' },
      }).key,
    ).toBe('look-000')
  })

  it('preserves customized peek frames and explicit mappings instead of forcing a new direction', () => {
    const original = pack('v2')
    original.actions.peek = { frames: ['look-270', 'look-180'], frame_ms: 160, loop: false }
    expect(withCodexStageActions(original).actions.peek).toEqual(original.actions.peek)
    original.actions.peek = { frames: ['look-270'], frame_ms: 160, loop: false }
    original.action_mappings = { 'stage.peek': 'peek' }
    expect(withCodexStageActions(original).actions.peek).toEqual(original.actions.peek)
    original.action_mappings = { 'stage.peek': 'look-180' }
    const completed = withCodexStageActions(original)
    expect(resolveAction(completed, 'peek', 'idle', false, { mappingKey: 'stage.peek' }).key).toBe('look-180')
  })

  it('falls back to neutral idle rather than a directional gaze when peek is missing', () => {
    const original = pack('v2')
    delete original.actions.peek
    expect(resolveAction(original, 'peek', 'idle', false).key).toBe('idle')
  })
})
