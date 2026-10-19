import type { AgentRect } from '@/host'
import { clamp, floorLine, freeBounds, type StageViewport } from './geometry'

export const PEEK_EDGES = ['bottom', 'left', 'right'] as const
export type PeekEdge = (typeof PEEK_EDGES)[number]
export type PeekAngles = Record<PeekEdge, number>
export interface PeekEye {
  x: number
  y: number
  eyes?: [{ x: number; y: number }, { x: number; y: number }]
  headTop?: { x: number; y: number }
}

export const PEEK_TOUCH_SIZE = 48
export const PEEK_TUCK = 1.06
export const PEEK_TILT = 35
export const DEFAULT_PEEK_ANGLES: Readonly<PeekAngles> = { bottom: 0, left: PEEK_TILT, right: PEEK_TILT }
export const PEEK_PREVIEW_MAX_ANGLE = 45
export const PEEK_BOTTOM_INSET = 8
export const PEEK_TILT_SECONDS = 0.35
export const PEEK_RISE_SECONDS = 1.6

export function normalizePeekAngle(value: unknown, fallback = PEEK_TILT): number {
  return typeof value === 'number' && Number.isFinite(value) ? clamp(value, 0, PEEK_PREVIEW_MAX_ANGLE) : fallback
}

export function normalizePeekAngles(value: unknown): PeekAngles {
  const source = value && typeof value === 'object' ? (value as Partial<PeekAngles>) : {}
  return {
    bottom: normalizePeekAngle(source.bottom, DEFAULT_PEEK_ANGLES.bottom),
    left: normalizePeekAngle(source.left),
    right: normalizePeekAngle(source.right),
  }
}

export function isPeekEdge(value: unknown): value is PeekEdge {
  return PEEK_EDGES.some(edge => edge === value)
}

export function peekHome(
  position: PeekEye,
  view: StageViewport,
  size: { width: number; height: number },
  edge: PeekEdge = 'bottom',
) {
  const range = freeBounds(view, size.width, size.height)
  return {
    x: edge === 'left' ? range.x[0] : edge === 'right' ? range.x[1] : clamp(position.x, ...range.x),
    y: edge === 'bottom' ? range.y[1] : clamp(position.y, Math.max(range.y[0], range.y[1] - size.height), range.y[1]),
  }
}

/** 下角附近选最近的一条边；侧边只开放一个身高的范围，等距优先底边。 */
export function dropPeekEdge(
  position: PeekEye,
  view: StageViewport,
  size: { width: number; height: number },
): PeekEdge | null {
  const range = freeBounds(view, size.width, size.height)
  const threshold = Math.min(20, Math.min(size.width, size.height) * 0.18)
  const left = Math.abs(position.x - range.x[0])
  const right = Math.abs(position.x - range.x[1])
  const side = Math.min(left, right)
  const bottom = Math.abs(range.y[1] - position.y)
  if (side > threshold) return null
  if (bottom <= threshold && bottom <= side) return 'bottom'
  if (position.y < Math.max(range.y[0], range.y[1] - size.height) || position.y > range.y[1] + threshold) return null
  return left <= right ? 'left' : 'right'
}

interface PeekLayout {
  fromLeft: boolean
  visible: AgentRect
  hit: AgentRect
  artwork: AgentRect & { rotation: number }
  eye: PeekEye | null
}

function viewRect(view: StageViewport): AgentRect {
  return {
    x: view.safeArea.left,
    y: view.safeArea.top,
    width: Math.max(1, view.width - view.safeArea.left - view.safeArea.right),
    height: Math.max(1, floorLine(view) - view.safeArea.top),
  }
}

function intersect(rect: AgentRect, view: AgentRect): AgentRect {
  const x = clamp(rect.x, view.x, view.x + view.width)
  const y = clamp(rect.y, view.y, view.y + view.height)
  return {
    x,
    y,
    width: Math.max(0, Math.min(rect.x + rect.width, view.x + view.width) - x),
    height: Math.max(0, Math.min(rect.y + rect.height, view.y + view.height) - y),
  }
}

function touchRect(visible: AgentRect, view: AgentRect): AgentRect {
  const width = Math.min(view.width, Math.max(PEEK_TOUCH_SIZE, visible.width))
  const height = Math.min(view.height, Math.max(PEEK_TOUCH_SIZE, visible.height))
  return {
    x: clamp(visible.x + visible.width / 2 - width / 2, view.x, view.x + view.width - width),
    y: clamp(visible.y + visible.height / 2 - height / 2, view.y, view.y + view.height - height),
    width,
    height,
  }
}

/** 沿当前边避开面板；侧边无下角空位时交给舞台退出偷窥。 */
export function peekPanelShift(
  rect: AgentRect,
  panel: AgentRect,
  view: StageViewport,
  edge: PeekEdge = 'bottom',
): PeekEye | null {
  const bounds = viewRect(view)
  const horizontal = edge === 'bottom'
  const start = horizontal ? rect.x : rect.y
  const length = horizontal ? rect.width : rect.height
  const min = horizontal ? bounds.x : Math.max(bounds.y, bounds.y + bounds.height - length * 2)
  const max = (horizontal ? bounds.x + bounds.width : bounds.y + bounds.height) - length
  const panelStart = horizontal ? panel.x : panel.y
  const panelEnd = panelStart + (horizontal ? panel.width : panel.height)
  const target = [panelStart - length - 0.01, panelEnd + 0.01]
    .filter(value => value >= min && value <= max)
    .sort((a, b) => Math.abs(a - start) - Math.abs(b - start))[0]
  if (target === undefined) return null
  return horizontal ? { x: target - start, y: 0 } : { x: 0, y: target - start }
}

/** 先完整藏到主边外，再按角度探出；根据投影眼距控制露眼位置。 */
export function peekLayout(
  position: PeekEye,
  size: { width: number; height: number },
  view: StageViewport,
  edge: PeekEdge | null,
  progress: number,
  eye: PeekEye | null,
  revealing = true,
  bottomTilt = 1,
  angle = DEFAULT_PEEK_ANGLES[edge ?? 'bottom'],
): PeekLayout {
  const normal = { ...position, ...size }
  if (!edge) return { fromLeft: false, visible: normal, hit: normal, artwork: { ...normal, rotation: 0 }, eye: null }

  const bounds = viewRect(view)
  const horizontal = edge === 'bottom'
  const anchor = eye ?? { x: 0.5, y: 0.45 }
  const amount = clamp(progress, 0, PEEK_TUCK)
  const rise = clamp((PEEK_TUCK - amount) / (PEEK_TUCK - 1), 0, 1)
  const eased = rise * rise * (3 - 2 * rise)
  const turn = clamp(bottomTilt, 0, 1)
  const poseAmount = (horizontal ? turn * turn * (3 - 2 * turn) : eased) * Math.min(1, amount)
  const onLeft = edge === 'left' || (horizontal && position.x + size.width / 2 <= bounds.x + bounds.width / 2)
  const side = (onLeft ? 1 : -1) * (horizontal ? -1 : 1)
  const tilt = revealing ? normalizePeekAngle(angle, DEFAULT_PEEK_ANGLES[edge]) * poseAmount : 0
  const rotation = tilt === 0 ? 0 : side * tilt
  const radians = (rotation * Math.PI) / 180
  const cos = Math.cos(radians)
  const sin = Math.sin(radians)
  const scale = Math.min(
    1,
    horizontal
      ? bounds.width / (Math.abs(cos) * size.width + Math.abs(sin) * size.height)
      : bounds.height / (Math.abs(sin) * size.width + Math.abs(cos) * size.height),
  )
  const width = size.width * scale
  const height = size.height * scale
  const local = { x: (anchor.x - 0.5) * width, y: (anchor.y - 0.5) * height }
  const offset = { x: local.x * cos - local.y * sin, y: local.x * sin + local.y * cos }
  const project = (point: { x: number; y: number }) => ({
    x: (point.x - 0.5) * width * cos - (point.y - 0.5) * height * sin,
    y: (point.x - 0.5) * width * sin + (point.y - 0.5) * height * cos,
  })
  const eyes = eye?.eyes?.map(project)
  const headTop = eye?.headTop ? project(eye.headTop) : null
  const rotatedWidth = Math.abs(cos) * width + Math.abs(sin) * height
  const rotatedHeight = Math.abs(sin) * width + Math.abs(cos) * height
  const center = { x: position.x + size.width / 2, y: position.y + size.height / 2 }
  if (horizontal) {
    center.x = clamp(center.x, bounds.x + rotatedWidth / 2, bounds.x + bounds.width - rotatedWidth / 2)
    if (revealing) {
      // 底边按头部眼位靠角，不为藏在边界外的整身轮廓留空；仍跟随面板避让的横移。
      const inset = Math.min(bounds.width / 2, width * 0.25 + 4)
      const eyeX = clamp(
        position.x + (onLeft ? inset : size.width - inset),
        bounds.x + inset,
        bounds.x + bounds.width - inset,
      )
      let headCenter = eyeX - offset.x
      if (eyes && headTop) {
        const padding = Math.max(4, (Math.abs(eye!.eyes![1].x - eye!.eyes![0].x) * width) / 2)
        const xs = [headTop.x, ...eyes.map(point => point.x)]
        // 校准后的逻辑宽度可能超出视口，靠角位置必须落在实际可见边界内。
        const corner = clamp(position.x + (onLeft ? 0 : size.width), bounds.x, bounds.x + bounds.width)
        const clearance = Math.min(padding + PEEK_BOTTOM_INSET, (bounds.width - Math.max(...xs) + Math.min(...xs)) / 2)
        headCenter = clamp(
          onLeft ? corner + clearance - Math.min(...xs) : corner - clearance - Math.max(...xs),
          bounds.x + clearance - Math.min(...xs),
          bounds.x + bounds.width - clearance - Math.max(...xs),
        )
      } else {
        headCenter += onLeft ? PEEK_BOTTOM_INSET : -PEEK_BOTTOM_INSET
      }
      center.x += (headCenter - center.x) * poseAmount
    }
  } else center.y = clamp(center.y, bounds.y + rotatedHeight / 2, bounds.y + bounds.height - rotatedHeight / 2)
  const axis = horizontal ? 'y' : 'x'
  const outward = edge === 'left' ? -1 : 1
  const boundary = horizontal ? bounds.y + bounds.height : edge === 'left' ? bounds.x : bounds.x + bounds.width
  const hidden = boundary + outward * ((horizontal ? rotatedHeight : rotatedWidth) / 2 + 4)
  const eyePadding = Math.max(2, height * 0.025)
  const upright = horizontal && tilt === 0
  let looking = boundary + outward * (upright && eye ? -eyePadding : Math.max(1, height * 0.01)) - offset[axis]
  if (eyes) {
    const selected = [...eyes].sort((a, b) => outward * (a[axis] - b[axis]))[0]
    const separation = Math.abs(eyes[0][axis] - eyes[1][axis])
    // Level eyes cannot be separated by a horizontal edge; keep both visible at 0 degrees.
    const clearance = upright ? eyePadding : Math.min(eyePadding, separation * 0.45)
    looking = boundary - outward * clearance - selected[axis]
  }
  if (!revealing) center[axis] += (hidden - center[axis]) * (amount / PEEK_TUCK)
  else if (amount > 1) center[axis] = hidden + (looking - hidden) * eased
  else center[axis] += (looking - center[axis]) * amount

  const visible = intersect(
    { x: center.x - rotatedWidth / 2, y: center.y - rotatedHeight / 2, width: rotatedWidth, height: rotatedHeight },
    bounds,
  )
  return {
    fromLeft: onLeft,
    visible,
    hit: touchRect(visible, bounds),
    artwork: { x: center.x - width / 2, y: center.y - height / 2, width, height, rotation },
    eye: eye ? { x: center.x + offset.x, y: center.y + offset.y } : null,
  }
}
