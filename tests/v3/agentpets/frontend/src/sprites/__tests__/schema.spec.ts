import { describe, expect, it } from 'vitest'

import builtinJson from '@/assets/packs/projector-cat/pack.json'
import { BUILTIN_PACK, builtinAsset, framePosition, HOST_ACTIONS, resolveAction, validatePack } from '@/sprites/schema'

const minimal = {
  name: '测试',
  grid: { cols: 2, rows: 2 },
  frames: { idle: 0, talk: 1, think: 3 },
  actions: { idle: ['idle'], speaking: { frames: ['talk', 'idle'], frame_ms: 200, loop: true } },
}

describe('sprite pack schema', () => {
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
