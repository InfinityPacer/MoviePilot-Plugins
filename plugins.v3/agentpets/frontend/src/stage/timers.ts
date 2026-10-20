/** Keep the remaining delay when the editor temporarily hides the stage. */
export class PausableTimers {
  private paused = false
  private jobs = new Map<string, { id?: number; remaining: number; started: number; callback: () => void }>()

  has(name: string) {
    return this.jobs.has(name)
  }

  clear(name: string) {
    const job = this.jobs.get(name)
    if (job?.id !== undefined) window.clearTimeout(job.id)
    this.jobs.delete(name)
  }

  set(name: string, delay: number, callback: () => void) {
    this.clear(name)
    const job = { remaining: delay, started: 0, callback }
    this.jobs.set(name, job)
    if (!this.paused) this.start(name)
  }

  private start(name: string) {
    const job = this.jobs.get(name)!
    job.started = performance.now()
    job.id = window.setTimeout(() => {
      this.jobs.delete(name)
      job.callback()
    }, job.remaining)
  }

  pause() {
    if (this.paused) return
    this.paused = true
    for (const job of this.jobs.values()) {
      if (job.id !== undefined) window.clearTimeout(job.id)
      job.remaining = Math.max(0, job.remaining - (performance.now() - job.started))
      job.id = undefined
    }
  }

  resume() {
    if (!this.paused) return
    this.paused = false
    for (const name of this.jobs.keys()) this.start(name)
  }

  dispose() {
    for (const name of this.jobs.keys()) this.clear(name)
  }
}
