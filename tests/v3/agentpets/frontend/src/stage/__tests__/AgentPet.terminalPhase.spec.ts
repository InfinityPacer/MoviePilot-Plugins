import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { h } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { AgentRect } from '@/host'

const hosts: ReturnType<typeof createMockHost>[] = []
afterEach(() => hosts.splice(0).forEach(host => host.dispose()))

async function setup(fixed = false) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-23T09:00:00Z'))
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  vi.stubGlobal('innerWidth', 1000)
  vi.stubGlobal('innerHeight', 800)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  let anchor: AgentRect | null = null
  const pet = createMockPet('stage', 'terminal-phase', {
    onAnchor: rect => {
      anchor = rect
    },
  })
  await pet.storage.set({ xRatio: 0.5, yRatio: 0.5 })
  const save = vi.spyOn(pet.storage, 'set')
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      lookDirections: true,
      artworkReady: true,
      restAvailable: true,
      settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: fixed ? 'fixed' : 'auto' },
    },
    slots: { default: () => h('span') },
  })
  await flushPromises()
  const stage = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const button = view.getByRole('button')
  async function advance(ms: number) {
    await vi.advanceTimersByTimeAsync(ms)
    await flushPromises()
  }
  async function pointer(type: string, target: Element | Window = window) {
    const r = anchor!
    const event = new MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      button: 0,
      clientX: r.x + r.width + 30,
      clientY: r.y + r.height / 2,
    })
    Object.defineProperties(event, {
      pointerId: { value: 1 },
      pointerType: { value: 'mouse' },
      isPrimary: { value: true },
    })
    await fireEvent(target, event)
  }

  // Replay the public event/state order from MoviePilot-Frontend@795c975 agentHostPhase.ts.
  // fire() alone does not update the mock host's persistent phase or thinking flag.
  function startTurn() {
    host.patch({ thinking: true })
    host.fire('agent.thinking.start')
    host.patch({ phase: 'thinking' })
  }
  function stopThinking() {
    host.patch({ thinking: false })
    host.fire('agent.thinking.end')
    if (host.getState().phase === 'thinking' || host.getState().phase === 'tool') host.patch({ phase: 'idle' })
  }
  function terminal(type: 'done' | 'error') {
    const awaiting = host.getState().phase === 'awaiting'
    host.fire(`agent.${type}`)
    host.patch({ phase: type === 'done' && awaiting ? 'awaiting' : type, toolName: null })
  }
  async function waitForWalk() {
    for (let elapsed = 0; elapsed < 14000 && stage.dataset.motion !== 'walk'; elapsed += 50) await advance(50)
    expect(stage.dataset.motion).toBe('walk')
  }
  await advance(32)
  return { host, stage, button, view, save, advance, pointer, startTurn, stopThinking, terminal, waitForWalk }
}

describe('persistent host terminal phases', () => {
  it.each(['done', 'error'] as const)(
    'preserves %s feedback, then resumes a fresh activity interval',
    async terminal => {
      const pet = await setup()
      pet.startTurn()
      pet.terminal(terminal)
      pet.stopThinking()
      await flushPromises()
      const duration = terminal === 'done' ? 2200 : 2600
      expect(pet.stage.dataset.pose).toBe(terminal === 'done' ? 'victory' : 'confused')
      await pet.pointer('pointermove')
      await pet.advance(duration - 1)
      expect(pet.stage.dataset.motion).toBe('idle')
      expect(pet.stage.dataset.gaze).toBeUndefined()
      expect(pet.stage.dataset.pose).toBe(terminal === 'done' ? 'victory' : 'confused')
      await pet.advance(1)
      expect(pet.stage.dataset.pose).toBe('idle')
      await pet.waitForWalk()
      expect(pet.host.getState()).toMatchObject({ phase: terminal, thinking: false })
      expect(pet.save).not.toHaveBeenCalled()
    },
  )

  it.each(['done', 'error'] as const)(
    'allows sustained gaze and the first long press after %s feedback',
    async terminal => {
      const pet = await setup(true)
      pet.startTurn()
      pet.terminal(terminal)
      pet.stopThinking()
      await pet.advance(3000)
      await pet.pointer('pointermove')
      await pet.advance(350)
      expect(pet.stage.dataset.gaze).toBe('look-090')
      pet.host.patch({ theme: 'dark' })
      await pet.advance(3000)
      expect(pet.stage.dataset.gaze).toBe('look-090')
      await pet.pointer('pointerdown', pet.button)
      await pet.advance(450)
      expect(pet.stage.dataset.gaze).toBeUndefined()
      expect(pet.stage.dataset.reaction).toBe('wave')
      await pet.pointer('pointerup')
      expect(pet.host.getState()).toMatchObject({ phase: terminal, thinking: false })
      expect(pet.save).not.toHaveBeenCalled()
    },
  )

  it.each(['done', 'error'] as const)('also resumes when thinking ends before the %s event', async terminal => {
    const pet = await setup()
    pet.startTurn()
    pet.stopThinking()
    pet.terminal(terminal)
    await pet.advance(3000)
    await pet.waitForWalk()
    expect(pet.host.getState()).toMatchObject({ phase: terminal, thinking: false })
  })

  it.each(['done', 'error'] as const)('does not treat %s as quiet while thinking remains true', async terminal => {
    const pet = await setup()
    pet.startTurn()
    pet.terminal(terminal)
    await pet.advance(3000)
    await pet.pointer('pointermove')
    await pet.advance(16000)
    expect(pet.stage.dataset.motion).toBe('idle')
    expect(pet.stage.dataset.gaze).toBeUndefined()
    pet.stopThinking()
    await pet.waitForWalk()
  })

  it.each(['thinking', 'tool', 'awaiting'] as const)('keeps %s blocked even with thinking=false', async phase => {
    const pet = await setup()
    pet.host.patch({ phase, thinking: false })
    await pet.pointer('pointermove')
    await pet.advance(16000)
    expect(pet.stage.dataset.motion).toBe('idle')
    expect(pet.stage.dataset.gaze).toBeUndefined()
    await pet.pointer('pointerdown', pet.button)
    await pet.advance(450)
    expect(pet.stage.dataset.reaction).toBeUndefined()
    await pet.pointer('pointerup')
  })

  it('keeps a pending choice blocked when the stream subsequently finishes', async () => {
    const pet = await setup()
    pet.startTurn()
    pet.host.fire('agent.awaiting')
    pet.host.patch({ phase: 'awaiting' })
    pet.terminal('done')
    pet.stopThinking()
    await pet.advance(3000)
    expect(pet.host.getState()).toMatchObject({ phase: 'awaiting', thinking: false })
    expect(pet.stage.dataset.pose).toBe('alert')
    await pet.pointer('pointermove')
    await pet.advance(16000)
    expect(pet.stage.dataset.motion).toBe('idle')
    expect(pet.stage.dataset.gaze).toBeUndefined()
  })

  it('lets a new turn cancel recovered gaze and resumes again after its error feedback', async () => {
    const pet = await setup()
    pet.startTurn()
    pet.terminal('done')
    pet.stopThinking()
    await pet.advance(3000)
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.stage.dataset.gaze).toBe('look-090')
    pet.startTurn()
    await flushPromises()
    expect(pet.stage.dataset.gaze).toBeUndefined()
    expect(pet.stage.dataset.pose).toBe('think')
    pet.terminal('error')
    pet.stopThinking()
    await pet.advance(3000)
    await pet.waitForWalk()
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['done', 'error'] as const)('can take and finish a short supported rest after %s', async terminal => {
    const pet = await setup(true)
    pet.startTurn()
    pet.terminal(terminal)
    pet.stopThinking()
    await pet.advance(90000)
    expect(pet.stage.dataset.pose).toBe('doze')
    await pet.advance(6000)
    expect(pet.stage.dataset.pose).not.toBe('doze')
    expect(pet.host.getState().phase).toBe(terminal)
    expect(pet.save).not.toHaveBeenCalled()
  })
})
