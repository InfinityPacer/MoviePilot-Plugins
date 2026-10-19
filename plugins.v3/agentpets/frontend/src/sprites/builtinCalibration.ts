import type { PluginApi } from '@/host'
import { withLoadTimeout } from '@/loading'
import { parseCalibration, type Calibration } from './calibration'
import { BUILTIN_PACKS, type SpritePack } from './schema'

export const YING_PACK: SpritePack = {
  id: 'ying',
  name: '小映',
  description: '小映校准参考帧',
  sheet: '',
  grid: { cols: 1, rows: 1 },
  frames: { idle: 0 },
  actions: {
    idle: { frames: ['idle'], frame_ms: 160, loop: false },
    peek: { frames: ['idle'], frame_ms: 160, loop: false },
  },
  random_actions: [],
  calibration: parseCalibration({ eye_x: 0.5, eye_y: 0.38 }),
}

export function builtinDefaultCalibration(key: string): Calibration {
  return parseCalibration((key === 'ying' ? YING_PACK : BUILTIN_PACKS[key])?.calibration)
}

/** Built-in art stays local; only the instance-scoped calibration is fetched. */
export async function loadBuiltinCalibration(
  api: Pick<PluginApi, 'get'> | null | undefined,
  pluginId: string,
  key: string,
  signal: AbortSignal,
): Promise<Calibration> {
  const fallback = builtinDefaultCalibration(key)
  if (!api?.get || !pluginId) return fallback
  const response = await withLoadTimeout(
    api.get<{ id: string; calibration: Calibration }>(
      `plugin/${pluginId}/packs/calibration?key=${encodeURIComponent(key)}`,
    ),
    signal,
  )
  if (!response?.success || response.data?.id !== key || !response.data.calibration) throw new Error('内置校准读取失败')
  return parseCalibration(response.data.calibration)
}
