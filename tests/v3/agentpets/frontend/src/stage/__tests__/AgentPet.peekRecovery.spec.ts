import { render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { PeekEdge } from '@/stage/peek'
import type { AgentRect } from '@/host'

async function setup(edge: PeekEdge, pinned = false, covered = false, roam: 'floor' | 'surfaces' = 'floor') {
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
  let anchor: AgentRect | null = null
  const pet = createMockPet('stage', 'ying', { onAnchor: rect => (anchor = rect) })
  await pet.storage.set({ xRatio: edge === 'right' ? 1 : 0, yRatio: 1, ...(pinned ? { peekEdge: edge } : {}) })
  const save = vi.spyOn(pet.storage, 'set')
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam },
    },
  })
  await vi.advanceTimersByTimeAsync(64)
  const root = view.container.querySelector('[data-motion]')!
  return {
    host,
    root,
    save,
    rect: () => anchor!,
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

  it('finds a new floor position when the original corner remains covered', async () => {
    const stage = await setup('bottom', false, true)
    try {
      expect(stage.root.getAttribute('data-peek-edge')).toBe('bottom')
      const control = document.querySelector<HTMLElement>('[data-peek-recovery]')!
      control.getBoundingClientRect = () => new DOMRect(0, 600, 240, 200)
      Object.defineProperty(document, 'elementsFromPoint', {
        configurable: true,
        value: (x: number, y: number) => (x < 240 && y >= 600 ? [control, document.body] : [document.body]),
      })
      await vi.advanceTimersByTimeAsync(14_000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.root.getAttribute('data-motion')).not.toBe('peek')
      expect(Math.max(0, 240 - stage.rect().x) / stage.rect().width).toBeLessThanOrEqual(0.1)
      expect(stage.save).not.toHaveBeenCalled()
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it('does not relocate a shelter while host work has priority', async () => {
    const stage = await setup('bottom', false, true)
    try {
      stage.host.patch({ phase: 'thinking', thinking: true })
      const control = document.querySelector<HTMLElement>('[data-peek-recovery]')!
      control.getBoundingClientRect = () => new DOMRect(0, 600, 240, 200)
      Object.defineProperty(document, 'elementsFromPoint', {
        configurable: true,
        value: (x: number, y: number) => (x < 240 && y >= 600 ? [control, document.body] : [document.body]),
      })
      await vi.advanceTimersByTimeAsync(20_000)
      expect(stage.root.getAttribute('data-peek-edge')).toBe('bottom')
      stage.host.patch({ phase: 'idle', thinking: false })
      await vi.advanceTimersByTimeAsync(14_000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.save).not.toHaveBeenCalled()
    } finally {
      stage.unmount()
    }
  })

  it('finds a newly exposed surface while the whole floor remains covered', async () => {
    const stage = await setup('bottom', false, true, 'surfaces')
    const card = document.createElement('div')
    card.className = 'v-card'
    card.dataset.peekRecovery = 'true'
    card.getBoundingClientRect = () => new DOMRect(240, 400, 480, 160)
    try {
      expect(stage.root.getAttribute('data-peek-edge')).toBe('bottom')
      const control = document.querySelector<HTMLElement>('button[data-peek-recovery]')!
      document.body.appendChild(card)
      Object.defineProperty(document, 'elementsFromPoint', {
        configurable: true,
        value: (x: number, y: number) =>
          y >= 600
            ? [control, document.body]
            : x >= 240 && x <= 720 && y >= 400 && y <= 560
              ? [card, document.body]
              : [document.body],
      })
      await vi.advanceTimersByTimeAsync(14_000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.rect().y + stage.rect().height).toBe(400)
      expect(stage.save).not.toHaveBeenCalled()
    } finally {
      stage.unmount()
    }
  })

  it('relocates safely without animation when reduced motion is enabled', async () => {
    const stage = await setup('bottom', false, true)
    try {
      stage.host.patch({ motionAllowed: false, reducedMotion: true })
      const control = document.querySelector<HTMLElement>('[data-peek-recovery]')!
      control.getBoundingClientRect = () => new DOMRect(0, 600, 240, 200)
      Object.defineProperty(document, 'elementsFromPoint', {
        configurable: true,
        value: (x: number, y: number) => (x < 240 && y >= 600 ? [control, document.body] : [document.body]),
      })
      await vi.advanceTimersByTimeAsync(8000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.root.getAttribute('data-motion')).toBe('idle')
      expect(stage.save).not.toHaveBeenCalled()
    } finally {
      stage.unmount()
    }
  })
})
