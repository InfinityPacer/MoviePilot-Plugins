import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { registerEditor } from '@/editor/presence'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import AgentPet from '@/stage/AgentPet.vue'

type PointerKind = 'mouse' | 'touch'

interface PointerOptions {
  id?: number
  kind?: PointerKind
  primary?: boolean
  x?: number
  y?: number
  detail?: number
}

interface SetupOptions {
  key?: string
  pluginId?: string
  previewRoot?: HTMLElement | null
  movement?: 'auto' | 'fixed'
  roam?: 'free' | 'floor' | 'surfaces'
  stored?: unknown
}

class TestPointerEvent extends MouseEvent {
  readonly pointerId: number
  readonly pointerType: PointerKind
  readonly isPrimary: boolean

  constructor(type: string, options: PointerOptions = {}) {
    super(type, {
      bubbles: true,
      cancelable: true,
      button: 0,
      clientX: options.x ?? 120,
      clientY: options.y ?? 160,
      detail: options.detail ?? 0,
    })
    this.pointerId = options.id ?? 1
    this.pointerType = options.kind ?? 'mouse'
    this.isPrimary = options.primary ?? true
  }
}

const hosts: Array<ReturnType<typeof createMockHost>> = []
const editorReleases: Array<() => void> = []
const fixtureNodes: Element[] = []

afterEach(() => {
  for (const release of editorReleases.splice(0)) release()
  for (const host of hosts.splice(0)) host.dispose()
  for (const node of fixtureNodes.splice(0)) node.remove()
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
})

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

async function firePointer(target: Element | Window, type: string, options: PointerOptions = {}) {
  await fireEvent(target, new TestPointerEvent(type, options))
}

async function clickPointer(target: Element, options: PointerOptions = {}) {
  await fireEvent(target, new TestPointerEvent('click', { ...options, detail: options.detail ?? 1 }))
}

async function longPress(button: HTMLElement, options: PointerOptions = {}) {
  await firePointer(button, 'pointerdown', options)
  await advance(450)
  await firePointer(window, 'pointerup', options)
  await flushPromises()
}

async function setup(options: SetupOptions = {}) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-22T00:00:00Z'))
  vi.spyOn(Math, 'random').mockReturnValue(0.5)

  const pluginId = options.pluginId ?? 'AgentPets'
  const host = createMockHost(pluginId)
  hosts.push(host)
  const interacting: boolean[] = []
  const anchors: Array<{ x: number; y: number; width: number; height: number } | null> = []
  const pet = createMockPet('stage', options.key ?? 'ying', {
    onAnchor: rect => anchors.push(rect),
    onInteracting: value => interacting.push(value),
  })
  if ('stored' in options) await pet.storage.set(options.stored)
  const api = {
    get: vi.fn().mockResolvedValue({ success: true, data: { scale: 1, speed: 1 } }),
  }
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      api,
      pluginId,
      previewRoot: options.previewRoot ?? null,
      settingsOverride: {
        movement: options.movement ?? 'fixed',
        roam: options.roam ?? 'free',
        scale: 1,
        speed: 1,
      },
    },
  })
  await flushPromises()
  await advance(1)
  const button = view.container.querySelector<HTMLButtonElement>('button')
  if (!button) throw new Error('AgentPet button did not render')
  const root = () => view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  return {
    host,
    pet,
    view,
    button,
    interacting,
    anchors,
    root,
    reaction: () => root().dataset.reaction,
    motion: () => root().dataset.motion,
    pose: () => root().dataset.pose,
  }
}

function addFixture(
  tag: 'div' | 'button',
  className: string,
  rect: { left: number; top: number; width: number; height: number },
) {
  const node = document.createElement(tag)
  node.className = className
  node.getBoundingClientRect = () =>
    ({
      ...rect,
      x: rect.left,
      y: rect.top,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      toJSON: () => rect,
    }) as DOMRect
  document.body.appendChild(node)
  fixtureNodes.push(node)
  return node
}

describe('AgentPet interaction gestures', () => {
  it('recognizes one long press at the 450ms boundary and suppresses its compatibility click', async () => {
    const pet = await setup()
    const open = vi.spyOn(pet.host, 'open')

    await firePointer(pet.button, 'pointerdown', { id: 11, kind: 'mouse' })
    await advance(449)
    expect(pet.reaction()).toBeUndefined()
    await firePointer(window, 'pointerup', { id: 11, kind: 'mouse' })
    await advance(1)
    expect(pet.reaction()).toBeUndefined()

    await firePointer(pet.button, 'pointerdown', { id: 12, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await advance(1000)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointerup', { id: 12, kind: 'mouse' })
    await clickPointer(pet.button, { id: 12, kind: 'mouse' })
    expect(open).not.toHaveBeenCalled()
  })

  it('recognizes a pointerup fallback at 450ms without running the due timer twice', async () => {
    const pet = await setup()
    const startedAt = Date.now()

    // Dispatch directly so the clock can cross 450ms without running the long-press timer.
    pet.button.dispatchEvent(new TestPointerEvent('pointerdown', { id: 13, kind: 'mouse' }))
    vi.setSystemTime(startedAt + 450)
    window.dispatchEvent(new TestPointerEvent('pointerup', { id: 13, kind: 'mouse' }))
    await flushPromises()
    expect(pet.reaction()).toBe('wave')

    await advance(1199)
    expect(pet.reaction()).toBe('wave')
    await advance(1)
    expect(pet.reaction()).toBeUndefined()
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
  })

  it('suppresses only the matching late click and recovers on the next pointer press', async () => {
    const pet = await setup()
    const open = vi.spyOn(pet.host, 'open')

    await longPress(pet.button, { id: 21, kind: 'mouse' })
    await clickPointer(pet.button, { id: 21, kind: 'mouse' })
    expect(open).not.toHaveBeenCalled()

    await advance(701)
    await clickPointer(pet.button, { id: 21, kind: 'mouse' })
    expect(open).toHaveBeenCalledTimes(1)
    await flushPromises()
    expect(pet.pose()).toBe('wave')
    expect(pet.reaction()).toBeUndefined()

    await firePointer(pet.button, 'pointerdown', { id: 22, kind: 'mouse' })
    await advance(100)
    await firePointer(window, 'pointerup', { id: 22, kind: 'mouse' })
    await clickPointer(pet.button, { id: 22, kind: 'mouse' })
    expect(open).toHaveBeenCalledTimes(2)
  })

  it('opens on a browser-contract keyboard-style click after a drag and clears the active reaction', async () => {
    const pet = await setup()
    const open = vi.spyOn(pet.host, 'open')

    await firePointer(pet.button, 'pointerdown', { id: 23, kind: 'mouse' })
    await firePointer(window, 'pointermove', { id: 23, kind: 'mouse', x: 170, y: 210 })
    await firePointer(window, 'pointerup', { id: 23, kind: 'mouse', x: 170, y: 210 })
    await flushPromises()
    expect(pet.reaction()).toBe('wave')

    await clickPointer(pet.button, { id: -1, kind: 'mouse', detail: 0 })
    expect(open).toHaveBeenCalledTimes(1)
    await flushPromises()
    expect(pet.reaction()).toBeUndefined()
    expect(pet.pose()).toBe('wave')
  })

  it('does not drag below the 6px Euclidean threshold', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 31, kind: 'mouse', x: 120, y: 160 })
    await firePointer(window, 'pointermove', { id: 31, kind: 'mouse', x: 123.5, y: 164.7 })
    expect(pet.motion()).not.toBe('drag')
    expect(pet.interacting).toEqual([])
    await firePointer(window, 'pointerup', { id: 31, kind: 'mouse', x: 123.5, y: 164.7 })
  })

  it('starts dragging at exactly 6px with a 3.6 by 4.8 diagonal', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 41, kind: 'touch', x: 120, y: 160 })
    await firePointer(window, 'pointermove', { id: 41, kind: 'touch', x: 123.6, y: 164.8 })
    expect(pet.motion()).toBe('drag')
    expect(pet.interacting).toEqual([true])
    await firePointer(window, 'pointerup', { id: 41, kind: 'touch', x: 123.6, y: 164.8 })
    expect(pet.interacting).toEqual([true, false])
  })

  it('can drag after a long press and clears the pending reaction when dragging starts', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 51, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointermove', { id: 51, kind: 'mouse', x: 150, y: 180 })
    expect(pet.motion()).toBe('drag')
    expect(pet.reaction()).toBeUndefined()
    await firePointer(window, 'pointercancel', { id: 51, kind: 'mouse', x: 150, y: 180 })
  })

  it.each(['mouse', 'touch'] as const)('uses the same %s long-press path', async kind => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 61, kind })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointerup', { id: 61, kind })
  })

  it('ignores a non-primary pointer down', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 71, kind: 'touch', primary: false })
    await advance(450)
    expect(pet.reaction()).toBeUndefined()
    await firePointer(window, 'pointerup', { id: 71, kind: 'touch', primary: false })
  })

  it('keeps the first pointer in control when a second pointer sends events', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 72, kind: 'mouse' })
    await firePointer(pet.button, 'pointerdown', { id: 73, kind: 'touch', primary: true })
    await firePointer(window, 'pointermove', { id: 73, kind: 'touch', primary: true, x: 220, y: 240 })
    await firePointer(window, 'pointerup', { id: 73, kind: 'touch', primary: true, x: 220, y: 240 })
    await firePointer(window, 'pointercancel', { id: 73, kind: 'touch', primary: true, x: 220, y: 240 })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointerup', { id: 72, kind: 'mouse' })
  })

  it('clears a recognized long press on pointer cancel', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 81, kind: 'touch' })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointercancel', { id: 81, kind: 'touch' })
    expect(pet.reaction()).toBeUndefined()
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
  })

  it('cancels a pending gesture when the document hides and does not replay it on restore', async () => {
    let visibility: DocumentVisibilityState = 'visible'
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility)
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 91, kind: 'mouse' })
    await advance(200)
    visibility = 'hidden'
    await fireEvent(document, new Event('visibilitychange'))
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()

    visibility = 'visible'
    await fireEvent(document, new Event('visibilitychange'))
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
  })

  it('cancels a pending gesture when the host page becomes hidden', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 101, kind: 'mouse' })
    await advance(200)
    pet.host.patch({ pageVisible: false })
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()

    pet.host.patch({ pageVisible: true })
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
  })

  it('cancels a pending gesture while the editor is open without replaying after close', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 111, kind: 'mouse' })
    await advance(200)
    const closeEditor = registerEditor()
    editorReleases.push(closeEditor)
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
    closeEditor()
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
  })

  it('cancels a pending gesture on window blur', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 121, kind: 'mouse' })
    await advance(200)
    await fireEvent(window, new Event('blur'))
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
  })

  it.each(['host hidden', 'editor', 'window blur'] as const)(
    'ends an active drag safely when %s interrupts it',
    async cause => {
      const pet = await setup()
      const save = vi.spyOn(pet.pet.storage, 'set')
      const id = cause === 'host hidden' ? 122 : cause === 'editor' ? 123 : 124

      await firePointer(pet.button, 'pointerdown', { id, kind: 'mouse', x: 120, y: 160 })
      await firePointer(window, 'pointermove', { id, kind: 'mouse', x: 170, y: 210 })
      expect(pet.motion()).toBe('drag')
      expect(pet.interacting).toEqual([true])
      const savesBeforeInterrupt = save.mock.calls.length

      let closeEditor: (() => void) | undefined
      if (cause === 'host hidden') {
        pet.host.patch({ pageVisible: false })
      } else if (cause === 'editor') {
        closeEditor = registerEditor()
        editorReleases.push(closeEditor)
      } else {
        await fireEvent(window, new Event('blur'))
      }
      await flushPromises()
      if (cause === 'editor') expect(save).toHaveBeenCalledTimes(savesBeforeInterrupt)

      expect(pet.interacting.at(-1)).toBe(false)
      expect(pet.motion()).not.toBe('drag')
      const position = pet.button.style.transform
      await firePointer(window, 'pointermove', { id, kind: 'mouse', x: 260, y: 300 })
      expect(pet.button.style.transform).toBe(position)

      if (cause === 'host hidden') pet.host.patch({ pageVisible: true })
      if (closeEditor) closeEditor()
      await advance(1000)
      expect(pet.reaction()).toBeUndefined()
      expect(pet.button.style.transform).not.toBe('')
    },
  )

  it('cancels a pending gesture and all timers on unmount', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 131, kind: 'mouse' })
    await advance(200)
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
    await advance(1000)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([
    { phase: 'thinking' as const, thinking: true, toolName: null },
    { phase: 'tool' as const, thinking: false, toolName: 'terminal' },
    { phase: 'awaiting' as const, thinking: false, toolName: null },
  ])('does not add a reaction while the host is $phase but keeps click and drag usable', async state => {
    const pet = await setup()
    const open = vi.spyOn(pet.host, 'open')
    pet.host.patch(state)
    await flushPromises()

    await longPress(pet.button, { id: 141, kind: 'mouse' })
    expect(pet.reaction()).toBeUndefined()
    await firePointer(pet.button, 'pointerdown', { id: 142, kind: 'mouse' })
    await advance(100)
    await firePointer(window, 'pointerup', { id: 142, kind: 'mouse' })
    await clickPointer(pet.button, { id: 142, kind: 'mouse' })
    expect(open).toHaveBeenCalledTimes(1)

    await firePointer(pet.button, 'pointerdown', { id: 143, kind: 'touch' })
    await firePointer(window, 'pointermove', { id: 143, kind: 'touch', x: 150, y: 180 })
    expect(pet.motion()).toBe('drag')
    await firePointer(window, 'pointercancel', { id: 143, kind: 'touch', x: 150, y: 180 })
  })

  it('does not replay a pending long press after a thinking phase returns to idle', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 144, kind: 'mouse' })
    await advance(200)
    pet.host.patch({ phase: 'thinking', thinking: true })
    await flushPromises()
    pet.host.patch({ phase: 'idle', thinking: false })
    await flushPromises()
    await advance(300)
    expect(pet.reaction()).toBeUndefined()
    await firePointer(window, 'pointerup', { id: 144, kind: 'mouse' })
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
  })

  it('keeps a cancelled long press cancelled across idle and the 450ms pointerup fallback', async () => {
    const pet = await setup()
    const startedAt = Date.now()

    await firePointer(pet.button, 'pointerdown', { id: 145, kind: 'mouse' })
    await advance(200)
    pet.host.patch({ phase: 'thinking', thinking: true })
    await flushPromises()
    vi.setSystemTime(startedAt + 450)
    pet.host.patch({ phase: 'idle', thinking: false })
    await flushPromises()
    await firePointer(window, 'pointerup', { id: 145, kind: 'mouse' })
    expect(pet.reaction()).toBeUndefined()
    await advance(1000)
    expect(pet.reaction()).toBeUndefined()
  })

  it.each([
    { name: 'agent.done', pose: 'victory' },
    { name: 'agent.error', pose: 'confused' },
    { name: 'agent.bubble', pose: 'talk' },
  ])('$name cancels a new reaction without replacing its own transient pose', async event => {
    const pet = await setup()

    await longPress(pet.button, { id: 151, kind: 'mouse' })
    expect(pet.reaction()).toBe('wave')
    pet.host.fire(event.name)
    await flushPromises()
    expect(pet.reaction()).toBeUndefined()
    expect(pet.pose()).toBe(event.pose)
  })

  it('does not steal an existing transient pose with a new long press', async () => {
    const pet = await setup()

    pet.host.fire('agent.done')
    await flushPromises()
    expect(pet.pose()).toBe('victory')
    await firePointer(pet.button, 'pointerdown', { id: 161, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBeUndefined()
    expect(pet.pose()).toBe('victory')
    await firePointer(window, 'pointerup', { id: 161, kind: 'mouse' })
  })

  it('does not add a reaction when motion is disabled', async () => {
    const pet = await setup()

    pet.host.patch({ motionAllowed: false, reducedMotion: true })
    await flushPromises()
    await longPress(pet.button, { id: 171, kind: 'mouse' })
    expect(pet.reaction()).toBeUndefined()
  })

  it('does not add a reaction for a contained preview', async () => {
    const pet = await setup({ previewRoot: document.createElement('div') })

    await longPress(pet.button, { id: 181, kind: 'mouse' })
    expect(pet.reaction()).toBeUndefined()
  })

  it('does not add a reaction when the host is unavailable', async () => {
    const pet = await setup()

    pet.host.patch({ available: false })
    await flushPromises()
    await longPress(pet.button, { id: 191, kind: 'mouse' })
    expect(pet.reaction()).toBeUndefined()
  })

  it('waves first, alternates to jump after cooldown, and fades at the documented duration', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 201, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointerup', { id: 201, kind: 'mouse' })
    await advance(1199)
    expect(pet.reaction()).toBe('wave')
    await advance(1)
    expect(pet.reaction()).toBeUndefined()

    await advance(4350)
    await firePointer(pet.button, 'pointerdown', { id: 202, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBe('jump')
    await firePointer(window, 'pointerup', { id: 202, kind: 'mouse' })
    await advance(1049)
    expect(pet.reaction()).toBe('jump')
    await advance(1)
    expect(pet.reaction()).toBeUndefined()
  })

  it('silences a rapid second long press and resumes with jump after a longer pause', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 203, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointerup', { id: 203, kind: 'mouse' })

    await advance(200)
    await firePointer(pet.button, 'pointerdown', { id: 204, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBeUndefined()
    await firePointer(window, 'pointerup', { id: 204, kind: 'mouse' })

    await advance(6000)
    await firePointer(pet.button, 'pointerdown', { id: 205, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBe('jump')
    await firePointer(window, 'pointerup', { id: 205, kind: 'mouse' })
  })

  it('ends the old pet drag on a key switch and does not pass its gesture to the new pet', async () => {
    const pet = await setup({ key: 'ying' })
    const nextInteracting: boolean[] = []
    const nextPet = createMockPet('stage', 'other', {
      onInteracting: value => nextInteracting.push(value),
    })

    await firePointer(pet.button, 'pointerdown', { id: 215, kind: 'mouse', x: 120, y: 160 })
    await firePointer(window, 'pointermove', { id: 215, kind: 'mouse', x: 180, y: 220 })
    expect(pet.motion()).toBe('drag')
    expect(pet.interacting).toEqual([true])

    await pet.view.rerender({ pet: nextPet })
    await flushPromises()
    expect(pet.interacting).toEqual([true, false])
    expect(nextInteracting).toEqual([])
    expect(pet.motion()).not.toBe('drag')

    const position = pet.button.style.transform
    await firePointer(window, 'pointermove', { id: 215, kind: 'mouse', x: 260, y: 300 })
    await firePointer(window, 'pointerup', { id: 215, kind: 'mouse', x: 260, y: 300 })
    expect(pet.button.style.transform).toBe(position)
    expect(nextInteracting).toEqual([])
    expect(pet.reaction()).toBeUndefined()

    await firePointer(pet.button, 'pointerdown', { id: 216, kind: 'touch', x: 130, y: 170 })
    await firePointer(window, 'pointermove', { id: 216, kind: 'touch', x: 190, y: 230 })
    expect(nextInteracting).toEqual([true])
    await firePointer(window, 'pointercancel', { id: 216, kind: 'touch', x: 190, y: 230 })
    expect(nextInteracting).toEqual([true, false])
  })

  it('keeps interaction memory isolated by plugin instance and pet key', async () => {
    const pet = await setup({ pluginId: 'AgentPetsA', key: 'ying' })

    await longPress(pet.button, { id: 211, kind: 'mouse' })
    expect(pet.reaction()).toBe('wave')
    await advance(6001)

    await pet.view.rerender({
      pluginId: 'AgentPetsB',
      pet: createMockPet('stage', 'ying'),
    })
    await flushPromises()
    await longPress(pet.button, { id: 212, kind: 'mouse' })
    expect(pet.reaction()).toBe('wave')
    await advance(6001)

    await pet.view.rerender({
      pluginId: 'AgentPetsA',
      pet: createMockPet('stage', 'other'),
    })
    await flushPromises()
    await longPress(pet.button, { id: 213, kind: 'mouse' })
    expect(pet.reaction()).toBe('wave')
    await advance(6001)

    await pet.view.rerender({
      pluginId: 'AgentPetsA',
      pet: createMockPet('stage', 'ying'),
    })
    await flushPromises()
    await longPress(pet.button, { id: 214, kind: 'mouse' })
    expect(pet.reaction()).toBe('jump')
  })

  it('expires interaction memory after 30 seconds', async () => {
    const pet = await setup()

    await longPress(pet.button, { id: 221, kind: 'mouse' })
    expect(pet.reaction()).toBe('wave')
    await advance(30000)
    await longPress(pet.button, { id: 222, kind: 'mouse' })
    expect(pet.reaction()).toBe('wave')
  })

  it('clears a wave when clearance hops to another surface and does not restore it on landing', async () => {
    const currentRect = { left: 100, top: 400, width: 600, height: 80 }
    const nextRect = { left: 100, top: 500, width: 600, height: 200 }
    const currentCard = addFixture('div', 'v-card', currentRect)
    const nextCard = addFixture('div', 'v-card', nextRect)
    const pet = await setup({
      movement: 'auto',
      roam: 'surfaces',
      stored: { roam: 'surfaces', xRatio: 0.2, yRatio: 0 },
    })
    expect(pet.motion()).toBe('idle')
    expect(pet.anchors.at(-1)?.y).toBeCloseTo(280)

    await advance(1500)
    const controlRect = { left: 0, top: 250, width: 800, height: 150 }
    const control = addFixture('button', 'gesture-control', controlRect)
    const inside = (rect: typeof currentRect, x: number, y: number) =>
      x >= rect.left && x <= rect.left + rect.width && y >= rect.top && y <= rect.top + rect.height
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (x: number, y: number) => {
        if (inside(nextRect, x, y)) return [nextCard, document.body]
        if (inside(currentRect, x, y)) return [currentCard, document.body]
        if (y >= controlRect.top && y < currentRect.top) return [control, document.body]
        return [document.body]
      },
    })

    const start = pet.anchors.at(-1)!
    await firePointer(pet.button, 'pointerdown', { id: 225, kind: 'mouse', x: start.x + 10, y: start.y + 10 })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointerup', { id: 225, kind: 'mouse', x: start.x + 10, y: start.y + 10 })

    await advance(50)
    expect(pet.motion()).toBe('fall')
    expect(pet.reaction()).toBeUndefined()
    for (let elapsed = 0; elapsed < 800 && pet.motion() === 'fall'; elapsed += 16) await advance(16)
    expect(pet.motion()).toBe('sit')
    expect(pet.reaction()).toBeUndefined()
  })

  it('adds a drop reaction immediately in fixed free mode', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 231, kind: 'mouse' })
    await firePointer(window, 'pointermove', { id: 231, kind: 'mouse', x: 160, y: 200 })
    await firePointer(window, 'pointerup', { id: 231, kind: 'mouse', x: 160, y: 200 })
    await flushPromises()
    expect(pet.reaction()).toBe('wave')
    expect(pet.interacting).toEqual([true, false])
  })

  it('does not record or respond to a cancelled drop', async () => {
    const pet = await setup()

    await firePointer(pet.button, 'pointerdown', { id: 241, kind: 'mouse' })
    await firePointer(window, 'pointermove', { id: 241, kind: 'mouse', x: 160, y: 200 })
    await firePointer(window, 'pointercancel', { id: 241, kind: 'mouse', x: 160, y: 200 })
    await flushPromises()
    expect(pet.reaction()).toBeUndefined()

    await firePointer(pet.button, 'pointerdown', { id: 242, kind: 'mouse' })
    await advance(450)
    expect(pet.reaction()).toBe('wave')
    await firePointer(window, 'pointerup', { id: 242, kind: 'mouse' })
    await advance(1199)
    expect(pet.reaction()).toBe('wave')
    await advance(1)
    expect(pet.reaction()).toBeUndefined()
  })

  it.each(['hidden', 'busy', 'editor', 'preview'] as const)(
    'clears a drop reaction pending in flight when %s interrupts it',
    async cause => {
      const pet = await setup({ movement: 'auto', roam: 'floor' })
      const id = cause === 'hidden' ? 243 : cause === 'busy' ? 244 : cause === 'editor' ? 245 : 246

      await firePointer(pet.button, 'pointerdown', { id, kind: 'mouse', x: 120, y: 160 })
      await firePointer(window, 'pointermove', { id, kind: 'mouse', x: 160, y: 80 })
      await firePointer(window, 'pointerup', { id, kind: 'mouse', x: 160, y: 80 })
      await flushPromises()
      expect(pet.motion()).toBe('fall')
      expect(pet.reaction()).toBeUndefined()

      let closeEditor: (() => void) | undefined
      let previewRoot: HTMLDivElement | undefined
      if (cause === 'hidden') {
        pet.host.patch({ pageVisible: false })
      } else if (cause === 'busy') {
        pet.host.patch({ phase: 'thinking', thinking: true })
      } else if (cause === 'editor') {
        closeEditor = registerEditor()
        editorReleases.push(closeEditor)
      } else {
        previewRoot = document.createElement('div')
        document.body.appendChild(previewRoot)
        fixtureNodes.push(previewRoot)
        await pet.view.rerender({ previewRoot })
      }
      await flushPromises()
      await advance(16)

      if (cause === 'hidden') pet.host.patch({ pageVisible: true })
      if (cause === 'busy') pet.host.patch({ phase: 'idle', thinking: false })
      if (closeEditor) closeEditor()
      if (previewRoot) await pet.view.rerender({ previewRoot: null })
      await flushPromises()

      for (let elapsed = 0; elapsed < 4500; elapsed += 32) {
        await advance(32)
        expect(pet.reaction()).toBeUndefined()
      }
    },
  )

  it.each(['busy', 'hidden'] as const)(
    'clears a pending drop reaction when %s interrupts the sit pause',
    async cause => {
      const pet = await setup({ movement: 'auto', roam: 'floor' })
      const id = cause === 'busy' ? 247 : 248

      await firePointer(pet.button, 'pointerdown', { id, kind: 'mouse', x: 120, y: 160 })
      await firePointer(window, 'pointermove', { id, kind: 'mouse', x: 160, y: 80 })
      await firePointer(window, 'pointerup', { id, kind: 'mouse', x: 160, y: 80 })
      await flushPromises()

      let sawSit = false
      for (let elapsed = 0; elapsed < 2000 && !sawSit; elapsed += 16) {
        await advance(16)
        if (pet.motion() === 'sit') sawSit = true
      }
      expect(sawSit).toBe(true)
      expect(pet.reaction()).toBeUndefined()

      if (cause === 'busy') pet.host.patch({ phase: 'thinking', thinking: true })
      else pet.host.patch({ pageVisible: false })
      await flushPromises()
      await advance(16)

      if (cause === 'busy') pet.host.patch({ phase: 'idle', thinking: false })
      else pet.host.patch({ pageVisible: true })
      await flushPromises()

      for (let elapsed = 0; elapsed < 4500; elapsed += 32) {
        await advance(32)
        expect(pet.reaction()).toBeUndefined()
      }
    },
  )

  it('waits for the floor landing and sit pause before adding a drop reaction', async () => {
    const pet = await setup({ movement: 'auto', roam: 'floor' })

    await firePointer(pet.button, 'pointerdown', { id: 251, kind: 'mouse' })
    await firePointer(window, 'pointermove', { id: 251, kind: 'mouse', x: 160, y: 80 })
    await firePointer(window, 'pointerup', { id: 251, kind: 'mouse', x: 160, y: 80 })

    let sawSit = false
    for (let elapsed = 0; elapsed < 4000 && !pet.reaction(); elapsed += 16) {
      await advance(16)
      if (pet.motion() === 'sit') sawSit = true
    }
    expect(sawSit).toBe(true)
    expect(pet.reaction()).toBe('wave')
  })
})
