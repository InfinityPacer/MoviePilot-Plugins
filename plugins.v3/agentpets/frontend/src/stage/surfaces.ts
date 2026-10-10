import type { AgentRect } from '@/host'
import { floorLine, standable, type StageViewport, type SurfaceBox } from '@/stage/geometry'

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

/**
 * 小映不应停留在其上方的可点击控件；调整范围时只改这一处。
 *
 * 包括链接卡片、列表项（侧栏菜单）和可聚焦元素，`tabindex="-1"` 只能脚本聚焦，不算。
 */
export const CONTROL_SELECTOR =
  'a, button, [role="button"], input, textarea, select, .v-btn, .v-card--link, .v-list-item, [tabindex]:not([tabindex="-1"])'

/**
 * 收集视口内可点击控件的矩形，供一次遮挡判断里的多个候选位置复用。
 *
 * - 排除小映自己的图层及其祖先，以及她正站着的元素和包住它的控件：她脚底在那张卡片上沿，
 *   本来就不算挡住它。
 * - 超过视口一半面积的可聚焦容器视为页面布局，不当作控件，否则她在哪里都算挡住。
 *
 * 只在落地、站定、窗口尺寸变化和站立低频复查时调用，不在动画帧里调用。
 */
export function collectControls(
  layer: Element | null,
  viewport: { width: number; height: number },
  standingOn: Element | null,
): AgentRect[] {
  const viewportArea = viewport.width * viewport.height
  const rects: AgentRect[] = []
  for (const el of Array.from(document.querySelectorAll(CONTROL_SELECTOR))) {
    if (layer && (layer.contains(el) || el.contains(layer))) continue
    if (standingOn && (el === standingOn || el.contains(standingOn))) continue
    const rect = el.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) continue
    if (rect.right <= 0 || rect.bottom <= 0 || rect.left >= viewport.width || rect.top >= viewport.height) continue
    if (rect.width * rect.height > viewportArea / 2) continue
    if (!surfaceVisible(el)) continue
    rects.push({ x: rect.left, y: rect.top, width: rect.width, height: rect.height })
  }
  return rects
}
