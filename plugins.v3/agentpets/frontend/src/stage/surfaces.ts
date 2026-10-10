import type { AgentRect } from '@/host'
import { coversAny, floorLine, standable, type StageViewport, type SurfaceBox } from '@/stage/geometry'

/**
 * 小映可以站上去的页面容器。
 *
 * 只列宿主常见的卡片、面板和对话框容器；调整可站范围时只改这一处。
 */
export const SURFACE_SELECTOR = '.v-card, .v-sheet, .v-overlay__content, [role="dialog"]'

/**
 * 一次查询最多做样式与遮挡判断的候选数。
 *
 * 上限只计视口内、几何上可站的元素：长页面滚到下方时，排在文档前面的大量元素已在视口外，
 * 若先截取再判断会一个可站面都找不到。矩形读取很便宜，样式和命中测试才是主要耗时。
 */
export const MAX_SURFACE_CANDIDATES = 400

/** 带 DOM 元素的可站表面。 */
export interface DomSurface extends SurfaceBox {
  el: Element
}

/** 读取元素当前的上边缘；元素已脱离文档或没有尺寸时返回 null。 */
export function measureSurface(el: Element): SurfaceBox | null {
  if (!el.isConnected) return null
  const rect = el.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return null
  return { left: rect.left, top: rect.top, right: rect.right }
}

/** 不接收指针或不可见的元素不算可站表面。 */
export function surfaceVisible(el: Element): boolean {
  const style = window.getComputedStyle(el)
  return style.pointerEvents !== 'none' && style.visibility !== 'hidden' && style.display !== 'none'
}

/**
 * 上边缘是否露在最上层：在可见部分的中点往下 2px 取命中元素，跳过小映自己的图层，
 * 第一个命中的必须是该元素本身或其后代。被遮罩、弹窗或其他元素压住的卡片因此不算。
 *
 * 浏览器不支持 `elementsFromPoint` 时不做遮挡判断。
 */
export function surfaceUnobstructed(
  el: Element,
  box: SurfaceBox,
  layer: Element | null,
  viewportWidth: number,
): boolean {
  if (typeof document.elementsFromPoint !== 'function') return true
  const left = Math.max(box.left, 0)
  const right = Math.min(box.right, viewportWidth)
  if (right <= left) return false
  const hit = document.elementsFromPoint((left + right) / 2, box.top + 2).find(item => !layer?.contains(item))
  return !!hit && (hit === el || el.contains(hit))
}

/**
 * 查询当前视口里所有可站表面。
 *
 * 只在开始下落或开始走动时调用一次，不在动画帧里调用；排除小映自己的图层及其祖先，
 * 以及上边缘被其他元素盖住的元素（遮挡判断只在这里做，站立后的重新校验不再做）。
 */
export function querySurfaces(
  layer: Element | null,
  viewport: StageViewport,
  charHeight: number,
  panel: AgentRect | null,
): DomSurface[] {
  const floor = floorLine(viewport)
  const candidates: DomSurface[] = []
  for (const el of Array.from(document.querySelectorAll(SURFACE_SELECTOR))) {
    const box = measureSurface(el)
    // 先按矩形筛掉视口外和几何上不可站的元素，它们不计入上限。
    if (!box || box.right <= 0 || box.left >= viewport.width || box.top >= floor) continue
    if (!standable(box, viewport, charHeight, panel)) continue
    if (layer && (layer.contains(el) || el.contains(layer))) continue
    candidates.push({ ...box, el })
    if (candidates.length >= MAX_SURFACE_CANDIDATES) break
  }
  return candidates.filter(
    candidate => surfaceVisible(candidate.el) && surfaceUnobstructed(candidate.el, candidate, layer, viewport.width),
  )
}

/** 用命中测试找附近可站面时的取样行数。 */
export const NEARBY_SURFACE_ROWS = 4

/**
 * 用命中测试在几列竖线上找可站面，耗时只与取样点数有关，与页面大小无关。
 *
 * 只用于避让控件时的兜底换面：在给定的几个 x 上，从上到下取若干行，命中元素的
 * `closest(SURFACE_SELECTOR)` 就是该处露在最上层的容器，再按可站规则过滤。
 * 比 `querySurfaces` 的全页扫描便宜，代价是比列间距还窄的面可能找不到。
 */
export function surfacesNear(
  layer: Element | null,
  viewport: StageViewport,
  charHeight: number,
  panel: AgentRect | null,
  columns: readonly number[],
): DomSurface[] {
  if (typeof document.elementsFromPoint !== 'function') return []
  const top = viewport.safeArea.top + charHeight
  const bottom = floorLine(viewport)
  const seen = new Set<Element>()
  const result: DomSurface[] = []
  for (const x of columns) {
    if (x < 0 || x >= viewport.width) continue
    for (let row = 0; row < NEARBY_SURFACE_ROWS; row += 1) {
      const y = top + ((row + 0.5) * (bottom - top)) / NEARBY_SURFACE_ROWS
      const hit = document.elementsFromPoint(x, y).find(item => !layer?.contains(item))
      const el = hit?.closest(SURFACE_SELECTOR)
      if (!el || seen.has(el)) continue
      seen.add(el)
      if (layer && el.contains(layer)) continue
      const box = measureSurface(el)
      if (!box || !standable(box, viewport, charHeight, panel) || !surfaceVisible(el)) continue
      if (!surfaceUnobstructed(el, box, layer, viewport.width)) continue
      result.push({ ...box, el })
    }
  }
  return result
}

/**
 * 小映不应停留在其上方的可点击控件；调整范围时只改这一处。
 *
 * 包括链接卡片、列表项（侧栏菜单）和可聚焦元素，`tabindex="-1"` 只能脚本聚焦，不算。
 */
export const CONTROL_SELECTOR =
  'a, button, [role="button"], input, textarea, select, .v-btn, .v-card--link, .v-list-item, [tabindex]:not([tabindex="-1"])'

/** 命中测试的取样网格：角色矩形内 3 列 × 4 行共 12 个点。 */
export const SAMPLE_COLS = 3
export const SAMPLE_ROWS = 4

/** 角色矩形内均匀分布的取样点（各格中心）。 */
export function samplePoints(rect: AgentRect, cols = SAMPLE_COLS, rows = SAMPLE_ROWS): Array<{ x: number; y: number }> {
  const points: Array<{ x: number; y: number }> = []
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      points.push({ x: rect.x + ((col + 0.5) * rect.width) / cols, y: rect.y + ((row + 0.5) * rect.height) / rows })
    }
  }
  return points
}

/**
 * 角色放在 `rect` 时，她身后实际露在最上层的可点击控件矩形。
 *
 * 在 12 个取样点调用 `elementsFromPoint`，跳过小映自己的图层，取第一个命中元素，再用
 * `closest(CONTROL_SELECTOR)` 找到所属控件。只看命中结果，所以遮罩底下、被溢出裁掉的控件
 * 不会算进来，耗时也只与取样点数有关，与页面大小无关。
 *
 * - 她正站着的元素以及包住它的控件不算：她脚底在那张卡片上沿，本来就不算挡住它。
 * - 超过视口一半面积的可聚焦容器视为页面布局，不当作控件，否则她在哪里都算挡住。
 *
 * 浏览器不支持 `elementsFromPoint` 时返回空列表。
 */
export function controlsUnder(
  rect: AgentRect,
  layer: Element | null,
  viewport: { width: number; height: number },
  standingOn: Element | null,
): AgentRect[] {
  return Array.from(eachControlUnder(rect, layer, viewport, standingOn))
}

/**
 * 角色放在 `rect` 时是否挡住控件：与某个命中控件的交集超过角色面积的 10%。
 *
 * 逐点取样，发现挡住就立即返回。寻找空位时多数候选位置在前几个点就能判定，
 * 单次判断的命中测试次数因此远低于“取样点数 × 候选数”的上界。
 */
export function coversControlAt(
  rect: AgentRect,
  layer: Element | null,
  viewport: { width: number; height: number },
  standingOn: Element | null,
  bodyArea = rect.width * rect.height,
): boolean {
  for (const control of eachControlUnder(rect, layer, viewport, standingOn)) {
    if (coversAny(rect, [control], bodyArea)) return true
  }
  return false
}

function* eachControlUnder(
  rect: AgentRect,
  layer: Element | null,
  viewport: { width: number; height: number },
  standingOn: Element | null,
): Generator<AgentRect> {
  if (typeof document.elementsFromPoint !== 'function') return
  const viewportArea = viewport.width * viewport.height
  const seen = new Set<Element>()
  for (const point of samplePoints(rect)) {
    if (point.x < 0 || point.y < 0 || point.x >= viewport.width || point.y >= viewport.height) continue
    const hit = document.elementsFromPoint(point.x, point.y).find(item => !layer?.contains(item))
    const control = hit?.closest(CONTROL_SELECTOR)
    if (!control || seen.has(control)) continue
    seen.add(control)
    if (layer && control.contains(layer)) continue
    if (standingOn && (control === standingOn || control.contains(standingOn))) continue
    const box = control.getBoundingClientRect()
    if (box.width * box.height > viewportArea / 2) continue
    yield { x: box.left, y: box.top, width: box.width, height: box.height }
  }
}
