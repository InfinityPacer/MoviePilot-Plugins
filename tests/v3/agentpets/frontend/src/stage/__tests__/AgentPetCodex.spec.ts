import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AgentRect } from '@/host'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
import { buildCodexPetPack, validatePack, withCodexStageActions } from '@/sprites/schema'
import legacyJson from '@tests/../fixtures/legacy-codex-v2.json'

const hosts: ReturnType<typeof createMockHost>[] = []

afterEach(() => {
  hosts.splice(0).forEach(host => host.dispose())
})

async function setup(motionAllowed = true) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  const host = createMockHost('Clone1')
  hosts.push(host)
  host.patch({ motionAllowed })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'legacy-pet', { onAnchor: rect => anchors.push(rect) })
  const api = {
    get: vi.fn().mockImplementation(async (path: string) => ({
      success: true,
      data: path.includes('/settings?key=')
        ? { scale: 1.2, speed: 1, roam: 'floor' }
        : { pack: { ...legacyJson, codex_version: 'v2' }, sheet_src: 'data:image/png;base64,AAAA' },
    })),
    post: vi.fn(),
  }
  const view = render(AgentPetCodex, { props: { agent: host, pet, api, pluginId: 'Clone1' } })
  await vi.advanceTimersByTimeAsync(32)
  const root = view.container.querySelector('.agent-pet-ying') as HTMLElement
  const sprite = view.container.querySelector('.agent-pet-sprites') as HTMLElement
  return { host, api, pet, view, anchors, root, sprite }
}

describe('Codex Pet stage', () => {
  it.each(['v1', 'v2'] as const)(
    'uses loaded %s capabilities for nearby attention without rewriting the atlas',
    async version => {
      vi.useFakeTimers()
      const host = createMockHost('Clone1')
      hosts.push(host)
      host.patch({ isMobile: false })
      const pack = buildCodexPetPack('standard-pet.png', 1536, version === 'v1' ? 1872 : 2288).pack
      const anchors: Array<AgentRect | null> = []
      const api = {
        get: vi.fn().mockResolvedValue({ success: true, data: { pack, sheet_src: 'data:image/png;base64,AAAA' } }),
        post: vi.fn(),
      }
      const view = render(AgentPetCodex, {
        props: {
          agent: host,
          api,
          pluginId: 'Clone1',
          pet: createMockPet('stage', pack.id, { onAnchor: rect => anchors.push(rect) }),
          settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: 'fixed' },
        },
      })
      await flushPromises()
      await vi.advanceTimersByTimeAsync(32)
      const stage = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
      const sprite = view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
      const frame = view.container.querySelector<HTMLElement>('.agent-pet-sprites__frame')!
      const sheetWrites = vi.spyOn(frame.style, 'setProperty')
      const point = (side: 'right' | 'left') => {
        const rect = anchors.at(-1)!
        return { x: side === 'right' ? rect.x + rect.width + 30 : rect.x - 30, y: rect.y + rect.height / 2 }
      }
      const move = async (side: 'right' | 'left') => {
        const { x, y } = point(side)
        const event = new MouseEvent('pointermove', { clientX: x, clientY: y, buttons: 0 })
        Object.defineProperties(event, { pointerType: { value: 'mouse' }, isPrimary: { value: true } })
        await fireEvent(window, event)
      }
      await move('right')
      await vi.advanceTimersByTimeAsync(350)
      await flushPromises()
      expect(stage.dataset.attention).toBe('mouse')
      expect(sprite.dataset.action).toBe(version === 'v2' ? 'look-090' : 'wave')
      if (version === 'v2') {
        expect(sprite.dataset.frame).toBe('look-090')
        expect(pack.frames[sprite.dataset.frame!]).toBe(76)
        await vi.advanceTimersByTimeAsync(120)
        await move('left')
        expect(sprite.dataset.action).toBe('look-270')
        expect(pack.frames[sprite.dataset.frame!]).toBe(84)
      } else {
        expect(stage.dataset.gaze).toBeUndefined()
        expect(pack.actions.waving.frames).toContain(sprite.dataset.frame)
      }
      expect(sheetWrites.mock.calls.filter(([key]) => key === 'background-image')).toHaveLength(0)
      expect(api.get).toHaveBeenCalledTimes(1)
      view.unmount()
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it.each(['v1', 'v2'] as const)('plays long-press responses from the standard %s native actions', async version => {
    vi.useFakeTimers()
    const host = createMockHost('Clone1')
    hosts.push(host)
    const pack = buildCodexPetPack('standard-pet.png', 1536, version === 'v1' ? 1872 : 2288).pack
    const api = {
      get: vi.fn().mockResolvedValue({
        success: true,
        data: { pack, sheet_src: 'data:image/png;base64,AAAA' },
      }),
      post: vi.fn(),
    }
    const view = render(AgentPetCodex, {
      props: {
        agent: host,
        pet: createMockPet('stage', pack.id),
        api,
        pluginId: 'Clone1',
        settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: 'fixed' },
      },
    })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(32)
    const button = view.getByRole('button')
    const stage = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
    const sprite = view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
    const pointer = (type: string) => {
      const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: 100, clientY: 100 })
      Object.defineProperties(event, {
        pointerId: { value: 1 },
        pointerType: { value: 'touch' },
        isPrimary: { value: true },
      })
      return event
    }
    const hold = async () => {
      await fireEvent(button, pointer('pointerdown'))
      await vi.advanceTimersByTimeAsync(450)
      await fireEvent(window, pointer('pointerup'))
      await flushPromises()
    }
    await hold()
    expect(stage.dataset.reaction).toBe('wave')
    expect(sprite.dataset.action).toBe('wave')
    expect(pack.actions.waving.frames).toContain(sprite.dataset.frame)
    expect(pack.frames[sprite.dataset.frame!]).toBeGreaterThanOrEqual(24)
    expect(pack.frames[sprite.dataset.frame!]).toBeLessThan(32)

    await vi.advanceTimersByTimeAsync(6000)
    await hold()
    expect(stage.dataset.reaction).toBe('jump')
    expect(sprite.dataset.action).toBe('jumping')
    expect(pack.actions.jumping.frames).toContain(sprite.dataset.frame)
    expect(pack.frames[sprite.dataset.frame!]).toBeGreaterThanOrEqual(32)
    expect(pack.frames[sprite.dataset.frame!]).toBeLessThan(40)
    expect(api.get).toHaveBeenCalledTimes(1)
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('ignores another pet appearance and applies shared activity without resetting its own size', async () => {
    const { host, root, anchors } = await setup(false)
    host.emit('agentpets.settings', { key: 'ying', scale: 0.6, speed: 2 })
    await vi.advanceTimersByTimeAsync(32)
    expect(anchors.at(-1)?.height).toBe(144)
    host.emit('agentpets.settings', { key: 'legacy-pet', scale: 0.9, speed: 0.8 })
    await vi.advanceTimersByTimeAsync(32)
    expect(anchors.at(-1)?.height).toBe(108)
    expect(root.dataset.roam).toBe('floor')
    host.emit('agentpets.settings', { roam: 'free', movement: 'fixed' })
    await vi.advanceTimersByTimeAsync(32)
    expect(root.dataset.movement).toBe('fixed')
    expect(anchors.at(-1)?.height).toBe(108)
  })

  it.each([
    ['left', 'bottom'],
    ['right', 'bottom'],
    ['left', 'left'],
    ['right', 'right'],
  ])('keeps a neutral level gaze at the %s corner via the %s edge', async (side, edge) => {
    vi.stubGlobal('innerWidth', 1280)
    vi.stubGlobal('innerHeight', 800)
    const { view, root, sprite, anchors } = await setup(false)
    const rect = anchors.at(-1)!
    const x = side === 'left' ? 0 : 1280 - rect.width
    const y = 800 - rect.height - (edge === 'bottom' ? 0 : rect.height / 2)
    const pointer = (type: string, clientX: number, clientY: number) => {
      const event = new MouseEvent(type, { bubbles: true, button: 0, clientX, clientY })
      Object.defineProperty(event, 'pointerId', { value: 1 })
      return event
    }
    view.getByRole('button').dispatchEvent(pointer('pointerdown', rect.x + 10, rect.y + 10))
    window.dispatchEvent(pointer('pointermove', x + 10, y + 10))
    window.dispatchEvent(pointer('pointerup', x + 10, y + 10))
    await vi.advanceTimersByTimeAsync(64)
    expect(root.dataset.peekEdge).toBe(edge)
    expect(sprite.dataset.action).toBe('peek')
    const completed = withCodexStageActions(validatePack({ ...legacyJson, codex_version: 'v2' }).pack!)
    expect(completed.frames[sprite.dataset.frame!]).toBe(0)
    const artwork = root.querySelector('.agent-pet-ying__artwork') as HTMLElement
    const rotation = edge === 'bottom' ? 0 : (side === 'left' ? 1 : -1) * 35
    expect(artwork.style.transform).toBe(`rotate(${rotation}deg)`)
  })

  it('shares mobile viewport recovery with the built-in stage', async () => {
    const visual = Object.assign(new EventTarget(), { width: 390, height: 700, offsetTop: 0, offsetLeft: 0 })
    vi.stubGlobal('visualViewport', visual)
    const { host, anchors } = await setup(false)
    host.patch({ isMobile: true })
    visual.height = 360
    visual.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(64)
    const anchor = anchors.at(-1)!
    expect(anchor.height).toBeCloseTo(120 * 1.2 * 0.8)
    expect(anchor.x + anchor.width).toBeLessThanOrEqual(390)
    expect(anchor.y + anchor.height).toBeCloseTo(360)
  })

  it('loads the selected legacy pet and applies saved and live sizes through the stage', async () => {
    const { host, api, view, anchors } = await setup()
    expect(api.get).toHaveBeenCalledWith('plugin/Clone1/pack?key=legacy-pet')
    expect(api.get).toHaveBeenCalledWith('plugin/Clone1/settings?key=legacy-pet')
    expect(view.getByRole('button', { name: '打开助手（旧版素材包）' })).toBeInTheDocument()
    expect(anchors.at(-1)?.height).toBe(144)
    expect(anchors.at(-1)?.width).toBeCloseTo((144 * 192) / 208)
    expect(view.container.querySelector('.agent-pet-ying__frames')).toBeNull()
    host.emit('agentpets.settings', { scale: 0.6, speed: 1, roam: 'floor' })
    await vi.advanceTimersByTimeAsync(32)
    expect(anchors.at(-1)?.height).toBe(72)
  })

  it('walks autonomously using left-facing frames, then reacts to the agent phase', async () => {
    const { host, root, sprite, anchors } = await setup()
    const startX = anchors.at(-1)!.x
    await vi.advanceTimersByTimeAsync(10_080)
    expect(root.dataset.motion).toBe('walk')
    expect(sprite.dataset.action).toBe('running-left')
    expect(anchors.at(-1)!.x).toBeLessThan(startX)
    const first = sprite.dataset.frame
    await vi.advanceTimersByTimeAsync(300)
    expect(sprite.dataset.frame).not.toBe(first)
    host.patch({ phase: 'thinking', thinking: true })
    await vi.advanceTimersByTimeAsync(32)
    expect(root.dataset.motion).toBe('idle')
    expect(sprite.dataset.action).toBe('thinking')
    expect(sprite.dataset.frame).toBe('thinking')
  })

  it('pauses movement and sprite frames when motion is disabled or the page is hidden', async () => {
    const { host, root, sprite, anchors } = await setup(false)
    const start = { ...anchors.at(-1)! }
    const frame = sprite.dataset.frame
    await vi.advanceTimersByTimeAsync(15_000)
    expect(root.dataset.motion).toBe('idle')
    expect(anchors.at(-1)).toEqual(start)
    expect(sprite.dataset.frame).toBe(frame)
    host.patch({ motionAllowed: true })
    await vi.advanceTimersByTimeAsync(800)
    expect(sprite.dataset.frame).not.toBe(frame)
    host.patch({ pageVisible: false })
    await vi.advanceTimersByTimeAsync(32)
    const hidden = sprite.dataset.frame
    await vi.advanceTimersByTimeAsync(15_000)
    expect(sprite.dataset.frame).toBe(hidden)
    expect(anchors.at(-1)).toEqual(start)
  })

  it('opens the native agent panel and releases animation and anchor resources on unmount', async () => {
    const { host, view, anchors, sprite } = await setup()
    const open = vi.spyOn(host, 'open')
    await fireEvent.click(view.getByRole('button'))
    expect(open).toHaveBeenCalledOnce()
    expect(sprite.dataset.action).toBe('wave')
    view.unmount()
    await vi.advanceTimersByTimeAsync(32)
    expect(anchors.at(-1)).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('reloads saved mappings only for its own instance and pet and uses them on real host phases', async () => {
    const { host, api, sprite } = await setup()
    const original = api.get.getMockImplementation()!
    api.get.mockImplementation(async (path: string) => {
      const result = await original(path)
      if (!path.includes('/settings?key=')) result.data.pack.action_mappings = { 'stage.think': 'review' }
      return result
    })
    const count = api.get.mock.calls.length
    host.emit('agentpets.pack.updated', { key: 'other' })
    await vi.advanceTimersByTimeAsync(32)
    expect(api.get.mock.calls).toHaveLength(count)
    host.emit('agentpets.pack.updated', { key: 'legacy-pet' })
    await vi.advanceTimersByTimeAsync(32)
    host.patch({ phase: 'thinking', thinking: true })
    await vi.advanceTimersByTimeAsync(32)
    expect(sprite.dataset.action).toBe('review')
  })
})
