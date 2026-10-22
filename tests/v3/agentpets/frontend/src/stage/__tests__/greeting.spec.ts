import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { buildCodexPetPack, BUILTIN_PACK } from '@/sprites/schema'
import {
  claimPageGreeting,
  greetingPlayback,
  GREETING_MARKER,
  GREETING_PAUSE_MS,
  GREETING_SETTLE_MS,
  GREETING_WAIT_MS,
  SINGLE_GREETING_MS,
  useStartupGreeting,
} from '@/stage/greeting'

afterEach(() => Reflect.deleteProperty(document, GREETING_MARKER))

describe('document greeting opportunity', () => {
  it('allows a new document, but not another pet, remount or reimport in the same document', () => {
    const page = document.implementation.createHTMLDocument()
    expect(claimPageGreeting(page)).toBe(true)
    expect(claimPageGreeting(page)).toBe(false)
    expect(Reflect.get(page, Symbol.for('moviepilot.agentpets.startup-greeting'))).toBe(true)
    expect(claimPageGreeting(document.implementation.createHTMLDocument())).toBe(true)
  })
})

describe('native greeting duration', () => {
  it.each(['v1', 'v2'] as const)('uses the complete %s waving sequence including the last frame', version => {
    const pack = buildCodexPetPack('pet.png', 1536, version === 'v1' ? 1872 : 2288).pack
    expect(greetingPlayback(pack)).toEqual({
      duration: pack.actions.wave.frames.length * 160,
      pause: 0,
      frameDriven: true,
    })
    expect(pack.actions.wave.loop).toBe(false)
  })

  it('respects stage mappings and individual durations without mutating the action', () => {
    const pack = buildCodexPetPack('pet.png', 1536, 2288).pack
    pack.actions.custom = { frames: ['idle', 'waving-1'], frame_ms: 900, frame_durations: [80, 320], loop: false }
    expect(greetingPlayback(pack, { 'stage.wave': 'custom' })).toEqual({ duration: 400, pause: 0, frameDriven: true })
    expect(greetingPlayback(BUILTIN_PACK, undefined, false)).toEqual({ duration: 960, pause: 0, frameDriven: true })
    expect(pack.actions.custom.frame_durations).toEqual([80, 320])
  })

  it('separates two single-frame waves with idle and skips a missing action', () => {
    const pack = buildCodexPetPack('pet.png', 1536, 2288).pack
    pack.actions.wave = { frames: ['waving-1'], frame_ms: 160, loop: false }
    expect(greetingPlayback(pack)).toEqual({ duration: SINGLE_GREETING_MS, pause: GREETING_PAUSE_MS })
    delete pack.actions.wave
    expect(greetingPlayback(pack)).toBeNull()
  })

  it('does not mistake a mapped idle action for greeting when the wave is missing', () => {
    const pack = buildCodexPetPack('pet.png', 1536, 2288).pack
    delete pack.actions.wave
    expect(greetingPlayback(pack, { 'intent.idle': 'waiting' })).toBeNull()
  })
})

describe('finite startup greeting', () => {
  function setup(ready = true, duration = 800, pause = 0, frameDriven = false) {
    vi.useFakeTimers()
    Reflect.deleteProperty(document, GREETING_MARKER)
    const allowed = ref(true)
    const loaded = ref(ready)
    const position = ref(0)
    const finished = vi.fn()
    let greeting!: ReturnType<typeof useStartupGreeting>
    const app = createApp({
      setup() {
        greeting = useStartupGreeting({
          allowed: () => allowed.value,
          ready: () => loaded.value,
          stable: () => position.value,
          playback: () => ({ duration, pause, frameDriven }),
          finished,
        })
        return () => h('div')
      },
    })
    app.mount(document.createElement('div'))
    greeting.arm()
    return { app, greeting, allowed, loaded, position, finished }
  }

  it('waits for loaded artwork and stable geometry, then completes exactly two rounds', async () => {
    const view = setup(false)
    await vi.advanceTimersByTimeAsync(2000)
    expect(view.greeting.round.value).toBe(0)
    view.loaded.value = true
    await nextTick()
    await vi.advanceTimersByTimeAsync(GREETING_SETTLE_MS - 1)
    view.position.value++
    await nextTick()
    await vi.advanceTimersByTimeAsync(GREETING_SETTLE_MS - 1)
    expect(view.greeting.phase.value).toBeNull()
    await vi.advanceTimersByTimeAsync(1)
    expect(view.greeting.round.value).toBe(1)
    await vi.advanceTimersByTimeAsync(800)
    expect(view.greeting.round.value).toBe(2)
    expect(view.greeting.phase.value).toBe('wave')
    await vi.advanceTimersByTimeAsync(800)
    expect(view.greeting.active.value).toBe(false)
    expect(view.finished).toHaveBeenCalledTimes(1)
    view.app.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('inserts idle only for single-frame greetings', async () => {
    const view = setup(true, SINGLE_GREETING_MS, GREETING_PAUSE_MS)
    await vi.advanceTimersByTimeAsync(GREETING_SETTLE_MS + SINGLE_GREETING_MS)
    expect(view.greeting.phase.value).toBe('pause')
    await vi.advanceTimersByTimeAsync(GREETING_PAUSE_MS)
    expect(view.greeting.round.value).toBe(2)
    expect(view.greeting.phase.value).toBe('wave')
    await vi.advanceTimersByTimeAsync(SINGLE_GREETING_MS)
    expect(view.greeting.phase.value).toBeNull()
    view.app.unmount()
  })

  it('ignores unrelated idle cycle notifications during the single-frame pause', async () => {
    const view = setup(true, SINGLE_GREETING_MS, GREETING_PAUSE_MS)
    await vi.advanceTimersByTimeAsync(GREETING_SETTLE_MS + SINGLE_GREETING_MS)
    expect(view.greeting.phase.value).toBe('pause')
    view.greeting.frameComplete()
    await vi.advanceTimersByTimeAsync(GREETING_PAUSE_MS)
    expect(view.greeting.round.value).toBe(2)
    expect(view.greeting.phase.value).toBe('wave')
    view.app.unmount()
  })

  it.each(['pending', 'playing'] as const)('does not resume a cancelled %s opportunity', async state => {
    const view = setup()
    if (state === 'playing') await vi.advanceTimersByTimeAsync(GREETING_SETTLE_MS)
    view.allowed.value = false
    await nextTick()
    view.allowed.value = true
    view.position.value++
    await nextTick()
    view.greeting.arm()
    await vi.advanceTimersByTimeAsync(10000)
    expect(view.greeting.phase.value).toBeNull()
    expect(view.greeting.round.value).toBe(state === 'pending' ? 0 : 1)
    view.app.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('expires delayed artwork and never greets after a later successful load', async () => {
    const view = setup(false)
    await vi.advanceTimersByTimeAsync(GREETING_WAIT_MS)
    view.loaded.value = true
    await nextTick()
    await vi.advanceTimersByTimeAsync(1000)
    expect(view.greeting.round.value).toBe(0)
    view.app.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('waits for actual frame completion even when a native sequence stalls past its expected duration', async () => {
    const view = setup(true, 800, 0, true)
    await vi.advanceTimersByTimeAsync(GREETING_SETTLE_MS + 3000)
    expect(view.greeting.round.value).toBe(1)
    expect(view.greeting.phase.value).toBe('wave')
    view.greeting.frameComplete(0)
    expect(view.greeting.round.value).toBe(1)
    view.greeting.frameComplete()
    await nextTick()
    expect(view.greeting.round.value).toBe(2)
    view.greeting.frameComplete(1)
    expect(view.greeting.phase.value).toBe('wave')
    await vi.advanceTimersByTimeAsync(3000)
    expect(view.greeting.phase.value).toBe('wave')
    view.greeting.frameComplete()
    expect(view.greeting.active.value).toBe(false)
    view.app.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
