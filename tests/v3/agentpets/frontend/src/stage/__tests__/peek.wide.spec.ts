import { describe, expect, it } from 'vitest'
import { floorLine, type StageViewport } from '@/stage/geometry'
import { peekHome, peekLayout, PEEK_TUCK, PEEK_TILT } from '@/stage/peek'
import { calibrationEye, calibrationLayout, parseCalibration } from '@/sprites/calibration'

describe('wide calibrated bottom peeking', () => {
  it.each([180, 390, 1280].flatMap(viewportWidth => [0, PEEK_TILT].map(tilt => ({ viewportWidth, tilt }))))(
    'keeps the calibrated eyes visible in a $viewportWidth px viewport at $tilt degrees',
    ({ viewportWidth, tilt }) => {
      const calibration = parseCalibration({
        top: 0.1,
        bottom: 0.35,
        baseline: 0.35,
        left_eye_x: 0.35,
        left_eye_y: 0.2,
        right_eye_x: 0.65,
        right_eye_y: 0.2,
        head_top_x: 0.5,
        head_top_y: 0.12,
      })
      const face = calibrationEye(calibration)!
      for (const inset of [0, 12]) {
        const view: StageViewport = {
          width: viewportWidth,
          height: 800,
          keyboardInset: 0,
          safeArea: { left: inset, right: inset, top: 24, bottom: 32 },
        }
        for (const height of [120, 180, 240]) {
          const size = { height, width: height * calibrationLayout(calibration, 12 / 13).aspectRatio }
          for (const x of [0, viewportWidth]) {
            const home = peekHome({ x, y: 0 }, view, size)
            const hidden = peekLayout(home, size, view, 'bottom', PEEK_TUCK, face, true, 1, tilt)
            const layout = peekLayout(home, size, view, 'bottom', 1, face, true, 1, tilt)
            const a = layout.artwork
            const angle = (a.rotation * Math.PI) / 180
            const eyes = face.eyes!.map(point => ({
              x:
                a.x +
                a.width / 2 +
                (point.x - 0.5) * a.width * Math.cos(angle) -
                (point.y - 0.5) * a.height * Math.sin(angle),
              y:
                a.y +
                a.height / 2 +
                (point.x - 0.5) * a.width * Math.sin(angle) +
                (point.y - 0.5) * a.height * Math.cos(angle),
            }))
            for (const point of eyes) {
              expect(point.x).toBeGreaterThanOrEqual(view.safeArea.left)
              expect(point.x).toBeLessThanOrEqual(view.width - view.safeArea.right)
            }
            expect(eyes.filter(point => point.y >= view.safeArea.top && point.y < floorLine(view))).toHaveLength(
              tilt === 0 ? 2 : 1,
            )
            expect(hidden.visible.height).toBe(0)
            for (const progress of [1.05, 1.03, 1.01, 1]) {
              const rising = peekLayout(home, size, view, 'bottom', progress, face, true, 1, tilt)
              expect(rising.artwork.x).toBeCloseTo(hidden.artwork.x)
              expect(rising.artwork.width).toBe(hidden.artwork.width)
              expect(rising.artwork.rotation).toBe(hidden.artwork.rotation)
            }
          }
        }
      }
    },
  )
})
