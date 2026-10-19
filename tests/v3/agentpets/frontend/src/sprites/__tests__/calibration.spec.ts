import { describe, expect, it } from 'vitest'
import {
  calibrationEye,
  calibrationLayout,
  calibrationPoint,
  moveCalibrationPoint,
  mirrorFace,
  parseCalibration,
  sameCalibration,
} from '@/sprites/calibration'

describe('stable sprite calibration', () => {
  it('mirrors the displayed face without changing source calibration or losing eye ordering', () => {
    const face = {
      x: 0.3,
      y: 0.4,
      eyes: [
        { x: 0.2, y: 0.39 },
        { x: 0.4, y: 0.41 },
      ] as [{ x: number; y: number }, { x: number; y: number }],
      headTop: { x: 0.28, y: 0.1 },
    }
    const before = structuredClone(face)
    const mirrored = mirrorFace(face)!
    expect(mirrored).toEqual({
      x: 0.7,
      y: 0.4,
      eyes: [
        { x: 0.6, y: 0.41 },
        { x: 0.8, y: 0.39 },
      ],
      headTop: { x: 0.72, y: 0.1 },
    })
    expect(face).toEqual(before)
    expect(mirrorFace(null)).toBeNull()
  })
  it('accepts clamped boundary points despite floating-point crop arithmetic', () => {
    const value = parseCalibration({
      left: 0.1531,
      right: 0.9514,
      top: 0.0423,
      bottom: 0.9821,
      baseline: 0.9524,
      offset_x: 0.0291,
      offset_y: -0.0153,
    })
    const moved = moveCalibrationPoint(value, 'head_top', { x: -1, y: -1 })
    expect(calibrationPoint(moved, 'head_top')!.x).toBeCloseTo(0)
    expect(calibrationPoint(moved, 'head_top')!.y).toBeCloseTo(0)
  })
  it('keeps legacy calibration until both real eyes are placed and maps the head independently', () => {
    const old = parseCalibration({ eye_x: 0.5, eye_y: 0.35 })
    const left = moveCalibrationPoint(old, 'left_eye', { x: 0.3, y: 0.32 })
    expect(calibrationEye(left)).toEqual(calibrationEye(old))
    const both = moveCalibrationPoint(left, 'right_eye', { x: 0.7, y: 0.36 })
    const all = moveCalibrationPoint(both, 'head_top', { x: 0.48, y: 0.08 })
    const face = calibrationEye(all)!
    expect(face.x).toBeCloseTo(0.5)
    expect(face.y).toBeCloseTo(0.34)
    expect(face.eyes![0].x).toBeCloseTo(0.3)
    expect(face.eyes![0].y).toBeCloseTo(0.32)
    expect(face.eyes![1].x).toBeCloseTo(0.7)
    expect(face.eyes![1].y).toBeCloseTo(0.36)
    expect(face.headTop!.x).toBeCloseTo(0.48)
    expect(face.headTop!.y).toBeCloseTo(0.08)
    expect(old.left_eye_x).toBeNull()
    expect(sameCalibration(all, both)).toBe(false)
  })
  it('inverts crop, baseline, zoom-independent normalized position and offsets', () => {
    const old = parseCalibration({
      left: 0.2,
      right: 0.8,
      top: 0.1,
      bottom: 0.9,
      baseline: 0.8,
      offset_x: 0.03,
      offset_y: -0.02,
    })
    const next = moveCalibrationPoint(old, 'left_eye', { x: 0.4, y: 0.3 })
    expect(next.left_eye_x).toBeCloseTo(0.41)
    expect(next.left_eye_y).toBeCloseTo(0.26)
    expect(calibrationPoint(next, 'left_eye')!.x).toBeCloseTo(0.4)
    expect(calibrationPoint(next, 'left_eye')!.y).toBeCloseTo(0.3)
  })
  it('clamps dragged points to the image, preserves ordering and refuses invalid numeric input', () => {
    const old = parseCalibration({
      left_eye_x: 0.3,
      left_eye_y: 0.3,
      right_eye_x: 0.7,
      right_eye_y: 0.3,
      head_top_x: 0.5,
      head_top_y: 0.1,
    })
    const moved = moveCalibrationPoint(old, 'left_eye', { x: 2, y: -1 })
    expect(moved.left_eye_x).toBeLessThan(old.right_eye_x!)
    expect(moved.left_eye_y).toBeGreaterThan(old.head_top_y!)
    expect(() => parseCalibration({ left_eye_x: 0.3 })).toThrow()
    expect(() => parseCalibration({ ...old, left_eye_x: 0.8 })).toThrow()
    expect(() => parseCalibration({ ...old, head_top_y: 0.4 })).toThrow()
    expect(() => parseCalibration({ ...old, right_eye_x: true })).toThrow()
  })
  it('maps the selected eye through the same crop, baseline and offset as the sprite', () => {
    const value = parseCalibration({
      left: 0.2,
      right: 0.8,
      top: 0.1,
      bottom: 0.9,
      baseline: 0.8,
      offset_x: 0.03,
      offset_y: -0.02,
      eye_x: 0.4,
      eye_y: 0.3,
    })
    expect(calibrationEye(value)!.x).toBeCloseTo(0.23 / 0.6)
    expect(calibrationEye(value)!.y).toBeCloseTo(0.28 / 0.8)
    expect(calibrationEye(parseCalibration({}))).toBeNull()
    expect(sameCalibration(parseCalibration({}), parseCalibration({ eye_x: null, eye_y: null }))).toBe(true)
    expect(sameCalibration(value, parseCalibration({}))).toBe(false)
  })
  it.each([
    { eye_x: 0.3 },
    { eye_y: 0.4 },
    { eye_x: true, eye_y: 0.4 },
    { eye_x: 0.1, eye_y: 0.4, left: 0.3 },
    { eye_x: 0.5, eye_y: 0.95, baseline: 0.6 },
  ])('rejects partial or clipped eye coordinates %o', value => {
    expect(() => parseCalibration(value)).toThrow()
  })
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
