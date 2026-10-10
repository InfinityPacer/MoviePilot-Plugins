import type { PluginApi } from '@/host'

/** 角色外观设置；边界与后端 `SCALE_RANGE`、`SPEED_RANGE` 一致。 */
export interface YingSettings {
  /** 角色大小倍率。 */
  scale: number
  /** 移动速度倍率。 */
  speed: number
}

export const SCALE_RANGE: [number, number] = [0.6, 1.6]
export const SPEED_RANGE: [number, number] = [0.5, 2]
export const DEFAULT_SETTINGS: YingSettings = { scale: 1, speed: 1 }

/**
 * 设置页向运行中的形象广播的自定义事件名。
 *
 * 设置页拖动滑块时经 `moviepilot:agent` 发出，形象只接受同一插件实例发出的事件，
 * 因而未保存的值也能实时预览，保存与否由设置页自己决定。
 */
export const SETTINGS_EVENT = 'agentpetying.settings'

function bounded(value: unknown, range: [number, number], fallback: number): number {
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.round(Math.min(Math.max(number, range[0]), range[1]) * 100) / 100
}

/** 规整任意来源的设置；缺失或非法字段回落默认值。 */
export function normalizeSettings(value: unknown): YingSettings {
  const source = value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
  return {
    scale: bounded(source.scale, SCALE_RANGE, DEFAULT_SETTINGS.scale),
    speed: bounded(source.speed, SPEED_RANGE, DEFAULT_SETTINGS.speed),
  }
}

/** 读取已保存的外观设置；接口不可用时返回默认值。 */
export async function loadSettings(api: PluginApi | null | undefined, pluginId: string): Promise<YingSettings> {
  if (!api?.get || !pluginId) return { ...DEFAULT_SETTINGS }
  try {
    const response = await api.get<YingSettings>(`plugin/${pluginId}/settings`)
    if (response?.success && response.data) return normalizeSettings(response.data)
  } catch {
    console.warn('[AgentPetYing] settings unavailable')
  }
  return { ...DEFAULT_SETTINGS }
}
