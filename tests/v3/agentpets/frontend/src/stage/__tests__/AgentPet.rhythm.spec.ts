import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createMockHost, createMockPet } from '@/dev/mockHost'
import { BUILTIN_PACKS } from '@/sprites/schema'
import { registerEditor } from '@/editor/presence'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'

const hosts: ReturnType<typeof createMockHost>[] = []
const editors: Array<() => void> = []
afterEach(() => {
  editors.splice(0).forEach(close => close())
  hosts.splice(0).forEach(host => host.dispose())
})

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

async function setup(key = 'builtin-' + 'kurisu-z256', fixed = false) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-24T00:00:00Z'))
  vi.spyOn(Math, 'random').mockReturnValue(0.99)
  vi.stubGlobal('innerWidth', 1000)
  vi.stubGlobal('innerHeight', 800)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  const pet = createMockPet('stage', key)
  await pet.storage!.set({ xRatio: 0.5, yRatio: 0.5 })
  const save = vi.spyOn(pet.storage!, 'set')
  const pack = BUILTIN_PACKS[key] ?? { ...BUILTIN_PACKS['builtin-kurisu'], id: key }
  const api = {
    get: vi
      .fn()
      .mockResolvedValue({ success: true, data: { pack, sheet_src: 'fixture.png', calibration: pack.calibration } }),
    post: vi.fn(),
  }
  const view = render(AgentPetCodex, {
    props: {
      agent: host,
      pet,
      api,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: fixed ? 'fixed' : 'auto' },
    },
  })
  await flushPromises()
  await advance(32)
  const stage = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const sprite = view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
  return { view, host, pet, save, api, stage, sprite }
}

async function until(predicate: () => boolean, limit = 16_000) {
  for (let elapsed = 0; elapsed <= limit; elapsed += 32) {
    if (predicate()) return
    await advance(32)
  }
  throw new Error('rhythm condition did not become true')
}

describe('built-in character rhythm', () => {
  it('selects the existing scan sequence for z256 without saving or inventing directional artwork', async () => {
    const pet = await setup()
    await until(() => pet.sprite.dataset.action === 'scan')
    expect(pet.stage.dataset.motion).toBe('idle')
    expect(pet.stage.dataset.rhythm).toBe('scan')
    const firstFrame = pet.sprite.dataset.frame
    await advance(320)
    expect(pet.sprite.dataset.frame).not.toBe(firstFrame)
    await until(() => !pet.stage.dataset.rhythm, 1000)
    expect(pet.sprite.dataset.action).toBe('idle')
    expect(pet.save).not.toHaveBeenCalled()
    expect(pet.api.post).not.toHaveBeenCalled()
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([
    ['builtin-nailong', 'cheer'],
    ['builtin-chibiterasu', 'lie'],
    ['builtin-kurisu', 'relaxed-sit'],
  ])('plays the curated %s action %s rather than a fallback alias', async (key, action) => {
    const pet = await setup(key)
    await until(() => pet.stage.dataset.rhythm === action)
    expect(pet.sprite.dataset.action).toBe(action)
    const started = Date.now()
    await until(() => !pet.stage.dataset.rhythm, 4500)
    const elapsed = Date.now() - started
    expect(elapsed).toBeGreaterThanOrEqual(2100)
    expect(elapsed).toBeLessThan(4000)
    expect(pet.save).not.toHaveBeenCalled()
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it('walks between decorative actions and retains short multi-step continuation', async () => {
    const pet = await setup()
    await until(() => !!pet.stage.dataset.rhythm)
    await until(() => !pet.stage.dataset.rhythm, 2000)
    await until(() => pet.stage.dataset.motion === 'walk')
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    await until(() => pet.stage.dataset.motion === 'idle')
    const ended = Date.now()
    await until(() => pet.stage.dataset.motion === 'walk', 2000)
    expect(Date.now() - ended).toBeLessThanOrEqual(1832)
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.save).not.toHaveBeenCalled()
  })

  it.each(['thinking', 'tool', 'awaiting'] as const)('lets %s preempt a decorative action immediately', async phase => {
    const pet = await setup()
    await until(() => !!pet.stage.dataset.rhythm)
    pet.host.patch({ phase, thinking: phase === 'thinking' })
    await flushPromises()
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.stage.dataset.pose).toBe(phase === 'thinking' ? 'think' : phase === 'tool' ? 'busy' : 'alert')
    expect(pet.sprite.dataset.action).not.toBe('scan')
    await advance(4000)
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it('lets a drag take over without saving the interrupted decorative action', async () => {
    const pet = await setup()
    await until(() => !!pet.stage.dataset.rhythm)
    const pointer = (type: string, x: number) => {
      const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: 300 })
      Object.defineProperties(event, {
        pointerId: { value: 1 },
        pointerType: { value: 'mouse' },
        isPrimary: { value: true },
      })
      return event
    }
    await fireEvent(pet.view.getByRole('button'), pointer('pointerdown', 300))
    await fireEvent(window, pointer('pointermove', 340))
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.stage.dataset.motion).toBe('drag')
    expect(pet.stage.dataset.pose).toBe('held')
    expect(pet.save).not.toHaveBeenCalled()
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['hidden', 'reduced-motion', 'unavailable', 'blur', 'editor'])(
    'discards a decorative action on %s and never replays it on resume',
    async reason => {
      const pet = await setup()
      await until(() => !!pet.stage.dataset.rhythm)
      let resume = () => {}
      if (reason === 'hidden') {
        pet.host.patch({ pageVisible: false })
        resume = () => pet.host.patch({ pageVisible: true })
      }
      if (reason === 'reduced-motion') {
        pet.host.patch({ motionAllowed: false })
        resume = () => pet.host.patch({ motionAllowed: true })
      }
      if (reason === 'unavailable') {
        pet.host.patch({ available: false })
        resume = () => pet.host.patch({ available: true })
      }
      if (reason === 'blur') await fireEvent(window, new Event('blur'))
      if (reason === 'editor') {
        resume = registerEditor()
        editors.push(resume)
      }
      await flushPromises()
      expect(pet.stage.dataset.rhythm).toBeUndefined()
      await advance(3000)
      resume()
      await advance(2000)
      expect(pet.stage.dataset.rhythm).toBeUndefined()
      // Hiding retains the existing last-position save, but no rhythm state is persisted.
      expect(pet.save).toHaveBeenCalledTimes(reason === 'hidden' ? 1 : 0)
      pet.view.unmount()
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it('respects an explicit mapping change even during a native action', async () => {
    const pet = await setup()
    await until(() => pet.stage.dataset.rhythm === 'scan')
    await pet.view.rerender({ mappingsOverride: { 'stage.think': 'idle', 'stage.wave': 'idle' } })
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    await advance(16_000)
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it('gives real host feedback priority over an idle decorative action', async () => {
    const pet = await setup()
    await until(() => pet.stage.dataset.rhythm === 'scan')
    pet.host.fire('agent.done')
    await flushPromises()
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.stage.dataset.pose).toBe('victory')
    expect(pet.sprite.dataset.action).toBe('success')
    await advance(3000)
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it('keeps an accepted long press and its nearby exploration ahead of idle weighting', async () => {
    const pet = await setup()
    await until(() => pet.stage.dataset.rhythm === 'scan')
    const event = (type: string) => {
      const value = new MouseEvent(type, { bubbles: true, button: 0, clientX: 300, clientY: 300 })
      Object.defineProperties(value, {
        pointerId: { value: 1 },
        pointerType: { value: 'touch' },
        isPrimary: { value: true },
      })
      return value
    }
    await fireEvent(pet.view.getByRole('button'), event('pointerdown'))
    await advance(450)
    await fireEvent(window, event('pointerup'))
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.stage.dataset.reaction).toBe('wave')
    await until(() => !pet.stage.dataset.reaction, 2000)
    await until(() => pet.stage.dataset.motion === 'walk', 2000)
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.save).not.toHaveBeenCalled()
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it('does not add decorative behavior to fixed positions, previews or imported packs', async () => {
    const pet = await setup('builtin-kurisu', true)
    await advance(30_000)
    expect(pet.stage.dataset.rhythm).toBeUndefined()
    expect(pet.stage.dataset.motion).toBe('idle')
    pet.view.unmount()
    const imported = await setup('imported-rhythm-fixture')
    await advance(16_000)
    expect(imported.stage.dataset.rhythm).toBeUndefined()
    imported.view.unmount()
    const preview = await setup('builtin-kurisu')
    const root = document.createElement('div')
    root.getBoundingClientRect = () => new DOMRect(0, 0, 800, 600)
    await preview.view.rerender({ previewRoot: root, nativeAction: 'cheer' })
    await advance(16_000)
    expect(preview.stage.dataset.rhythm).toBeUndefined()
    expect(preview.sprite.dataset.action).toBe('cheer')
    preview.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
