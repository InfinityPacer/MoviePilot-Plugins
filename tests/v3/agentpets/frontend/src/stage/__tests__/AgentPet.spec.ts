import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'

function setup() {
  const host = createMockHost('AgentPets')
  const anchors: unknown[] = []
  const interacting: boolean[] = []
  const pet = createMockPet('stage', 'ying', {
    onAnchor: rect => anchors.push(rect),
    onInteracting: value => interacting.push(value),
  })
  const api = {
    get: vi.fn().mockResolvedValue({ success: true, data: { scale: 1.2, speed: 1 } }),
  }
  const view = render(AgentPet, {
    props: { agent: host, pet, api, pluginId: 'AgentPets' },
  })
  return { host, pet, api, anchors, interacting, view }
}

/** jsdom 没有 PointerEvent，用带 pointerId 的 MouseEvent 代替。 */
function pointer(type: string, init: { pointerId: number; clientX: number; clientY: number }) {
  const event = new MouseEvent(type, {
    bubbles: true,
    button: 0,
    clientX: init.clientX,
    clientY: init.clientY,
  })
  Object.defineProperty(event, 'pointerId', { value: init.pointerId })
  return event
}

async function flush() {
  await new Promise(resolve => setTimeout(resolve, 0))
  await new Promise(resolve => requestAnimationFrame(() => resolve(null)))
}

describe('AgentPet (ying)', () => {
  it('loads saved settings and reports a bubble anchor', async () => {
    const { api, anchors } = setup()
    await flush()
    expect(api.get).toHaveBeenCalledWith('plugin/AgentPets/settings')
    const button = await screen.findByRole('button', {
      name: '打开助手（小映）',
    })
    expect(button).toBeInTheDocument()
    expect(anchors.at(-1)).toMatchObject({ height: 144 })
  })

  it('opens the native panel on click and keyboard activation', async () => {
    const { host } = setup()
    const open = vi.spyOn(host, 'open')
    await flush()
    const button = await screen.findByRole('button')
    await fireEvent.click(button)
    expect(open).toHaveBeenCalledTimes(1)
  })

  it('does not open the panel after a drag and marks interaction', async () => {
    const { host, interacting } = setup()
    const open = vi.spyOn(host, 'open')
    await flush()
    const button = await screen.findByRole('button')
    button.dispatchEvent(pointer('pointerdown', { pointerId: 1, clientX: 100, clientY: 100 }))
    window.dispatchEvent(pointer('pointermove', { pointerId: 1, clientX: 160, clientY: 40 }))
    expect(interacting).toEqual([true])
    window.dispatchEvent(pointer('pointerup', { pointerId: 1, clientX: 160, clientY: 40 }))
    await fireEvent.click(button)
    expect(interacting).toEqual([true, false])
    expect(open).not.toHaveBeenCalled()
  })

  it('applies live settings only from its own plugin instance', async () => {
    const { host, anchors } = setup()
    await flush()
    host.emit('agentpets.settings', { scale: 0.6, speed: 1 })
    await flush()
    expect(anchors.at(-1)).toMatchObject({ height: 72 })
    host.fire('agentpets.settings', { scale: 1.6, speed: 1 })
    await flush()
    expect(anchors.at(-1)).toMatchObject({ height: 72 })
  })

  it('switches frames for host phases and events', async () => {
    const { host, view } = setup()
    await flush()
    const root = view.container.querySelector('.agent-pet-ying') as HTMLElement
    host.patch({ phase: 'thinking', thinking: true })
    await flush()
    expect(root.dataset.pose).toBe('think')
    host.fire('agent.done')
    await flush()
    expect(root.dataset.pose).toBe('victory')
  })

  it('releases subscriptions and the anchor on unmount', async () => {
    const { host, anchors, view } = setup()
    await flush()
    const removeListener = vi.spyOn(window, 'removeEventListener')
    view.unmount()
    expect(anchors.at(-1)).toBeNull()
    expect(removeListener).toHaveBeenCalledWith('resize', expect.any(Function))
    host.fire('agent.done')
  })
})

describe('AgentPet roam and frame fallback', () => {
  afterEach(() => {
    document.querySelectorAll('.v-card').forEach(card => card.remove())
  })

  function addCard(rect: { left: number; top: number; width: number; height: number }) {
    const card = document.createElement('div')
    card.className = 'v-card'
    card.getBoundingClientRect = () =>
      ({
        ...rect,
        x: rect.left,
        y: rect.top,
        right: rect.left + rect.width,
        bottom: rect.top + rect.height,
        toJSON: () => rect,
      }) as DOMRect
    document.body.appendChild(card)
    return card
  }

  async function mountStill(stored: unknown, roam = 'surfaces') {
    const host = createMockHost('AgentPets')
    host.patch({ motionAllowed: false })
    const anchors: Array<{ x: number; y: number } | null> = []
    const pet = createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) })
    await pet.storage.set(stored)
    const api = { get: vi.fn().mockResolvedValue({ success: true, data: { scale: 1, speed: 1, roam } }) }
    const view = render(AgentPet, { props: { agent: host, pet, api, pluginId: 'AgentPets' } })
    await flush()
    return { host, pet, anchors, view }
  }

  it('lands on the card below and falls to the floor when the card disappears', async () => {
    const card = addCard({ left: 100, top: 400, width: 600, height: 200 })
    const { anchors, pet } = await mountStill({ roam: 'surfaces', xRatio: 0.3, yRatio: 0 })
    expect(anchors.at(-1)).toMatchObject({ y: 280 })

    card.remove()
    await new Promise(resolve => setTimeout(resolve, 650))
    await flush()
    expect(anchors.at(-1)).toMatchObject({ y: window.innerHeight - 120 })
    expect(await pet.storage.get()).toMatchObject({ roam: 'surfaces', yRatio: 1 })
  })

  it('polls the surface every 500ms only while motion is allowed', async () => {
    const rect = { left: 100, top: 400, width: 600, height: 200 }
    const card = addCard(rect)
    const { host, anchors } = await mountStill({ roam: 'surfaces', xRatio: 0.3, yRatio: 0 })
    expect(anchors.at(-1)).toMatchObject({ y: 280 })

    // 只靠 CSS 动画移动：位置变了，但没有 DOM 变化也没有滚动。
    rect.top = 350
    await new Promise(resolve => setTimeout(resolve, 600))
    await flush()
    expect(anchors.at(-1)).toMatchObject({ y: 280 })

    // 恢复动画时宿主状态变化本身会触发一次校验，之后的移动只能靠定时器发现。
    host.patch({ motionAllowed: true })
    await flush()
    expect(anchors.at(-1)).toMatchObject({ y: 230 })
    rect.top = 300
    await new Promise(resolve => setTimeout(resolve, 600))
    await flush()
    expect(anchors.at(-1)).toMatchObject({ y: 180 })
    card.remove()
  })

  it('ignores narrow cards and lands on the floor', async () => {
    const card = addCard({ left: 250, top: 400, width: 100, height: 200 })
    const { anchors } = await mountStill({ roam: 'surfaces', xRatio: 0.3, yRatio: 0 })
    expect(anchors.at(-1)).toMatchObject({ y: window.innerHeight - 120 })
    card.remove()
  })

  it('stays in place in free mode and returns to the floor in floor mode', async () => {
    const { host, anchors } = await mountStill({ roam: 'free', xRatio: 0.3, yRatio: 0.5 }, 'free')
    const floating = anchors.at(-1)!.y
    expect(floating).toBeLessThan(window.innerHeight - 120)
    host.emit('agentpets.settings', { scale: 1, speed: 1, roam: 'floor' })
    await flush()
    expect(anchors.at(-1)).toMatchObject({ y: window.innerHeight - 120 })
  })

  it('keeps the last good frame when a frame fails to load', async () => {
    const { host, view } = await mountStill(null)
    const img = view.container.querySelector('img') as HTMLImageElement
    expect(img).toHaveClass('agent-pet-ying__frame--pending')
    img.dispatchEvent(new Event('load'))
    await flush()
    const good = img.getAttribute('src')
    expect(good).toContain('ying/idle.webp')
    expect(img).not.toHaveClass('agent-pet-ying__frame--pending')

    host.fire('agent.done')
    await flush()
    expect(img.getAttribute('src')).toContain('ying/victory.webp')
    img.dispatchEvent(new Event('error'))
    await flush()
    expect(img.getAttribute('src')).toBe(good)
    expect(img).not.toHaveClass('agent-pet-ying__frame--pending')
  })
})
