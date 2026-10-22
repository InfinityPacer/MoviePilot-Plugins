export const LONG_PRESS_MS = 450

const MEMORY_LIMIT = 20
const MEMORY_WINDOW_MS = 30_000
const INTERACTION_LIMIT = 4

interface InteractionState {
  lastAt: number
  count: number
  lastResponseAt?: number
  lastPose?: 'wave' | 'jump'
}

/** Small, per-stage memory; interactions never write persistent pet settings. */
export class InteractionMemory {
  private states = new Map<string, InteractionState>()

  private active(key: string, now: number): InteractionState | undefined {
    const state = this.states.get(key)
    return state && now >= state.lastAt && now - state.lastAt < MEMORY_WINDOW_MS ? state : undefined
  }

  private remember(key: string, state: InteractionState) {
    this.states.delete(key)
    this.states.set(key, state)
    if (this.states.size > MEMORY_LIMIT) this.states.delete(this.states.keys().next().value!)
  }

  record(key: string, now: number): void {
    const state = this.active(key, now) ?? { lastAt: now, count: 0 }
    state.lastAt = now
    state.count = Math.min(INTERACTION_LIMIT, state.count + 1)
    this.remember(key, state)
  }

  respond(key: string, now: number): { pose: 'wave' | 'jump'; duration: number } | null {
    const state = this.active(key, now) ?? { lastAt: now, count: 0 }
    const duration = this.duration(state, now)
    if (duration === null) return null
    const pose = state.lastPose === 'wave' ? 'jump' : 'wave'
    state.lastResponseAt = now
    state.lastPose = pose
    this.remember(key, state)
    return { pose, duration }
  }

  /** Touch previews reserve nothing until release; attention keeps explicit pose order. */
  attend(key: string, now: number, commit = true): { duration: number } | null {
    const prior = this.active(key, now) ?? { lastAt: now, count: 0 }
    const next = { ...prior, lastAt: now, count: Math.min(INTERACTION_LIMIT, prior.count + 1) }
    const duration = this.duration(next, now)
    if (duration === null) return null
    if (commit) this.remember(key, { ...next, lastResponseAt: now })
    return { duration }
  }

  private duration(state: InteractionState, now: number): number | null {
    const repeated = Math.max(0, state.count - 1)
    const cooldown = Math.min(6000, 2400 + repeated * 1200)
    if (state.lastResponseAt !== undefined && now - state.lastResponseAt < cooldown) return null
    return Math.max(700, 1200 - repeated * 150)
  }

  landingDelay(key: string, now: number): number {
    const count = this.active(key, now)?.count ?? 0
    return Math.min(1350, 900 + Math.max(0, count - 1) * 150)
  }
}
