import type { AgentPetContext } from '@/host'
import type { RoamMode } from './geometry'
import type { PeekEdge } from './peek'
import type { PausableTimers } from './timers'

/** Per-user position in pet.storage; coordinates remain relative to the current viewport. */
export interface StoredPosition {
  /** Activity mode when saved. */
  roam?: RoamMode
  /** Horizontal ratio within the available range, from 0 (left) to 1 (right). */
  xRatio: number
  /** Vertical ratio from the safe-area top to the ground; used for surfaces and free placement. */
  yRatio?: number
  peekEdge?: PeekEdge
}

const SAVE_THROTTLE = 30_000
interface PositionScope {
  pet: AgentPetContext | null
  pluginId: string
}

/** Serializes saves within one Pet identity; old completions cannot update a new scope. */
export class PositionStorage {
  private lastSaved = ''
  private lastSaveAt = 0
  private generation = 0
  private pending: { repeat: boolean; immediate: boolean } | null = null
  private disposed = false

  constructor(
    private scope: () => PositionScope,
    private snapshot: () => StoredPosition | null,
    private timers: Pick<PausableTimers, 'has' | 'set' | 'clear'>,
  ) {}

  async read(): Promise<StoredPosition | null> {
    try {
      const stored = await this.scope().pet?.storage?.get?.<StoredPosition>()
      if (stored && typeof stored.xRatio === 'number' && Number.isFinite(stored.xRatio)) return stored
    } catch {
      console.warn('[AgentPets] position unavailable')
    }
    return null
  }

  request(immediate = false) {
    if (this.disposed) return
    if (immediate) {
      this.timers.clear('save')
      this.write(true)
      return
    }
    const wait = this.lastSaveAt + SAVE_THROTTLE - Date.now()
    if (wait <= 0) this.write()
    else if (!this.timers.has('save')) this.timers.set('save', wait, () => this.write())
  }

  reset() {
    this.generation++
    this.pending = null
    this.lastSaved = ''
    this.lastSaveAt = 0
    this.timers.clear('save')
  }

  /** Flush an already scheduled save before invalidating in-flight completions. */
  dispose() {
    if (this.disposed) return
    if (this.timers.has('save')) this.write()
    this.disposed = true
    this.reset()
  }

  private write(immediate = false) {
    if (this.disposed) return
    const value = this.snapshot()
    if (value) void this.persist(value, immediate)
  }

  private async persist(value: StoredPosition, immediate: boolean) {
    const { pet: owner, pluginId } = this.scope()
    if (!owner?.storage?.set) return
    if (this.pending) {
      this.pending.repeat = true
      this.pending.immediate ||= immediate
      return
    }
    const key = JSON.stringify(value)
    if (key === this.lastSaved) return
    const generation = this.generation
    const petKey = owner.key
    const current = () => {
      const scope = this.scope()
      return (
        !this.disposed &&
        generation === this.generation &&
        owner === scope.pet &&
        pluginId === scope.pluginId &&
        petKey === scope.pet?.key
      )
    }
    const write = { repeat: false, immediate: false }
    this.pending = write
    this.lastSaveAt = Date.now()
    try {
      await owner.storage.set(value)
      if (current()) this.lastSaved = key
    } catch {
      if (current()) console.warn('[AgentPets] position not saved')
    } finally {
      if (this.pending === write) {
        this.pending = null
        if (write.repeat && current()) this.request(write.immediate)
      }
    }
  }
}
