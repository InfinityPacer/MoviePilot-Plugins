import { describe, expect, it } from 'vitest'
import { BUILTIN_PACKS } from '@/sprites/schema'
import { calibrationEye, calibrationForAction, mirrorFace } from '@/sprites/calibration'
import { peekHome, peekLayout, PEEK_TUCK, PEEK_TILT } from '@/stage/peek'
import type { PeekEdge } from '@/stage/peek'
import type { StageViewport } from '@/stage/geometry'

const cells = { 'builtin-chibiterasu': [160, 139], 'builtin-nailong': [480, 414], 'builtin-kurisu': [384, 414] }
const edges: Array<[PeekEdge, boolean]> = [
  ['bottom', true],
  ['bottom', false],
  ['left', true],
  ['right', false],
]

describe('measured built-in peek landmarks', () => {
  it.each(Object.keys(cells).flatMap(key => [0, PEEK_TILT].map(angle => ({ key, angle }))))(
    'keeps eyes visible for $key at $angle degrees, including level bottom eyes',
    ({ key, angle }) => {
      const cell = cells[key as keyof typeof cells]
      const pack = BUILTIN_PACKS[key]
      const original = calibrationEye(calibrationForAction(pack.calibration!, pack.action_baselines, 'peek'))!
      expect(original.eyes).toHaveLength(2)
      expect(original.headTop!.y).toBeLessThan(original.eyes![0].y)
      for (const width of [390, 1280]) {
        const view: StageViewport = {
          width,
          height: 800,
          keyboardInset: 0,
          safeArea: { left: 12, right: 12, top: 20, bottom: 32 },
        }
        for (const scale of [0.6, 1, 1.6]) {
          const size = { width: (120 * scale * cell[0]) / cell[1], height: 120 * scale }
          for (const [edge, fromLeft] of edges) {
            const home = peekHome({ x: fromLeft ? 12 : width, y: 800 }, view, size, edge)
            const face = key === 'builtin-chibiterasu' && fromLeft ? mirrorFace(original)! : original
            const hidden = peekLayout(home, size, view, edge, PEEK_TUCK, face, false)
            expect(edge === 'bottom' ? hidden.visible.height : hidden.visible.width).toBe(0)
            const layout = peekLayout(home, size, view, edge, 1, face, true, 1, edge === 'bottom' ? angle : PEEK_TILT)
            expect(layout.fromLeft).toBe(fromLeft)
            const a = layout.artwork
            const radians = (a.rotation * Math.PI) / 180
            const projected = face.eyes!.map(point => ({
              x:
                a.x +
                a.width / 2 +
                (point.x - 0.5) * a.width * Math.cos(radians) -
                (point.y - 0.5) * a.height * Math.sin(radians),
              y:
                a.y +
                a.height / 2 +
                (point.x - 0.5) * a.width * Math.sin(radians) +
                (point.y - 0.5) * a.height * Math.cos(radians),
            }))
            const inside = projected.filter(
              point => point.x > 12 && point.x < width - 12 && point.y > 20 && point.y < 768,
            )
            expect(inside, `${key}/${edge}/${fromLeft}/${width}/${scale}/${angle}`).toHaveLength(
              edge === 'bottom' && angle === 0 ? 2 : 1,
            )
          }
        }
      }
    },
  )
})
