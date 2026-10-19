/** 单格原图上的归一化坐标。所有动画帧共用这个显示参考框。 */
export interface Calibration {
  left: number
  top: number
  right: number
  bottom: number
  baseline: number
  offset_x: number
  offset_y: number
  eye_x: number | null
  eye_y: number | null
  left_eye_x: number | null
  left_eye_y: number | null
  right_eye_x: number | null
  right_eye_y: number | null
  head_top_x: number | null
  head_top_y: number | null
}

export const LANDMARKS = ['left_eye', 'right_eye', 'head_top'] as const
export type Landmark = (typeof LANDMARKS)[number]
export interface CalibrationPoint {
  x: number
  y: number
}
export interface CalibratedFace extends CalibrationPoint {
  eyes?: [CalibrationPoint, CalibrationPoint]
  headTop?: CalibrationPoint
}
export type CalibrationNumberKey = Exclude<keyof Calibration, `${Landmark | 'eye'}_${'x' | 'y'}`>

export const DEFAULT_CALIBRATION: Calibration = {
  left: 0,
  top: 0,
  right: 1,
  bottom: 1,
  baseline: 1,
  offset_x: 0,
  offset_y: 0,
  eye_x: null,
  eye_y: null,
  left_eye_x: null,
  left_eye_y: null,
  right_eye_x: null,
  right_eye_y: null,
  head_top_x: null,
  head_top_y: null,
}

export function parseCalibration(raw: unknown): Calibration {
  if (raw == null) return { ...DEFAULT_CALIBRATION }
  if (typeof raw !== 'object' || Array.isArray(raw)) throw new Error('显示校准字段无效')
  const value = { ...DEFAULT_CALIBRATION }
  for (const [key, item] of Object.entries(raw)) {
    if (Object.hasOwn(value, key) && value[key as keyof Calibration] === null && item === null) continue
    const low = key.startsWith('offset_') ? -0.25 : 0
    const high = key.startsWith('offset_') ? 0.25 : 1
    if (!Object.hasOwn(value, key) || typeof item !== 'number' || !Number.isFinite(item) || item < low || item > high)
      throw new Error(`显示校准 ${key} 超出范围`)
    value[key as keyof Calibration] = Math.round(item * 10000) / 10000
  }
  if (value.right - value.left < 0.1 - 1e-6 || value.bottom - value.top < 0.1 - 1e-6)
    throw new Error('有效显示区域的宽高至少为原格子的 10%')
  if (value.baseline <= value.top || value.baseline > value.bottom) throw new Error('脚底基线必须在显示区域内')
  for (const key of ['eye', ...LANDMARKS] as const) {
    if ((value[`${key}_x`] === null) !== (value[`${key}_y`] === null)) throw new Error('校准点需要同时设置横纵坐标')
    const point = calibrationPoint(value, key)
    if (point && (point.x < -1e-8 || point.x > 1 + 1e-8 || point.y < -1e-8 || point.y > 1 + 1e-8))
      throw new Error('校准点必须在最终显示区域内')
  }
  if (value.left_eye_x != null && value.right_eye_x != null && value.left_eye_x >= value.right_eye_x)
    throw new Error('画面左眼必须位于画面右眼左侧')
  if (value.head_top_y != null && [value.left_eye_y, value.right_eye_y].some(y => y != null && value.head_top_y! >= y))
    throw new Error('头顶必须位于双眼上方')
  return value
}

/** 眼位与素材使用同一裁切、基线和偏移，缺省不推测皮肤的眼睛位置。 */
export function calibrationPoint(value: Calibration, key: Landmark | 'eye'): CalibrationPoint | null {
  const x = value[`${key}_x`],
    y = value[`${key}_y`]
  if (x == null || y == null) return null
  return {
    x: (x - value.left + value.offset_x) / (value.right - value.left),
    y: (y - value.top + value.bottom - value.baseline + value.offset_y) / (value.bottom - value.top),
  }
}

export function calibrationEye(value: Calibration): CalibratedFace | null {
  const left = calibrationPoint(value, 'left_eye'),
    right = calibrationPoint(value, 'right_eye')
  if (!left || !right) return calibrationPoint(value, 'eye')
  const headTop = calibrationPoint(value, 'head_top')
  return { x: (left.x + right.x) / 2, y: (left.y + right.y) / 2, eyes: [left, right], ...(headTop ? { headTop } : {}) }
}

/** Mirror the displayed artwork and landmarks together, retaining screen-left/right eye order. */
export function mirrorFace(face: CalibratedFace | null): CalibratedFace | null {
  if (!face) return null
  const mirror = (point: CalibrationPoint) => ({ x: 1 - point.x, y: point.y })
  return {
    ...mirror(face),
    ...(face.eyes
      ? { eyes: [mirror(face.eyes[1]), mirror(face.eyes[0])] as [CalibrationPoint, CalibrationPoint] }
      : {}),
    ...(face.headTop ? { headTop: mirror(face.headTop) } : {}),
  }
}

export function suggestedLandmark(value: Calibration, key: Landmark): CalibrationPoint {
  const center = calibrationPoint(value, 'eye') ?? { x: 0.5, y: 0.35 }
  return {
    x: Math.max(0.05, Math.min(0.95, center.x + (key === 'left_eye' ? -0.1 : key === 'right_eye' ? 0.1 : 0))),
    y: Math.max(0.02, Math.min(0.95, center.y - (key === 'head_top' ? 0.2 : 0))),
  }
}

/** 把拖拽坐标反算到原图；限制在实际可见范围内，防止越界或双眼交叉。 */
export function moveCalibrationPoint(value: Calibration, key: Landmark, point: CalibrationPoint): Calibration {
  const clamp = (n: number, low: number, high: number) => {
    if (low > high) throw new Error('当前显示框无法容纳校准点，请先调整显示范围')
    return Math.min(high, Math.max(low, n))
  }
  const minX = Math.max(
    0,
    value.left - value.offset_x,
    key === 'right_eye' && value.left_eye_x != null ? value.left_eye_x + 0.0001 : 0,
  )
  const maxX = Math.min(
    1,
    value.right - value.offset_x,
    key === 'left_eye' && value.right_eye_x != null ? value.right_eye_x - 0.0001 : 1,
  )
  const minY = Math.max(
    0,
    value.top - value.bottom + value.baseline - value.offset_y,
    key !== 'head_top' && value.head_top_y != null ? value.head_top_y + 0.0001 : 0,
  )
  const maxY = Math.min(
    1,
    value.baseline - value.offset_y,
    ...(key === 'head_top'
      ? [value.left_eye_y, value.right_eye_y].filter((y): y is number => y != null).map(y => y - 0.0001)
      : []),
  )
  return parseCalibration({
    ...value,
    [`${key}_x`]: clamp(value.left - value.offset_x + point.x * (value.right - value.left), minX, maxX),
    [`${key}_y`]: clamp(
      value.top - value.bottom + value.baseline - value.offset_y + point.y * (value.bottom - value.top),
      minY,
      maxY,
    ),
  })
}

export function sameCalibration(a?: Calibration, b?: Calibration): boolean {
  return (Object.keys(DEFAULT_CALIBRATION) as Array<keyof Calibration>).every(
    key => (a?.[key] ?? DEFAULT_CALIBRATION[key]) === (b?.[key] ?? DEFAULT_CALIBRATION[key]),
  )
}

export function calibrationForAction(
  value: Calibration,
  baselines: Record<string, number> | undefined,
  action: string,
  referenceBaseline = value.baseline,
): Calibration {
  const baseline = baselines && Object.hasOwn(baselines, action) ? baselines[action] : undefined
  if (baseline === undefined) return value
  // Native pose offsets remain relative to the user's common reference frame.
  const adjusted = Math.max(value.top + 0.0001, Math.min(value.bottom, value.baseline + baseline - referenceBaseline))
  return { ...value, baseline: Math.round(adjusted * 10000) / 10000 }
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
