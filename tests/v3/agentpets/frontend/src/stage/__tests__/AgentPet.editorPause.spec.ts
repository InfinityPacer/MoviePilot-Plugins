import { render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { registerEditor } from '@/editor/presence'
import { createMockHost, createMockPet } from '@/dev/mockHost'

afterEach(() => {
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  document.querySelectorAll('body > nav').forEach(element => element.remove())
})

it('suspends global stage work without saving or losing position and resumes after the last editor', async () => {
  vi.useFakeTimers()
  const host = createMockHost('AgentPets'),
    pet = createMockPet('stage', 'ying')
  const save = vi.spyOn(pet.storage!, 'set')
  const view = render(AgentPet, {
    props: { agent: host, pet, settingsOverride: { scale: 1, speed: 1, movement: 'auto', roam: 'free' } },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(50)
  const button = view.container.querySelector<HTMLElement>('button')!
  const position = button.style.transform
  const close = registerEditor(),
    closeSecond = registerEditor()
  const writes = save.mock.calls.length
  expect(vi.getTimerCount()).toBe(0)
  await vi.advanceTimersByTimeAsync(60000)
  expect(button.style.transform).toBe(position)
  expect(save).toHaveBeenCalledTimes(writes)
  close()
  expect(vi.getTimerCount()).toBe(0)
  closeSecond()
  expect(vi.getTimerCount()).toBeGreaterThan(0)
  expect(button.style.transform).toBe(position)
  view.unmount()
  host.dispose()
  expect(vi.getTimerCount()).toBe(0)
})

it('applies reduced motion selected while an editor pauses a moving stage', async () => {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  const host = createMockHost('AgentPets')
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet: createMockPet('stage', 'ying'),
      settingsOverride: { scale: 1, speed: 1, movement: 'auto', roam: 'free' },
    },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(10001)
  const stage = view.container.querySelector<HTMLElement>('[data-motion]')!
  expect(stage.dataset.motion).toBe('walk')
  const close = registerEditor()
  host.patch({ motionAllowed: false, reducedMotion: true })
  expect(vi.getTimerCount()).toBe(0)
  close()
  await flushPromises()
  expect(stage.dataset.motion).toBe('idle')
  const position = view.container.querySelector<HTMLElement>('button')!.style.transform
  await vi.advanceTimersByTimeAsync(100)
  expect(view.container.querySelector<HTMLElement>('button')!.style.transform).toBe(position)
  view.unmount()
  host.dispose()
})

it('rechecks a moved bottom dock after a viewport change received while paused', async () => {
  vi.useFakeTimers()
  const host = createMockHost('AgentPets')
  host.patch({ motionAllowed: false })
  const nav = document.createElement('nav')
  nav.style.position = 'fixed'
  let top = window.innerHeight - 64
  nav.getBoundingClientRect = () => new DOMRect(0, top, window.innerWidth, window.innerHeight - top)
  document.body.appendChild(nav)
  Object.defineProperty(document, 'elementsFromPoint', {
    configurable: true,
    value: (_x: number, y: number) => (y >= top ? [nav, document.body] : [document.body]),
  })
  const anchors: Array<{ y: number; height: number } | null> = []
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet: createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) }),
      settingsOverride: { scale: 1, speed: 1, movement: 'auto', roam: 'floor' },
    },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(50)
  const before = anchors.at(-1)!
  expect(before.y + before.height).toBeCloseTo(top - 8)
  const close = registerEditor()
  top -= 64
  host.patch({
    viewport: { ...host.getState().viewport, width: window.innerWidth - 20 },
    isMobile: true,
  })
  await vi.advanceTimersByTimeAsync(2000)
  expect(anchors.at(-1)).toEqual(before)
  close()
  await flushPromises()
  await vi.advanceTimersByTimeAsync(20)
  const resumed = anchors.at(-1)!
  expect(resumed.y + resumed.height).toBeCloseTo(top - 8)
  view.unmount()
  host.dispose()
})

it('replays visual viewport changes after the editor closes without a host update', async () => {
  vi.useFakeTimers()
  const visual = Object.assign(new EventTarget(), {
    width: window.innerWidth,
    height: window.innerHeight,
    offsetLeft: 0,
    offsetTop: 0,
  })
  vi.stubGlobal('visualViewport', visual)
  const host = createMockHost('AgentPets')
  host.patch({ motionAllowed: false })
  const nav = document.createElement('nav')
  nav.style.position = 'fixed'
  let top = visual.height - 64
  nav.getBoundingClientRect = () => new DOMRect(0, top, visual.width, 64)
  document.body.appendChild(nav)
  Object.defineProperty(document, 'elementsFromPoint', {
    configurable: true,
    value: (_x: number, y: number) => (y >= top && y <= top + 64 ? [nav, document.body] : [document.body]),
  })
  const anchors: Array<{ y: number; height: number } | null> = []
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet: createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) }),
      settingsOverride: { scale: 1, speed: 1, movement: 'auto', roam: 'floor' },
    },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(50)
  const before = anchors.at(-1)!
  const close = registerEditor()
  visual.height -= 120
  top = visual.height - 64
  visual.dispatchEvent(new Event('resize'))
  await vi.advanceTimersByTimeAsync(2000)
  expect(anchors.at(-1)).toEqual(before)
  close()
  await flushPromises()
  await vi.advanceTimersByTimeAsync(20)
  const resumed = anchors.at(-1)!
  expect(resumed.y + resumed.height).toBeCloseTo(top - 8)
  view.unmount()
  host.dispose()
})
