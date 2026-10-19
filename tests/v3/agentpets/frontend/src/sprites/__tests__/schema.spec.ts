import { describe, expect, it } from 'vitest'

import builtinJson from '@/assets/packs/projector-cat/pack.json'
import legacyJson from '@tests/../fixtures/legacy-codex-v2.json'
import {
  buildCodexPetPack,
  BUILTIN_PACK,
  builtinAsset,
  framePosition,
  HOST_ACTIONS,
  resolveAction,
  validatePack,
  withCodexStageActions,
} from '@/sprites/schema'

const minimal = {
  name: '测试',
  grid: { cols: 2, rows: 2 },
  frames: { idle: 0, talk: 1, think: 3 },
  actions: { idle: ['idle'], speaking: { frames: ['talk', 'idle'], frame_ms: 200, loop: true } },
}

describe('sprite pack schema', () => {
  it.each([
    null,
    [],
    'idle',
    { missing: 0.8 },
    { idle: true },
    { idle: -0.1 },
    { idle: 1.1 },
    { idle: NaN },
    { idle: '0.8' },
    { idle: 0 },
  ])('rejects invalid action baselines %j', action_baselines => {
    expect(validatePack({ ...minimal, id: 'builtin-nailong', action_baselines }).errors.length).toBeGreaterThan(0)
  })
  it('retains explicit per-action baselines without changing legacy pack defaults', () => {
    expect(validatePack(minimal).pack?.action_baselines).toBeUndefined()
    expect(
      validatePack({ ...minimal, id: 'builtin-nailong', action_baselines: { idle: 0.87654 } }).pack?.action_baselines,
    ).toEqual({
      idle: 0.8765,
    })
    expect(validatePack({ ...minimal, id: 'custom', action_baselines: { idle: 0.8 } }).errors).toContain(
      'action_baselines 仅供内置逐帧形象使用',
    )
  })
  it('accepts the builtin pack and only uses host actions for random actions', () => {
    expect(validatePack(builtinJson).errors).toEqual([])
    expect(BUILTIN_PACK.grid).toEqual({ cols: 4, rows: 2 })
    expect(Object.keys(BUILTIN_PACK.frames)).toEqual([
      'idle',
      'blink',
      'talk',
      'think',
      'jump',
      'wave',
      'sleep',
      'confused',
    ])
    for (const name of BUILTIN_PACK.random_actions) expect(HOST_ACTIONS).toContain(name)
    for (const name of HOST_ACTIONS) {
      if (name !== 'disassemble' && name !== 'charge') expect(BUILTIN_PACK.actions[name]).toBeDefined()
    }
  })

  it('normalizes shorthand actions', () => {
    const { pack, errors } = validatePack(JSON.stringify(minimal))
    expect(errors).toEqual([])
    expect(pack?.actions.idle).toEqual({ frames: ['idle'], frame_ms: 160, loop: false })
  })

  it('converts Codex Pet v1 and v2 sheets into valid AgentPets packs', () => {
    const v1 = buildCodexPetPack('Kurisu.png', 1536, 1872)
    expect(v1.version).toBe('v1')
    expect(v1.pack).toMatchObject({
      id: 'kurisu',
      name: 'Kurisu',
      grid: { cols: 8, rows: 9 },
    })
    expect(Object.keys(v1.pack.frames as object)).toHaveLength(57)
    expect(validatePack(v1.pack).errors).toEqual([])

    const v2 = buildCodexPetPack('C:\\Pets\\Kurisu v2.webp', 1536, 2288)
    const validation = validatePack(v2.pack)
    expect(v2.version).toBe('v2')
    expect(validation.errors).toEqual([])
    expect(v2.pack).toMatchObject({
      id: 'kurisu-v2',
      grid: { cols: 8, rows: 11 },
    })
    expect((v2.pack.frames as Record<string, number>)['look-000']).toBe(72)
    expect((v2.pack.frames as Record<string, number>)['look-337-5']).toBe(87)
    expect(validation.pack?.actions.scan.frames).toHaveLength(17)
    expect(validation.pack?.actions.scan.frames[16]).toBe('look-000')
    expect(validation.pack?.actions.thinking.frames[0]).toBe('waiting-1')
    expect(validation.pack?.actions.error.frames[0]).toBe('failed-1')
  })

  it('uses Codex Pet manifest metadata when generating a pack', () => {
    const result = buildCodexPetPack('spritesheet.webp', 1536, 1872, {
      id: 'cute-rem',
      displayName: 'Cute Rem',
      description: 'A community pet',
    })

    expect(result.pack).toMatchObject({ id: 'cute-rem', name: 'Cute Rem', description: 'A community pet' })
    expect(validatePack(result.pack).errors).toEqual([])
  })

  it('rejects unsupported Codex Pet sheet dimensions', () => {
    expect(() => buildCodexPetPack('pet.png', 512, 512)).toThrow('只支持 Codex Pet v1')
  })

  it('reports structural errors', () => {
    expect(validatePack('{').errors[0]).toContain('解析失败')
    expect(validatePack({ ...minimal, frames: { talk: 0 } }).errors).toContain('frames 必须包含 idle 帧')
    expect(validatePack({ ...minimal, frames: { idle: 4 } }).errors[0]).toContain('frames.idle')
    expect(validatePack({ ...minimal, actions: { x: ['missing'] } }).errors[0]).toContain('未定义的帧')
    expect(validatePack({ ...minimal, random_actions: ['dance'] }).errors[0]).toContain('不是宿主动作名')
  })

  it('resolves action, then intent, then thinking, then idle', () => {
    const pack = validatePack(minimal).pack!
    expect(resolveAction(pack, 'speaking', 'idle', false).key).toBe('speaking')
    expect(resolveAction(pack, 'wave', 'speaking', false).key).toBe('speaking')
    expect(resolveAction(pack, null, 'success', false).key).toBe('idle')
    expect(resolveAction(BUILTIN_PACK, null, 'docked', true).key).toBe('docked')
    expect(resolveAction(BUILTIN_PACK, 'charge', 'reaction', true).key).toBe('reaction')
    expect(resolveAction({ ...pack, actions: {} }, null, 'idle', false).action.frames).toEqual(['idle'])
  })

  it('maps frames to sprite sheet positions', () => {
    const pack = validatePack(minimal).pack!
    expect(framePosition(pack, 'idle')).toEqual({ x: 0, y: 0 })
    expect(framePosition(pack, 'think')).toEqual({ x: 100, y: 100 })
    expect(framePosition(BUILTIN_PACK, 'sleep')).toEqual({ x: (2 / 3) * 100, y: 100 })
    expect(builtinAsset('sheet.webp', 'https://h/plugin/file/x/frontend/dist/assets/a.js')).toBe(
      'https://h/plugin/file/x/frontend/dist/assets/packs/projector-cat/sheet.webp',
    )
  })
})

describe('Codex stage compatibility', () => {
  it('retains v1 and v2 markers through frontend validation', () => {
    for (const height of [1872, 2288]) {
      const generated = buildCodexPetPack('pet.png', 1536, height)
      expect(validatePack(generated.pack).pack?.codex_version).toBe(generated.version)
    }
    expect(validatePack({ ...minimal, codex_version: 'v2' }).errors.join()).toContain('网格不匹配')
    expect(validatePack({ ...minimal, codex_version: 'v3' }).errors.join()).toContain('只支持')
  })

  it('fills directional runs for the legacy pack while preserving its custom actions', () => {
    const legacy = validatePack({ ...legacyJson, codex_version: 'v2' }).pack!
    const before = JSON.stringify(legacy)
    const completed = withCodexStageActions(legacy)
    expect(completed.actions.thinking).toEqual(legacy.actions.thinking)
    expect(completed.frames.thinking).toBe(43)
    expect(completed.actions.wave).toEqual(legacy.actions.wave)
    expect(completed.actions['running-right'].frames.map(name => completed.frames[name])).toEqual([
      8, 9, 10, 11, 12, 13, 14, 15,
    ])
    expect(completed.actions['running-left'].frames.map(name => completed.frames[name])).toEqual([
      16, 17, 18, 19, 20, 21, 22, 23,
    ])
    expect(completed.actions.speaking.frames.map(name => completed.frames[name])).toEqual([56, 57, 58, 59, 60, 61])
    expect(JSON.stringify(legacy)).toBe(before)
    expect(validatePack(completed).errors).toEqual([])
    expect(withCodexStageActions(BUILTIN_PACK)).toBe(BUILTIN_PACK)
  })
})
