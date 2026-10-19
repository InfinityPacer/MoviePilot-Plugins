import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { AgentRect } from '@/host'
import * as geometry from '@/stage/geometry'

afterEach(() => {
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  document.querySelectorAll('[data-probe]').forEach(el => el.remove())
})

describe('autonomous mobile step-off landing clearance', () => {
  it.each([
    ['no-idle-step-off', 0.9],
    ['repeated-idle-step-off', 0.1],
    ['ground-control-removed', 0.1],
    ['ground-control-clears-later', 0.1],
  ] as const)('%s', async (name, random) => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(random)
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('innerHeight', 844)
    vi.stubGlobal(
      'visualViewport',
      Object.assign(new EventTarget(), {
        width: 390,
        height: 844,
        offsetLeft: 0,
        offsetTop: 0,
      }),
    )
    const origin = Date.now()
    const support: unknown[] = []
    const original = geometry.checkSupport
    vi.spyOn(geometry, 'checkSupport').mockImplementation((...args) => {
      const result = original(...args)
      if (result.kind === 'fall') support.push({ at: Date.now() - origin, args, result })
      return result
    })
    const host = createMockHost('AgentPets')
    host.patch({ isMobile: true, motionAllowed: true })
    let anchor: AgentRect | null = null
    const pet = createMockPet('stage', 'ying', {
      onAnchor: rect => {
        anchor = rect
      },
    })
    const view = render(AgentPet, {
      props: { agent: host, pet, pluginId: 'AgentPets', settingsOverride: { scale: 1.3, speed: 1, roam: 'surfaces' } },
    })
    await vi.advanceTimersByTimeAsync(64)
    const card = document.createElement('div')
    card.className = 'v-card'
    card.dataset.probe = 'card'
    card.getBoundingClientRect = () => new DOMRect(80, 500, 160, 180)
    const control = document.createElement('button')
    control.dataset.probe = 'control'
    control.getBoundingClientRect = () => new DOMRect(0, 680, 390, 164)
    document.body.append(card, control)
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (x: number, y: number) => {
        if (control.isConnected && y >= 680 && y < 844) return [control, document.body]
        if (x >= 80 && x <= 240 && y >= 500 && y < 680) return [card, document.body]
        return [document.body]
      },
    })
    const transitions: unknown[] = []
    let previous = ''
    for (let elapsed = 0; elapsed < 48000; elapsed += 32) {
      if (name === 'ground-control-clears-later' && elapsed >= 20000 && control.isConnected) {
        expect(transitions.filter(entry => (entry as { motion: string }).motion === 'fall')).toHaveLength(1)
        control.remove()
      }
      if (name === 'ground-control-removed' && elapsed >= 3000 && control.isConnected) control.remove()
      await vi.advanceTimersByTimeAsync(32)
      const motion = view.container.querySelector('[data-motion]')?.getAttribute('data-motion')
      if (motion !== previous) {
        transitions.push({ at: Date.now() - origin, motion, anchor })
        previous = motion ?? ''
      }
    }
    const falls = transitions.filter(entry => (entry as { motion: string }).motion === 'fall').length
    view.unmount()
    host.dispose()
    expect(support).toHaveLength(0)
    expect(falls).toBe(name === 'no-idle-step-off' || name === 'repeated-idle-step-off' ? 1 : 2)
  })
})
