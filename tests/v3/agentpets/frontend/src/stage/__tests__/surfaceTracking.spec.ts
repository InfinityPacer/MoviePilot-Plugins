import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SurfaceTracking } from '@/stage/surfaceTracking'
import { PausableTimers } from '@/stage/timers'

let observers: TestObserver[] = []
class TestObserver {
  observe = vi.fn()
  disconnect = vi.fn()
  constructor(readonly callback: MutationCallback) {
    observers.push(this)
  }
  deliver(target: Node) {
    this.callback([{ target } as MutationRecord], this as unknown as MutationObserver)
  }
}
const tracking: SurfaceTracking[] = []
beforeEach(() => {
  vi.useFakeTimers()
  observers = []
  vi.stubGlobal('MutationObserver', TestObserver)
})
afterEach(() => {
  tracking.splice(0).forEach(value => value.dispose())
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
function setup() {
  const layer = document.createElement('div')
  const own = document.createElement('button')
  layer.appendChild(own)
  const outside = document.createElement('section')
  const timers = new PausableTimers()
  const check = vi.fn()
  const poll = vi.fn()
  const watcher = new SurfaceTracking(timers, () => layer, check, poll)
  tracking.push(watcher)
  return { watcher, timers, check, poll, layer, own, outside }
}

describe('surface observation resources', () => {
  it('observes the selected preview subtree and ignores only the pet own mutations', async () => {
    const f = setup()
    f.watcher.observe(f.outside)
    expect(observers[0].observe).toHaveBeenCalledWith(f.outside, { subtree: true, childList: true, attributes: true })
    observers[0].deliver(f.own)
    await vi.advanceTimersByTimeAsync(500)
    expect(f.check).not.toHaveBeenCalled()
    observers[0].deliver(f.outside)
    observers[0].deliver(f.outside)
    await vi.advanceTimersByTimeAsync(499)
    expect(f.check).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(f.check).toHaveBeenCalledTimes(1)
  })

  it('combines scroll bursts per frame and cancels pending checks on pause', async () => {
    const f = setup()
    f.watcher.observe(document.body)
    window.dispatchEvent(new Event('scroll'))
    window.dispatchEvent(new Event('scroll'))
    await vi.advanceTimersByTimeAsync(32)
    expect(f.check).toHaveBeenCalledTimes(1)
    window.dispatchEvent(new Event('scroll'))
    observers[0].deliver(f.outside)
    f.watcher.pause()
    expect(observers[0].disconnect).toHaveBeenCalledTimes(1)
    expect(f.watcher.observing).toBe(false)
    await vi.advanceTimersByTimeAsync(600)
    expect(f.check).toHaveBeenCalledTimes(1)
    expect(f.timers.has('surface')).toBe(false)
  })

  it('rejects late observer and frame callbacks after a different surface starts being watched', () => {
    const f = setup()
    let finish!: FrameRequestCallback
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
      finish = callback
      return 9
    })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    f.watcher.observe(document.body)
    window.dispatchEvent(new Event('scroll'))
    f.watcher.observe(f.outside)
    observers[0].deliver(f.outside)
    finish(0)
    expect(f.check).not.toHaveBeenCalled()
    expect(f.timers.has('surface')).toBe(false)
    expect(f.watcher.observing).toBe(true)
  })

  it('keeps the remaining mutation delay when shared editor timers pause', async () => {
    const f = setup()
    f.watcher.observe(document.body)
    observers[0].deliver(f.outside)
    await vi.advanceTimersByTimeAsync(100)
    f.timers.pause()
    await vi.advanceTimersByTimeAsync(1000)
    expect(f.check).not.toHaveBeenCalled()
    f.timers.resume()
    await vi.advanceTimersByTimeAsync(400)
    expect(f.check).toHaveBeenCalledTimes(1)
  })

  it('keeps polling every 500ms even without a surface observer and does not duplicate intervals', async () => {
    const f = setup()
    f.watcher.syncPolling(true)
    f.watcher.syncPolling(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(f.poll).toHaveBeenCalledTimes(4)
    f.watcher.pause()
    await vi.advanceTimersByTimeAsync(500)
    expect(f.poll).toHaveBeenCalledTimes(5)
    f.watcher.syncPolling(false)
    await vi.advanceTimersByTimeAsync(1000)
    expect(f.poll).toHaveBeenCalledTimes(5)
    f.watcher.syncPolling(true)
    await vi.advanceTimersByTimeAsync(500)
    expect(f.poll).toHaveBeenCalledTimes(6)
  })

  it('preserves scroll checks on browsers without MutationObserver', async () => {
    const f = setup()
    vi.stubGlobal('MutationObserver', undefined)
    f.watcher.observe(document.body)
    expect(f.watcher.observing).toBe(false)
    window.dispatchEvent(new Event('scroll'))
    await vi.advanceTimersByTimeAsync(32)
    expect(f.check).toHaveBeenCalledTimes(1)
  })

  it('disposes interval, mutation throttle, observer and scroll frame and cannot be restarted', async () => {
    const f = setup()
    f.watcher.observe(document.body)
    f.watcher.syncPolling(true)
    observers[0].deliver(f.outside)
    window.dispatchEvent(new Event('scroll'))
    f.watcher.dispose()
    f.watcher.observe(document.body)
    f.watcher.syncPolling(true)
    observers[0].deliver(f.outside)
    window.dispatchEvent(new Event('scroll'))
    await vi.advanceTimersByTimeAsync(2000)
    expect(f.check).not.toHaveBeenCalled()
    expect(f.poll).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
    expect(observers).toHaveLength(1)
  })
})
