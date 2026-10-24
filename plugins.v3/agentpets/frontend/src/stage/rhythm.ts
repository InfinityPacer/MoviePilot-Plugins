import { stageAction, type ActionMappings } from '@/sprites/mappings'
import { BUILTIN_PACKS, resolveAction, type PackAction, type SpritePack } from '@/sprites/schema'
import { actionDuration, MAX_ACTION_CYCLE_MS } from './playback'
import type { Pose } from './poses'

export interface RhythmAction {
  key: string
  pose: Pose
  weight: number
  cooldown: number
  duration: number
  cycle: number | null
}

export interface CharacterRhythm {
  id: string
  interval: readonly [number, number]
  radiusScale: number
  hopChance: number
  edgeChance: number
  walkWeight: number
  actions: readonly RhythmAction[]
}

interface ActionChoice {
  key: string
  pose: Pose
  weight: number
  cooldown: number
  hold?: number
}

type Profile = Omit<CharacterRhythm, 'id' | 'actions'> & { actions: readonly ActionChoice[] }

const PROFILES: Readonly<Record<string, Profile>> = {
  'builtin-nailong': {
    interval: [6500, 11_500],
    radiusScale: 1,
    hopChance: 0.28,
    edgeChance: 0.15,
    walkWeight: 8,
    actions: [{ key: 'cheer', pose: 'victory', weight: 3, cooldown: 36_000 }],
  },
  'builtin-chibiterasu': {
    interval: [7000, 12_000],
    radiusScale: 0.7,
    hopChance: 0.18,
    edgeChance: 0.1,
    walkWeight: 8,
    actions: [
      { key: 'relaxed-sit', pose: 'sit', weight: 2, cooldown: 28_000, hold: 2200 },
      { key: 'lie', pose: 'doze', weight: 1, cooldown: 40_000, hold: 2800 },
    ],
  },
  'builtin-kurisu': {
    interval: [9000, 15_000],
    radiusScale: 0.85,
    hopChance: 0.1,
    edgeChance: 0.1,
    walkWeight: 6,
    actions: [
      { key: 'look-up', pose: 'think', weight: 3, cooldown: 30_000 },
      { key: 'relaxed-sit', pose: 'sit', weight: 2, cooldown: 28_000, hold: 2400 },
    ],
  },
  ['builtin-kurisu' + '-z256']: {
    interval: [8500, 14_500],
    radiusScale: 0.7,
    hopChance: 0.1,
    edgeChance: 0.1,
    walkWeight: 8,
    actions: [
      { key: 'wave', pose: 'wave', weight: 2, cooldown: 36_000 },
      { key: 'scan', pose: 'think', weight: 2, cooldown: 28_000 },
    ],
  },
}

function cells(pack: SpritePack, action: PackAction): number[] {
  return action.frames
    .map(frame => pack.frames[frame])
    .filter((cell, index, all) => index === 0 || cell !== all[index - 1])
}

/** Curate real existing artwork; explicit user mappings still win over these defaults. */
export function builtinRhythm(pack: SpritePack, mappings?: ActionMappings): CharacterRhythm | null {
  const profile = PROFILES[pack.id]
  if (!profile) return null
  // Bundled stage mappings describe work/landing, not the curated idle repertoire.
  const defaults = BUILTIN_PACKS[pack.id]?.action_mappings ?? {}
  const configured =
    mappings ??
    Object.fromEntries(Object.entries(pack.action_mappings ?? {}).filter(([key, value]) => defaults[key] !== value))
  const idle = pack.actions.idle ? cells(pack, pack.actions.idle) : [pack.frames.idle]
  const seen = new Set([idle.join(',')])
  const actions: RhythmAction[] = []
  for (const choice of profile.actions) {
    const resolved = resolveAction(pack, choice.key, undefined, false, {
      mappings: configured,
      mappingKey: stageAction(choice.pose, false).key,
    })
    const sequence = cells(pack, resolved.action)
    const signature = sequence.join(',')
    if (
      resolved.key === 'idle' ||
      seen.has(signature) ||
      !sequence.length ||
      sequence.some(cell => !Number.isInteger(cell) || cell < 0 || cell >= pack.grid.cols * pack.grid.rows) ||
      (sequence.length === 1 && idle.includes(sequence[0]))
    )
      continue
    const cycle = sequence.length > 1 ? actionDuration(resolved.action) : null
    const duration = cycle ?? choice.hold ?? 2200
    if (!Number.isFinite(duration) || duration <= 0 || duration > MAX_ACTION_CYCLE_MS) continue
    seen.add(signature)
    actions.push({ ...choice, key: resolved.key, cycle, duration })
  }
  return { ...profile, id: pack.id, actions }
}

/** Cooldowns and diversity are session-only; an actual move separates decorative actions. */
export class RhythmPolicy {
  private played = new Map<string, number>()
  private last: string | null = null
  private needsWalk = false

  pick(profile: CharacterRhythm, now: number, random: () => number): RhythmAction | null {
    if (this.needsWalk) return null
    let eligible = profile.actions.filter(action => {
      const at = this.played.get(action.key)
      return at === undefined || now - at >= action.cooldown
    })
    if (eligible.length > 1) eligible = eligible.filter(action => action.key !== this.last)
    let sample = random() * (profile.walkWeight + eligible.reduce((sum, action) => sum + action.weight, 0))
    if (sample < profile.walkWeight) return null
    sample -= profile.walkWeight
    for (const action of eligible) {
      if (sample < action.weight) {
        this.played.set(action.key, now)
        this.last = action.key
        this.needsWalk = true
        return action
      }
      sample -= action.weight
    }
    return null
  }

  walked() {
    this.needsWalk = false
  }

  reset() {
    this.played.clear()
    this.last = null
    this.needsWalk = false
  }
}
