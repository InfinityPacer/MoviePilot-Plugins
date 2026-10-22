import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createMockHost, createMockPet } from '@/dev/mockHost'
import { registerEditor } from '@/editor/presence'
import AgentPet from '@/stage/AgentPet.vue'
import { ActivityPolicy } from '@/stage/activity'
import type { AgentRect } from '@/host'

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

async function setup(fixed = false, sleepLoaded = true, roam: 'free' | 'floor' = 'free', mobile = false) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-22T00:00:00Z'))
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  vi.stubGlobal('innerWidth', 1000)
  vi.stubGlobal('innerHeight', 800)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  host.patch({ isMobile: mobile })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) })
  await pet.storage!.set({ xRatio: 0.5, yRatio: 0.5 })
  const save = vi.spyOn(pet.storage!, 'set')
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam, movement: fixed ? 'fixed' : 'auto' },
    },
  })
  await flushPromises()
  for (const img of Array.from(view.container.querySelectorAll('img')))
    await fireEvent(img, new Event(img.dataset.pose === 'doze' && !sleepLoaded ? 'error' : 'load'))
  await advance(32)
  const stage = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const button = view.container.querySelector<HTMLButtonElement>('button')!
  return { host, pet, save, view, stage, button, anchors }
}

async function until(predicate: () => boolean, limit = 30_000) {
  for (let waited = 0; waited <= limit; waited += 50) {
    if (predicate()) return waited
    await advance(50)
  }
  throw new Error('activity condition did not become true')
}

async function pointer(target: Element | Window, type: string, x = 300, y = 300) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: x, clientY: y })
  Object.defineProperties(event, {
    pointerId: { value: 1 },
    pointerType: { value: 'mouse' },
    isPrimary: { value: true },
  })
  await fireEvent(target, event)
}

describe('stage autonomous activity episodes', () => {
  it('continues after a short pause and does not save autonomous routes', async () => {
    const pet = await setup()
    await until(() => pet.stage.dataset.motion === 'walk')
    await until(() => pet.stage.dataset.motion === 'idle')
    const firstEnd = Date.now()
    await until(() => pet.stage.dataset.motion === 'walk', 2000)
    expect(Date.now() - firstEnd).toBeLessThanOrEqual(1800)
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('explores nearby after an accepted long press instead of restarting the ordinary wait', async () => {
    const pet = await setup()
    const origin = { ...pet.anchors.at(-1)! }
    await pointer(pet.button, 'pointerdown')
    await advance(450)
    expect(pet.stage.dataset.reaction).toBe('wave')
    await pointer(window, 'pointerup')
    await until(() => !pet.stage.dataset.reaction, 2000)
    await until(() => pet.stage.dataset.motion === 'walk', 2000)
    await until(() => pet.stage.dataset.motion === 'idle')
    const next = pet.anchors.at(-1)!
    expect(Math.abs(next.x - origin.x)).toBeLessThanOrEqual(216)
    expect(Math.abs(next.y - origin.y)).toBeLessThanOrEqual(216)
  })

  it('does not promote a cancelled press into an interaction boost', async () => {
    const pet = await setup()
    await pointer(pet.button, 'pointerdown')
    await advance(200)
    await pointer(window, 'pointercancel')
    await advance(2000)
    expect(pet.stage.dataset.motion).toBe('idle')
    expect(pet.stage.dataset.reaction).toBeUndefined()
  })

  it('does not cross the mobile viewport just because the corner activity was selected', async () => {
    const pet = await setup(false, true, 'floor', true)
    const origin = { ...pet.anchors.at(-1)! }
    await advance(9967)
    vi.mocked(Math.random).mockReturnValueOnce(0.1).mockReturnValueOnce(0.1)
    await until(() => pet.stage.dataset.motion === 'walk', 1000)
    await until(() => pet.stage.dataset.motion === 'idle')
    const next = pet.anchors.at(-1)!
    expect(Math.abs(next.x - origin.x)).toBeLessThanOrEqual(origin.height * 0.9)
    expect(next.y + next.height).toBe(800)
  })

  it('discards continuation when work takes over and starts only a fresh interval afterwards', async () => {
    const pet = await setup()
    await until(() => pet.stage.dataset.motion === 'walk')
    await until(() => pet.stage.dataset.motion === 'idle')
    pet.host.patch({ phase: 'tool' })
    await advance(2000)
    expect(pet.stage.dataset.pose).toBe('busy')
    expect(pet.stage.dataset.motion).toBe('idle')
    pet.host.patch({ phase: 'idle' })
    await advance(2000)
    expect(pet.stage.dataset.motion).toBe('idle')
  })

  it.each(['blur', 'hidden', 'editor', 'unavailable', 'reduced-motion', 'viewport'])(
    'drops the old episode across %s and resumes with a fresh wait',
    async reason => {
      const pet = await setup()
      await until(() => pet.stage.dataset.motion === 'walk')
      await until(() => pet.stage.dataset.motion === 'idle')
      let resume = () => {}
      if (reason === 'blur') await fireEvent(window, new Event('blur'))
      if (reason === 'hidden') {
        pet.host.patch({ pageVisible: false })
        resume = () => pet.host.patch({ pageVisible: true })
      }
      if (reason === 'editor') {
        resume = registerEditor()
        editors.push(resume)
      }
      if (reason === 'unavailable') {
        pet.host.patch({ available: false })
        resume = () => pet.host.patch({ available: true })
      }
      if (reason === 'reduced-motion') {
        pet.host.patch({ motionAllowed: false })
        resume = () => pet.host.patch({ motionAllowed: true })
      }
      if (reason === 'viewport') await fireEvent(window, new Event('resize'))
      await advance(2000)
      expect(pet.stage.dataset.motion).toBe('idle')
      resume()
      await advance(2000)
      expect(pet.stage.dataset.motion).toBe('idle')
      await until(() => pet.stage.dataset.motion === 'walk', 14_000)
      pet.view.unmount()
      pet.host.dispose()
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it('ends a long walk at the episode deadline instead of extending it indefinitely', async () => {
    const pet = await setup()
    vi.stubGlobal('innerWidth', 4000)
    await fireEvent(window, new Event('resize'))
    await pet.view.rerender({ settingsOverride: { scale: 1, speed: 0.5, roam: 'free', movement: 'auto' } })
    vi.spyOn(ActivityPolicy.prototype, 'target').mockReturnValue({ x: 3000, y: 340 })
    await until(() => pet.stage.dataset.motion === 'walk')
    await advance(24_000)
    expect(pet.stage.dataset.motion).toBe('walk')
    await advance(1050)
    expect(pet.stage.dataset.motion).toBe('idle')
    await advance(2000)
    expect(pet.stage.dataset.motion).toBe('idle')
    expect(pet.save).not.toHaveBeenCalled()
  })

  it.each(['agent.panel.close', 'agent.thinking.end', 'agent.tool.end', 'agent.bubble'])(
    'starts a fresh activity interval after %s instead of remaining idle',
    async event => {
      const pet = await setup()
      await until(() => pet.stage.dataset.motion === 'walk')
      await until(() => pet.stage.dataset.motion === 'idle')
      pet.host.fire(event)
      await advance(2000)
      expect(pet.stage.dataset.motion).toBe('idle')
      await until(() => pet.stage.dataset.motion === 'walk', 14_000)
    },
  )

  it('resumes after activating an already-open panel without a new host event', async () => {
    const pet = await setup()
    pet.host.patch({ panelOpen: true })
    await fireEvent.click(pet.button)
    expect(pet.host.calls).toContain('open()')
    await until(() => pet.stage.dataset.motion === 'walk', 14_000)
  })

  it('explores around the final dropped position after responding and saves only the drop', async () => {
    const pet = await setup()
    const before = pet.anchors.at(-1)!
    await pointer(pet.button, 'pointerdown', before.x + 10, before.y + 10)
    await pointer(window, 'pointermove', 610, 460)
    await pointer(window, 'pointerup', 610, 460)
    expect(pet.stage.dataset.reaction).toBe('wave')
    const dropped = { ...pet.anchors.at(-1)! }
    const saveCount = pet.save.mock.calls.length
    expect(saveCount).toBe(1)
    await until(() => !pet.stage.dataset.reaction, 2000)
    await until(() => pet.stage.dataset.motion === 'walk', 2000)
    await until(() => pet.stage.dataset.motion === 'idle')
    const explored = pet.anchors.at(-1)!
    expect(Math.hypot(explored.x - dropped.x, explored.y - dropped.y)).toBeGreaterThan(0)
    expect(Math.abs(explored.x - dropped.x)).toBeLessThanOrEqual(216)
    expect(Math.abs(explored.y - dropped.y)).toBeLessThanOrEqual(216)
    expect(pet.save).toHaveBeenCalledTimes(saveCount)
  })

  it('resumes automatic exploration after resting without any external wake-up', async () => {
    const delay = vi.spyOn(ActivityPolicy.prototype, 'delay').mockReturnValue(91_000)
    const pet = await setup()
    await advance(90_000)
    expect(pet.stage.dataset.pose).toBe('doze')
    delay.mockRestore()
    await advance(6000)
    expect(pet.stage.dataset.pose).not.toBe('doze')
    await until(() => pet.stage.dataset.motion === 'walk', 14_000)
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('wakes itself after a short rest without host or pointer activity', async () => {
    const pet = await setup(true)
    await advance(90_000)
    expect(pet.stage.dataset.pose).toBe('doze')
    const position = pet.button.style.transform
    await advance(6000)
    expect(pet.stage.dataset.pose).not.toBe('doze')
    expect(pet.button.style.transform).toBe(position)
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('skips rest when its sleep artwork failed rather than freezing in a fallback frame', async () => {
    const pet = await setup(true, false)
    await advance(97_000)
    expect(pet.stage.dataset.pose).not.toBe('doze')
  })

  it('does not queue sleep behind a long-running working pose', async () => {
    const pet = await setup(true)
    pet.host.patch({ phase: 'thinking' })
    await advance(97_000)
    expect(pet.stage.dataset.pose).toBe('think')
    pet.host.patch({ phase: 'idle' })
    await advance(32)
    expect(pet.stage.dataset.pose).not.toBe('doze')
  })

  it('cancels a rest across editor pause and releases every timer on unmount', async () => {
    const pet = await setup(true)
    await advance(90_000)
    expect(pet.stage.dataset.pose).toBe('doze')
    const close = registerEditor()
    editors.push(close)
    await advance(10_000)
    expect(vi.getTimerCount()).toBe(0)
    close()
    await advance(32)
    expect(pet.stage.dataset.pose).not.toBe('doze')
    pet.view.unmount()
    pet.host.dispose()
    expect(vi.getTimerCount()).toBe(0)
  })
})
