import type { AgentRect } from '@/host'
import { standable, type StageViewport, type SurfaceBox } from '@/stage/geometry'

/**
 * 小映可以站上去的页面容器。
 *
 * 只列宿主常见的卡片、面板和对话框容器；调整可站范围时只改这一处。
 */
export const SURFACE_SELECTOR = '.v-card, .v-sheet, .v-overlay__content, [role="dialog"]'

/** 一次查询最多检查的元素数，避免超长列表页的单次查询过慢。 */
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
  const result: DomSurface[] = []
  const elements = document.querySelectorAll(SURFACE_SELECTOR)
  const count = Math.min(elements.length, MAX_SURFACE_CANDIDATES)
  for (let index = 0; index < count; index += 1) {
    const el = elements[index]
    if (layer && (layer.contains(el) || el.contains(layer))) continue
    const box = measureSurface(el)
    if (!box || !standable(box, viewport, charHeight, panel) || !surfaceVisible(el)) continue
    if (!surfaceUnobstructed(el, box, layer, viewport.width)) continue
    result.push({ ...box, el })
  }
  return result
}

/** 小映不应停留在其上方的可点击控件；调整范围时只改这一处。 */
export const CONTROL_SELECTOR = 'a, button, [role="button"], input, textarea, select, .v-btn'

/**
 * 角色矩形是否挡住了可点击控件。
 *
 * 在取样点调用 `elementsFromPoint`，跳过小映自己的图层，看第一个命中的元素是否落在控件里。
 * 只在落地、站定和窗口尺寸变化时调用，不在动画帧里调用；浏览器不支持时视为不遮挡。
 */
export function coversControl(points: Array<{ x: number; y: number }>, layer: Element | null): boolean {
  if (typeof document.elementsFromPoint !== 'function') return false
  for (const point of points) {
    if (point.x < 0 || point.y < 0 || point.x > window.innerWidth || point.y > window.innerHeight) continue
    const hit = document.elementsFromPoint(point.x, point.y).find(item => !layer?.contains(item))
    if (hit?.closest(CONTROL_SELECTOR)) return true
  }
  return false
}
