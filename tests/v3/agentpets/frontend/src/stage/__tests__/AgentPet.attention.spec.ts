import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { h } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import { registerEditor } from '@/editor/presence'
import type { AgentRect } from '@/host'

const hosts: ReturnType<typeof createMockHost>[] = []
const editors: Array<() => void> = []

afterEach(() => {
  editors.splice(0).forEach(close => close())
  hosts.splice(0).forEach(host => host.dispose())
})

async function setup(directions = true, previewRoot: HTMLElement | null = null) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-22T00:00:00Z'))
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  host.patch({ isMobile: false })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'attention', { onAnchor: rect => anchors.push(rect) })
  const save = vi.spyOn(pet.storage, 'set')
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      lookDirections: directions,
      aspectRatio: 0.8,
      previewRoot,
      settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: 'fixed' },
    },
    slots: { default: ({ gazeAction }: { gazeAction?: string }) => h('span', { 'data-native-look': gazeAction }) },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(32)
  const root = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const button = view.getByRole('button')
  const rect = () => anchors.at(-1)!
  const point = (side: 'right' | 'left' | 'up' = 'right') => {
    const r = rect()
    return side === 'right'
      ? { x: r.x + r.width + 30, y: r.y + r.height / 2 }
      : side === 'left'
        ? { x: r.x - 30, y: r.y + r.height / 2 }
        : { x: r.x + r.width / 2, y: r.y - 30 }
  }
  const inside = () => {
    const r = rect()
    return { x: r.x + r.width * 0.8, y: r.y + r.height / 2 }
  }
  async function pointer(type: string, p = point(), kind = 'mouse', target: Element | Window = window, extra = {}) {
    const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: p.x, clientY: p.y })
    Object.defineProperties(event, {
      pointerId: { value: 1 },
      pointerType: { value: kind },
      isPrimary: { value: true },
      ...Object.fromEntries(Object.entries(extra).map(([key, value]) => [key, { value }])),
    })
    await fireEvent(target, event)
  }
  async function advance(ms: number) {
    await vi.advanceTimersByTimeAsync(ms)
    await flushPromises()
  }
  return {
    host,
    pet,
    save,
    view,
    root,
    button,
    rect,
    point,
    inside,
    pointer,
    advance,
    gaze: () => root.dataset.gaze,
    attention: () => root.dataset.attention,
    pose: () => root.dataset.pose,
  }
}

describe('stage nearby attention', () => {
  it('waits 350ms, looks at the pointer without moving, and does not loop for a stationary pointer', async () => {
    const pet = await setup()
    const position = pet.button.style.transform
    await pet.pointer('pointermove')
    await pet.advance(349)
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1)
    expect(pet.gaze()).toBe('look-090')
    expect(pet.attention()).toBe('mouse')
    expect(pet.button.style.transform).toBe(position)
    await pet.advance(1200)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointermove')
    await pet.advance(10000)
    expect(pet.gaze()).toBeUndefined()
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('rejects a fast pass and restarts dwell after pointer movement above 8px', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(200)
    const near = pet.point()
    await pet.pointer('pointermove', { x: near.x + 10, y: near.y })
    await pet.advance(349)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointermove', { x: 0, y: 0 })
    await pet.advance(1000)
    expect(pet.gaze()).toBeUndefined()
  })

  it('updates only an active gaze with rate limiting and resets on leaving the viewport', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
    await pet.pointer('pointermove', pet.point('up'))
    expect(pet.gaze()).toBe('look-090')
    await pet.advance(120)
    await pet.pointer('pointermove', pet.point('up'))
    expect(pet.gaze()).toBe('look-000')
    await fireEvent(window, new MouseEvent('pointerout', { relatedTarget: null }))
    expect(pet.gaze()).toBeUndefined()
  })

  it('waves at low frequency without directional art and never invents a look frame', async () => {
    const pet = await setup(false)
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.pose()).toBe('wave')
    expect(pet.attention()).toBe('mouse')
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1200)
    expect(pet.attention()).toBeUndefined()
  })

  it.each(['touch', 'pen'])('does not use %s pointer movement as desktop hover', async kind => {
    const pet = await setup()
    await pet.pointer('pointermove', pet.point(), kind)
    await pet.advance(1000)
    expect(pet.gaze()).toBeUndefined()
  })

  it('ignores pressed buttons, non-primary pointers and compatibility mouse movement on mobile', async () => {
    const pet = await setup()
    await pet.pointer('pointermove', pet.point(), 'mouse', window, { buttons: 1 })
    await pet.advance(400)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointermove', pet.point(), 'mouse', window, { isPrimary: false })
    await pet.advance(400)
    expect(pet.gaze()).toBeUndefined()
    pet.host.patch({ isMobile: true })
    await pet.pointer('pointermove')
    await pet.advance(400)
    expect(pet.gaze()).toBeUndefined()
  })

  it.each(['busy', 'hidden', 'reduced', 'editor', 'blur'] as const)(
    'cleans a pending dwell when %s interrupts and does not replay it',
    async cause => {
      const pet = await setup()
      await pet.pointer('pointermove')
      await pet.advance(200)
      if (cause === 'busy') pet.host.patch({ phase: 'thinking', thinking: true })
      if (cause === 'hidden') pet.host.patch({ pageVisible: false })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: false, reducedMotion: true })
      if (cause === 'editor') editors.push(registerEditor())
      if (cause === 'blur') await fireEvent(window, new Event('blur'))
      await pet.advance(1000)
      expect(pet.gaze()).toBeUndefined()
      if (cause === 'busy') pet.host.patch({ phase: 'idle', thinking: false })
      if (cause === 'hidden') pet.host.patch({ pageVisible: true })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: true, reducedMotion: false })
      if (cause === 'editor') editors.pop()!()
      await pet.advance(1000)
      expect(pet.gaze()).toBeUndefined()
    },
  )

  it('never overrides host completion feedback and releases timers when unmounted', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    pet.host.fire('agent.done')
    await flushPromises()
    expect(pet.gaze()).toBeUndefined()
    expect(pet.pose()).toBe('victory')
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBeUndefined()
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('shares a cooldown with long presses instead of repeatedly greeting on reentry', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.pointer('pointermove', { x: 0, y: 0 })
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointerdown', pet.inside(), 'mouse', pet.button)
    await pet.advance(450)
    expect(pet.root.dataset.reaction).toBeUndefined()
    await pet.pointer('pointerup', pet.inside())
  })

  it('clears a gaze when direction capability is removed and ignores contained previews', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.view.rerender({ lookDirections: false })
    expect(pet.gaze()).toBeUndefined()
    pet.view.unmount()
    const preview = document.createElement('div')
    const next = await setup(true, preview)
    await next.pointer('pointermove')
    await next.advance(350)
    expect(next.gaze()).toBeUndefined()
  })

  it('does not replay attention or pass it to another pet after an instance/key switch', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
    await pet.view.rerender({ pluginId: 'Clone2', pet: createMockPet('stage', 'another') })
    await flushPromises()
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1200)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
  })

  it('ends gaze on a page click and leaves normal keyboard-style clicks available', async () => {
    const pet = await setup()
    const open = vi.spyOn(pet.host, 'open')
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.pointer('pointerdown', { x: 0, y: 0 })
    expect(pet.gaze()).toBeUndefined()
    await fireEvent.click(pet.button, { detail: 0 })
    expect(open).toHaveBeenCalledTimes(1)
  })
})

describe('stage touch attention', () => {
  it('briefly looks at a touch point without swallowing the original short click', async () => {
    const pet = await setup()
    const open = vi.spyOn(pet.host, 'open')
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    expect(pet.gaze()).toBe('look-090')
    expect(pet.attention()).toBe('touch')
    await pet.advance(100)
    await pet.pointer('pointerup', pet.inside(), 'touch')
    await fireEvent.click(pet.button, { detail: 1 })
    expect(open).toHaveBeenCalledTimes(1)
    expect(pet.gaze()).toBeUndefined()
  })

  it('lets a 450ms touch hold replace the uncommitted gaze with the first wave', async () => {
    const pet = await setup()
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    expect(pet.gaze()).toBe('look-090')
    await pet.advance(450)
    expect(pet.gaze()).toBeUndefined()
    expect(pet.root.dataset.reaction).toBe('wave')
    await pet.pointer('pointerup', pet.inside(), 'touch')
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('does not consume a cancelled touch preview or retain it when a drag starts', async () => {
    const pet = await setup()
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    await pet.pointer('pointercancel', pet.inside(), 'touch')
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    expect(pet.gaze()).toBe('look-090')
    const point = pet.inside()
    await pet.pointer('pointermove', { x: point.x + 6, y: point.y }, 'touch')
    expect(pet.gaze()).toBeUndefined()
    expect(pet.root.dataset.motion).toBe('drag')
    await pet.pointer('pointercancel', point, 'touch')
  })

  it('does not invent touch gaze for v1 or let a second pointer replace an active gesture', async () => {
    const pet = await setup(false)
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointercancel', pet.inside(), 'touch')
    await pet.view.rerender({ lookDirections: true })
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    await pet.pointer('pointerdown', pet.point('left'), 'touch', pet.button, { pointerId: 2, isPrimary: false })
    expect(pet.gaze()).toBe('look-090')
    await pet.pointer('pointercancel', pet.inside(), 'touch')
  })

  it('commits only a released short touch and preserves the next explicit wave', async () => {
    const pet = await setup()
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    await pet.advance(100)
    await pet.pointer('pointerup', pet.inside(), 'touch')
    expect(pet.gaze()).toBe('look-090')
    await pet.advance(700)
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointercancel', pet.inside(), 'touch')
    await pet.advance(6000)
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    await pet.advance(450)
    expect(pet.root.dataset.reaction).toBe('wave')
    await pet.pointer('pointerup', pet.inside(), 'touch')
  })
})
