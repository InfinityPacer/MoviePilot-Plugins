import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createMockHost, createMockPet } from '@/dev/mockHost'
import { ActivityPolicy } from '@/stage/activity'
import AgentPet from '@/stage/AgentPet.vue'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
import { GREETING_MARKER, GREETING_SETTLE_MS } from '@/stage/greeting'
import { greetingLines, LINES } from '@/stage/lines'
import { buildCodexPetPack } from '@/sprites/schema'

const hosts: ReturnType<typeof createMockHost>[] = []
afterEach(() => {
  hosts.splice(0).forEach(host => host.dispose())
})

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

async function pointer(target: Element | Window, type: string, id: number, x = 120, y = 160) {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: x, clientY: y })
  Object.assign(event, { pointerId: id, pointerType: 'mouse', isPrimary: true })
  await fireEvent(target, event)
}

async function setup(options: { codex?: boolean; preview?: boolean; greeting?: boolean } = {}) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 9, 24, 20, 0))
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  // 公共 setup 默认占掉本页招手机会，只有问候用例放开。
  if (options.greeting) Reflect.deleteProperty(document, GREETING_MARKER)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  host.patch({ isMobile: false })
  const pack = buildCodexPetPack('lines-pet.png', 1536, 2288).pack
  const pet = createMockPet('stage', options.codex ? pack.id : 'ying')
  const say = vi.fn().mockReturnValue({ shown: true })
  Object.assign(pet, { say })
  const api = {
    get: vi.fn().mockResolvedValue({ success: true, data: { pack, sheet_src: 'data:image/png;base64,AAAA' } }),
  }
  const view = render(options.codex ? AgentPetCodex : AgentPet, {
    props: {
      agent: host,
      pet,
      api,
      pluginId: 'AgentPets',
      settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: 'fixed' },
      previewRoot: options.preview ? document.createElement('div') : null,
    },
  })
  await flushPromises()
  for (const img of Array.from(view.container.querySelectorAll('img'))) await fireEvent.load(img)
  await advance(32)
  const button = view.container.querySelector<HTMLButtonElement>('button')!
  return { host, pet, say, view, button, spoken: () => say.mock.calls.map(call => call[0] as string) }
}

async function longPress(button: Element, id: number) {
  await pointer(button, 'pointerdown', id)
  await advance(450)
  await pointer(window, 'pointerup', id)
}

describe('小映 lines through pet.say', () => {
  it('greets once for the local time slot on the first startup wave', async () => {
    const pet = await setup({ greeting: true })
    await advance(GREETING_SETTLE_MS + 2000)
    expect(pet.spoken()).toHaveLength(1)
    expect(greetingLines(new Date(2026, 9, 24, 20, 0))).toContain(pet.spoken()[0])
  })

  it('answers a long-press poke and switches to teasing on the third poke', async () => {
    const pet = await setup()
    await longPress(pet.button, 1)
    expect(LINES.poke).toContain(pet.spoken()[0])
    await advance(7000)
    await longPress(pet.button, 2)
    expect(LINES.poke).toContain(pet.spoken()[1])
    await advance(7000)
    await longPress(pet.button, 3)
    expect(LINES.tease).toContain(pet.spoken()[2])
  })

  it('says nothing while the reaction is cooling down', async () => {
    const pet = await setup()
    await longPress(pet.button, 1)
    await advance(500)
    await longPress(pet.button, 2)
    expect(pet.spoken()).toHaveLength(1)
  })

  it('comments on being put down after a drag', async () => {
    const pet = await setup()
    await pointer(pet.button, 'pointerdown', 5)
    await pointer(window, 'pointermove', 5, 160, 200)
    await pointer(window, 'pointerup', 5, 160, 200)
    await flushPromises()
    expect(pet.spoken()).toHaveLength(1)
    expect(LINES.drop).toContain(pet.spoken()[0])
  })

  it('mumbles when a pointer wakes it from a doze, but not when a rest simply ends', async () => {
    vi.spyOn(ActivityPolicy.prototype, 'delay').mockReturnValue(200_000)
    const pet = await setup()
    await advance(90_000)
    expect(pet.view.container.querySelector<HTMLElement>('.agent-pet-ying')!.dataset.pose).toBe('doze')
    await advance(6000)
    expect(pet.spoken()).toEqual([])
    await advance(90_000)
    await pointer(pet.button, 'pointerdown', 9)
    expect(pet.spoken()).toHaveLength(1)
    expect(LINES.wake).toContain(pet.spoken()[0])
    await pointer(window, 'pointerup', 9)
  })

  it.each([{ codex: true }, { preview: true }])('keeps other stage pets and previews silent (%o)', async options => {
    const pet = await setup(options)
    await longPress(pet.button, 1)
    expect(pet.say).not.toHaveBeenCalled()
  })
})
