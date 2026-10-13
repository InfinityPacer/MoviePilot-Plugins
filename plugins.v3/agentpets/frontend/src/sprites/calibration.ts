/** 单格原图上的归一化坐标。所有动画帧共用这个显示参考框。 */
export interface Calibration {
  left: number
  top: number
  right: number
  bottom: number
  baseline: number
  offset_x: number
  offset_y: number
}

export const DEFAULT_CALIBRATION: Calibration = {
  left: 0,
  top: 0,
  right: 1,
  bottom: 1,
  baseline: 1,
  offset_x: 0,
  offset_y: 0,
}

export function parseCalibration(raw: unknown): Calibration {
  if (raw == null) return { ...DEFAULT_CALIBRATION }
  if (typeof raw !== 'object' || Array.isArray(raw)) throw new Error('显示校准字段无效')
  const value = { ...DEFAULT_CALIBRATION }
  for (const [key, item] of Object.entries(raw)) {
    const low = key.startsWith('offset_') ? -0.25 : 0
    const high = key.startsWith('offset_') ? 0.25 : 1
    if (!Object.hasOwn(value, key) || typeof item !== 'number' || !Number.isFinite(item) || item < low || item > high)
      throw new Error(`显示校准 ${key} 超出范围`)
    value[key as keyof Calibration] = Math.round(item * 10000) / 10000
  }
  if (value.right - value.left < 0.1 - 1e-6 || value.bottom - value.top < 0.1 - 1e-6)
    throw new Error('有效显示区域的宽高至少为原格子的 10%')
  if (value.baseline <= value.top || value.baseline > value.bottom) throw new Error('脚底基线必须在显示区域内')
  return value
}

export function sameCalibration(a?: Calibration, b?: Calibration): boolean {
  return (Object.keys(DEFAULT_CALIBRATION) as Array<keyof Calibration>).every(
    key => (a?.[key] ?? DEFAULT_CALIBRATION[key]) === (b?.[key] ?? DEFAULT_CALIBRATION[key]),
  )
}

export function calibrationLayout(value: Calibration, cellRatio: number) {
  const width = value.right - value.left
  const height = value.bottom - value.top
  return {
    aspectRatio: (cellRatio * width) / height,
    frame: {
      width: `${100 / width}%`,
      height: `${100 / height}%`,
      left: `${((-value.left + value.offset_x) / width) * 100}%`,
      top: `${((-value.top + value.bottom - value.baseline + value.offset_y) / height) * 100}%`,
    },
  }
}
