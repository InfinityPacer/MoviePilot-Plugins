import type { PluginApi } from '@/host'
import type { RoamMode } from '@/stage/geometry'
import { DEFAULT_PEEK_ANGLES, normalizePeekAngles, PEEK_EDGES, type PeekAngles } from './peek'
import { parseDialogue, type DialogueSettings } from './dialogue'

/** 角色外观设置；边界与后端 `SCALE_RANGE`、`SPEED_RANGE` 一致。 */
export interface YingSettings {
  /** 角色大小倍率。 */
  movement?: 'auto' | 'fixed'
  scale: number
  /** 移动速度倍率。 */
  speed: number
  /** 活动范围：surfaces 站在页面元素上，floor 只在底边，free 自由停放。 */
  roam: RoamMode
  /** 当前 Pet 的偷看角度；底边默认 0 度，左右侧边默认 35 度。 */
  peek_angles?: PeekAngles
  /** Optional per-Pet role lines; omitted values do not migrate legacy settings. */
  dialogue?: DialogueSettings
}

export type PetAppearance = Pick<YingSettings, 'scale' | 'speed' | 'peek_angles' | 'dialogue'>
export type SharedActivity = Required<Pick<YingSettings, 'roam' | 'movement'>>

export function appearanceOf(value: PetAppearance): PetAppearance {
  const angles = normalizePeekAngles(value.peek_angles)
  const dialogue = parseDialogue(value.dialogue)
  return {
    scale: value.scale,
    speed: value.speed,
    ...(PEEK_EDGES.some(edge => angles[edge] !== DEFAULT_PEEK_ANGLES[edge]) ? { peek_angles: angles } : {}),
    ...(dialogue ? { dialogue } : {}),
  }
}

export function sharedOf(value: YingSettings): SharedActivity {
  return { roam: value.roam, movement: value.movement ?? 'auto' }
}

export function sameAppearance(a: PetAppearance, b: PetAppearance): boolean {
  const left = normalizePeekAngles(a.peek_angles)
  const right = normalizePeekAngles(b.peek_angles)
  return (
    a.scale === b.scale &&
    a.speed === b.speed &&
    PEEK_EDGES.every(edge => left[edge] === right[edge]) &&
    JSON.stringify(parseDialogue(a.dialogue)) === JSON.stringify(parseDialogue(b.dialogue))
  )
}

export function sameShared(a: SharedActivity, b: SharedActivity): boolean {
  return a.roam === b.roam && a.movement === b.movement
}

export const SCALE_RANGE: [number, number] = [0.6, 1.6]
export const SPEED_RANGE: [number, number] = [0.5, 2]
export const ROAM_MODES: readonly RoamMode[] = ['surfaces', 'floor', 'free']
export const DEFAULT_SETTINGS: YingSettings = { scale: 1, speed: 1, roam: 'surfaces', movement: 'auto' }

/**
 * 设置页向运行中的形象广播的自定义事件名。
 *
 * 保存并回读成功后经 `moviepilot:agent` 发出，形象只接受同一插件实例和 Pet 的事件。
 * 未保存草稿通过局部预览的 settingsOverride 生效，不提前修改正式舞台。
 */
export const SETTINGS_EVENT = 'agentpets.settings'

function bounded(value: unknown, range: [number, number], fallback: number): number {
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.round(Math.min(Math.max(number, range[0]), range[1]) * 100) / 100
}

/** 规整任意来源的设置；缺失或非法字段回落默认值。 */
export function normalizeSettings(value: unknown): YingSettings {
  const source = value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
  return {
    movement: source.movement === 'fixed' ? 'fixed' : 'auto',
    ...appearanceOf({
      scale: bounded(source.scale, SCALE_RANGE, DEFAULT_SETTINGS.scale),
      speed: bounded(source.speed, SPEED_RANGE, DEFAULT_SETTINGS.speed),
      peek_angles: normalizePeekAngles(source.peek_angles),
      dialogue: parseDialogue(source.dialogue),
    }),
    roam: ROAM_MODES.includes(source.roam as RoamMode) ? (source.roam as RoamMode) : DEFAULT_SETTINGS.roam,
  }
}

/** 读取已保存的外观设置；接口不可用时返回默认值。 */
export async function loadSettings(
  api: Pick<PluginApi, 'get'> | null | undefined,
  pluginId: string,
  key = 'ying',
  confirmed?: () => void,
): Promise<YingSettings> {
  if (!api?.get || !pluginId) return { ...DEFAULT_SETTINGS }
  try {
    const response = await api.get<YingSettings>(`plugin/${pluginId}/settings?key=${encodeURIComponent(key)}`)
    if (response?.success && response.data && typeof response.data === 'object' && !Array.isArray(response.data)) {
      const value = normalizeSettings(response.data)
      confirmed?.()
      return value
    }
  } catch {
    console.warn('[AgentPets] settings unavailable')
  }
  return { ...DEFAULT_SETTINGS }
}
