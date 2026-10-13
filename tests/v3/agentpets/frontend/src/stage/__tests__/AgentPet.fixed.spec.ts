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
function pointer(type: string, clientX: number, clientY: number) {
  const event = new MouseEvent(type, { bubbles: true, button: 0, clientX, clientY })
  Object.defineProperty(event, 'pointerId', { value: 1 })
  return event
}
async function setup() {
  vi.useFakeTimers()
  vi.stubGlobal('innerWidth', 390)
  vi.stubGlobal('innerHeight', 844)
  const visual = Object.assign(new EventTarget(), { width: 390, height: 844, offsetLeft: 0, offsetTop: 0 })
  vi.stubGlobal('visualViewport', visual)
  const host = createMockHost('AgentPets')
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'ying', { onAnchor: value => anchors.push(value) })
  await pet.storage.set({ xRatio: 0.5, yRatio: 0.8 })
  const save = vi.spyOn(pet.storage, 'set')
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam: 'surfaces', movement: 'fixed' },
    },
  })
  cleanup.push(
    () => host.dispose(),
    () => view.unmount(),
  )
  await vi.advanceTimersByTimeAsync(64)
  const button = view.container.querySelector('button')!
  const rect = () => anchors.at(-1)!
  return { host, pet, save, view, button, rect, visual }
}
describe('fixed placement', () => {
  it('stays put through idle and session actions, and stops immediately after dragging', async () => {
    const s = await setup()
    const original = s.rect()
    await vi.advanceTimersByTimeAsync(45000)
    expect(s.rect()).toEqual(original)
    s.host.patch({ phase: 'thinking' })
    await vi.advanceTimersByTimeAsync(32)
    expect(s.view.container.querySelector('[data-pose]')?.getAttribute('data-pose')).toBe('think')
    expect(s.rect()).toEqual(original)
    s.button.dispatchEvent(pointer('pointerdown', original.x + 10, original.y + 10))
    window.dispatchEvent(pointer('pointermove', 90, 180))
    window.dispatchEvent(pointer('pointerup', 90, 180))
    await vi.advanceTimersByTimeAsync(32)
    expect(s.rect().x).toBeCloseTo(80)
    expect(s.rect().y).toBeCloseTo(170)
    expect(s.view.container.querySelector('[data-motion]')?.getAttribute('data-motion')).toBe('idle')
    await vi.advanceTimersByTimeAsync(45000)
    expect(s.rect().y).toBeCloseTo(170)
    expect(s.save).toHaveBeenCalled()
  })
  it('restores the preferred point after a keyboard or orientation change without persisting the clamp', async () => {
    const s = await setup()
    const original = { ...s.rect() }
    s.visual.height = 360
    s.visual.width = 260
    s.visual.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(64)
    expect(s.rect().y + s.rect().height).toBeLessThanOrEqual(360)
    expect(s.rect().height).toBeGreaterThanOrEqual(48)
    s.host.patch({ pageVisible: false })
    await vi.advanceTimersByTimeAsync(32)
    expect(s.save.mock.calls.at(-1)?.[0]).toMatchObject({ xRatio: 0.5, yRatio: 0.8 })
    s.visual.height = 844
    s.visual.width = 390
    s.visual.dispatchEvent(new Event('resize'))
    s.host.patch({ pageVisible: true })
    await vi.advanceTimersByTimeAsync(64)
    expect(s.rect()).toEqual(original)
  })
  it('cancels an in-flight fall when fixed and restores the saved activity range when switched back', async () => {
    const s = await setup()
    await s.view.rerender({ settingsOverride: { scale: 1, speed: 1, roam: 'floor', movement: 'auto' } })
    await vi.advanceTimersByTimeAsync(32)
    expect(s.view.container.querySelector('[data-motion]')?.getAttribute('data-motion')).toBe('fall')
    await s.view.rerender({ settingsOverride: { scale: 1, speed: 1, roam: 'floor', movement: 'fixed' } })
    await vi.advanceTimersByTimeAsync(32)
    const fixed = s.rect().y
    await vi.advanceTimersByTimeAsync(15000)
    expect(s.rect().y).toBe(fixed)
    await s.view.rerender({ settingsOverride: { scale: 1, speed: 1, roam: 'floor', movement: 'auto' } })
    await vi.advanceTimersByTimeAsync(2000)
    expect(s.rect().y + s.rect().height).toBeCloseTo(844)
  })
})
