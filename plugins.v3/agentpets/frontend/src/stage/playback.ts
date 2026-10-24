import { stageAction, type ActionMappings } from '@/sprites/mappings'
import { resolveAction, type PackAction, type SpritePack } from '@/sprites/schema'
import type { Pose } from './poses'

export const NOMINAL_WALK_HEIGHTS_PER_SECOND = 70 / 120
export const MAX_ACTION_CYCLE_MS = 6000

export function actionDuration(action: PackAction): number {
  return action.frames.reduce((total, _, index) => total + (action.frame_durations?.[index] ?? action.frame_ms), 0)
}

/** Preserve each sequence's relative cadence while actual travel drives the clock. */
export function travelFrame(action: PackAction, traveledHeights: number): number {
  const duration = actionDuration(action)
  if (!Number.isFinite(traveledHeights) || traveledHeights < 0 || !Number.isFinite(duration) || duration <= 0) return 0
  let elapsed = ((traveledHeights / NOMINAL_WALK_HEIGHTS_PER_SECOND) * 1000) % duration
  for (let index = 0; index < action.frames.length; index += 1) {
    const frameMs = action.frame_durations?.[index] ?? action.frame_ms
    if (elapsed < frameMs) return index
    elapsed -= frameMs
  }
  return 0
}

export function phaseFrame(action: PackAction, phase: number): number {
  if (!Number.isFinite(phase)) return 0
  return Math.min(action.frames.length - 1, Math.floor(Math.max(0, Math.min(1, phase)) * action.frames.length))
}

/** Prefer existing physical-stage artwork, without replacing an explicit user mapping. */
export function resolveStageAction(
  pack: SpritePack,
  pose: Pose,
  facingLeft = false,
  peeking = false,
  mappings?: ActionMappings,
) {
  const stage = stageAction(pose, facingLeft, peeking)
  const configured = mappings ?? pack.action_mappings ?? {}
  const physical = pose === 'sit' ? 'land' : pose === 'jump' || pose === 'fall' ? pose : undefined
  const action = !peeking && !configured[stage.key] && physical && pack.actions[physical] ? physical : stage.action
  return { ...resolveAction(pack, action, undefined, false, { mappings, mappingKey: stage.key }), requested: action }
}

export function stageCycleDuration(pack: SpritePack, pose: Pose, mappings?: ActionMappings): number | undefined {
  const resolved = resolveStageAction(pack, pose, false, false, mappings)
  if (resolved.key === 'idle' || resolved.action.frames.length < 2) return undefined
  const duration = actionDuration(resolved.action)
  return Number.isFinite(duration) && duration > 0 && duration <= MAX_ACTION_CYCLE_MS ? duration : undefined
}

export function airborneFramePhase(action: string, pose: Pose, progress: number | undefined): number | undefined {
  if ((pose !== 'jump' && pose !== 'fall') || progress === undefined || !Number.isFinite(progress)) return undefined
  if (action === 'jumping') return (pose === 'jump' ? 0 : 0.5) + Math.max(0, Math.min(1, progress)) * 0.5
  return action === pose ? progress : undefined
}
