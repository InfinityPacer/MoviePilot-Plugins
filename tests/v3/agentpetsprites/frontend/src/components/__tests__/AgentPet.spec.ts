import { render } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import AgentPet from '@/components/AgentPet.vue'
import { createMockPet } from '@/dev/mockHost'

async function flush() {
  for (let index = 0; index < 4; index += 1) await Promise.resolve()
}

describe('AgentPet (sprites)', () => {
  it('plays the builtin intent sequence and stops on non-looping actions', async () => {
    vi.useFakeTimers()
    const view = render(AgentPet, { props: { pet: createMockPet('renderer', 'projector-cat'), intent: 'success' } })
    const root = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    expect(root.dataset.action).toBe('success')
    expect(root.dataset.frame).toBe('jump')
    await vi.advanceTimersByTimeAsync(260)
    expect(root.dataset.frame).toBe('wave')
    await vi.advanceTimersByTimeAsync(260 * 10)
    expect(root.dataset.frame).toBe('idle')
  })

  it('prefers the host action over the intent and shows a static frame when motion is off', async () => {
    vi.useFakeTimers()
    const view = render(AgentPet, {
      props: { pet: createMockPet('renderer', 'projector-cat'), action: 'happy-jump', motionActive: false },
    })
    const root = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    expect(root.dataset.action).toBe('happy-jump')
    await vi.advanceTimersByTimeAsync(2000)
    expect(root.dataset.frame).toBe('jump')
  })

  it('loads a user pack through the instance api', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        success: true,
        data: {
          pack: { id: 'mine', name: '我的', grid: { cols: 1, rows: 1 }, frames: { idle: 0 }, actions: {} },
          sheet_src: 'data:image/png;base64,AAAA',
        },
      }),
      post: vi.fn(),
    }
    const view = render(AgentPet, { props: { pet: createMockPet('renderer', 'mine'), api, pluginId: 'Clone1' } })
    await flush()
    expect(api.get).toHaveBeenCalledWith('plugin/Clone1/pack?key=mine')
    expect(view.container.querySelector('.agent-pet-sprites')).toHaveAttribute('data-pack', 'mine')
  })

  it('falls back to the builtin pack when the api fails', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const api = { get: vi.fn().mockResolvedValue({ success: false, message: 'gone' }), post: vi.fn() }
    const view = render(AgentPet, { props: { pet: createMockPet('renderer', 'gone'), api } })
    await flush()
    expect(view.container.querySelector('.agent-pet-sprites')).toHaveAttribute('data-pack', 'projector-cat')
    expect(warn).toHaveBeenCalled()
  })
})
