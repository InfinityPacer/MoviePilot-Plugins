import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { AgentRect } from '@/host'
import type { RoamMode } from '@/stage/geometry'

function pointer(type: string, clientX: number, clientY: number) {
  const event = new MouseEvent(type, { bubbles: true, button: 0, clientX, clientY })
  Object.defineProperty(event, 'pointerId', { value: 1 })
  return event
}

async function setup(roam: RoamMode = 'free', scale = 1.3, motionAllowed = false, covered = false) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.9)
  vi.stubGlobal('innerWidth', 390)
  vi.stubGlobal('innerHeight', 844)
  const visual = Object.assign(new EventTarget(), { width: 390, height: 844, offsetLeft: 0, offsetTop: 0 })
  vi.stubGlobal('visualViewport', visual)
  if (covered) {
    const controls = Array.from({ length: 4 }, (_, row) => {
      const control = document.createElement('button')
      control.getBoundingClientRect = () => new DOMRect(0, row * 211, 390, 211)
      document.body.appendChild(control)
      return control
    })
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (_x: number, y: number) => [controls[Math.min(3, Math.floor(y / 211))], document.body],
    })
  }
  const host = createMockHost('AgentPets')
  host.patch({ isMobile: true, motionAllowed })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) })
  const save = vi.spyOn(pet.storage, 'set')
  const view = render(AgentPet, {
    props: { agent: host, pet, pluginId: 'AgentPets', settingsOverride: { scale, speed: 1, roam } },
  })
  await vi.advanceTimersByTimeAsync(64)
  const button = view.container.querySelector('button')!
  const rect = () => anchors.at(-1)!
  const drag = (toX: number, toY: number) => {
    button.dispatchEvent(pointer('pointerdown', rect().x + 10, rect().y + 10))
    window.dispatchEvent(pointer('pointermove', toX, toY))
    window.dispatchEvent(pointer('pointerup', toX, toY))
  }
  const unmount = () => {
    view.unmount()
    host.dispose()
  }
  return { host, anchors, rect, button, visual, drag, save, unmount }
}

afterEach(() => {
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  document.querySelectorAll('body > button, body > nav, body > .v-card').forEach(el => el.remove())
})

describe('mobile stage recovery', () => {
  it.each([0.6, 1, 1.3, 1.6])('keeps a draggable 48px when controls cover the screen at scale %s', async scale => {
    const stage = await setup('free', scale, false, true)
    expect(stage.rect().height).toBe(48)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(844)
    const sunkY = stage.rect().y
    stage.drag(180, 300)
    await vi.advanceTimersByTimeAsync(32)
    expect(stage.rect().y).toBeLessThan(sunkY - 100)
    expect(stage.rect().height).toBeCloseTo(120 * scale * 0.8)
    expect(stage.save).toHaveBeenCalledTimes(1)
    stage.unmount()
  })

  it('preserves the visible shelter across desktop, mobile and scale changes', async () => {
    const stage = await setup('floor', 1.3, false, true)
    stage.host.patch({ isMobile: false })
    await vi.advanceTimersByTimeAsync(2300)
    expect(stage.rect().height).toBeGreaterThanOrEqual(48)
    stage.host.patch({ isMobile: true })
    stage.host.emit('agentpets.settings', { scale: 0.6, speed: 1, roam: 'floor' })
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect().height).toBeGreaterThanOrEqual(48)
    await vi.advanceTimersByTimeAsync(2300)
    expect(stage.rect().height).toBeGreaterThanOrEqual(48)
    stage.unmount()
  })

  it.each(['free', 'floor', 'surfaces'] as const)(
    'recovers %s without a host update as the keyboard and address bar move',
    async roam => {
      const stage = await setup(roam)
      stage.visual.height = 480
      stage.visual.dispatchEvent(new Event('resize'))
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.rect().y + stage.rect().height).toBeLessThanOrEqual(480)
      stage.visual.offsetTop = 90
      stage.visual.offsetLeft = 20
      stage.visual.width = 350
      stage.visual.dispatchEvent(new Event('scroll'))
      stage.drag(-100, -100)
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.rect().y).toBeGreaterThanOrEqual(90)
      expect(stage.rect().x).toBeGreaterThanOrEqual(20)
      const remove = vi.spyOn(stage.visual, 'removeEventListener')
      stage.unmount()
      expect(remove).toHaveBeenCalledWith('resize', expect.any(Function))
      expect(remove).toHaveBeenCalledWith('scroll', expect.any(Function))
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it('recovers on window resize even when the host still reports old dimensions', async () => {
    const stage = await setup('free')
    stage.host.dispose()
    vi.stubGlobal('innerWidth', 260)
    vi.stubGlobal('innerHeight', 420)
    window.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect().x + stage.rect().width).toBeLessThanOrEqual(260)
    expect(stage.rect().y + stage.rect().height).toBeLessThanOrEqual(420)
    stage.unmount()
  })

  it('stops a free walk from returning to its old offscreen target after rotation', async () => {
    const stage = await setup('free', 1, true)
    stage.drag(50, 80)
    await vi.advanceTimersByTimeAsync(14000)
    expect(stage.button.closest('.agent-pet-ying')?.getAttribute('data-motion')).toBe('walk')
    stage.visual.height = 250
    stage.visual.width = 240
    stage.visual.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(16000)
    expect(stage.rect().y + stage.rect().height).toBeLessThanOrEqual(250)
    expect(stage.rect().x + stage.rect().width).toBeLessThanOrEqual(240)
    stage.unmount()
  })

  it('replaces a falling target when the keyboard opens midair', async () => {
    const stage = await setup('floor', 1, true)
    stage.drag(160, 180)
    await vi.advanceTimersByTimeAsync(64)
    stage.visual.height = 400
    stage.visual.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(1800)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(400)
    stage.unmount()
  })

  it('cancels an old horizontal hop target when the viewport shrinks mid-jump', async () => {
    const stage = await setup('surfaces', 1, true)
    const card = document.createElement('div')
    card.className = 'v-card'
    card.getBoundingClientRect = () => new DOMRect(220, 300, 170, 200)
    const control = document.createElement('button')
    control.getBoundingClientRect = () => new DOMRect(0, 680, 390, 164)
    document.body.append(card, control)
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (x: number, y: number) => {
        if (y >= 680) return [control, document.body]
        if (x >= 220 && y >= 300 && y <= 500) return [card, document.body]
        return [document.body]
      },
    })
    await vi.advanceTimersByTimeAsync(2000)
    expect(stage.button.closest('.agent-pet-ying')?.getAttribute('data-motion')).toBe('fall')
    stage.visual.width = 180
    stage.visual.height = 420
    stage.visual.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(2000)
    expect(stage.rect().x + stage.rect().width).toBeLessThanOrEqual(180)
    expect(stage.rect().y + stage.rect().height).toBeLessThanOrEqual(420)
    stage.unmount()
  })

  it('stands above a fixed bottom navigation and releases its space after it disappears', async () => {
    const stage = await setup('floor', 1)
    const nav = document.createElement('nav')
    nav.style.position = 'fixed'
    nav.getBoundingClientRect = () => new DOMRect(0, 780, 390, 64)
    document.body.appendChild(nav)
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (_x: number, y: number) => (y >= 780 ? [nav, document.body] : [document.body]),
    })
    await vi.advanceTimersByTimeAsync(2200)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(772)
    nav.style.position = 'static'
    await vi.advanceTimersByTimeAsync(2200)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(844)
    stage.unmount()
  })
})
