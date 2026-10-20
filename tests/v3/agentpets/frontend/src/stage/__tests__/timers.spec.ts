import { expect, it, vi } from 'vitest'
import { PausableTimers } from '@/stage/timers'
import { registerEditor, onEditorPresence } from '@/editor/presence'

it('preserves remaining delays, including tasks added while paused', () => {
  vi.useFakeTimers()
  const clock = vi.spyOn(performance, 'now')
  clock.mockReturnValue(0)
  const timers = new PausableTimers(),
    callback = vi.fn()
  timers.set('peek', 1000, callback)
  vi.advanceTimersByTime(400)
  clock.mockReturnValue(400)
  timers.pause()
  timers.set('blink', 100, callback)
  vi.advanceTimersByTime(10000)
  expect(callback).not.toHaveBeenCalled()
  timers.resume()
  vi.advanceTimersByTime(100)
  expect(callback).toHaveBeenCalledTimes(1)
  vi.advanceTimersByTime(500)
  expect(callback).toHaveBeenCalledTimes(2)
  timers.set('pending', 1000, callback)
  timers.dispose()
  expect(vi.getTimerCount()).toBe(0)
})

it('resumes only after the last editor closes and releases subscriptions', () => {
  const changed = vi.fn(),
    off = onEditorPresence(changed)
  const first = registerEditor(),
    second = registerEditor()
  first()
  expect(changed.mock.calls.map(([active]) => active)).toEqual([false, true])
  second()
  second()
  off()
  expect(changed.mock.calls.map(([active]) => active)).toEqual([false, true, false])
})
