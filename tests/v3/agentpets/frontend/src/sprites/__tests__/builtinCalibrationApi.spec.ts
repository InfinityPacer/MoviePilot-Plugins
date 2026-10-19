import { describe, expect, it, vi } from 'vitest'
import { builtinDefaultCalibration, loadBuiltinCalibration } from '@/sprites/builtinCalibration'
import { calibrationForAction, parseCalibration } from '@/sprites/calibration'
import { BUILTIN_PACKS } from '@/sprites/schema'

const keys = ['ying', ...Object.keys(BUILTIN_PACKS)]

describe('instance-scoped built-in calibration', () => {
  it.each(keys)('loads only the calibration for %s and retains bundled artwork', async key => {
    const original = JSON.stringify(BUILTIN_PACKS)
    const calibration = parseCalibration({ ...builtinDefaultCalibration(key), offset_x: 0.02 })
    const api = { get: vi.fn().mockResolvedValue({ success: true, data: { id: key, calibration } }) }
    const result = await loadBuiltinCalibration(api, 'Clone1', key, new AbortController().signal)
    expect(result).toEqual(calibration)
    expect(api.get).toHaveBeenCalledExactlyOnceWith(`plugin/Clone1/packs/calibration?key=${key}`)
    expect(JSON.stringify(BUILTIN_PACKS)).toBe(original)
  })

  it.each(keys)('keeps %s available offline without sharing mutable defaults', async key => {
    const value = await loadBuiltinCalibration(null, 'Clone1', key, new AbortController().signal)
    value.offset_x = 0.2
    expect(builtinDefaultCalibration(key).offset_x).not.toBe(0.2)
  })

  it.each([
    { success: false },
    { success: true, data: { id: 'other', calibration: {} } },
    { success: true, data: { id: 'ying' } },
    { success: true, data: { id: 'ying', calibration: { left: 0.95 } } },
  ])('rejects invalid readback instead of exposing a saveable default: %j', async response => {
    const api = { get: vi.fn().mockResolvedValue(response) }
    await expect(loadBuiltinCalibration(api, 'Clone1', 'ying', new AbortController().signal)).rejects.toThrow()
  })

  it('stops waiting on abort and timeout', async () => {
    vi.useFakeTimers()
    for (const abort of [true, false]) {
      const controller = new AbortController()
      const api = { get: vi.fn().mockReturnValue(new Promise(() => undefined)) }
      const rejected = expect(loadBuiltinCalibration(api, 'Clone1', 'ying', controller.signal)).rejects.toThrow()
      if (abort) controller.abort()
      else await vi.advanceTimersByTimeAsync(5000)
      await rejected
      expect(vi.getTimerCount()).toBe(0)
    }
  })

  it('applies a saved common baseline while preserving native per-action offsets', () => {
    const original = builtinDefaultCalibration('builtin-kurisu')
    const edited = parseCalibration({ ...original, baseline: original.baseline - 0.05 })
    const pack = BUILTIN_PACKS['builtin-kurisu']
    for (const action of ['idle', 'sleep', 'peek', 'jump']) {
      const native = calibrationForAction(original, pack.action_baselines, action)
      const current = calibrationForAction(edited, pack.action_baselines, action, original.baseline)
      expect(current.baseline).toBeCloseTo(native.baseline - 0.05)
    }
    const cropped = parseCalibration({ top: 0.4, bottom: 0.8, baseline: 0.6 })
    const shifted = calibrationForAction(cropped, { sleep: 0.5 }, 'sleep', 1)
    expect(shifted.baseline).toBeGreaterThan(cropped.top)
    expect(shifted.baseline).toBeLessThanOrEqual(cropped.bottom)
  })
})
