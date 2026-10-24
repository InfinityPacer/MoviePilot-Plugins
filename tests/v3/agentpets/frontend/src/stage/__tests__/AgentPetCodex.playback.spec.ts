import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createMockHost, createMockPet } from '@/dev/mockHost'
import { buildCodexPetPack, BUILTIN_PACK, BUILTIN_PACKS } from '@/sprites/schema'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
import { phaseFrame, travelFrame } from '@/stage/playback'

const hosts: Array<ReturnType<typeof createMockHost>> = []
afterEach(() => hosts.splice(0).forEach(host => host.dispose()))

async function setup() {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  const pack = {
    ...BUILTIN_PACK,
    id: 'cycle-fixture',
    frames: { ...BUILTIN_PACK.frames, a: 0, b: 1, c: 2 },
    actions: {
      ...BUILTIN_PACK.actions,
      wave: { frames: ['a', 'b', 'c'], frame_ms: 100, frame_durations: [300, 600, 900], loop: true },
    },
  }
  const api = {
    get: vi.fn().mockResolvedValue({ success: true, data: { pack, sheet_src: 'fixture.png' } }),
    post: vi.fn(),
  }
  const view = render(AgentPetCodex, {
    props: {
      agent: host,
      pet: createMockPet('stage', pack.id),
      api,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: 'fixed' },
    },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(32)
  const root = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const sprite = view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
  return { view, host, root, sprite, api }
}

function pointer(type: string, x = 100, y = 100) {
  const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y })
  Object.defineProperties(event, {
    pointerId: { value: 1 },
    pointerType: { value: 'touch' },
    isPrimary: { value: true },
  })
  return event
}

describe('stage action completion', () => {
  it.each([0.4, 1, 2.5])('keeps all eight native gait frames aligned with actual travel at speed %s', async speed => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    const host = createMockHost('AgentPets')
    hosts.push(host)
    const pack = buildCodexPetPack('gait.png', 1536, 2288).pack
    const api = {
      get: vi.fn().mockResolvedValue({ success: true, data: { pack, sheet_src: 'fixture.png' } }),
      post: vi.fn(),
    }
    const view = render(AgentPetCodex, {
      props: {
        agent: host,
        pet: createMockPet('stage', pack.id),
        api,
        pluginId: 'AgentPets',
        settingsOverride: { scale: 1.2, speed, roam: 'free', movement: 'auto' },
      },
    })
    await flushPromises()
    const root = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
    const sprite = view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
    for (let elapsed = 0; elapsed < 14_000 && root.dataset.motion !== 'walk'; elapsed += 32)
      await vi.advanceTimersByTimeAsync(32)
    expect(root.dataset.motion).toBe('walk')
    const frames = new Set<string>()
    for (let elapsed = 0; elapsed < 3000 && root.dataset.motion === 'walk'; elapsed += 32) {
      await vi.advanceTimersByTimeAsync(32)
      if (root.dataset.motion !== 'walk') break
      const action = pack.actions[sprite.dataset.action!]
      expect(sprite.dataset.frame).toBe(action.frames[travelFrame(action, Number(root.dataset.walkTravel))])
      frames.add(sprite.dataset.frame!)
    }
    expect(frames.size).toBeGreaterThan(1)
    host.patch({ phase: 'thinking', thinking: true })
    await flushPromises()
    expect(root.dataset.motion).toBe('idle')
    expect(root.dataset.walkTravel).toBeUndefined()
    expect(sprite.dataset.action).toBe('thinking')
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps a long-press response until its actual final frame has finished', async () => {
    const { view, root, sprite, api } = await setup()
    await fireEvent(view.getByRole('button'), pointer('pointerdown'))
    await vi.advanceTimersByTimeAsync(450)
    await fireEvent(window, pointer('pointerup'))
    expect(root.dataset.reaction).toBe('wave')
    await vi.advanceTimersByTimeAsync(1200)
    expect(root.dataset.reaction).toBe('wave')
    expect(sprite.dataset.frame).toBe('c')
    await vi.advanceTimersByTimeAsync(599)
    expect(root.dataset.reaction).toBe('wave')
    await vi.advanceTimersByTimeAsync(1)
    expect(root.dataset.reaction).toBeUndefined()
    expect(root.dataset.pose).toBe('idle')
    expect(api.get).toHaveBeenCalledOnce()
    expect(api.post).not.toHaveBeenCalled()
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('restarts the same event action without letting the old completion end it', async () => {
    const { host, root, sprite } = await setup()
    host.fire('agent.panel.open')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(500)
    host.fire('agent.panel.open')
    await flushPromises()
    expect(sprite.dataset.frame).toBe('a')
    await vi.advanceTimersByTimeAsync(1300)
    expect(root.dataset.pose).toBe('wave')
    await vi.advanceTimersByTimeAsync(500)
    expect(root.dataset.pose).toBe('idle')
  })

  it.each(['thinking', 'tool', 'awaiting'] as const)(
    'lets %s take over an ordinary response immediately',
    async phase => {
      const { host, root } = await setup()
      host.fire('agent.panel.open')
      await flushPromises()
      await vi.advanceTimersByTimeAsync(500)
      host.patch({ phase, thinking: phase === 'thinking' })
      await flushPromises()
      expect(root.dataset.pose).toBe(phase === 'thinking' ? 'think' : phase === 'tool' ? 'busy' : 'alert')
      await vi.advanceTimersByTimeAsync(3000)
      expect(root.dataset.pose).toBe(phase === 'thinking' ? 'think' : phase === 'tool' ? 'busy' : 'alert')
    },
  )

  it('lets a drag interrupt an ordinary event without waiting for its cycle', async () => {
    const { host, view, root } = await setup()
    host.fire('agent.panel.open')
    await flushPromises()
    await fireEvent(view.getByRole('button'), pointer('pointerdown'))
    await fireEvent(window, pointer('pointermove', 160, 140))
    expect(root.dataset.pose).toBe('held')
    expect(root.dataset.motion).toBe('drag')
    await vi.advanceTimersByTimeAsync(3000)
    expect(root.dataset.pose).toBe('held')
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['hidden', 'reduced-motion', 'unavailable', 'blur'] as const)(
    'cancels a frame-driven interaction on %s without replaying the old round',
    async reason => {
      const { host, view, root, api } = await setup()
      await fireEvent(view.getByRole('button'), pointer('pointerdown'))
      await vi.advanceTimersByTimeAsync(450)
      await fireEvent(window, pointer('pointerup'))
      await vi.advanceTimersByTimeAsync(500)
      expect(root.dataset.reaction).toBe('wave')
      if (reason === 'hidden') host.patch({ pageVisible: false })
      if (reason === 'reduced-motion') host.patch({ motionAllowed: false, reducedMotion: true })
      if (reason === 'unavailable') host.patch({ available: false })
      if (reason === 'blur') await fireEvent(window, new Event('blur'))
      await flushPromises()
      expect(root.dataset.reaction).toBeUndefined()
      await vi.advanceTimersByTimeAsync(3000)
      host.patch({ available: true, pageVisible: true, motionAllowed: true, reducedMotion: false })
      await flushPromises()
      await vi.advanceTimersByTimeAsync(2000)
      expect(root.dataset.reaction).toBeUndefined()
      expect(root.dataset.pose).toBe('idle')
      expect(api.post).not.toHaveBeenCalled()
      view.unmount()
      await vi.advanceTimersByTimeAsync(32)
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it('drives ascent and descent frames from an actual safe card hop and finishes the landing cycle', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.1)
    vi.stubGlobal('innerWidth', 1000)
    vi.stubGlobal('innerHeight', 800)
    const card = document.createElement('div')
    card.className = 'v-card'
    card.getBoundingClientRect = () => new DOMRect(350, 600, 300, 160)
    document.body.appendChild(card)
    Object.defineProperty(document, 'elementsFromPoint', {
      configurable: true,
      value: (x: number, y: number) =>
        card.isConnected && x >= 350 && x <= 650 && y >= 600 && y <= 760 ? [card, document.body] : [document.body],
    })
    const host = createMockHost('AgentPets')
    hosts.push(host)
    host.patch({ isMobile: false })
    const pack = {
      ...BUILTIN_PACK,
      id: 'physical-fixture',
      frames: { ...BUILTIN_PACK.frames, a: 0, b: 1, c: 2 },
      actions: {
        ...BUILTIN_PACK.actions,
        jump: { frames: ['a', 'b', 'c'], frame_ms: 100, loop: true },
        fall: { frames: ['a', 'b', 'c'], frame_ms: 100, loop: true },
        land: { frames: ['a', 'b', 'c'], frame_ms: 500, loop: true },
      },
    }
    const api = {
      get: vi.fn().mockResolvedValue({ success: true, data: { pack, sheet_src: 'fixture.png' } }),
      post: vi.fn(),
    }
    const view = render(AgentPetCodex, {
      props: {
        agent: host,
        pet: createMockPet('stage', pack.id),
        api,
        pluginId: 'AgentPets',
        settingsOverride: { scale: 1, speed: 1, roam: 'surfaces', movement: 'auto' },
      },
    })
    try {
      await flushPromises()
      const root = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
      const sprite = view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
      for (let elapsed = 0; elapsed < 14_000 && root.dataset.motion !== 'fall'; elapsed += 16)
        await vi.advanceTimersByTimeAsync(16)
      expect(root.dataset.motion).toBe('fall')
      const phases = new Set<string>()
      for (let elapsed = 0; elapsed < 4000 && root.dataset.motion === 'fall'; elapsed += 16) {
        const pose = root.dataset.pose!
        expect(['jump', 'fall']).toContain(pose)
        expect(sprite.dataset.action).toBe(pose)
        const action = pack.actions[pose as 'jump' | 'fall']
        expect(sprite.dataset.frame).toBe(action.frames[phaseFrame(action, Number(root.dataset.airProgress))])
        phases.add(pose)
        await vi.advanceTimersByTimeAsync(16)
      }
      expect(phases).toEqual(new Set(['jump', 'fall']))
      expect(root.dataset.motion).toBe('sit')
      expect(sprite.dataset.action).toBe('land')
      await vi.advanceTimersByTimeAsync(900)
      expect(root.dataset.motion).toBe('sit')
      expect(sprite.dataset.frame).toBe('b')
      await vi.advanceTimersByTimeAsync(599)
      expect(root.dataset.motion).toBe('sit')
      expect(sprite.dataset.frame).toBe('c')
      await vi.advanceTimersByTimeAsync(1)
      expect(root.dataset.motion).toBe('idle')
      expect(sprite.dataset.action).toBe('idle')
      expect(root.dataset.airProgress).toBeUndefined()
      expect(api.post).not.toHaveBeenCalled()
    } finally {
      view.unmount()
      card.remove()
      await vi.advanceTimersByTimeAsync(32)
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['builtin-chibiterasu', 'builtin-nailong', 'builtin-kurisu'])(
    'uses the existing physical artwork for %s previews without changing saved settings',
    async key => {
      vi.useFakeTimers()
      const before = JSON.stringify(BUILTIN_PACKS[key])
      const api = {
        get: vi
          .fn()
          .mockResolvedValue({ success: true, data: { id: key, calibration: BUILTIN_PACKS[key].calibration } }),
        post: vi.fn(),
      }
      const preview = document.createElement('div')
      preview.getBoundingClientRect = () =>
        ({ x: 0, y: 0, width: 800, height: 600, top: 0, left: 0, right: 800, bottom: 600 }) as DOMRect
      const view = render(AgentPetCodex, {
        props: {
          pet: createMockPet('stage', key),
          api,
          pluginId: 'AgentPets',
          previewRoot: preview,
          previewPose: 'jump',
          settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: 'fixed' },
        },
      })
      await flushPromises()
      const sprite = view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
      expect(sprite.dataset.action).toBe('jump')
      await view.rerender({ previewPose: 'fall' })
      expect(sprite.dataset.action).toBe('fall')
      await view.rerender({ previewPose: 'sit' })
      expect(sprite.dataset.action).toBe('land')
      await view.rerender({ mappingsOverride: { 'stage.sit': 'idle' } })
      expect(sprite.dataset.action).toBe('idle')
      await flushPromises()
      expect(JSON.stringify(BUILTIN_PACKS[key])).toBe(before)
      expect(api.post).not.toHaveBeenCalled()
      view.unmount()
      await vi.advanceTimersByTimeAsync(32)
      expect(vi.getTimerCount()).toBe(0)
    },
  )
})
