import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createMockHost, createMockPet } from '@/dev/mockHost'
import { registerEditor } from '@/editor/presence'
import type { AgentRect } from '@/host'
import AgentPet from '@/stage/AgentPet.vue'

const hosts: ReturnType<typeof createMockHost>[] = []
const editors: Array<() => void> = []
const fixtures: HTMLElement[] = []
afterEach(() => {
  editors.splice(0).forEach(close => close())
  hosts.splice(0).forEach(host => host.dispose())
  fixtures.splice(0).forEach(el => el.remove())
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
})

function box(rect: DOMRect, kind = 'card') {
  const el = document.createElement(kind === 'control' ? 'button' : 'div')
  if (kind === 'card') el.className = 'v-card'
  el.getBoundingClientRect = () => rect
  document.body.append(el)
  fixtures.push(el)
  return el
}

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

async function until(predicate: () => boolean, limit = 14000) {
  for (let waited = 0; waited <= limit; waited += 16) {
    if (predicate()) return
    await advance(16)
  }
  throw new Error('hop condition did not become true')
}

async function setup(options: { fixed?: boolean; mobile?: boolean; roam?: 'surfaces' | 'floor' | 'free' } = {}) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.1)
  vi.stubGlobal('innerWidth', options.mobile ? 390 : 1000)
  vi.stubGlobal('innerHeight', 800)
  Object.defineProperty(document, 'elementsFromPoint', {
    configurable: true,
    value: (x: number, y: number) => [
      ...fixtures
        .filter(el => {
          const r = el.getBoundingClientRect()
          return (
            el.isConnected && el.style.display !== 'none' && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom
          )
        })
        .reverse(),
      document.body,
    ],
  })
  const host = createMockHost('AgentPets')
  hosts.push(host)
  host.patch({ isMobile: options.mobile ?? false })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'ying', { onAnchor: r => anchors.push(r) })
  const roam = options.roam ?? 'surfaces'
  await pet.storage!.set({ roam, xRatio: 0.5, yRatio: 1 })
  const save = vi.spyOn(pet.storage!, 'set')
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam, movement: options.fixed ? 'fixed' : 'auto' },
    },
  })
  await flushPromises()
  for (const img of Array.from(view.container.querySelectorAll('img'))) await fireEvent(img, new Event('load'))
  await advance(64)
  const root = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const rect = () => anchors.at(-1)!
  const card = box(new DOMRect(options.mobile ? 80 : 350, 600, options.mobile ? 230 : 300, 160))
  return { host, pet, save, view, root, rect, anchors, card }
}

describe('autonomous upward card exploration', () => {
  it('chooses an unobstructed higher card without a drag or clearance trigger, then continues', async () => {
    const stage = await setup()
    expect(stage.rect().y + stage.rect().height).toBe(800)
    await until(() => stage.root.dataset.motion === 'fall')
    await until(() => stage.root.dataset.motion === 'idle' && stage.rect().y + stage.rect().height === 600, 3000)
    vi.mocked(Math.random).mockReturnValue(0.5)
    await until(() => stage.root.dataset.motion === 'walk', 2000)
    expect(stage.save).not.toHaveBeenCalled()
    for (const r of stage.anchors) {
      if (!r) continue
      expect(r.x).toBeGreaterThanOrEqual(0)
      expect(r.y).toBeGreaterThanOrEqual(0)
      expect(r.x + r.width).toBeLessThanOrEqual(1000)
      expect(r.y + r.height).toBeLessThanOrEqual(800)
    }
  })

  it.each(['fixed', 'floor', 'free'] as const)('never chooses cards in %s mode', async mode => {
    const stage = await setup({ fixed: mode === 'fixed', roam: mode === 'fixed' ? 'surfaces' : mode })
    const motions = new Set<string>()
    for (let i = 0; i < 1000; i++) {
      await advance(16)
      motions.add(stage.root.dataset.motion!)
    }
    expect(motions.has('fall')).toBe(false)
  })

  it.each(['far', 'high', 'narrow', 'covered', 'hidden', 'unsafe-landing'] as const)(
    'keeps ordinary exploration when the nearby card is %s',
    async reason => {
      const stage = await setup()
      if (reason === 'far') stage.card.getBoundingClientRect = () => new DOMRect(850, 600, 150, 160)
      if (reason === 'high') stage.card.getBoundingClientRect = () => new DOMRect(350, 350, 300, 160)
      if (reason === 'narrow') stage.card.getBoundingClientRect = () => new DOMRect(480, 600, 30, 160)
      if (reason === 'covered') box(new DOMRect(350, 590, 300, 190), 'cover')
      if (reason === 'hidden') stage.card.style.display = 'none'
      if (reason === 'unsafe-landing') box(new DOMRect(300, 450, 400, 145), 'control')
      await until(() => stage.root.dataset.motion === 'walk')
      expect(stage.rect().y + stage.rect().height).toBe(800)
    },
  )

  it('uses the shorter mobile upward reach', async () => {
    const stage = await setup({ mobile: true })
    await until(() => stage.root.dataset.motion === 'walk')
    expect(stage.rect().y + stage.rect().height).toBe(800)
  })

  it('can hop onto a reachable mobile card and keep all reported frames visible', async () => {
    const stage = await setup({ mobile: true })
    stage.card.getBoundingClientRect = () => new DOMRect(80, 660, 230, 100)
    await until(() => stage.root.dataset.motion === 'fall')
    await until(() => stage.root.dataset.motion === 'idle' && stage.rect().y + stage.rect().height === 660, 3000)
    expect(stage.save).not.toHaveBeenCalled()
    expect(
      stage.anchors.every(r => !r || (r.x >= 0 && r.x + r.width <= 390 && r.y >= 0 && r.y + r.height <= 800)),
    ).toBe(true)
  })

  it('still steps down naturally after an autonomous upward visit', async () => {
    const stage = await setup()
    await until(() => stage.root.dataset.motion === 'fall')
    await until(() => stage.root.dataset.motion === 'idle' && stage.rect().y + stage.rect().height === 600, 3000)
    // Edge exits are selected after the current finite exploration episode, not every continuation.
    await until(() => stage.root.dataset.motion === 'fall', 30000)
    await until(() => stage.root.dataset.motion === 'idle' && stage.rect().y + stage.rect().height === 800, 3000)
    expect(stage.save).not.toHaveBeenCalled()
  })

  it('rejects a hop whose endpoints are clear but flight corridor crosses the conversation panel', async () => {
    const stage = await setup()
    stage.host.patch({ panelOpen: true, panelRect: { x: 350, y: 625, width: 300, height: 30 } })
    await advance(32)
    await until(() => stage.root.dataset.motion === 'walk')
    expect(stage.rect().y + stage.rect().height).toBe(800)
  })

  it('stops steering toward the old landing when work interrupts the ascent', async () => {
    const stage = await setup()
    stage.card.getBoundingClientRect = () => new DOMRect(580, 600, 200, 160)
    await until(() => stage.root.dataset.motion === 'fall')
    await advance(160)
    const interrupted = { ...stage.rect() }
    stage.host.patch({ phase: 'tool' })
    await advance(2500)
    expect(stage.rect().x).toBeCloseTo(interrupted.x)
    expect(stage.rect().y + stage.rect().height).toBe(800)
    expect(stage.save).not.toHaveBeenCalled()
  })

  it.each(['removed', 'moved', 'covered'] as const)('does not land on an airborne target that was %s', async reason => {
    const stage = await setup()
    await until(() => stage.root.dataset.motion === 'fall')
    if (reason === 'removed') stage.card.remove()
    if (reason === 'moved') stage.card.getBoundingClientRect = () => new DOMRect(350, 500, 300, 160)
    if (reason === 'covered') box(new DOMRect(350, 590, 300, 190), 'cover')
    await until(() => stage.root.dataset.motion === 'idle', 4000)
    expect(stage.rect().y + stage.rect().height).toBe(800)
    expect(stage.save).not.toHaveBeenCalled()
  })

  it.each(['work', 'hidden', 'editor', 'reduced-motion', 'drag'] as const)(
    'drops the old upward target when %s takes over',
    async reason => {
      const stage = await setup()
      await until(() => stage.root.dataset.motion === 'fall')
      if (reason === 'work') stage.host.patch({ phase: 'tool' })
      if (reason === 'hidden') stage.host.patch({ pageVisible: false })
      if (reason === 'editor') editors.push(registerEditor())
      if (reason === 'reduced-motion') stage.host.patch({ motionAllowed: false })
      if (reason === 'drag') {
        const event = new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 500, clientY: 700 })
        Object.defineProperties(event, {
          pointerId: { value: 7 },
          pointerType: { value: 'mouse' },
          isPrimary: { value: true },
        })
        await fireEvent(stage.view.container.querySelector('button')!, event)
      }
      await advance(2500)
      expect(stage.rect().y + stage.rect().height).not.toBe(600)
      stage.view.unmount()
      stage.host.dispose()
      expect(vi.getTimerCount()).toBe(0)
    },
  )
})
