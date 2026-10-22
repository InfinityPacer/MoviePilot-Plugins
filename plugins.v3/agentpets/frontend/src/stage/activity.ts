import { isBlocked, pickFreeTarget, pickWalkTarget } from './geometry'
import { resolveAction, type SpritePack } from '@/sprites/schema'

/** Respect explicit sleep mappings without treating an idle fallback as resting artwork. */
export function supportsRest(pack: SpritePack, mappings?: Record<string, string>): boolean {
  const resolved = resolveAction(pack, 'sleep', undefined, false, { mappings, mappingKey: 'stage.doze' })
  const indices = resolved.action.frames.map(frame => pack.frames[frame])
  const idle = pack.actions.idle?.frames.map(frame => pack.frames[frame]) ?? [pack.frames.idle]
  return (
    resolved.key !== 'idle' &&
    indices.length > 0 &&
    indices.every(index => Number.isInteger(index) && index >= 0 && index < pack.grid.cols * pack.grid.rows) &&
    indices.some(index => !idle.includes(index))
  )
}

export interface ActivityPoint {
  x: number
  y: number
}

interface Visit extends ActivityPoint {
  at: number
}

export interface ActivityArea {
  current: ActivityPoint
  bounds: { x: [number, number]; y: [number, number] }
  free: boolean
  height: number
  mobile: boolean
  span: [number, number] | null
  allowed: (point: ActivityPoint) => boolean
}

export function activityRadius(height: number, mobile: boolean): number {
  return Math.max(48, Math.min(260, height * (mobile ? 0.9 : 1.8)))
}

const VISIT_LIMIT = 6
const VISIT_WINDOW = 45_000
const EPISODE_WINDOW = 25_000
const INTERACTION_WINDOW = 16_000

/** A finite activity episode and short-lived route preferences, never saved to storage. */
export class ActivityPolicy {
  private visits: Visit[] = []
  private remaining = 0
  private episodeUntil = 0
  private excitedUntil = 0
  private nearbyOrigin: ActivityPoint | null = null
  private boostPending = false
  private stepsTaken = 0

  private prune(now: number) {
    this.visits = this.visits.filter(visit => now >= visit.at && now - visit.at < VISIT_WINDOW)
    if (now >= this.episodeUntil) this.remaining = 0
    if (now >= this.excitedUntil) {
      this.nearbyOrigin = null
      this.boostPending = false
    }
  }

  continuing(now: number): boolean {
    this.prune(now)
    return this.remaining > 0
  }

  excited(now: number): boolean {
    this.prune(now)
    return this.nearbyOrigin !== null
  }

  delay(now: number, random: () => number): number {
    const short = this.continuing(now) || (this.excited(now) && this.boostPending)
    return short ? 800 + random() * 1000 : 6000 + random() * 8000
  }

  begin(now: number, random: () => number) {
    if (this.continuing(now)) return
    this.remaining = this.excited(now) ? 3 : random() < 0.5 ? 2 : 3
    this.episodeUntil = now + EPISODE_WINDOW
    this.stepsTaken = 0
    this.boostPending = false
  }

  remainingTime(now: number): number {
    this.prune(now)
    return this.remaining > 0 ? Math.max(0, this.episodeUntil - now) : 0
  }

  interact(point: ActivityPoint, now: number) {
    this.cancel()
    this.nearbyOrigin = { ...point }
    this.excitedUntil = now + INTERACTION_WINDOW
    this.boostPending = true
  }

  arrived(from: ActivityPoint, to: ActivityPoint, now: number) {
    this.prune(now)
    this.visits.push({ ...from, at: now }, { ...to, at: now })
    this.visits = this.visits.slice(-VISIT_LIMIT)
    this.remaining = Math.max(0, this.remaining - 1)
    this.stepsTaken++
  }

  cancel() {
    this.remaining = 0
    this.episodeUntil = 0
    this.excitedUntil = 0
    this.nearbyOrigin = null
    this.boostPending = false
    this.stepsTaken = 0
  }

  reset() {
    this.cancel()
    this.visits = []
  }

  target(area: ActivityArea, now: number, random: () => number): ActivityPoint | null {
    this.prune(now)
    const nearby = area.mobile || this.stepsTaken > 0 || this.excited(now) || random() < 0.8
    const origin = this.nearbyOrigin ?? area.current
    const radius = activityRadius(area.height, area.mobile)
    const minDistance = Math.max(12, Math.min(area.mobile ? 24 : 40, area.height * 0.25))
    const bounds = nearby
      ? {
          x: [Math.max(area.bounds.x[0], origin.x - radius), Math.min(area.bounds.x[1], origin.x + radius)] as [
            number,
            number,
          ],
          y: [Math.max(area.bounds.y[0], origin.y - radius), Math.min(area.bounds.y[1], origin.y + radius)] as [
            number,
            number,
          ],
        }
      : { x: [...area.bounds.x] as [number, number], y: [...area.bounds.y] as [number, number] }
    if (area.span) {
      if (area.current.x <= area.span[0]) bounds.x[1] = Math.min(bounds.x[1], area.span[0])
      else if (area.current.x >= area.span[1]) bounds.x[0] = Math.max(bounds.x[0], area.span[1])
    }
    if (bounds.x[0] > bounds.x[1] || bounds.y[0] > bounds.y[1]) return null

    const candidates: ActivityPoint[] = []
    for (let attempt = 0; attempt < 4; attempt++) {
      if (area.free) {
        const point = pickFreeTarget(random, area.current, bounds, minDistance)
        if (point) candidates.push(point)
      } else {
        const x = pickWalkTarget(random, area.current.x, bounds.x, area.span, minDistance)
        if (x !== null) candidates.push({ x, y: area.current.y })
      }
    }
    // Bounded alternatives also work in narrow spaces or with repeated random samples.
    candidates.push({ x: bounds.x[0], y: area.current.y }, { x: bounds.x[1], y: area.current.y })
    if (area.free) candidates.push({ x: area.current.x, y: bounds.y[0] }, { x: area.current.x, y: bounds.y[1] })

    let selected: ActivityPoint | null = null
    let lowestPenalty = Infinity
    const seen = new Set<string>()
    for (const point of candidates) {
      const signature = `${point.x}:${point.y}`
      if (seen.has(signature)) continue
      seen.add(signature)
      if (
        point.x < bounds.x[0] ||
        point.x > bounds.x[1] ||
        point.y < bounds.y[0] ||
        point.y > bounds.y[1] ||
        Math.hypot(point.x - area.current.x, point.y - area.current.y) < minDistance ||
        isBlocked(point.x, area.span) ||
        !area.allowed(point)
      )
        continue
      const avoidRadius = Math.max(24, area.height * 0.5)
      const penalty = this.visits.reduce(
        (sum, visit) => sum + Math.max(0, 1 - Math.hypot(point.x - visit.x, point.y - visit.y) / avoidRadius),
        0,
      )
      if (penalty < lowestPenalty) {
        lowestPenalty = penalty
        selected = point
      }
    }
    return selected
  }
}
