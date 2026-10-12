import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { AgentRect } from '@/host'
import AgentPet from '@/stage/AgentPet.vue'

const cleanup: Array<() => void> = []
afterEach(() =>
  cleanup
    .splice(0)
    .reverse()
    .forEach(dispose => dispose()),
)

describe('stage recovery', () => {
  it.each([
    [390, -1],
    [390, 1],
    [1024, -1],
    [1024, 1],
  ])('stays accessible when a card leaves a %ipx viewport toward %i', async (width, direction) => {
    vi.useFakeTimers()
    vi.stubGlobal('innerWidth', width)
    const host = createMockHost('AgentPets')
    host.patch({ motionAllowed: false })
    cleanup.push(() => host.dispose())
    const anchors: Array<AgentRect | null> = []
    const pet = createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) })
    await pet.storage.set({ xRatio: 0.3, yRatio: 0 })
    let left = 0
    const card = document.createElement('div')
    card.className = 'v-card'
    card.getBoundingClientRect = () =>
      ({ x: left, y: 400, left, top: 400, right: left + width, bottom: 600, width, height: 200 }) as DOMRect
    document.body.appendChild(card)
    cleanup.push(() => card.remove())
    const view = render(AgentPet, {
      props: { agent: host, pet, pluginId: 'AgentPets', settingsOverride: { scale: 1, speed: 1, roam: 'surfaces' } },
    })
    cleanup.push(() => view.unmount())
    await vi.advanceTimersByTimeAsync(32)
    expect(anchors.at(-1)!.y + anchors.at(-1)!.height).toBe(400)
    left = direction * (width + 100)
    window.dispatchEvent(new Event('scroll'))
    await vi.advanceTimersByTimeAsync(600)
    const last = anchors.at(-1)!
    expect(last.x).toBeGreaterThanOrEqual(0)
    expect(last.x + last.width).toBeLessThanOrEqual(width)
    expect(last.y + last.height).toBe(window.innerHeight)
  })

  it.each(['settings', 'storage'])('uses a fallback when %s never completes and ignores late data', async pending => {
    vi.useFakeTimers()
    const host = createMockHost('AgentPets')
    host.patch({ motionAllowed: false })
    cleanup.push(() => host.dispose())
    const pet = createMockPet('stage', 'ying')
    let resolve!: (value: unknown) => void
    const stalled = new Promise(done => {
      resolve = done
    })
    const api = { get: vi.fn().mockResolvedValue({ success: true, data: { scale: 1, speed: 1, roam: 'floor' } }) }
    if (pending === 'settings') api.get.mockReturnValue(stalled)
    else pet.storage.get = vi.fn().mockReturnValue(stalled)
    const view = render(AgentPet, { props: { agent: host, pet, api, pluginId: 'AgentPets' } })
    cleanup.push(() => view.unmount())
    await vi.advanceTimersByTimeAsync(5100)
    const button = view.container.querySelector('button')!
    expect(button.style.display).not.toBe('none')
    const before = button.style.transform
    resolve(pending === 'settings' ? { success: true, data: { scale: 1.6, speed: 2, roam: 'free' } } : { xRatio: 0 })
    await vi.advanceTimersByTimeAsync(32)
    expect(button.style.transform).toBe(before)
    expect(button.style.height).toBe('120px')
  })

  it('releases pending startup timers on unmount', async () => {
    vi.useFakeTimers()
    const host = createMockHost('AgentPets')
    const pet = createMockPet('stage', 'ying')
    const api = { get: vi.fn().mockReturnValue(new Promise(() => undefined)) }
    const view = render(AgentPet, { props: { agent: host, pet, api, pluginId: 'AgentPets' } })
    await vi.advanceTimersByTimeAsync(1)
    view.unmount()
    host.dispose()
    expect(vi.getTimerCount()).toBe(0)
  })
})
