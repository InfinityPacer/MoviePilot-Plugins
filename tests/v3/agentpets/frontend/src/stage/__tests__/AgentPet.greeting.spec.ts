import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import { registerEditor } from '@/editor/presence'
import AgentPet from '@/stage/AgentPet.vue'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import { buildCodexPetPack, type SpritePack } from '@/sprites/schema'
import { GREETING_MARKER, GREETING_SETTLE_MS } from '@/stage/greeting'

const hosts: ReturnType<typeof createMockHost>[] = []
const releases: Array<() => void> = []

afterEach(() => {
  releases.splice(0).forEach(release => release())
  hosts.splice(0).forEach(host => host.dispose())
  Reflect.deleteProperty(document, GREETING_MARKER)
})

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

async function setup(
  options: {
    kind?: 'v1' | 'v2' | 'ying' | 'renderer'
    delayed?: boolean
    state?: Record<string, unknown>
    pack?: SpritePack
    preview?: boolean
  } = {},
) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  host.patch({ isMobile: false, ...options.state })
  const kind = options.kind ?? 'v2'
  const pack = options.pack ?? buildCodexPetPack('greeting-pet.png', 1536, kind === 'v1' ? 1872 : 2288).pack
  let resolvePack: ((value: unknown) => void) | undefined
  const response = { success: true, data: { pack, sheet_src: 'data:image/png;base64,AAAA' } }
  const api = {
    get: vi.fn().mockImplementation(() =>
      options.delayed
        ? new Promise(resolve => {
            resolvePack = resolve
          })
        : Promise.resolve(response),
    ),
  }
  const pet = createMockPet(kind === 'renderer' ? 'renderer' : 'stage', kind === 'ying' ? 'ying' : pack.id)
  const save = vi.spyOn(pet.storage, 'set')
  const view = render(kind === 'ying' ? AgentPet : kind === 'renderer' ? AgentPetSprite : AgentPetCodex, {
    props: {
      agent: host,
      pet,
      api,
      pluginId: 'AgentPets',
      ...(kind !== 'renderer'
        ? {
            settingsOverride: { scale: 1, speed: 1, roam: 'free', movement: 'fixed' },
            previewRoot: options.preview ? document.createElement('div') : null,
          }
        : { strictPreview: options.preview }),
    },
  })
  await flushPromises()
  await advance(32)
  const root = () =>
    view.container.querySelector<HTMLElement>(kind === 'renderer' ? '.agent-pet-sprites' : '.agent-pet-ying')!
  const sprite = () => view.container.querySelector<HTMLElement>('.agent-pet-sprites')!
  return { host, pet, save, view, pack, root, sprite, resolve: () => resolvePack?.(response) }
}

describe('startup stage greeting', () => {
  it.each(['v1', 'v2'] as const)(
    'waits for loaded %s artwork and restarts the complete native wave twice',
    async kind => {
      Reflect.deleteProperty(document, GREETING_MARKER)
      const pet = await setup({ kind, delayed: true })
      await advance(1600)
      expect(pet.root().dataset.greetingRound).toBeUndefined()
      pet.resolve()
      await flushPromises()
      await advance(GREETING_SETTLE_MS)
      expect(pet.root().dataset.greetingRound).toBe('1')
      expect(pet.sprite().dataset.frame).toBe('waving-1')
      const atlas = pet.view.container.querySelector<HTMLElement>('.agent-pet-sprites__frame')!
      const writes = vi.spyOn(atlas.style, 'setProperty')
      const duration = pet.pack.actions.wave.frames.length * 160
      await advance(duration - 1)
      expect(pet.root().dataset.greetingRound).toBe('1')
      expect(pet.sprite().dataset.frame).toBe(pet.pack.actions.wave.frames.at(-1))
      await advance(1)
      expect(pet.root().dataset.greetingRound).toBe('2')
      expect(pet.sprite().dataset.frame).toBe('waving-1')
      await advance(duration)
      expect(pet.root().dataset.greeting).toBeUndefined()
      expect(pet.root().dataset.pose).toBe('idle')
      expect(writes.mock.calls.filter(([name]) => name === 'background-image')).toHaveLength(0)
      expect(pet.save).not.toHaveBeenCalled()
    },
  )

  it('waits for the actual idle and wave image elements for single-frame artwork', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const pet = await setup({ kind: 'ying' })
    await advance(500)
    expect(pet.root().dataset.greetingRound).toBeUndefined()
    for (const name of ['idle', 'wave']) {
      await fireEvent.load(pet.view.container.querySelector(`img[src*="/${name}.webp"]`)!)
    }
    await advance(GREETING_SETTLE_MS)
    expect(pet.root().dataset.pose).toBe('wave')
    await advance(600)
    expect(pet.root().dataset.pose).toBe('idle')
    expect(pet.root().dataset.greeting).toBe('pause')
    await advance(220)
    expect(pet.root().dataset.pose).toBe('wave')
    expect(pet.root().dataset.greetingRound).toBe('2')
    await advance(600)
    expect(pet.root().dataset.greeting).toBeUndefined()
  })

  it('does not repeat after a route change, remount or another selected pet', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const first = await setup()
    await advance(GREETING_SETTLE_MS)
    expect(first.root().dataset.greetingRound).toBe('1')
    first.host.fire('agent.preview')
    first.view.unmount()
    const next = await setup({ kind: 'v1' })
    await advance(3000)
    expect(next.root().dataset.greetingRound).toBeUndefined()
    await next.view.rerender({ pet: createMockPet('stage', 'other') })
    await advance(3000)
    expect(next.root().dataset.greetingRound).toBeUndefined()
  })

  it.each(['busy', 'hidden', 'reduced', 'unavailable', 'editor', 'blur', 'done', 'error'] as const)(
    'cancels on %s and never replays on recovery',
    async cause => {
      Reflect.deleteProperty(document, GREETING_MARKER)
      const pet = await setup()
      await advance(GREETING_SETTLE_MS)
      expect(pet.root().dataset.greetingRound).toBe('1')
      if (cause === 'busy') pet.host.patch({ phase: 'thinking', thinking: true })
      if (cause === 'hidden') pet.host.patch({ pageVisible: false })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: false, reducedMotion: true })
      if (cause === 'unavailable') pet.host.patch({ available: false })
      if (cause === 'editor') releases.push(registerEditor())
      if (cause === 'blur') await fireEvent(window, new Event('blur'))
      if (cause === 'done' || cause === 'error') pet.host.fire('agent.' + cause)
      await flushPromises()
      expect(pet.root().dataset.greeting).toBeUndefined()
      pet.host.patch({
        phase: 'idle',
        thinking: false,
        pageVisible: true,
        motionAllowed: true,
        reducedMotion: false,
        available: true,
      })
      releases.splice(0).forEach(release => release())
      await advance(3000)
      expect(pet.root().dataset.greeting).toBeUndefined()
      expect(pet.root().dataset.greetingRound).toBe('1')
    },
  )

  it('lets a pointer hold cancel greeting and receive the first explicit wave without cooldown', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const pet = await setup()
    await advance(GREETING_SETTLE_MS)
    const button = pet.view.getByRole('button')
    const event = new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 80, clientY: 120 })
    Object.defineProperties(event, {
      pointerId: { value: 1 },
      pointerType: { value: 'mouse' },
      isPrimary: { value: true },
    })
    await fireEvent(button, event)
    expect(pet.root().dataset.greeting).toBeUndefined()
    await advance(450)
    expect(pet.root().dataset.reaction).toBe('wave')
  })

  it('skips previews without consuming the real page opportunity', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const preview = await setup({ preview: true })
    await advance(600)
    expect(preview.root().dataset.greetingRound).toBeUndefined()
    expect(Reflect.get(document, GREETING_MARKER)).toBeUndefined()
    preview.view.unmount()
    const pet = await setup()
    await advance(GREETING_SETTLE_MS)
    expect(pet.root().dataset.greetingRound).toBe('1')
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('skips a pack with no wave action and leaves its ordinary idle intact', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const pack = buildCodexPetPack('greeting-pet.png', 1536, 2288).pack
    delete pack.actions.wave
    // A non-Codex pack has no standard layout from which missing actions can be restored.
    delete pack.codex_version
    const pet = await setup({ pack })
    await advance(2500)
    expect(pet.root().dataset.greetingRound).toBeUndefined()
    expect(pet.sprite().dataset.action).toBe('idle')
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('cancels delayed artwork when a user acts before the picture appears', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const pet = await setup({ delayed: true })
    await fireEvent(window, new KeyboardEvent('keydown', { key: 'Enter' }))
    pet.resolve()
    await flushPromises()
    await advance(2500)
    expect(pet.root().dataset.greetingRound).toBeUndefined()
    expect(pet.sprite().dataset.action).toBe('idle')
  })

  it.each([{ motionAllowed: false }, { phase: 'thinking', thinking: true }, { pageVisible: false }])(
    'does not defer a startup blocked by %j',
    async state => {
      Reflect.deleteProperty(document, GREETING_MARKER)
      const pet = await setup({ state })
      pet.host.patch({ phase: 'idle', thinking: false, motionAllowed: true, pageVisible: true })
      await advance(2500)
      expect(pet.root().dataset.greetingRound).toBeUndefined()
    },
  )
})

describe('startup renderer greeting', () => {
  it('only changes artwork for two waves and retains host-owned geometry and storage', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const pet = await setup({ kind: 'renderer' })
    await advance(GREETING_SETTLE_MS)
    expect(pet.root().dataset.greetingRound).toBe('1')
    expect(pet.sprite().dataset.action).toBe('wave')
    await advance(pet.pack.actions.wave.frames.length * 160)
    expect(pet.root().dataset.greetingRound).toBe('2')
    expect(pet.sprite().dataset.frame).toBe('waving-1')
    await advance(pet.pack.actions.wave.frames.length * 160)
    expect(pet.sprite().dataset.action).toBe('idle')
    expect(pet.view.container.querySelector('.agent-pet-ying')).toBeNull()
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('is cancelled by a host pointer gesture and cannot replay a partial sequence', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const pet = await setup({ kind: 'renderer' })
    await advance(GREETING_SETTLE_MS)
    await fireEvent(window, new MouseEvent('pointerdown'))
    await advance(2500)
    expect(pet.root().dataset.greeting).toBeUndefined()
    expect(pet.root().dataset.greetingRound).toBe('1')
    expect(pet.sprite().dataset.action).toBe('idle')
  })

  it.each(['busy', 'hidden', 'reduced', 'editor', 'error'] as const)(
    'preserves the renderer host when %s interrupts',
    async cause => {
      Reflect.deleteProperty(document, GREETING_MARKER)
      const pet = await setup({ kind: 'renderer' })
      await advance(GREETING_SETTLE_MS)
      if (cause === 'busy') pet.host.patch({ phase: 'thinking', thinking: true })
      if (cause === 'hidden') pet.host.patch({ pageVisible: false })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: false, reducedMotion: true })
      if (cause === 'editor') releases.push(registerEditor())
      if (cause === 'error') pet.host.fire('agent.error')
      await flushPromises()
      expect(pet.root().dataset.greeting).toBeUndefined()
      pet.host.patch({ phase: 'idle', thinking: false, pageVisible: true, motionAllowed: true, reducedMotion: false })
      releases.splice(0).forEach(release => release())
      await advance(2500)
      expect(pet.root().dataset.greetingRound).toBe('1')
      expect(pet.save).not.toHaveBeenCalled()
    },
  )

  it('uses idle between two single-frame waves without changing the pack', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const pack = buildCodexPetPack('greeting-pet.png', 1536, 2288).pack
    pack.actions.wave = { frames: ['waving-1'], frame_ms: 160, loop: false }
    const pet = await setup({ kind: 'renderer', pack })
    await advance(GREETING_SETTLE_MS)
    expect(pet.sprite().dataset.frame).toBe('waving-1')
    await advance(600)
    expect(pet.sprite().dataset.action).toBe('idle')
    await advance(220)
    expect(pet.sprite().dataset.frame).toBe('waving-1')
    expect(pet.root().dataset.greetingRound).toBe('2')
    await advance(600)
    expect(pet.root().dataset.greeting).toBeUndefined()
    expect(pack.actions.wave.loop).toBe(false)
  })

  it('does not consume a page opportunity in renderer calibration previews', async () => {
    Reflect.deleteProperty(document, GREETING_MARKER)
    const pet = await setup({ kind: 'renderer', preview: true })
    await advance(2500)
    expect(pet.root().dataset.greetingRound).toBeUndefined()
    expect(Reflect.get(document, GREETING_MARKER)).toBeUndefined()
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
