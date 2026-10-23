import type { SpritePack } from '@/sprites/schema'

export const ATTENTION_DWELL_MS = 350
export const ATTENTION_LEAVE_MS = 300
export const TOUCH_LOOK_MS = 700
const GAZE_INTERVAL_MS = 120

interface Point {
  x: number
  y: number
}

interface Rect extends Point {
  width: number
  height: number
}

const LOOK_DIRECTIONS = [
  '000',
  '022-5',
  '045',
  '067-5',
  '090',
  '112-5',
  '135',
  '157-5',
  '180',
  '202-5',
  '225',
  '247-5',
  '270',
  '292-5',
  '315',
  '337-5',
] as const

/** Native single-frame directions only; never animate an entire scan as a gaze. */
export function supportsLookDirections(pack: SpritePack): boolean {
  return (
    pack.codex_version === 'v2' &&
    LOOK_DIRECTIONS.every(direction => {
      const action = pack.actions[`look-${direction}`]
      const index = action?.frames.length === 1 ? pack.frames[action.frames[0]] : undefined
      return (
        !!action && !action.loop && Number.isInteger(index) && index! >= 0 && index! < pack.grid.cols * pack.grid.rows
      )
    })
  )
}

/** Distance hysteresis with optional stillness for brief fallback responses. */
export class ProximityTracker {
  private anchor: Point | null = null
  private entered = false
  private consumed = false

  sample(point: Point, rect: Rect, requireStillness = true): 'arm' | 'near' | 'leave' {
    const radius = Math.min(96, Math.max(48, rect.height / 2))
    const dx = Math.max(rect.x - point.x, 0, point.x - rect.x - rect.width)
    const dy = Math.max(rect.y - point.y, 0, point.y - rect.y - rect.height)
    if (!Number.isFinite(point.x + point.y) || Math.hypot(dx, dy) > radius + (this.entered ? 16 : 0)) {
      this.reset()
      return 'leave'
    }
    this.entered = true
    if (this.consumed) return 'near'
    if (!this.anchor || (requireStillness && Math.hypot(point.x - this.anchor.x, point.y - this.anchor.y) > 8)) {
      this.anchor = point
      return 'arm'
    }
    return 'near'
  }

  consume(): void {
    this.consumed = true
  }

  reset(): void {
    this.anchor = null
    this.entered = false
    this.consumed = false
  }
}

/** 000 is screen-up; quantization never changes the character's position or facing. */
export class GazeTracker {
  private direction: number | null = null
  private changedAt = 0

  select(point: Point, origin: Point, now: number): string | null {
    const dx = point.x - origin.x,
      dy = point.y - origin.y
    if (!Number.isFinite(dx + dy + now)) return this.action()
    if (Math.hypot(dx, dy) < 12) return this.action()
    const degrees = ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360
    if (this.direction !== null) {
      const delta = Math.abs(((degrees - this.direction * 22.5 + 540) % 360) - 180)
      if (delta <= 17.25 || this.remainingDelay(now) > 0) return this.action()
    }
    this.direction = Math.round(degrees / 22.5) % 16
    this.changedAt = now
    return this.action()
  }

  private action(): string | null {
    return this.direction === null ? null : `look-${LOOK_DIRECTIONS[this.direction]}`
  }

  remainingDelay(now: number): number {
    return this.direction === null ? 0 : Math.max(0, GAZE_INTERVAL_MS - (now - this.changedAt))
  }

  reset(): void {
    this.direction = null
    this.changedAt = 0
  }
}
