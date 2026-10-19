import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { PeekEdge } from '@/stage/peek'

async function setup(edge: PeekEdge, pinned = false, covered = false) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.9)
  vi.stubGlobal('innerWidth', 1280)
  vi.stubGlobal('innerHeight', 800)
  if (covered) {
    const control = document.createElement('button')
    control.dataset.peekRecovery = 'true'
    control.getBoundingClientRect = () => new DOMRect(0, 600, 1280, 200)
    document.body.appendChild(control)
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (_x: number, y: number) => (y >= 600 ? [control, document.body] : [document.body]),
    })
  }
  const host = createMockHost('AgentPets')
  const pet = createMockPet('stage', 'ying')
  await pet.storage.set({ xRatio: edge === 'right' ? 1 : 0, yRatio: 1, ...(pinned ? { peekEdge: edge } : {}) })
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam: 'floor' },
    },
  })
  await vi.advanceTimersByTimeAsync(64)
  const root = view.container.querySelector('[data-motion]')!
  return {
    host,
    root,
    unmount() {
      view.unmount()
      host.dispose()
    },
  }
}

afterEach(() => {
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  document.querySelectorAll('[data-peek-recovery]').forEach(el => el.remove())
})

describe('peek recovery after reduced motion', () => {
  it.each(['bottom', 'left', 'right'] as const)('restores automatic %s exits across repeated toggles', async edge => {
    const stage = await setup(edge)
    try {
      await vi.advanceTimersByTimeAsync(13_135)
      vi.mocked(Math.random)
        .mockReturnValueOnce(0.1)
        .mockReturnValueOnce(edge === 'right' ? 0.9 : 0.1)
        .mockReturnValueOnce(edge === 'bottom' ? 0.25 : 0.75)
      await vi.advanceTimersByTimeAsync(33)
      expect(stage.root.getAttribute('data-peek-edge')).toBe(edge)
      for (const beforeFreeze of [0, 1000, 3000]) {
        await vi.advanceTimersByTimeAsync(beforeFreeze)
        stage.host.patch({ motionAllowed: false })
        await vi.advanceTimersByTimeAsync(10_000)
        expect(stage.root.getAttribute('data-peek-edge')).toBe(edge)
        stage.host.patch({ motionAllowed: true })
      }
      await vi.advanceTimersByTimeAsync(10_000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.root.getAttribute('data-motion')).not.toBe('peek')
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['bottom', 'left', 'right'] as const)('keeps manually pinned %s peeks pinned', async edge => {
    const stage = await setup(edge, true)
    try {
      stage.host.patch({ motionAllowed: false })
      await vi.advanceTimersByTimeAsync(10_000)
      stage.host.patch({ motionAllowed: true })
      await vi.advanceTimersByTimeAsync(20_000)
      expect(stage.root.getAttribute('data-peek-edge')).toBe(edge)
    } finally {
      stage.unmount()
    }
  })

  it('retains clearance shelter until the control is no longer covered', async () => {
    const stage = await setup('bottom', false, true)
    try {
      expect(stage.root.getAttribute('data-peek-edge')).toBe('bottom')
      stage.host.patch({ motionAllowed: false })
      await vi.advanceTimersByTimeAsync(10_000)
      stage.host.patch({ motionAllowed: true })
      await vi.advanceTimersByTimeAsync(20_000)
      expect(stage.root.getAttribute('data-peek-edge')).toBe('bottom')
      delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
      await vi.advanceTimersByTimeAsync(3000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
    } finally {
      stage.unmount()
    }
  })
})
