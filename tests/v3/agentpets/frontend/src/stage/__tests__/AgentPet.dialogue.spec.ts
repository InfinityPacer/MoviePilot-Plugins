import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createMockHost, createMockPet } from '@/dev/mockHost'
import { registerEditor } from '@/editor/presence'
import type { AgentHostState, AgentRect } from '@/host'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'
import { BUILTIN_PACK, BUILTIN_PACKS } from '@/sprites/schema'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
import { ActivityPolicy } from '@/stage/activity'
import { DIALOGUE_LINES, type DialogueSettings } from '@/stage/dialogue'
import { GREETING_MARKER } from '@/stage/greeting'
import type { YingSettings } from '@/stage/settings'

const hosts: ReturnType<typeof createMockHost>[] = []
const editors: Array<() => void> = []
const fixtures: HTMLElement[] = []
afterEach(() => {
  editors.splice(0).forEach(close => close())
  hosts.splice(0).forEach(host => host.dispose())
  fixtures.splice(0).forEach(el => el.remove())
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
})

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

async function pointer(target: Element | Window, type: string, x = 300, y = 300) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: x, clientY: y })
  Object.assign(event, { pointerId: 1, pointerType: 'touch', isPrimary: true })
  await fireEvent(target, event)
}

async function until(predicate: () => boolean, limit = 16_000) {
  for (let elapsed = 0; elapsed <= limit; elapsed += 16) {
    if (predicate()) return
    await advance(16)
  }
  throw new Error('dialogue event did not complete')
}

async function setup(
  options: {
    dialogue?: DialogueSettings | null
    fixed?: boolean
    roam?: 'free' | 'floor' | 'surfaces'
    preview?: boolean
    greeting?: boolean
    random?: number
    hostState?: Partial<AgentHostState>
    longLanding?: boolean
    storedSettings?: boolean
  } = {},
) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-24T00:00:00Z'))
  vi.spyOn(Math, 'random').mockReturnValue(options.random ?? 0.5)
  vi.stubGlobal('innerWidth', 1000)
  vi.stubGlobal('innerHeight', 800)
  if (options.greeting) Reflect.deleteProperty(document, GREETING_MARKER)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  host.patch({ isMobile: false, ...options.hostState })
  const anchors: Array<AgentRect | null> = []
  const pack = options.longLanding
    ? {
        ...BUILTIN_PACK,
        id: 'dialogue-landing-fixture',
        frames: { ...BUILTIN_PACK.frames, a: 0, b: 1, c: 2 },
        actions: {
          ...BUILTIN_PACK.actions,
          land: { frames: ['a', 'b', 'c'], frame_ms: 600, loop: true },
        },
      }
    : BUILTIN_PACKS['builtin-kurisu']
  const pet = createMockPet('stage', pack.id, { onAnchor: rect => anchors.push(rect) })
  await pet.storage.set({ xRatio: 0.5, yRatio: 1 })
  const save = vi.spyOn(pet.storage, 'set')
  const say = vi.fn().mockReturnValue({ shown: true })
  Object.assign(pet, { say })
  const settings: YingSettings = {
    scale: 1,
    speed: 1,
    roam: options.roam ?? 'free',
    movement: options.fixed === false ? 'auto' : 'fixed',
    ...(options.dialogue === null ? {} : { dialogue: options.dialogue ?? { mode: 'interaction', voice: 'neutral' } }),
  }
  const api = {
    get: vi.fn().mockImplementation(async (path: string) => {
      if (path.includes('/settings?')) return { success: true, data: settings }
      if (path.includes('/packs/calibration?')) {
        const key = decodeURIComponent(path.split('key=')[1])
        return { success: true, data: { id: key, calibration: builtinDefaultCalibration(key) } }
      }
      return { success: true, data: { pack, sheet_src: 'fixture.png' } }
    }),
    post: vi.fn(),
  }
  const view = render(AgentPetCodex, {
    props: {
      agent: host,
      pet,
      api,
      pluginId: 'AgentPets',
      settingsOverride: options.storedSettings ? undefined : settings,
      previewRoot: options.preview ? document.createElement('div') : null,
    },
  })
  await flushPromises()
  await advance(32)
  expect(view.emitted('load-state')?.at(-1)).toEqual(['ready'])
  const stage = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const button = view.getByRole('button')
  const spoken = () => say.mock.calls.map(call => call[0] as string)
  return { view, host, pet, save, api, say, stage, button, spoken, rect: () => anchors.at(-1)! }
}

async function longPress(button: Element) {
  await pointer(button, 'pointerdown')
  await advance(450)
  await pointer(window, 'pointerup')
}

async function setupHop() {
  Object.defineProperty(document, 'elementsFromPoint', {
    configurable: true,
    value: (x: number, y: number) => [
      ...fixtures
        .filter(el => {
          const rect = el.getBoundingClientRect()
          return (
            el.isConnected &&
            el.style.display !== 'none' &&
            x >= rect.left &&
            x <= rect.right &&
            y >= rect.top &&
            y <= rect.bottom
          )
        })
        .reverse(),
      document.body,
    ],
  })
  const stage = await setup({
    fixed: false,
    roam: 'surfaces',
    random: 0.1,
    longLanding: true,
    dialogue: { mode: 'occasional', voice: 'neutral' },
  })
  const card = document.createElement('div')
  card.className = 'v-card'
  card.getBoundingClientRect = () => new DOMRect(350, 600, 300, 160)
  document.body.append(card)
  fixtures.push(card)
  return { ...stage, card }
}

describe('per-Pet contextual dialogue', () => {
  it('lets a user-selected neutral voice answer a built-in long press without an AI call', async () => {
    const pet = await setup()
    await longPress(pet.button)
    expect(pet.say).toHaveBeenCalledOnce()
    expect(DIALOGUE_LINES.neutral.poke).toContain(pet.spoken()[0])
    expect(pet.api.post).not.toHaveBeenCalled()
    expect(pet.host.calls).not.toContain('open()')
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('greets only with the first actual startup wave', async () => {
    const pet = await setup({ greeting: true })
    await until(() => pet.say.mock.calls.length === 1, 5000)
    expect(DIALOGUE_LINES.neutral.greeting).toContain(pet.spoken()[0])
    await advance(30_000)
    expect(pet.say).toHaveBeenCalledOnce()
    expect(pet.save).not.toHaveBeenCalled()
  })

  it.each([null, { mode: 'off', voice: 'wry' }] as const)(
    'keeps an unconfigured or off built-in silent (%o)',
    async dialogue => {
      const pet = await setup({ dialogue })
      await longPress(pet.button)
      expect(pet.stage.dataset.reaction).toBe('wave')
      expect(pet.say).not.toHaveBeenCalled()
    },
  )

  it('does not interrupt a live walk when only dialogue is turned off', async () => {
    const pet = await setup({ fixed: false })
    await until(() => pet.stage.dataset.motion === 'walk')
    await advance(96)
    const before = { ...pet.rect() }
    await pet.view.rerender({
      settingsOverride: {
        scale: 1,
        speed: 1,
        roam: 'free',
        movement: 'auto',
        dialogue: { mode: 'off', voice: 'neutral' },
      },
    })
    expect(pet.stage.dataset.motion).toBe('walk')
    await advance(96)
    expect(Math.hypot(pet.rect().x - before.x, pet.rect().y - before.y)).toBeGreaterThan(0)
    expect(pet.say).not.toHaveBeenCalled()
    expect(pet.save).not.toHaveBeenCalled()
  })

  it.each([
    { phase: 'thinking', thinking: true },
    { phase: 'tool' },
    { phase: 'awaiting' },
    { pageVisible: false },
    { motionAllowed: false, reducedMotion: true },
    { available: false },
  ] as const)('stays silent under host priority %o and never replays on resume', async hostState => {
    const pet = await setup({ hostState })
    await longPress(pet.button)
    expect(pet.say).not.toHaveBeenCalled()
    pet.host.patch({ phase: 'idle', thinking: false, pageVisible: true, motionAllowed: true, available: true })
    await advance(20_000)
    expect(pet.say).not.toHaveBeenCalled()
  })

  it.each(['preview', 'editor'] as const)('never speaks from %s', async reason => {
    const pet = await setup({ preview: reason === 'preview' })
    if (reason === 'editor') editors.push(registerEditor())
    await longPress(pet.button)
    expect(pet.say).not.toHaveBeenCalled()
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it.each(['cancel', 'work', 'blur'] as const)('does not promote a %s long press into a line', async reason => {
    const pet = await setup()
    await pointer(pet.button, 'pointerdown')
    await advance(200)
    if (reason === 'cancel') await pointer(window, 'pointercancel')
    if (reason === 'work') pet.host.patch({ phase: 'tool' })
    if (reason === 'blur') await fireEvent(window, new Event('blur'))
    await advance(500)
    await pointer(window, 'pointerup')
    expect(pet.say).not.toHaveBeenCalled()
  })

  it('waits for actual gravity and the whole landing cycle before a drop line', async () => {
    const pet = await setup({ fixed: false, roam: 'floor', longLanding: true })
    const origin = pet.rect()
    await pointer(pet.button, 'pointerdown', origin.x + 10, origin.y + 10)
    await pointer(window, 'pointermove', 400, 330)
    await pointer(window, 'pointerup', 400, 330)
    expect(pet.stage.dataset.motion).toBe('fall')
    expect(pet.say).not.toHaveBeenCalled()
    await until(() => pet.stage.dataset.motion === 'sit', 2000)
    await advance(1200)
    expect(pet.stage.dataset.motion).toBe('sit')
    expect(pet.say).not.toHaveBeenCalled()
    await until(() => pet.stage.dataset.motion === 'idle', 1000)
    expect(pet.say).toHaveBeenCalledOnce()
    expect(DIALOGUE_LINES.neutral.drop).toContain(pet.spoken()[0])
  })

  it('does not call a cancelled drop a successful landing', async () => {
    const pet = await setup({ fixed: false, roam: 'floor' })
    const origin = pet.rect()
    await pointer(pet.button, 'pointerdown', origin.x + 10, origin.y + 10)
    await pointer(window, 'pointermove', 400, 330)
    await pointer(window, 'pointercancel', 400, 330)
    await advance(4000)
    expect(pet.say).not.toHaveBeenCalled()
  })

  it('announces an autonomous hop only after the actual landing cycle finishes', async () => {
    const pet = await setupHop()
    await until(() => pet.stage.dataset.motion === 'fall')
    expect(pet.say).not.toHaveBeenCalled()
    await until(() => pet.stage.dataset.motion === 'sit', 3000)
    await advance(1200)
    expect(pet.stage.dataset.motion).toBe('sit')
    expect(pet.say).not.toHaveBeenCalled()
    await until(() => pet.stage.dataset.motion === 'idle', 1000)
    expect(pet.rect().y + pet.rect().height).toBe(600)
    expect(pet.say).toHaveBeenCalledOnce()
    expect(DIALOGUE_LINES.neutral.hop).toContain(pet.spoken()[0])
    expect(pet.save).not.toHaveBeenCalled()
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it.each(['removed', 'moved', 'work', 'editor'] as const)(
    'drops a pending hop line when %s takes over during landing',
    async reason => {
      const pet = await setupHop()
      await until(() => pet.stage.dataset.motion === 'sit')
      if (reason === 'removed') pet.card.remove()
      if (reason === 'moved') pet.card.getBoundingClientRect = () => new DOMRect(350, 500, 300, 160)
      if (reason === 'work') pet.host.patch({ phase: 'tool' })
      if (reason === 'editor') editors.push(registerEditor())
      await advance(3000)
      expect(pet.say).not.toHaveBeenCalled()
    },
  )

  it.each(['interaction', 'occasional'] as const)('uses %s mode for a real natural doze wake', async mode => {
    const pet = await setup({ random: 0.1, dialogue: { mode, voice: 'neutral' } })
    await advance(90_000)
    expect(pet.stage.dataset.pose).toBe('doze')
    expect(pet.say).not.toHaveBeenCalled()
    await advance(6000)
    expect(pet.stage.dataset.pose).not.toBe('doze')
    expect(pet.say).toHaveBeenCalledTimes(mode === 'occasional' ? 1 : 0)
    if (mode === 'occasional') expect(DIALOGUE_LINES.neutral.wake).toContain(pet.spoken()[0])
  })

  it('lets real input wake a doze but never reports another wake when the cancelled rest timer would end', async () => {
    const pet = await setup({ random: 0.1, dialogue: { mode: 'occasional', voice: 'lively' } })
    await advance(90_000)
    expect(pet.stage.dataset.pose).toBe('doze')
    await pointer(pet.button, 'pointerdown')
    await pointer(window, 'pointerup')
    expect(DIALOGUE_LINES.lively.wake).toContain(pet.spoken()[0])
    await advance(20_000)
    expect(pet.say).toHaveBeenCalledOnce()
  })

  it('does not describe a host-interrupted rest as a natural wake', async () => {
    const pet = await setup({ random: 0.1, dialogue: { mode: 'occasional', voice: 'neutral' } })
    await advance(90_000)
    pet.host.fire('agent.done')
    await advance(6000)
    expect(pet.say).not.toHaveBeenCalled()
  })

  it('keeps ordinary walking, blinking and idle postures silent', async () => {
    vi.spyOn(ActivityPolicy.prototype, 'delay').mockReturnValue(3000)
    const pet = await setup({ fixed: false, dialogue: { mode: 'occasional', voice: 'wry' } })
    await until(() => pet.stage.dataset.motion === 'walk')
    await advance(30_000)
    expect(pet.say).not.toHaveBeenCalled()
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it('ignores synchronous own bubble feedback but still lets subsequent host feedback preempt the reaction', async () => {
    const pet = await setup()
    pet.say.mockImplementation(() => {
      pet.host.fire('agent.bubble')
      return { shown: true }
    })
    await longPress(pet.button)
    expect(pet.stage.dataset.reaction).toBe('wave')
    expect(pet.say).toHaveBeenCalledOnce()
    pet.host.fire('agent.bubble')
    await flushPromises()
    expect(pet.stage.dataset.reaction).toBeUndefined()
  })

  it('resets dialogue throttling for a different plugin instance', async () => {
    const pet = await setup()
    await longPress(pet.button)
    await advance(7000)
    await pet.view.rerender({ pluginId: 'Clone1' })
    await flushPromises()
    await longPress(pet.button)
    expect(pet.say).toHaveBeenCalledTimes(2)
    expect(pet.api.post).not.toHaveBeenCalled()
  })

  it.each(['key', 'instance'] as const)(
    'never borrows previous preferences while the new %s settings are loading',
    async boundary => {
      const pet = await setup({ storedSettings: true })
      await longPress(pet.button)
      expect(pet.say).toHaveBeenCalledOnce()
      const key = boundary === 'key' ? 'builtin-nailong' : pet.pet.key
      const pluginId = boundary === 'instance' ? 'Clone1' : 'AgentPets'
      const path = `plugin/${pluginId}/settings?key=${key}`
      let complete!: (value: { success: boolean; data: YingSettings }) => void
      const pending = new Promise<{ success: boolean; data: YingSettings }>(resolve => {
        complete = resolve
      })
      const read = pet.api.get.getMockImplementation()!
      pet.api.get.mockImplementation(async (query: string) => (query === path ? pending : read(query)))
      const nextPet = createMockPet('stage', key)
      Object.assign(nextPet, { say: pet.say })
      await pet.view.rerender({ pluginId, pet: nextPet })
      await flushPromises()
      await advance(32)
      expect(pet.api.get).toHaveBeenCalledWith(path)
      await longPress(pet.button)
      expect(pet.say).toHaveBeenCalledOnce()
      complete({
        success: true,
        data: { scale: 1, speed: 1, roam: 'free', movement: 'fixed', dialogue: { mode: 'off', voice: 'wry' } },
      })
      await flushPromises()
      await advance(7000)
      await longPress(pet.button)
      expect(pet.say).toHaveBeenCalledOnce()
      expect(pet.api.post).not.toHaveBeenCalled()
    },
  )
})
