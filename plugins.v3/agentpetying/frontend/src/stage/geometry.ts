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
 * 面板压住地面带时，角色左边 x 不能落入的区间。
 *
 * 面板底边高于角色头顶时不影响走路，返回 null。
 */
export function blockedSpan(panel: AgentRect | null, ground: number, charWidth: number): [number, number] | null {
  if (!panel || panel.width <= 0 || panel.height <= 0) return null
  if (panel.y + panel.height <= ground) return null
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
