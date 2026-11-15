import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockPet } from '@/dev/mockHost'
import { PositionStorage, type StoredPosition } from '@/stage/positionStorage'
import { PausableTimers } from '@/stage/timers'

function setup() {
  const scope = { pet: createMockPet('stage', 'ying'), pluginId: 'AgentPets' }
  let value: StoredPosition | null = { roam: 'floor', xRatio: 0.4, yRatio: 1 }
  const timers = new PausableTimers()
  const storage = new PositionStorage(
    () => scope,
    () => value,
    timers,
  )
  const save = vi.spyOn(scope.pet.storage, 'set').mockResolvedValue(undefined)
  return {
    scope,
    timers,
    storage,
    save,
    position: (next: StoredPosition | null) => {
      value = next
    },
  }
}

function deferred() {
  let resolve!: () => void
  let reject!: (error: Error) => void
  const promise = new Promise<void>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

describe('position storage lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-15T12:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('coalesces deferred requests and samples the latest position when the throttle expires', async () => {
    const f = setup()
    f.storage.request()
    await vi.advanceTimersByTimeAsync(1000)
    f.position({ xRatio: 0.5 })
    f.storage.request()
    f.position({ xRatio: 0.7 })
    f.storage.request()
    await vi.advanceTimersByTimeAsync(28_999)
    expect(f.save).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(f.save.mock.calls.map(([value]) => value)).toEqual([
      { roam: 'floor', xRatio: 0.4, yRatio: 1 },
      { xRatio: 0.7 },
    ])
    f.storage.dispose()
  })

  it('retains the remaining throttle delay while editor timers are paused', async () => {
    const f = setup()
    f.storage.request()
    await vi.advanceTimersByTimeAsync(1000)
    f.position({ xRatio: 0.8 })
    f.storage.request()
    f.timers.pause()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(f.save).toHaveBeenCalledTimes(1)
    f.timers.resume()
    await vi.advanceTimersByTimeAsync(28_999)
    expect(f.save).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(f.save).toHaveBeenCalledTimes(2)
    f.storage.dispose()
  })

  it('serializes pending writes and preserves an immediate request over later normal requests', async () => {
    const f = setup()
    const pending = deferred()
    f.save.mockReturnValueOnce(pending.promise)
    f.storage.request()
    f.position({ xRatio: 0.9 })
    f.storage.request(true)
    f.storage.request()
    expect(f.save).toHaveBeenCalledTimes(1)
    pending.resolve()
    await vi.advanceTimersByTimeAsync(0)
    expect(f.save).toHaveBeenCalledTimes(2)
    expect(f.save).toHaveBeenLastCalledWith({ xRatio: 0.9 })
    f.storage.dispose()
  })

  it('cannot reuse a completion after the plugin instance changes with the same Pet object', async () => {
    const f = setup()
    const pending = deferred()
    f.save.mockReturnValueOnce(pending.promise)
    f.storage.request()
    f.scope.pluginId = 'AgentPets_clone'
    f.storage.reset()
    pending.resolve()
    await vi.advanceTimersByTimeAsync(0)
    f.storage.request(true)
    expect(f.save).toHaveBeenCalledTimes(2)
    f.storage.dispose()
  })

  it('cancels the old delayed position when its scope is reset', async () => {
    const f = setup()
    f.storage.request()
    await vi.advanceTimersByTimeAsync(1000)
    f.position({ xRatio: 0.8 })
    f.storage.request()
    f.storage.reset()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(f.save).toHaveBeenCalledTimes(1)
    f.storage.dispose()
  })

  it('flushes one delayed position on dispose and leaves no future timer or request', async () => {
    const f = setup()
    f.storage.request()
    await vi.advanceTimersByTimeAsync(1000)
    f.position({ xRatio: 0.8 })
    f.storage.request()
    f.storage.dispose()
    expect(f.save).toHaveBeenCalledTimes(2)
    expect(f.timers.has('save')).toBe(false)
    f.storage.request(true)
    f.storage.dispose()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(f.save).toHaveBeenCalledTimes(2)
  })

  it('does not revive a pending repeat when its write settles after disposal', async () => {
    const f = setup()
    const pending = deferred()
    f.save.mockReturnValueOnce(pending.promise)
    f.storage.request()
    f.position({ xRatio: 0.9 })
    f.storage.request(true)
    f.storage.dispose()
    pending.resolve()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(f.save).toHaveBeenCalledTimes(1)
    expect(f.timers.has('save')).toBe(false)
  })

  it('does not save a snapshot that is temporarily unavailable', async () => {
    const f = setup()
    f.position(null)
    f.storage.request(true)
    expect(f.save).not.toHaveBeenCalled()
    f.storage.dispose()
  })

  it.each([null, {}, { xRatio: NaN }, { xRatio: Infinity }, { xRatio: '0.5' }])(
    'ignores malformed stored coordinates: %s',
    async value => {
      const f = setup()
      vi.spyOn(f.scope.pet.storage, 'get').mockResolvedValue(value)
      expect(await f.storage.read()).toBeNull()
      f.storage.dispose()
    },
  )
})
