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
})
