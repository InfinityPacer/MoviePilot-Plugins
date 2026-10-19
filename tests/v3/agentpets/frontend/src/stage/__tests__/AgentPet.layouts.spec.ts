import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { AgentRect } from '@/host'

function pointer(type: string, x: number, y: number) {
  const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y })
  Object.defineProperty(event, 'pointerId', { value: 1 })
  return event
}

async function setup(width = 1280, mobile = false, floor = false, scale = 1) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.9)
  vi.stubGlobal('innerWidth', width)
  vi.stubGlobal('innerHeight', 800)
  Object.defineProperty(document, 'elementsFromPoint', {
    configurable: true,
    value: (x: number, y: number) => [
      ...Array.from(document.querySelectorAll('[data-layout-fixture]'))
        .reverse()
        .filter(el => {
          const r = el.getBoundingClientRect()
          return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom
        }),
      document.body,
    ],
  })
  const host = createMockHost('AgentPets')
  host.patch({ isMobile: mobile, motionAllowed: false })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) })
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      aspectRatio: 1,
      settingsOverride: { scale, speed: 1, roam: floor ? 'floor' : 'surfaces' },
    },
  })
  await vi.advanceTimersByTimeAsync(64)
  const button = view.container.querySelector('button')!
  const rect = () => anchors.at(-1)!
  const drop = (x: number, feet: number) => {
    const height = 120 * scale * (mobile ? 0.8 : 1)
    const peeking = !!button.closest('[data-peek-edge]')
    const grabX = peeking ? height / 2 : 10
    const grabY = peeking ? height * 0.3 : 10
    button.dispatchEvent(pointer('pointerdown', rect().x + 10, rect().y + 10))
    window.dispatchEvent(pointer('pointermove', x + grabX, feet - height + grabY))
    window.dispatchEvent(pointer('pointerup', x + grabX, feet - height + grabY))
  }
  return {
    host,
    button,
    anchors,
    rect,
    drop,
    unmount: () => {
      view.unmount()
      host.dispose()
    },
  }
}

function card(left: number, right: number) {
  const el = document.createElement('div')
  el.className = 'v-card'
  el.dataset.layoutFixture = ''
  el.getBoundingClientRect = () => new DOMRect(left, 400, right - left, 200)
  document.body.appendChild(el)
  return el
}

function mobilePluginList() {
  return [10, 160, 310, 460, 610].map(top => {
    const row = card(16, 374)
    row.classList.add('v-card--link')
    row.getBoundingClientRect = () => new DOMRect(16, top, 358, 140)
    return row
  })
}

function mobileDock() {
  const wrapper = document.createElement('div')
  wrapper.className = 'footer-nav-container'
  wrapper.style.position = 'fixed'
  wrapper.style.pointerEvents = 'none'
  wrapper.getBoundingClientRect = () => new DOMRect(0, 704, 390, 96)
  const bar = document.createElement('div')
  bar.className = 'v-card footer-nav-card'
  bar.style.pointerEvents = 'auto'
  bar.dataset.layoutFixture = ''
  bar.getBoundingClientRect = () => new DOMRect(20, 704, 350, 64)
  wrapper.appendChild(bar)
  document.body.appendChild(wrapper)
  return wrapper
}

afterEach(() => {
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  document.querySelectorAll('[data-layout-fixture], .footer-nav-container').forEach(el => el.remove())
})

describe('autonomous edge movement in MP layouts', () => {
  // Wide content cards with the host's 260px/80px/0px sidebars and 16px gutters.
  it.each([
    ['vertical', 276, 'right', false],
    ['collapsed', 96, 'right', false],
    ['horizontal', 16, 'left', false],
    ['horizontal', 16, 'right', false],
    ['mobile', 16, 'left', true],
    ['mobile', 16, 'right', true],
  ] as const)('keeps support on %s card at %spx toward the %s edge', async (_layout, left, side, mobile) => {
    const width = mobile ? 390 : 1280
    const stage = await setup(width, mobile)
    card(left, width - 16)
    const petWidth = stage.rect().width
    const edge = side === 'left' ? Math.max(0, left - petWidth / 2) : width - petWidth
    stage.drop(edge + (side === 'left' ? 10 : -10), 400)
    await vi.advanceTimersByTimeAsync(64)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(400)
    vi.mocked(Math.random).mockReturnValueOnce(0).mockReturnValue(0.9)
    stage.host.patch({ motionAllowed: true })
    await vi.advanceTimersByTimeAsync(5999)
    vi.mocked(Math.random)
      .mockReturnValueOnce(0.1)
      .mockReturnValueOnce(side === 'left' ? 0.1 : 0.9)
      .mockReturnValueOnce(0.1)
    const start = stage.anchors.length
    await vi.advanceTimersByTimeAsync(4000)
    expect(Number(stage.button.style.transform.match(/translate3d\(([^,]+)px/)?.[1])).toBeCloseTo(edge)
    expect(stage.button.closest('.agent-pet-ying')?.getAttribute('data-motion')).toBe('idle')
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(400)
    for (const frame of stage.anchors.slice(start)) {
      if (frame) expect(frame.y + frame.height).toBeCloseTo(400)
    }
    stage.unmount()
  })

  it.each([
    ['vertical', 276],
    ['collapsed', 96],
  ] as const)('still steps down from the %s interior card', async (_layout, left) => {
    const stage = await setup()
    card(left, 1264)
    stage.drop(left - 50, 400)
    await vi.advanceTimersByTimeAsync(64)
    vi.mocked(Math.random).mockReturnValueOnce(0).mockReturnValue(0.9)
    stage.host.patch({ motionAllowed: true })
    await vi.advanceTimersByTimeAsync(5999)
    vi.mocked(Math.random).mockReturnValueOnce(0.1).mockReturnValueOnce(0.1).mockReturnValueOnce(0.1)
    await vi.advanceTimersByTimeAsync(2500)
    expect(stage.rect().x + stage.rect().width / 2).toBeLessThan(left)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(800)
    stage.unmount()
  })
})

describe('MP App Dock across viewport widths', () => {
  it.each([
    [390, true],
    [800, false],
    [1280, false],
  ] as const)('reserves and releases the Dock at width %s', async (width, mobile) => {
    const stage = await setup(width, mobile, true)
    const wrapper = document.createElement('div')
    wrapper.className = 'footer-nav-container'
    wrapper.style.position = 'fixed'
    wrapper.style.pointerEvents = 'none'
    wrapper.getBoundingClientRect = () => new DOMRect(0, 696, width, 104)
    const bar = document.createElement('div')
    bar.className = 'v-card footer-nav-card'
    bar.style.position = 'relative'
    bar.style.pointerEvents = 'auto'
    bar.dataset.layoutFixture = ''
    bar.getBoundingClientRect = () => new DOMRect(width * 0.1, 696, width * 0.8, 64)
    wrapper.appendChild(bar)
    document.body.appendChild(wrapper)
    await vi.advanceTimersByTimeAsync(2200)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(688)
    wrapper.remove()
    await vi.advanceTimersByTimeAsync(2200)
    expect(stage.rect().y + stage.rect().height).toBeCloseTo(800)
    stage.unmount()
  })
})

describe('eye-anchored mobile Dock clearance', () => {
  it.each(['side', 'platform'] as const)('still prefers a clear %s before automatic sheltering', async clearSpot => {
    const stage = await setup(390, true)
    try {
      const rows = mobilePluginList()
      if (clearSpot === 'side') rows.at(-1)!.getBoundingClientRect = () => new DOMRect(16, 610, 160, 140)
      else rows[3].remove()
      mobileDock()
      await vi.advanceTimersByTimeAsync(2200)
      expect(stage.rect().height).toBe(96)
      expect(stage.button.style.clipPath).toBe('')
      if (clearSpot === 'side') {
        expect(stage.rect().x).toBeGreaterThan(150)
        expect(stage.rect().y + stage.rect().height).toBeCloseTo(696)
      } else expect(stage.rect().y + stage.rect().height).toBeCloseTo(610)
    } finally {
      stage.unmount()
    }
  })

  it.each([
    ['left', 0.6],
    ['right', 0.6],
    ['left', 1],
    ['right', 1],
    ['left', 1.3],
    ['right', 1.3],
    ['left', 1.6],
    ['right', 1.6],
  ] as const)('keeps the %s corner eye visible and draggable at scale %s', async (side, scale) => {
    const stage = await setup(390, true, false, scale)
    try {
      mobilePluginList()
      mobileDock()
      await vi.advanceTimersByTimeAsync(2200)
      const height = 120 * scale * 0.8
      const edge = side === 'left' ? 0 : 390 - height
      stage.drop(edge, 696)
      await vi.advanceTimersByTimeAsync(2200)
      if (side === 'left') expect(stage.rect().x).toBeCloseTo(0)
      else expect(stage.rect().x + stage.rect().width).toBeCloseTo(390)
      expect(stage.rect().y + stage.rect().height).toBeCloseTo(704)
      expect(stage.rect().height).toBeGreaterThan(0)
      expect(stage.rect().height).toBeLessThan(height)
      expect(parseFloat(stage.button.style.height)).toBeGreaterThanOrEqual(48)
      expect(stage.button.style.clipPath).toBe('')
      expect(stage.button.closest('.agent-pet-ying')?.getAttribute('data-motion')).toBe('peek')
      const parked = { ...stage.rect() }

      // Remaining controls must not trigger repeated walks or shrink the fallback again.
      vi.mocked(Math.random).mockReturnValue(0.1)
      stage.host.patch({ motionAllowed: true })
      const start = stage.anchors.length
      await vi.advanceTimersByTimeAsync(16000)
      for (const frame of stage.anchors.slice(start)) {
        if (frame) {
          expect(frame).toEqual(parked)
        }
      }
    } finally {
      stage.unmount()
    }
  })

  it('allows random peeks to touch the mobile Dock rather than leaving a gap', async () => {
    const stage = await setup(390, true, true)
    try {
      mobileDock()
      await vi.advanceTimersByTimeAsync(2200)
      vi.mocked(Math.random).mockReturnValue(0.1)
      stage.host.patch({ motionAllowed: true })
      const start = stage.anchors.length
      await vi.advanceTimersByTimeAsync(16000)
      expect(
        stage.anchors
          .slice(start)
          .some(frame => frame && frame.height < 96 && Math.abs(frame.y + frame.height - 704) < 0.01),
      ).toBe(true)
      expect(stage.button.style.clipPath).toBe('')
    } finally {
      stage.unmount()
    }
  })

  it('moves a stable eye from the screen edge to the Dock and back', async () => {
    const stage = await setup(390, true)
    try {
      mobilePluginList()
      await vi.advanceTimersByTimeAsync(2200)
      const height = stage.rect().height
      expect(height).toBeGreaterThan(0)
      expect(height).toBeLessThan(96)
      const dock = mobileDock()
      await vi.advanceTimersByTimeAsync(2200)
      expect(stage.rect().height).toBeCloseTo(height)
      expect(stage.rect().y + stage.rect().height).toBeCloseTo(704)
      expect(stage.button.style.clipPath).toBe('')
      dock.remove()
      await vi.advanceTimersByTimeAsync(2200)
      expect(stage.rect().height).toBeCloseTo(height)
      expect(stage.rect().y + stage.rect().height).toBeCloseTo(800)
    } finally {
      stage.unmount()
    }
  })

  it('recalculates the same eye after switching desktop and mobile scale', async () => {
    const stage = await setup(390, false)
    try {
      mobilePluginList()
      mobileDock()
      await vi.advanceTimersByTimeAsync(2200)
      const height = stage.rect().height
      expect(height).toBeLessThan(120)
      stage.host.patch({ isMobile: true })
      await vi.advanceTimersByTimeAsync(2200)
      expect(stage.rect().height).toBeGreaterThan(0)
      expect(stage.rect().height).toBeLessThan(96)
      expect(stage.rect().y + stage.rect().height).toBeCloseTo(704)
      expect(parseFloat(stage.button.style.height)).toBeGreaterThanOrEqual(48)
      expect(stage.button.style.clipPath).toBe('')
      stage.host.patch({ isMobile: false })
      await vi.advanceTimersByTimeAsync(2200)
      expect(stage.rect().height).toBeCloseTo(height)
    } finally {
      stage.unmount()
    }
  })

  it('resumes ordinary movement after the clickable rows stop blocking the Dock edge', async () => {
    const stage = await setup(390, true)
    try {
      const rows = mobilePluginList()
      mobileDock()
      await vi.advanceTimersByTimeAsync(2200)
      expect(stage.rect().height).toBeLessThan(96)
      const edge = stage.rect().x
      rows.forEach(row => row.classList.remove('v-card--link'))
      vi.mocked(Math.random).mockReturnValue(0.5)
      stage.host.patch({ motionAllowed: true })
      const start = stage.anchors.length
      await vi.advanceTimersByTimeAsync(16000)
      expect(stage.anchors.slice(start).some(frame => frame && Math.abs(frame.x - edge) > 10)).toBe(true)
      expect(stage.rect().height).toBe(96)
      expect(stage.button.style.clipPath).toBe('')
    } finally {
      stage.unmount()
    }
  })
})
