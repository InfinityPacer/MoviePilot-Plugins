import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { resolveAction, type SpritePack } from '@/sprites/schema'
import type { ActionMappings } from '@/sprites/mappings'

export const GREETING_MARKER = Symbol.for('moviepilot.agentpets.startup-greeting')
export const GREETING_SETTLE_MS = 300
export const GREETING_WAIT_MS = 5000
export const SINGLE_GREETING_MS = 600
export const GREETING_PAUSE_MS = 220

export interface GreetingPlayback {
  duration: number
  pause: number
  frameDriven?: boolean
}

/** A document marker also survives component remounts and federation reimports. */
export function claimPageGreeting(page: Document, owner: symbol | boolean = true): boolean {
  if (Reflect.get(page, GREETING_MARKER)) return false
  Reflect.defineProperty(page, GREETING_MARKER, { value: owner, configurable: true })
  return true
}

export function greetingPlayback(pack: SpritePack, mappings?: ActionMappings, stage = true): GreetingPlayback | null {
  const resolved = resolveAction(pack, 'wave', undefined, false, {
    mappings,
    mappingKey: stage ? 'stage.wave' : undefined,
  })
  if (resolved.key === 'idle') return null
  const action = resolved.action
  if (!action.frames.length || action.frames.some(frame => !(frame in pack.frames))) return null
  if (action.frames.length === 1) return { duration: SINGLE_GREETING_MS, pause: GREETING_PAUSE_MS }
  const duration = action.frames.reduce(
    (total, _, index) => total + (action.frame_durations?.[index] ?? action.frame_ms),
    0,
  )
  return Number.isFinite(duration) && duration > 0 ? { duration, pause: 0, frameDriven: true } : null
}

interface GreetingOptions {
  allowed: () => boolean
  ready: () => boolean
  stable: () => unknown
  playback: () => GreetingPlayback | null
  finished?: () => void
}

/** Finite startup sequence; cancellation never restores a pending or partial greeting. */
export function useStartupGreeting(options: GreetingOptions) {
  const pending = ref(false)
  const phase = ref<'wave' | 'pause' | null>(null)
  const round = ref(0)
  const active = computed(() => pending.value || phase.value !== null)
  let handled = false
  let stopped = false
  let timer = 0
  let deadline = 0
  let playback: GreetingPlayback | null = null
  const owner = Symbol()

  function consumeOpportunity() {
    if (typeof document === 'undefined') return
    if (Reflect.get(document, GREETING_MARKER) === owner)
      Reflect.defineProperty(document, GREETING_MARKER, { value: true, configurable: true })
  }

  function clearTimers() {
    window.clearTimeout(timer)
    window.clearTimeout(deadline)
    timer = deadline = 0
  }

  function finish(notify = true) {
    consumeOpportunity()
    const wasActive = active.value
    handled = true
    clearTimers()
    pending.value = false
    phase.value = null
    if (wasActive && notify) options.finished?.()
  }

  async function playRound() {
    if (stopped || !options.allowed() || !options.ready() || !playback) return finish()
    consumeOpportunity()
    pending.value = false
    phase.value = 'wave'
    const current = ++round.value
    await nextTick()
    if (stopped || phase.value !== 'wave' || round.value !== current) return
    // Multi-frame artwork reports completion instead of estimating it from wall-clock time.
    if (!playback.frameDriven) timer = window.setTimeout(completeRound, playback.duration)
  }

  function completeRound() {
    if (phase.value !== 'wave' || !playback) return
    if (round.value === 2) return finish()
    if (playback.pause) {
      phase.value = 'pause'
      timer = window.setTimeout(() => void playRound(), playback!.pause)
    } else void playRound()
  }

  function frameComplete(completedRound = round.value) {
    if (!playback?.frameDriven || completedRound !== round.value) return
    if (options.ready() && options.allowed()) completeRound()
    else if (phase.value) finish()
  }

  function prepare() {
    if (!pending.value) return
    window.clearTimeout(timer)
    if (!options.allowed()) return finish()
    if (!options.ready()) return
    playback = options.playback()
    if (!playback) return finish()
    timer = window.setTimeout(() => {
      window.clearTimeout(deadline)
      void playRound()
    }, GREETING_SETTLE_MS)
  }

  function arm() {
    if (typeof document === 'undefined' || handled || !claimPageGreeting(document, owner)) return
    handled = true
    if (!options.allowed()) return finish()
    pending.value = true
    deadline = window.setTimeout(() => finish(), GREETING_WAIT_MS)
    prepare()
  }

  watch([options.ready, options.stable, options.playback], prepare, { flush: 'post' })
  watch(
    options.allowed,
    allowed => {
      if (!allowed && active.value) finish()
    },
    { flush: 'sync' },
  )
  watch(
    options.ready,
    ready => {
      if (!ready && phase.value) finish()
    },
    { flush: 'sync' },
  )
  onBeforeUnmount(() => {
    stopped = true
    if (pending.value && !round.value && Reflect.get(document, GREETING_MARKER) === owner)
      Reflect.deleteProperty(document, GREETING_MARKER)
    finish(false)
  })

  return { pending, phase, round, active, arm, frameComplete, cancel: finish }
}
