import { fireEvent, render } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AgentRect } from '@/host'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
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
      data: path.endsWith('/settings')
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
    expect(api.get).toHaveBeenCalledWith('plugin/Clone1/settings')
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
      if (!path.endsWith('/settings')) result.data.pack.action_mappings = { 'stage.think': 'review' }
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
