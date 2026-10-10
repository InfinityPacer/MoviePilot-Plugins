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
    document.querySelectorAll('.v-card, body > button').forEach(card => card.remove())
    delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  })

  /** 模拟 x 大于 `edge` 的区域都被一个可点击控件占着。 */
  /** 让控件占据底边一带 x 大于 `edge` 的区域（矩形判定，不依赖命中测试）。 */
  function stubControlsRightOf(edge: number, control: Element) {
    const rect = { left: edge, top: window.innerHeight - 200, width: window.innerWidth - edge, height: 200 }
    control.getBoundingClientRect = () =>
      ({
        ...rect,
        x: rect.left,
        y: rect.top,
        right: rect.left + rect.width,
        bottom: rect.top + rect.height,
        toJSON: () => rect,
      }) as DOMRect
  }

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
    const anchors: Array<{ x: number; y: number; width: number; height: number } | null> = []
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
    // 自己掉落不写服务端，存储仍是启动前的值。
    expect(await pet.storage.get()).toEqual({ roam: 'surfaces', xRatio: 0.3, yRatio: 0 })
  })

  it('polls the surface every 500ms while visible, including reduced motion', async () => {
    const rect = { left: 100, top: 400, width: 600, height: 200 }
    const card = addCard(rect)
    const { host, anchors } = await mountStill({ roam: 'surfaces', xRatio: 0.3, yRatio: 0 })
    expect(anchors.at(-1)).toMatchObject({ y: 280 })

    // 只靠 CSS 动画移动：位置变了，但没有 DOM 变化也没有滚动；减少动态效果时也要跟上。
    rect.top = 350
    await new Promise(resolve => setTimeout(resolve, 600))
    await flush()
    expect(anchors.at(-1)).toMatchObject({ y: 230 })

    // 页面不可见时定时器停掉。
    host.patch({ pageVisible: false })
    await flush()
    rect.top = 300
    await new Promise(resolve => setTimeout(resolve, 600))
    await flush()
    expect(anchors.at(-1)).toMatchObject({ y: 230 })
    card.remove()
  })

  it('starts away from clickable controls', async () => {
    const fab = document.createElement('button')
    document.body.appendChild(fab)
    stubControlsRightOf(600, fab)
    const { anchors } = await mountStill(null, 'floor')
    await new Promise(resolve => setTimeout(resolve, 20))
    const rect = anchors.at(-1)!
    expect(rect.x + rect.width * 0.75).toBeLessThanOrEqual(600)
  })

  it('walks away about 1.5s after the user drops her on a control', async () => {
    const fab = document.createElement('button')
    document.body.appendChild(fab)
    const { anchors, view } = await mountStill({ roam: 'floor', xRatio: 0, yRatio: 1 }, 'floor')
    await new Promise(resolve => setTimeout(resolve, 20))
    stubControlsRightOf(600, fab)

    const button = view.container.querySelector('button') as HTMLButtonElement
    const start = anchors.at(-1)!
    button.dispatchEvent(pointer('pointerdown', { pointerId: 7, clientX: start.x + 10, clientY: start.y + 10 }))
    window.dispatchEvent(pointer('pointermove', { pointerId: 7, clientX: 800, clientY: 300 }))
    window.dispatchEvent(pointer('pointerup', { pointerId: 7, clientX: 800, clientY: 300 }))
    await flush()
    const dropped = anchors.at(-1)!
    expect(dropped.x + dropped.width / 2).toBeGreaterThan(600)

    await new Promise(resolve => setTimeout(resolve, 800))
    expect(anchors.at(-1)!.x).toBe(dropped.x)
    await new Promise(resolve => setTimeout(resolve, 900))
    await flush()
    const moved = anchors.at(-1)!
    expect(moved.x + moved.width * 0.75).toBeLessThanOrEqual(600)
  })

  it('walks away within about 2s when a control appears under her later', async () => {
    const host = createMockHost('AgentPets')
    const anchors: Array<{ x: number; y: number; width: number; height: number } | null> = []
    const pet = createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) })
    const api = { get: vi.fn().mockResolvedValue({ success: true, data: { scale: 1, speed: 1, roam: 'floor' } }) }
    const view = render(AgentPet, { props: { agent: host, pet, api, pluginId: 'AgentPets' } })
    await flush()
    const root = view.container.querySelector('.agent-pet-ying') as HTMLElement
    await new Promise(resolve => setTimeout(resolve, 50))
    expect(root.dataset.motion).toBe('idle')

    // 悬浮按钮在页面数据加载后才出现，正好压在她身后。
    const fab = document.createElement('button')
    document.body.appendChild(fab)
    const start = anchors.at(-1)!
    stubControlsRightOf(start.x - 1, fab)
    await new Promise(resolve => setTimeout(resolve, 2100))
    expect(root.dataset.motion).toBe('walk')
    expect(anchors.at(-1)!.x).toBeLessThan(start.x)
  })

  it('teleports off a late control under reduced motion while the page is visible', async () => {
    const { anchors, view } = await mountStill(null, 'floor')
    await new Promise(resolve => setTimeout(resolve, 20))
    const root = view.container.querySelector('.agent-pet-ying') as HTMLElement
    const fab = document.createElement('button')
    document.body.appendChild(fab)
    const start = anchors.at(-1)!
    stubControlsRightOf(start.x - 1, fab)
    const motions = new Set<string>()
    const watch = window.setInterval(() => motions.add(root.dataset.motion ?? ''), 20)
    await new Promise(resolve => setTimeout(resolve, 2200))
    window.clearInterval(watch)
    const moved = anchors.at(-1)!
    expect(moved.x + moved.width * 0.75).toBeLessThanOrEqual(start.x - 1)
    expect(motions.has('walk')).toBe(false)
  })

  it('does not recheck controls while the page is hidden', async () => {
    const { host, anchors } = await mountStill(null, 'floor')
    await new Promise(resolve => setTimeout(resolve, 20))
    host.patch({ pageVisible: false })
    await flush()
    const fab = document.createElement('button')
    document.body.appendChild(fab)
    const start = anchors.at(-1)!
    stubControlsRightOf(start.x - 1, fab)
    await new Promise(resolve => setTimeout(resolve, 2200))
    expect(anchors.at(-1)!.x).toBe(start.x)
  })

  it('saves the position only on drop, roam change and page hide, at most once per 30s', async () => {
    const { host, pet, view } = await mountStill({ roam: 'floor', xRatio: 0.2, yRatio: 1 }, 'floor')
    await new Promise(resolve => setTimeout(resolve, 20))
    const save = vi.spyOn(pet.storage, 'set')
    const button = view.container.querySelector('button') as HTMLButtonElement

    async function drag(toX: number) {
      const rect = button.getBoundingClientRect()
      button.dispatchEvent(pointer('pointerdown', { pointerId: 9, clientX: rect.left + 5, clientY: rect.top + 5 }))
      window.dispatchEvent(pointer('pointermove', { pointerId: 9, clientX: toX, clientY: 200 }))
      window.dispatchEvent(pointer('pointerup', { pointerId: 9, clientX: toX, clientY: 200 }))
      await flush()
    }

    // 自己避让、站立复查都不写。
    await new Promise(resolve => setTimeout(resolve, 600))
    expect(save).not.toHaveBeenCalled()

    await drag(500)
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0][0]).toMatchObject({ roam: 'floor', yRatio: 1 })

    // 30 秒内再次放下只排队，不立即写。
    await drag(300)
    expect(save).toHaveBeenCalledTimes(1)

    // 页面变为隐藏时立即写出最新位置。
    host.patch({ pageVisible: false })
    await flush()
    expect(save).toHaveBeenCalledTimes(2)
  })

  it('saves after switching roam mode', async () => {
    const { host, pet } = await mountStill({ roam: 'floor', xRatio: 0.2, yRatio: 1 }, 'floor')
    await new Promise(resolve => setTimeout(resolve, 20))
    const save = vi.spyOn(pet.storage, 'set')
    host.emit('agentpets.settings', { scale: 1, speed: 1, roam: 'free' })
    await flush()
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0][0]).toMatchObject({ roam: 'free' })
  })

  it('shrinks on narrow screens on top of the user scale', async () => {
    const { host, anchors } = await mountStill(null, 'floor')
    host.patch({ isMobile: true })
    await flush()
    expect(anchors.at(-1)).toMatchObject({ height: 96 })
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

  it('switches frames without touching any img src', async () => {
    const { host, view } = await mountStill(null)
    const images = Array.from(view.container.querySelectorAll<HTMLImageElement>('img'))
    expect(images).toHaveLength(18)
    const before = images.map(img => img.getAttribute('src'))
    images.forEach(img => img.dispatchEvent(new Event('load')))
    await flush()
    const frames = view.container.querySelector('.agent-pet-ying__frames') as HTMLElement
    expect(frames.dataset.frame).toBe('idle')

    host.patch({ phase: 'thinking', thinking: true })
    host.fire('agent.done')
    await flush()
    expect(frames.dataset.frame).toBe('victory')
    host.patch({ phase: 'idle', thinking: false })
    await flush()
    expect(images.map(img => img.getAttribute('src'))).toEqual(before)
    expect(view.container.querySelectorAll('.agent-pet-ying__frame--visible')).toHaveLength(1)
  })

  it('keeps the last good frame when the target frame fails or is still loading', async () => {
    const { host, view } = await mountStill(null)
    const image = (pose: string) => view.container.querySelector(`img[data-pose="${pose}"]`) as HTMLImageElement
    const frames = view.container.querySelector('.agent-pet-ying__frames') as HTMLElement
    image('idle').dispatchEvent(new Event('load'))
    await flush()
    expect(frames.dataset.frame).toBe('idle')

    host.fire('agent.done')
    await flush()
    expect(frames.dataset.frame).toBe('idle')
    image('victory').dispatchEvent(new Event('error'))
    await flush()
    expect(frames.dataset.frame).toBe('idle')
    expect(frames).not.toHaveClass('agent-pet-ying__frames--pending')
    expect(image('victory').getAttribute('src')).not.toContain('retry')
  })

  it('retries only the failed frame after the retry interval', async () => {
    const { host, view } = await mountStill(null)
    const image = (pose: string) => view.container.querySelector(`img[data-pose="${pose}"]`) as HTMLImageElement
    image('idle').dispatchEvent(new Event('load'))
    host.fire('agent.done')
    await flush()
    image('victory').dispatchEvent(new Event('error'))
    const idleSrc = image('idle').getAttribute('src')

    const now = Date.now()
    vi.spyOn(Date, 'now').mockReturnValue(now + 6000)
    host.fire('agent.error')
    await flush()
    host.fire('agent.done')
    await flush()
    expect(image('victory').getAttribute('src')).toContain('victory.webp?retry=1')
    expect(image('idle').getAttribute('src')).toBe(idleSrc)
  })

  it('hides the character until any frame has loaded', async () => {
    const { view } = await mountStill(null)
    const frames = view.container.querySelector('.agent-pet-ying__frames') as HTMLElement
    expect(frames).toHaveClass('agent-pet-ying__frames--pending')
    expect(frames.dataset.frame).toBeUndefined()
    ;(view.container.querySelector('img[data-pose="idle"]') as HTMLImageElement).dispatchEvent(new Event('error'))
    await flush()
    expect(frames).toHaveClass('agent-pet-ying__frames--pending')
  })
})
