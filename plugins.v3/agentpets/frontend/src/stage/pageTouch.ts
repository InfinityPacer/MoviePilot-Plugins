import { LONG_PRESS_MS } from './interaction'
import { CONTROL_SELECTOR } from './surfaces'

const TAP_SLOP = 10
const EXCLUDED_TARGETS = [
  CONTROL_SELECTOR,
  'label, summary, [contenteditable]:not([contenteditable="false"]), [draggable="true"]',
  '[role="link"], [role="checkbox"], [role="radio"], [role="switch"], [role="tab"]',
  '[role="menuitem"], [role="option"], [role="combobox"], [role="slider"], [role="spinbutton"]',
  '[role="textbox"], [role="searchbox"], [role="treeitem"], dialog, [role="dialog"]',
  '.v-field, .v-input, .v-slider, .v-overlay__scrim, .agent-pet-ying',
].join(', ')

function backgroundTarget(event: PointerEvent): Element | null {
  const path = event.composedPath().filter((item): item is Element => item instanceof Element)
  if (!path.length || path.some(element => element.matches(EXCLUDED_TARGETS))) return null
  return path[0].isConnected ? path[0] : null
}

function finitePoint(event: PointerEvent): boolean {
  return Number.isFinite(event.clientX + event.clientY) && event.clientX >= 0 && event.clientY >= 0
}

/** Observe a single short background tap; never capture or prevent the page's input. */
export class PageTapTracker {
  private pending: { id: number; x: number; y: number; at: number; target: Element; down: PointerEvent } | null = null

  start(event: PointerEvent, now: number): void {
    this.reset()
    if (event.pointerType !== 'touch' || event.isPrimary === false || event.button !== 0 || event.defaultPrevented)
      return
    const target = backgroundTarget(event)
    if (target && finitePoint(event))
      this.pending = { id: event.pointerId, x: event.clientX, y: event.clientY, at: now, target, down: event }
  }

  move(event: PointerEvent): void {
    const tap = this.pending
    if (!tap || tap.id !== event.pointerId) return
    if (!finitePoint(event) || Math.hypot(event.clientX - tap.x, event.clientY - tap.y) >= TAP_SLOP) this.reset()
  }

  finish(event: PointerEvent, now: number): { x: number; y: number } | null {
    this.move(event)
    const tap = this.pending
    if (!tap || tap.id !== event.pointerId) return null
    this.reset()
    if (
      event.pointerType !== 'touch' ||
      event.isPrimary === false ||
      event.defaultPrevented ||
      tap.down.defaultPrevented ||
      now < tap.at ||
      now - tap.at >= LONG_PRESS_MS ||
      !tap.target.isConnected ||
      tap.target.closest(EXCLUDED_TARGETS) ||
      !backgroundTarget(event)
    )
      return null
    return { x: event.clientX, y: event.clientY }
  }

  reset(): void {
    this.pending = null
  }
}
