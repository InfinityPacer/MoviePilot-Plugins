import type { AgentHostState, AgentRect } from '@/host'

/** 角色活动所需的视口信息。 */
export interface StageViewport {
  width: number
  height: number
  keyboardInset: number
  safeArea: { top: number; right: number; bottom: number; left: number }
}

/** 从宿主状态读取视口；宿主缺失时退回浏览器窗口尺寸。 */
export function readViewport(state: AgentHostState | null): StageViewport {
  if (state?.viewport) return state.viewport
  return {
    width: window.innerWidth,
    height: window.innerHeight,
    keyboardInset: 0,
    safeArea: { top: 0, right: 0, bottom: 0, left: 0 },
  }
}

/** 角色站在地面时的顶边 y：视口底部减去安全区和软键盘高度。 */
export function groundTop(viewport: StageViewport, charHeight: number): number {
  const floor = viewport.height - viewport.safeArea.bottom - viewport.keyboardInset
  return Math.max(viewport.safeArea.top, floor - charHeight)
}

/** 角色左边 x 的可活动范围。 */
export function xBounds(viewport: StageViewport, charWidth: number): [number, number] {
  const min = viewport.safeArea.left
  const max = Math.max(min, viewport.width - viewport.safeArea.right - charWidth)
  return [min, max]
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

/** 水平位置换算为可活动范围内的比例，用于跨视口尺寸记住落脚点。 */
export function xToRatio(x: number, bounds: [number, number]): number {
  const [min, max] = bounds
  if (max <= min) return 0
  return clamp((x - min) / (max - min), 0, 1)
}

export function ratioToX(ratio: number, bounds: [number, number]): number {
  const [min, max] = bounds
  return min + clamp(ratio, 0, 1) * (max - min)
}

/**
 * 面板挡住角色所在水平带时，角色左边 x 不能落入的区间。
 *
 * `standY` 是角色站立时的顶边 y；面板与 [standY, standY + charHeight] 没有纵向重叠时返回 null。
 */
export function blockedSpan(
  panel: AgentRect | null,
  standY: number,
  charWidth: number,
  charHeight = 0,
): [number, number] | null {
  if (!panel || panel.width <= 0 || panel.height <= 0) return null
  if (panel.y + panel.height <= standY) return null
  if (charHeight > 0 && panel.y >= standY + charHeight) return null
  return [panel.x - charWidth, panel.x + panel.width]
}

export function isBlocked(x: number, span: [number, number] | null): boolean {
  return !!span && x > span[0] && x < span[1]
}

/**
 * 在可活动范围内挑一个不被面板挡住、且离当前位置足够远的散步目标。
 *
 * 角色不会穿过面板：目标只在当前所在的一侧挑选。没有可走的位置时返回 null。
 */
export function pickWalkTarget(
  random: () => number,
  current: number,
  bounds: [number, number],
  span: [number, number] | null,
  minDistance = 40,
): number | null {
  let [min, max] = bounds
  if (span) {
    if (current <= span[0]) max = Math.min(max, span[0])
    else if (current >= span[1]) min = Math.max(min, span[1])
  }
  if (max - min < minDistance) return null
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const target = min + random() * (max - min)
    if (Math.abs(target - current) >= minDistance && !isBlocked(target, span)) return target
  }
  return null
}

/** 被面板挡住时把角色推到面板外较近的一侧。 */
export function escapeSpan(x: number, span: [number, number] | null, bounds: [number, number]): number {
  if (!isBlocked(x, span) || !span) return x
  const left = span[0]
  const right = span[1]
  const preferLeft = x - left < right - x
  if (preferLeft && left >= bounds[0]) return left
  if (right <= bounds[1]) return right
  return left >= bounds[0] ? left : x
}

/** 两个矩形是否在像素级上相同，用于避免重复上报气泡锚点。 */
export function sameRect(a: AgentRect | null, b: AgentRect | null): boolean {
  if (!a || !b) return a === b
  return (
    Math.round(a.x) === Math.round(b.x) &&
    Math.round(a.y) === Math.round(b.y) &&
    Math.round(a.width) === Math.round(b.width) &&
    Math.round(a.height) === Math.round(b.height)
  )
}

/** 视口内可站表面的上边缘与左右边界。 */
export interface SurfaceBox {
  left: number
  top: number
  right: number
}

/** 可站表面的最小宽度（CSS 像素）。 */
export const MIN_SURFACE_WIDTH = 120

/** 视口地面线（角色脚底所在的 y）：视口底部减去安全区和软键盘高度。 */
export function floorLine(viewport: StageViewport): number {
  return viewport.height - viewport.safeArea.bottom - viewport.keyboardInset
}

/**
 * 表面能否让角色站上去。
 *
 * 宽度至少 120px；上边缘在视口地面线以上，且上方留得下角色身高；
 * 整条上边缘落在 Agent 面板里的表面视为面板自身的内容，不算。
 */
export function standable(
  box: SurfaceBox,
  viewport: StageViewport,
  charHeight: number,
  panel: AgentRect | null,
): boolean {
  if (box.right - box.left < MIN_SURFACE_WIDTH) return false
  if (box.top - charHeight < viewport.safeArea.top) return false
  if (box.top >= floorLine(viewport)) return false
  if (
    panel &&
    box.left >= panel.x &&
    box.right <= panel.x + panel.width &&
    box.top >= panel.y &&
    box.top <= panel.y + panel.height
  ) {
    return false
  }
  return true
}

/** 正下方最近的表面：中心 x 落在表面上，上边缘不高于脚底。 */
export function findLanding<T extends SurfaceBox>(boxes: readonly T[], centerX: number, feetY: number): T | null {
  let best: T | null = null
  for (const box of boxes) {
    if (centerX < box.left || centerX > box.right || box.top < feetY - 2) continue
    if (!best || box.top < best.top) best = box
  }
  return best
}

/** 活动范围：surfaces 站在页面元素上，floor 只在底边，free 没有重力、自由停放。 */
export type RoamMode = 'surfaces' | 'floor' | 'free'

/** 落点：角色顶边 y 与所站的表面（站在底边或自由停放时为 null）。 */
export interface Landing<T extends SurfaceBox = SurfaceBox> {
  y: number
  surface: T | null
}

/**
 * 按活动范围计算松手或开始下落时的落点。
 *
 * floor 总是底边；free 原地停下（只收进视口）；surfaces 落到正下方最近的可站表面，
 * 没有可站表面时落到底边。`boxes` 由调用方在开始下落时查询一次，已按 `standable` 过滤。
 */
export function computeLanding<T extends SurfaceBox>(
  mode: RoamMode,
  boxes: readonly T[],
  position: { x: number; y: number },
  viewport: StageViewport,
  size: { width: number; height: number },
): Landing<T> {
  const ground = groundTop(viewport, size.height)
  if (mode === 'free') return { y: clamp(position.y, viewport.safeArea.top, ground), surface: null }
  if (mode === 'surfaces') {
    const surface = findLanding(boxes, position.x + size.width / 2, position.y + size.height)
    if (surface) return { y: surface.top - size.height, surface }
  }
  return { y: ground, surface: null }
}

/** 站在表面上时左边 x 的范围：中心不离开表面，也不出视口。 */
export function surfaceXBounds(box: SurfaceBox, viewport: StageViewport, charWidth: number): [number, number] {
  const [minX, maxX] = xBounds(viewport, charWidth)
  const min = Math.max(minX, box.left - charWidth / 2)
  const max = Math.min(maxX, box.right - charWidth / 2)
  return [min, Math.max(min, max)]
}

/** 脚下表面重新校验的结论：跟着表面移动，或者开始下落。 */
export type SupportResult = { kind: 'fall' } | { kind: 'follow'; dx: number; y: number }

/**
 * 重新校验脚下的表面。
 *
 * 表面消失（`next` 为 null）、不再可站、或移动缩小后角色中心不在其上时下落；
 * 否则跟随表面的水平位移和上边缘。
 */
export function checkSupport(
  previous: SurfaceBox,
  next: SurfaceBox | null,
  centerX: number,
  viewport: StageViewport,
  charHeight: number,
  panel: AgentRect | null,
): SupportResult {
  if (!next || !standable(next, viewport, charHeight, panel)) return { kind: 'fall' }
  const dx = next.left - previous.left
  const center = centerX + dx
  if (center < next.left || center > next.right) return { kind: 'fall' }
  return { kind: 'follow', dx, y: next.top - charHeight }
}

/** 自由停放时左边 x、顶边 y 的范围。 */
export function freeBounds(
  viewport: StageViewport,
  charWidth: number,
  charHeight: number,
): { x: [number, number]; y: [number, number] } {
  return { x: xBounds(viewport, charWidth), y: [viewport.safeArea.top, groundTop(viewport, charHeight)] }
}

/** 自由停放时在视口内挑一个离当前位置足够远的游走目标。 */
export function pickFreeTarget(
  random: () => number,
  current: { x: number; y: number },
  bounds: { x: [number, number]; y: [number, number] },
  minDistance = 60,
): { x: number; y: number } | null {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const target = {
      x: bounds.x[0] + random() * (bounds.x[1] - bounds.x[0]),
      y: bounds.y[0] + random() * (bounds.y[1] - bounds.y[0]),
    }
    if (Math.hypot(target.x - current.x, target.y - current.y) >= minDistance) return target
  }
  return null
}
