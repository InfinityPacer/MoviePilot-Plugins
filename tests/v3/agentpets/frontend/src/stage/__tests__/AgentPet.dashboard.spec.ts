import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { AgentRect } from '@/host'
import * as geometry from '@/stage/geometry'

afterEach(() => {
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  document.querySelectorAll('[data-dashboard-probe]').forEach(el => el.remove())
})

function fixture(className: string, rect: DOMRect, parent: Element = document.body, tag = 'div') {
  const el = document.createElement(tag)
  el.className = className
  el.dataset.dashboardProbe = 'true'
  el.getBoundingClientRect = () => rect
  parent.appendChild(el)
  return el
}

describe('mobile dashboard right edge with fixed Dock and poster controls', () => {
  it.each([
    ['right-edge-1.5', 1.5, 1],
    ['right-edge-1.3', 1.3, 1],
    ['inset-1.5', 1.5, 0.95],
  ] as const)('%s', async (_name, scale, xRatio) => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.9)
    vi.stubGlobal('innerWidth', 430)
    vi.stubGlobal('innerHeight', 935)
    vi.stubGlobal(
      'visualViewport',
      Object.assign(new EventTarget(), {
        width: 430,
        height: 935,
        offsetLeft: 0,
        offsetTop: 0,
      }),
    )
    const origin = Date.now()
    const supportFailures: unknown[] = []
    const original = geometry.checkSupport
    vi.spyOn(geometry, 'checkSupport').mockImplementation((...args) => {
      const result = original(...args)
      if (result.kind === 'fall') {
        const [previous, next, center, viewport, height, , width = 0] = args
        const maxX = geometry.xBounds(viewport, width)[1]
        supportFailures.push({
          at: Date.now() - origin,
          previous,
          next,
          center,
          height,
          width,
          reconstructedLeft: center - width / 2,
          maxX,
          excess: center - width / 2 - maxX,
        })
      }
      return result
    })
    const host = createMockHost('AgentPets')
    host.patch({
      isMobile: true,
      motionAllowed: true,
      viewport: {
        width: 430,
        height: 935,
        keyboardInset: 0,
        safeArea: { top: 59, right: 0, bottom: 34, left: 0 },
      },
    })
    let anchor: AgentRect | null = null
    const pet = createMockPet('stage', 'ying', {
      onAnchor: rect => {
        anchor = rect
      },
    })
    await pet.storage!.set({ roam: 'surfaces', xRatio, yRatio: 1 })
    const view = render(AgentPet, {
      props: {
        agent: host,
        pet,
        pluginId: 'AgentPets',
        settingsOverride: { scale, speed: 1, roam: 'surfaces' },
      },
    })
    await vi.advanceTimersByTimeAsync(64)

    fixture('v-card storage', new DOMRect(16, 139, 398, 155))
    fixture('v-card media', new DOMRect(16, 313, 398, 232))
    const douban = fixture('v-card dc-card', new DOMRect(16, 563, 398, 550))
    for (let col = 0; col < 6; col++) {
      fixture('dc-poster', new DOMRect(35 + col * 63, 724, 60, 90), douban, 'a')
    }
    const dock = fixture('footer-nav-container', new DOMRect(0, 830, 430, 105))
    dock.style.position = 'fixed'
    dock.style.pointerEvents = 'none'
    const primary = fixture('v-card footer-nav-card', new DOMRect(24, 830, 310, 64), dock)
    primary.style.pointerEvents = 'auto'
    const accessory = fixture('v-card footer-nav-card', new DOMRect(342, 830, 64, 64), dock)
    accessory.style.pointerEvents = 'auto'
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (x: number, y: number) => [
        ...Array.from(document.querySelectorAll<HTMLElement>('[data-dashboard-probe]'))
          .reverse()
          .filter(el => {
            const r = el.getBoundingClientRect()
            return el.style.pointerEvents !== 'none' && x >= r.left && x < r.right && y >= r.top && y < r.bottom
          }),
        document.body,
      ],
    })
    const transitions: Array<{
      at: number
      motion: string | null | undefined
      anchor: AgentRect | null
    }> = []
    let previous = ''
    for (let elapsed = 0; elapsed < 24000; elapsed += 16) {
      await vi.advanceTimersByTimeAsync(16)
      const motion = view.container.querySelector('[data-motion]')?.getAttribute('data-motion')
      if (motion !== previous) {
        transitions.push({ at: Date.now() - origin, motion, anchor })
        previous = motion ?? ''
      }
    }
    const falls = transitions.filter(entry => entry.motion === 'fall').length
    const finalAnchor = anchor as AgentRect | null
    view.unmount()
    host.dispose()
    expect(falls).toBe(1)
    expect(supportFailures).toHaveLength(0)
    // Bubble anchors are deduplicated at whole-pixel precision.
    expect(Math.abs(finalAnchor!.y + finalAnchor!.height - 563)).toBeLessThan(1)
  })
})
