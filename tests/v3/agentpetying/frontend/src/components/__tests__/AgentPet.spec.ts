import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import AgentPet from '@/components/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'

function setup() {
  const host = createMockHost('AgentPetYing')
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
    props: { agent: host, pet, api, pluginId: 'AgentPetYing' },
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
    expect(api.get).toHaveBeenCalledWith('plugin/AgentPetYing/settings')
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
    host.emit('agentpetying.settings', { scale: 0.6, speed: 1 })
    await flush()
    expect(anchors.at(-1)).toMatchObject({ height: 72 })
    host.fire('agentpetying.settings', { scale: 1.6, speed: 1 })
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
