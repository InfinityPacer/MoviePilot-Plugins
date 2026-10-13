import { describe, expect, it } from 'vitest'
import { calibrationLayout, parseCalibration } from '@/sprites/calibration'

describe('stable sprite calibration', () => {
  it('maps the source foot to the same bottom line and uses content dimensions', () => {
    const value = parseCalibration({ left: 0.2, right: 0.8, top: 0.1, bottom: 0.95, baseline: 0.9 })
    const layout = calibrationLayout(value, 192 / 208)
    expect(layout.aspectRatio).toBeCloseTo(((192 / 208) * 0.6) / 0.85)
    const frameTop = parseFloat(layout.frame.top) / 100
    const frameHeight = parseFloat(layout.frame.height) / 100
    expect(frameTop + value.baseline * frameHeight).toBeCloseTo(1)
    expect(calibrationLayout(parseCalibration(null), 1).frame).toEqual({
      width: '100%',
      height: '100%',
      left: '0%',
      top: '0%',
    })
  })
  it.each([{ left: 0.95 }, { baseline: 0 }, { offset_y: 0.3 }, { top: NaN }, { extra: 1 }])(
    'rejects invalid bounds %o',
    value => {
      expect(() => parseCalibration(value)).toThrow()
    },
  )
})
