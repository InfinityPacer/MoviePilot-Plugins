import { render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { createMockPet } from '@/dev/mockHost'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import { NOMINAL_WALK_HEIGHTS_PER_SECOND } from '@/stage/playback'

async function setup(props: Record<string, unknown> = {}) {
  vi.useFakeTimers()
  const pack = {
    id: 'playback-fixture',
    name: 'Playback fixture',
    grid: { cols: 8, rows: 1 },
    frames: { idle: 0, a: 1, b: 2, c: 3, d: 4, e: 5, f: 6 },
    actions: {
      idle: { frames: ['idle'], frame_ms: 100, loop: false },
      'running-left': { frames: ['a', 'b', 'c', 'd', 'e', 'f'], frame_ms: 100, loop: true },
      wave: { frames: ['a', 'b', 'c'], frame_ms: 100, frame_durations: [100, 200, 300], loop: true },
    },
  }
  const api = {
    get: vi.fn().mockResolvedValue({ success: true, data: { pack, sheet_src: 'fixture.png' } }),
    post: vi.fn(),
  }
  const view = render(AgentPetSprite, {
    props: { pet: createMockPet('stage', pack.id), api, pluginId: 'AgentPets', ...props },
  })
  await flushPromises()
  const root = view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
  return { view, root, api }
}

describe('sprite movement and single-cycle playback', () => {
  it('never advances a distance-driven gait from a wall-clock timer', async () => {
    const { view, root, api } = await setup({ action: 'running-left', walkTravel: 0 })
    expect(root.dataset.frame).toBe('a')
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(2000)
    expect(root.dataset.frame).toBe('a')
    for (const [ms, frame] of [
      [101, 'b'],
      [301, 'd'],
      [501, 'f'],
      [601, 'a'],
    ] as const) {
      await view.rerender({ walkTravel: (ms / 1000) * NOMINAL_WALK_HEIGHTS_PER_SECOND })
      expect(root.dataset.frame).toBe(frame)
      expect(vi.getTimerCount()).toBe(0)
    }
    await view.rerender({ action: 'idle', walkTravel: undefined })
    expect(root.dataset.frame).toBe('idle')
    expect(api.get).toHaveBeenCalledOnce()
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('lets disabled motion and explicit physical phases remain static', async () => {
    const { view, root } = await setup({ action: 'running-left', framePhase: 0.9 })
    expect(root.dataset.frame).toBe('f')
    await vi.advanceTimersByTimeAsync(5000)
    expect(root.dataset.frame).toBe('f')
    await view.rerender({ motionActive: false })
    expect(root.dataset.frame).toBe('a')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('reports one actual cycle and holds its last frame even for looping artwork', async () => {
    const completed = vi.fn()
    const { view, root } = await setup({ action: 'wave', playbackRound: 12, 'onAction-complete': completed })
    await vi.advanceTimersByTimeAsync(599)
    expect(root.dataset.frame).toBe('c')
    expect(completed).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(completed).toHaveBeenCalledExactlyOnceWith(12)
    await vi.advanceTimersByTimeAsync(3000)
    expect(completed).toHaveBeenCalledOnce()
    expect(root.dataset.frame).toBe('c')
    expect(vi.getTimerCount()).toBe(0)
    await view.rerender({ playbackRound: 13 })
    expect(root.dataset.frame).toBe('a')
    await vi.advanceTimersByTimeAsync(600)
    expect(completed).toHaveBeenLastCalledWith(13)
    expect(completed).toHaveBeenCalledTimes(2)
  })

  it('cancels an old cycle when the same action is replayed with a new owner', async () => {
    const completed = vi.fn()
    const { view } = await setup({ action: 'wave', playbackRound: 21, 'onAction-complete': completed })
    await vi.advanceTimersByTimeAsync(400)
    await view.rerender({ playbackRound: 22 })
    await vi.advanceTimersByTimeAsync(200)
    expect(completed).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(400)
    expect(completed).toHaveBeenCalledExactlyOnceWith(22)
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
