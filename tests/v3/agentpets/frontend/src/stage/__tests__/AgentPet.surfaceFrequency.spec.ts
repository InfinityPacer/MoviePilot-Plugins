import { render } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import AgentPet from '@/stage/AgentPet.vue'
import * as surfaces from '@/stage/surfaces'

function measured(el: HTMLElement, left: number, top: number, width: number, height: number) {
  el.getBoundingClientRect = () =>
    ({ left, top, right: left + width, bottom: top + height, width, height, x: left, y: top }) as DOMRect
  return el
}

describe('stage surface query frequency', () => {
  it.each([
    ['ordinary', 10, false],
    ['long', 3000, false],
    ['previewRoot', 10, true],
  ] as const)('keeps %s idle checks local and stops polling when hidden', async (name, count, contained) => {
    vi.useFakeTimers()
    const host = createMockHost('AgentPets')
    host.patch({ motionAllowed: false })
    const pet = createMockPet('stage', 'ying')
    await pet.storage.set({ xRatio: 0.3, yRatio: 0 })
    const scope = measured(document.createElement('section'), 100, 100, 1000, 800)
    document.body.appendChild(scope)
    for (let index = 0; index < count; index++) {
      const top = index < count - 10 ? -10000 + index : 400 + (index - (count - 10)) * 20
      const card = measured(document.createElement('div'), contained ? 100 : 0, top + (contained ? 100 : 0), 1000, 60)
      card.className = 'v-card'
      scope.appendChild(card)
    }
    const scan = vi.spyOn(surfaces, 'querySurfaces')
    const support = vi.spyOn(surfaces, 'measureSurface')
    const view = render(AgentPet, {
      props: {
        agent: host,
        pet,
        pluginId: 'AgentPets',
        previewRoot: contained ? scope : null,
        settingsOverride: { scale: 1, speed: 1, roam: 'surfaces' },
      },
    })
    try {
      await vi.advanceTimersByTimeAsync(64)
      const startupScans = scan.mock.calls.length
      const startupSupport = support.mock.calls.length
      expect(startupScans).toBeGreaterThan(0)
      await vi.advanceTimersByTimeAsync(2000)
      expect(scan).toHaveBeenCalledTimes(startupScans)
      expect(support.mock.calls.length - startupSupport).toBe(4)
      console.info(
        JSON.stringify({
          scenario: name,
          cards: count,
          simulatedIdleMs: 2000,
          startupScans,
          additionalIdleScans: 0,
          supportingElementChecks: 4,
        }),
      )
      host.patch({ pageVisible: false })
      await vi.advanceTimersByTimeAsync(64)
      const hiddenScans = scan.mock.calls.length
      const hiddenSupport = support.mock.calls.length
      await vi.advanceTimersByTimeAsync(2000)
      expect(scan).toHaveBeenCalledTimes(hiddenScans)
      expect(support).toHaveBeenCalledTimes(hiddenSupport)
    } finally {
      view.unmount()
      host.dispose()
      scope.remove()
      vi.useRealTimers()
    }
  })
})
