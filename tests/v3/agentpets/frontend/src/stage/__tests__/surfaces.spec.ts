import { afterEach, describe, expect, it, vi } from 'vitest'

import { collectControls, querySurfaces, surfaceUnobstructed } from '@/stage/surfaces'

const viewport = { width: 1000, height: 800, keyboardInset: 0, safeArea: { top: 0, right: 0, bottom: 0, left: 0 } }
const box = { left: 100, top: 400, right: 700 }

function card(): HTMLElement {
  const el = document.createElement('div')
  el.className = 'v-card'
  el.getBoundingClientRect = () =>
    ({ ...box, x: 100, y: 400, width: 600, height: 200, bottom: 600, toJSON: () => box }) as DOMRect
  document.body.appendChild(el)
  return el
}

function stubHits(hits: (point: { x: number; y: number }) => Element[]) {
  const spy = vi.fn((x: number, y: number) => hits({ x, y }))
  Object.defineProperty(document, 'elementsFromPoint', { configurable: true, value: spy })
  return spy
}

afterEach(() => {
  delete (document as { elementsFromPoint?: unknown }).elementsFromPoint
  document.body.innerHTML = ''
})

describe('surface occlusion', () => {
  it('probes 2px below the middle of the visible top edge', () => {
    const el = card()
    const spy = stubHits(() => [el])
    expect(surfaceUnobstructed(el, { left: -200, top: 400, right: 600 }, null, 1000)).toBe(true)
    expect(spy).toHaveBeenCalledWith(300, 402)
  })

  it('accepts the element itself or its descendants as the first hit', () => {
    const el = card()
    const child = document.createElement('span')
    el.appendChild(child)
    stubHits(() => [child, el, document.body])
    expect(surfaceUnobstructed(el, box, null, 1000)).toBe(true)
  })

  it('rejects a card covered by a scrim or another element', () => {
    const el = card()
    const scrim = document.createElement('div')
    document.body.appendChild(scrim)
    stubHits(() => [scrim, el])
    expect(surfaceUnobstructed(el, box, null, 1000)).toBe(false)
    expect(querySurfaces(null, viewport, 120, null)).toEqual([])
  })

  it('skips the stage layer itself when hit testing', () => {
    const el = card()
    const layer = document.createElement('div')
    const character = document.createElement('button')
    layer.appendChild(character)
    document.body.appendChild(layer)
    stubHits(() => [character, el])
    expect(querySurfaces(layer, viewport, 120, null).map(item => item.el)).toEqual([el])
  })

  it('treats browsers without elementsFromPoint as unobstructed', () => {
    const el = card()
    expect(surfaceUnobstructed(el, box, null, 1000)).toBe(true)
  })
})

function withRect<T extends Element>(el: T, rect: { left: number; top: number; width: number; height: number }): T {
  el.getBoundingClientRect = () =>
    ({
      ...rect,
      x: rect.left,
      y: rect.top,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
      toJSON: () => rect,
    }) as DOMRect
  return el
}

describe('surface query on long pages', () => {
  it('filters by viewport before applying the candidate limit', () => {
    // 3000 张卡片，往下滚后前 2990 张都在视口上方。
    for (let index = 0; index < 3000; index += 1) {
      const card = withRect(document.createElement('div'), {
        left: 100,
        top: index < 2990 ? -10000 + index : 300 + (index - 2990) * 40,
        width: 600,
        height: 30,
      })
      card.className = 'v-card'
      document.body.appendChild(card)
    }
    const styleSpy = vi.spyOn(window, 'getComputedStyle')
    const surfaces = querySurfaces(null, viewport, 120, null)
    expect(surfaces.length).toBeGreaterThan(0)
    expect(surfaces.every(surface => surface.top >= 120)).toBe(true)
    // 样式读取只发生在视口内的候选上，耗时与页面长度无关。
    expect(styleSpy.mock.calls.length).toBeLessThanOrEqual(10)
  })
})

describe('control rectangles', () => {
  const view = { width: 1000, height: 800 }

  it('collects visible controls in the viewport, including list items and focusable elements', () => {
    const link = withRect(document.createElement('a'), { left: 0, top: 100, width: 256, height: 48 })
    const item = withRect(document.createElement('div'), { left: 0, top: 160, width: 256, height: 48 })
    item.className = 'v-list-item'
    const focusable = withRect(document.createElement('div'), { left: 300, top: 100, width: 80, height: 40 })
    focusable.setAttribute('tabindex', '0')
    const scriptOnly = withRect(document.createElement('div'), { left: 400, top: 100, width: 80, height: 40 })
    scriptOnly.setAttribute('tabindex', '-1')
    const offscreen = withRect(document.createElement('button'), { left: 0, top: 2000, width: 80, height: 40 })
    const layout = withRect(document.createElement('main'), { left: 0, top: 0, width: 1000, height: 800 })
    layout.setAttribute('tabindex', '0')
    document.body.append(link, item, focusable, scriptOnly, offscreen, layout)

    expect(collectControls(null, view, null)).toEqual([
      { x: 0, y: 100, width: 256, height: 48 },
      { x: 0, y: 160, width: 256, height: 48 },
      { x: 300, y: 100, width: 80, height: 40 },
    ])
  })

  it('skips the stage layer and the link card she stands on', () => {
    const layer = document.createElement('div')
    const character = withRect(document.createElement('button'), { left: 10, top: 10, width: 80, height: 100 })
    layer.appendChild(character)
    const linkCard = withRect(document.createElement('div'), { left: 0, top: 110, width: 400, height: 200 })
    linkCard.className = 'v-card v-card--link'
    const other = withRect(document.createElement('div'), { left: 500, top: 110, width: 400, height: 200 })
    other.className = 'v-card v-card--link'
    document.body.append(layer, linkCard, other)

    expect(collectControls(layer, view, linkCard)).toEqual([{ x: 500, y: 110, width: 400, height: 200 }])
  })
})
