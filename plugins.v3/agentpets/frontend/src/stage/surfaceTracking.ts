import type { PausableTimers } from './timers'

const SURFACE_CHECK_INTERVAL = 500

/** Owns observation resources; support geometry and standing decisions remain in the stage. */
export class SurfaceTracking {
  private observer: MutationObserver | null = null
  private frame = 0
  private interval = 0
  private generation = 0
  private disposed = false

  constructor(
    private timers: Pick<PausableTimers, 'has' | 'set' | 'clear'>,
    private layer: () => Element | null,
    private check: () => void,
    private poll: () => void,
  ) {}

  get observing() {
    return this.observer !== null
  }

  observe(root: Node) {
    if (this.disposed) return
    this.pause()
    const generation = this.generation
    window.addEventListener('scroll', this.onScroll, { capture: true, passive: true })
    if (typeof MutationObserver === 'undefined') return
    this.observer = new MutationObserver(records => {
      if (this.disposed || generation !== this.generation) return
      // The stage's own transforms cannot move its supporting element.
      if (records.every(record => this.layer()?.contains(record.target))) return
      if (!this.timers.has('surface'))
        this.timers.set('surface', SURFACE_CHECK_INTERVAL, () => {
          if (!this.disposed && generation === this.generation) this.check()
        })
    })
    this.observer.observe(root, { subtree: true, childList: true, attributes: true })
  }

  /** Keep the original 500ms cadence even when animation is disabled. */
  syncPolling(wanted: boolean) {
    if (wanted && !this.disposed && !this.interval) {
      const id = window.setInterval(() => {
        if (!this.disposed && this.interval === id) this.poll()
      }, SURFACE_CHECK_INTERVAL)
      this.interval = id
    }
    if ((!wanted || this.disposed) && this.interval) {
      window.clearInterval(this.interval)
      this.interval = 0
    }
  }

  /** Pausing observation does not decide whether the stage should keep polling. */
  pause() {
    this.generation++
    window.removeEventListener('scroll', this.onScroll, { capture: true })
    this.observer?.disconnect()
    this.observer = null
    this.timers.clear('surface')
    if (this.frame) window.cancelAnimationFrame(this.frame)
    this.frame = 0
  }

  dispose() {
    this.disposed = true
    this.pause()
    this.syncPolling(false)
  }

  private onScroll = () => {
    if (this.disposed || this.frame) return
    const generation = this.generation
    this.frame = window.requestAnimationFrame(() => {
      if (this.disposed || generation !== this.generation) return
      this.frame = 0
      this.check()
    })
  }
}
