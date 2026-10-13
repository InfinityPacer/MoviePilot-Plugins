import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { AgentRect } from '@/host'
import type { YingSettings } from '@/stage/settings'

function pointer(type: string, x: number, y: number) {
  const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y })
  Object.defineProperty(event, 'pointerId', { value: 1 })
  return event
}

function box(tag: string, rect: DOMRect, card = false) {
  const el = document.createElement(tag)
  if (card) el.className = 'v-card v-card--link'
  el.getBoundingClientRect = () => rect
  document.body.appendChild(el)
  return el
}

async function setup(motionAllowed = false, scale = 1, overrides: Partial<YingSettings> = {}) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.9)
  vi.stubGlobal('innerWidth', 1280)
  vi.stubGlobal('innerHeight', 800)
  Object.defineProperty(document, 'elementsFromPoint', {
    configurable: true,
    value: (x: number, y: number) => [
      ...Array.from(document.querySelectorAll('body > .v-card, body > button')).filter(el => {
        const r = el.getBoundingClientRect()
        return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom
      }),
      document.body,
    ],
  })
  const host = createMockHost('AgentPets')
  host.patch({ isMobile: false, motionAllowed })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) })
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      settingsOverride: { scale, speed: 1, roam: 'surfaces', ...overrides },
    },
  })
  await vi.advanceTimersByTimeAsync(64)
  const button = view.container.querySelector('button')!
  const rect = () => anchors.at(-1)!
  const drop = (x: number, feet: number) => {
    button.dispatchEvent(pointer('pointerdown', rect().x + 10, rect().y + 10))
    window.dispatchEvent(pointer('pointermove', x + 10, feet - 120 * scale + 10))
    window.dispatchEvent(pointer('pointerup', x + 10, feet - 120 * scale + 10))
  }
  const unmount = () => {
    view.unmount()
    host.dispose()
  }
  return { host, pet, rect, anchors, drop, unmount }
}

afterEach(() => {
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  document.querySelectorAll('body > .v-card, body > button').forEach(el => el.remove())
})

describe('desktop card placement', () => {
  it.each([false, true])('snaps a slightly overlapping drop onto a plugin card (motion %s)', async motion => {
    const stage = await setup(motion)
    box('div', new DOMRect(200, 400, 400, 200), true)
    stage.drop(300, 412)
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(400)
    await vi.advanceTimersByTimeAsync(2400)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(400)
    stage.unmount()
  })

  it('honors a manual card placement over automatic clearance from the preceding row', async () => {
    const stage = await setup()
    box('div', new DOMRect(150, 160, 500, 224), true)
    const card = box('div', new DOMRect(200, 400, 400, 200), true)
    stage.drop(300, 400)
    await vi.advanceTimersByTimeAsync(2400)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(400)
    card.getBoundingClientRect = () => new DOMRect(200, 420, 400, 200)
    window.dispatchEvent(new Event('scroll'))
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(420)
    card.remove()
    await vi.advanceTimersByTimeAsync(700)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(800)
    stage.unmount()
  })

  it('does not pull a drop well below the card back onto its top', async () => {
    const stage = await setup()
    box('div', new DOMRect(200, 400, 400, 200), true)
    stage.drop(300, 460)
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(800)
    stage.unmount()
  })

  it.each([0.6, 1, 1.6])('keeps a draggable desktop shelter at scale %s', async scale => {
    const stage = await setup(false, scale)
    box('button', new DOMRect(0, 0, 1280, 400))
    box('button', new DOMRect(0, 400, 1280, 400))
    await vi.advanceTimersByTimeAsync(2400)
    expect(stage.rect().height).toBeGreaterThanOrEqual(48)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(800)
    stage.drop(300, 300)
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect().height).toBeCloseTo(120 * scale)
    stage.unmount()
  })

  it('keeps every reported frame inside the desktop viewport during a high platform hop', async () => {
    const stage = await setup(true)
    box('div', new DOMRect(200, 140, 400, 200), true)
    box('button', new DOMRect(0, 600, 1280, 200))
    await vi.advanceTimersByTimeAsync(4500)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(140)
    for (const rect of stage.anchors) {
      if (!rect) continue
      expect(rect.x).toBeGreaterThanOrEqual(0)
      expect(rect.y).toBeGreaterThanOrEqual(0)
      expect(rect.x + rect.width).toBeLessThanOrEqual(1280)
      expect(rect.y + rect.height).toBeLessThanOrEqual(800)
    }
    stage.unmount()
  })
})

describe('desktop conversation panel', () => {
  const panel = { x: 900, y: 0, width: 380, height: 800 }

  it.each(['surfaces', 'floor', 'free'] as const)(
    'moves %s pets clear immediately when the conversation opens',
    async roam => {
      const stage = await setup(true, 1, { roam })
      const save = vi.spyOn(stage.pet.storage, 'set')
      expect(stage.rect().x).toBeGreaterThan(panel.x)
      stage.host.patch({ panelOpen: true, panelRect: panel })
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.rect().x + stage.rect().width).toBeLessThanOrEqual(panel.x)
      await vi.advanceTimersByTimeAsync(4500)
      expect(stage.rect().x + stage.rect().width).toBeLessThanOrEqual(panel.x)
      expect(save).not.toHaveBeenCalled()
      stage.unmount()
    },
  )

  it('temporarily moves a fixed pet clear and restores its preferred point after closing', async () => {
    const stage = await setup(true, 1, { movement: 'fixed' })
    const preferred = { ...stage.rect() }
    const save = vi.spyOn(stage.pet.storage, 'set')
    stage.host.patch({ panelOpen: true, panelRect: panel })
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect().x + stage.rect().width).toBeLessThanOrEqual(panel.x)
    expect(save).not.toHaveBeenCalled()
    stage.host.patch({ pageVisible: false })
    await vi.advanceTimersByTimeAsync(64)
    expect(save.mock.calls.at(-1)?.[0]).toMatchObject({ xRatio: 0.88, yRatio: 1 })
    stage.host.patch({ pageVisible: true, panelOpen: false, panelRect: null })
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect()).toEqual(preferred)
    stage.unmount()
  })

  it('saves the final landing after dropping on a card partially covered by the open panel', async () => {
    const stage = await setup(true)
    box('div', new DOMRect(925, 400, 300, 200), true)
    stage.host.patch({ panelOpen: true, panelRect: { ...panel, x: 950, width: 330 } })
    await vi.advanceTimersByTimeAsync(64)
    const save = vi.spyOn(stage.pet.storage, 'set')
    stage.drop(1000, 400)
    await vi.advanceTimersByTimeAsync(2200)
    expect(stage.rect().x + stage.rect().width).toBeLessThanOrEqual(950)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(800)
    expect(save.mock.calls.at(-1)?.[0]).toMatchObject({ roam: 'surfaces', yRatio: 1 })
    stage.unmount()
  })

  it('moves a falling pet clear without its old trajectory carrying it back behind the panel', async () => {
    const stage = await setup(true)
    stage.drop(1000, 300)
    await vi.advanceTimersByTimeAsync(64)
    const start = stage.anchors.length
    stage.host.patch({ panelOpen: true, panelRect: panel })
    await vi.advanceTimersByTimeAsync(2500)
    expect(stage.anchors.length).toBeGreaterThan(start)
    for (const rect of stage.anchors.slice(start)) {
      if (rect) expect(rect.x + rect.width).toBeLessThanOrEqual(panel.x)
    }
    stage.unmount()
  })
})
