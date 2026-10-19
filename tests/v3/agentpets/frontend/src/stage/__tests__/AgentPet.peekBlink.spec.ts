import { fireEvent, render } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import { BUILTIN_PACKS } from '@/sprites/schema'
import type { PeekEdge } from '@/stage/peek'

const BLINKING_PETS = [
  ['ying', 'blink'],
  ['builtin-nailong', 'frame-001'],
  ['builtin-kurisu', 'frame-001'],
  ['builtin-kurisu-z256', 'blink'],
] as const
const EDGES: PeekEdge[] = ['bottom', 'left', 'right']

async function setup(key: string, edge: PeekEdge, preview = false) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  vi.stubGlobal('innerWidth', 1280)
  vi.stubGlobal('innerHeight', 800)
  const host = createMockHost('AgentPets')
  const pet = createMockPet('stage', key)
  await pet.storage.set({ xRatio: edge === 'right' ? 1 : 0, yRatio: 1, peekEdge: edge })
  const canvas = document.createElement('div')
  canvas.getBoundingClientRect = () => new DOMRect(0, 0, 800, 500)
  document.body.appendChild(canvas)
  const view = render(key === 'ying' ? AgentPet : AgentPetCodex, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam: 'floor', movement: 'auto' },
      ...(preview ? { previewRoot: canvas, previewPeekEdge: edge } : {}),
    },
  })
  for (const image of Array.from(view.container.querySelectorAll('img'))) await fireEvent.load(image)
  await vi.advanceTimersByTimeAsync(64)
  const root = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const frame = () =>
    view.container.querySelector<HTMLElement>(key === 'ying' ? '.agent-pet-ying__frames' : '.agent-pet-sprites')!
      .dataset.frame!
  const geometry = () =>
    ['.agent-pet-ying__character', '.agent-pet-ying__clip', '.agent-pet-ying__artwork'].map(
      selector => root.querySelector<HTMLElement>(selector)!.style.cssText,
    )
  return {
    host,
    root,
    frame,
    geometry,
    unmount() {
      view.unmount()
      host.dispose()
      canvas.remove()
    },
  }
}

async function sample(stage: Awaited<ReturnType<typeof setup>>, duration = 7000) {
  const seen = new Set<string>([stage.frame()])
  const geometry = stage.geometry()
  for (let elapsed = 0; elapsed < duration; elapsed += 20) {
    await vi.advanceTimersByTimeAsync(20)
    seen.add(stage.frame())
    expect(stage.geometry()).toEqual(geometry)
  }
  return seen
}

describe('native blinking during settled peeks', () => {
  it.each(BLINKING_PETS.flatMap(([key, blink]) => EDGES.map(edge => ({ key, blink, edge }))))(
    '$key retains its existing blink on the $edge without moving the stage geometry',
    async ({ key, blink, edge }) => {
      const stage = await setup(key, edge)
      try {
        expect(stage.root.dataset.peekEdge).toBe(edge)
        expect(stage.root.dataset.peekPhase).toBe('look')
        const frames = await sample(stage)
        expect(frames.has(blink)).toBe(true)
        expect(frames.size).toBe(2)
      } finally {
        stage.unmount()
      }
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it.each(BLINKING_PETS)('%s stops blinking while motion is disabled or the page is hidden', async key => {
    const stage = await setup(key, 'bottom')
    try {
      for (const state of [
        { motionAllowed: false, pageVisible: true },
        { motionAllowed: true, pageVisible: false },
      ]) {
        stage.host.patch(state)
        await vi.advanceTimersByTimeAsync(32)
        expect((await sample(stage)).size).toBe(1)
      }
      stage.host.patch({ pageVisible: true })
      await vi.advanceTimersByTimeAsync(32)
      expect((await sample(stage)).size).toBe(2)
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(BLINKING_PETS)('%s keeps calibration peek previews on their first frame', async key => {
    const stage = await setup(key, 'bottom', true)
    try {
      expect(stage.root.dataset.peekEdge).toBe('bottom')
      expect((await sample(stage)).size).toBe(1)
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps Chibiterasu native rather than borrowing an unrelated pose and preserves renderer peeks', () => {
    expect(BUILTIN_PACKS['builtin-chibiterasu'].actions.peek.frames).toEqual(['frame-000'])
    expect(BUILTIN_PACKS['projector-cat'].actions.peek.frames).toEqual(['blink', 'idle', 'blink'])
  })
})
