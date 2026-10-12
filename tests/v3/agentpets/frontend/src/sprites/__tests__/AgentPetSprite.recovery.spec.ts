import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMockPet } from '@/dev/mockHost'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'

function images() {
  const requests: ControlledImage[] = []
  class ControlledImage {
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    naturalWidth = 128
    naturalHeight = 128
    src = ''
    constructor() {
      requests.push(this)
    }
  }
  vi.stubGlobal('Image', ControlledImage)
  return requests
}

function api() {
  return {
    get: vi.fn().mockResolvedValue({
      success: true,
      data: {
        pack: { id: 'mine', name: '我的', grid: { cols: 1, rows: 1 }, frames: { idle: 0 }, actions: {} },
        sheet_src: 'https://example.com/missing.png',
      },
    }),
    post: vi.fn(),
  }
}

describe('sprite image recovery', () => {
  it('does not report a user pack ready before the image has loaded', async () => {
    const requests = images()
    const view = mount(AgentPetSprite, { props: { api: api(), pet: createMockPet('renderer', 'mine') } })
    try {
      await flushPromises()
      expect(view.emitted('load-state')).not.toContainEqual(['ready'])
      requests.find(image => image.src.includes('missing.png'))!.onload?.()
      await flushPromises()
      expect(view.emitted('load-state')).toContainEqual(['ready'])
      expect(view.attributes('data-pack')).toBe('mine')
    } finally {
      view.unmount()
    }
  })

  it.each([false, true])('handles image errors with strict preview %s', async strictPreview => {
    const requests = images()
    const view = mount(AgentPetSprite, { props: { api: api(), pet: createMockPet('renderer', 'mine'), strictPreview } })
    try {
      await flushPromises()
      requests.find(image => image.src.includes('missing.png'))!.onerror?.()
      await flushPromises()
      expect(view.emitted('load-state')).toContainEqual(['error'])
      if (strictPreview) expect(view.find('.agent-pet-sprites__frame').exists()).toBe(false)
      else {
        requests.find(image => image.src.includes('projector-cat'))?.onload?.()
        await flushPromises()
        expect(view.attributes('data-pack')).toBe('projector-cat')
      }
    } finally {
      view.unmount()
    }
  })

  it('cleans up an unresolved pack request on unmount', async () => {
    vi.useFakeTimers()
    const provider = api()
    provider.get.mockReturnValue(new Promise(() => undefined))
    const view = mount(AgentPetSprite, { props: { api: provider, pet: createMockPet('renderer', 'mine') } })
    await vi.advanceTimersByTimeAsync(1)
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('sprite loading boundaries', () => {
  it.each(['timeout', 'empty-size'])('rejects an image with %s and clears its handlers', async failure => {
    vi.useFakeTimers()
    const requests = images()
    const view = mount(AgentPetSprite, {
      props: { api: api(), pet: createMockPet('renderer', 'mine'), strictPreview: true },
    })
    try {
      await flushPromises()
      const image = requests[0]
      if (failure === 'timeout') await vi.advanceTimersByTimeAsync(5000)
      else {
        image.naturalHeight = 0
        image.onload?.()
        await flushPromises()
      }
      expect(view.emitted('load-state')).toContainEqual(['error'])
      expect(view.emitted('load-state')).not.toContainEqual(['ready'])
      expect(image.onload).toBeNull()
      expect(image.onerror).toBeNull()
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      view.unmount()
    }
  })

  it('releases pending image handlers and ignores completion after unmount', async () => {
    vi.useFakeTimers()
    const requests = images()
    const states = vi.fn()
    const view = mount(AgentPetSprite, {
      props: { api: api(), pet: createMockPet('renderer', 'mine'), onLoadState: states },
    })
    await flushPromises()
    const complete = requests[0].onload
    view.unmount()
    await flushPromises()
    complete?.()
    await flushPromises()
    expect(requests[0].onload).toBeNull()
    expect(requests[0].onerror).toBeNull()
    expect(states).not.toHaveBeenCalledWith('ready')
    expect(vi.getTimerCount()).toBe(0)
  })
})
