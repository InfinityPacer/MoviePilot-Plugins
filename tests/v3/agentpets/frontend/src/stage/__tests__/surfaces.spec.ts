import { afterEach, describe, expect, it, vi } from 'vitest'

import { MAX_CLEAR_CANDIDATES, pickClearX } from '@/stage/geometry'
import {
  controlsUnder,
  coversControlAt,
  querySurfaces,
  SAMPLE_COLS,
  SAMPLE_ROWS,
  samplePoints,
  surfaceUnobstructed,
} from '@/stage/surfaces'

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

describe('control hit testing', () => {
  const view = { width: 1000, height: 800 }
  const pet = { x: 100, y: 100, width: 90, height: 120 }
  const petRect = () => ({ left: pet.x, top: pet.y, width: pet.width, height: pet.height })

  it('samples a 3 by 4 grid inside the character', () => {
    const points = samplePoints(pet)
    expect(points).toHaveLength(12)
    expect(points[0]).toEqual({ x: 115, y: 115 })
    expect(points[11]).toEqual({ x: 175, y: 205 })
  })

  it('maps the first hit to its control and returns the control rectangle', () => {
    const link = withRect(document.createElement('a'), { left: 0, top: 150, width: 256, height: 48 })
    const label = document.createElement('span')
    link.appendChild(label)
    document.body.appendChild(link)
    stubHits(({ y }) => (y > 150 && y < 198 ? [label, link, document.body] : [document.body]))
    expect(controlsUnder(pet, null, view, null)).toEqual([{ x: 0, y: 150, width: 256, height: 48 }])
  })

  it('ignores controls hidden under a scrim or other element', () => {
    const button = withRect(document.createElement('button'), { left: 100, top: 100, width: 90, height: 120 })
    const scrim = document.createElement('div')
    document.body.append(button, scrim)
    stubHits(() => [scrim, button])
    expect(controlsUnder(pet, null, view, null)).toEqual([])
  })

  it('keeps tabindex controls but skips layout containers, her layer and the card she stands on', () => {
    const layer = document.createElement('div')
    const character = document.createElement('button')
    layer.appendChild(character)
    const focusable = withRect(document.createElement('div'), { left: 100, top: 100, width: 60, height: 40 })
    focusable.setAttribute('tabindex', '0')
    const layout = withRect(document.createElement('main'), { left: 0, top: 0, width: 1000, height: 800 })
    layout.setAttribute('tabindex', '0')
    const inLayout = document.createElement('p')
    layout.appendChild(inLayout)
    const card = withRect(document.createElement('div'), { left: 0, top: 220, width: 400, height: 200 })
    card.className = 'v-card v-card--link'
    document.body.append(layer, focusable, layout, card)

    stubHits(({ y }) => [character, y < 140 ? focusable : y < 200 ? inLayout : card])
    expect(controlsUnder(pet, layer, view, card)).toEqual([{ x: 100, y: 100, width: 60, height: 40 }])
  })

  it('stops sampling as soon as a covering control is found', () => {
    const button = withRect(document.createElement('button'), petRect())
    document.body.appendChild(button)
    const hits = stubHits(() => [button])
    expect(coversControlAt(pet, null, view, null)).toBe(true)
    expect(hits).toHaveBeenCalledTimes(1)
    // 只擦到一点边的控件不算挡住，继续取样。
    const sliver = withRect(document.createElement('button'), { left: 185, top: 100, width: 50, height: 20 })
    document.body.appendChild(sliver)
    const sliverHits = stubHits(() => [sliver])
    expect(coversControlAt(pet, null, view, null)).toBe(false)
    expect(sliverHits).toHaveBeenCalledTimes(12)
  })

  it('returns nothing without elementsFromPoint', () => {
    expect(controlsUnder(pet, null, view, null)).toEqual([])
  })

  it('bounds the work of one clearance search regardless of page size', () => {
    // 合成页面：3000 张卡片、9000 个控件。命中测试只按取样点调用，不遍历页面元素。
    const controls: HTMLElement[] = []
    for (let index = 0; index < 3000; index += 1) {
      const card = document.createElement('div')
      card.className = 'v-card'
      for (let inner = 0; inner < 3; inner += 1) {
        const button = withRect(document.createElement('button'), { left: 0, top: 0, width: 1000, height: 300 })
        card.appendChild(button)
        controls.push(button)
      }
      document.body.appendChild(card)
    }
    // 最坏情况：每个点都命中控件，所有候选位置都被挡住。
    const hits = stubHits(({ x }) => [controls[Math.floor(x) % controls.length], document.body])
    const query = vi.spyOn(document, 'querySelectorAll')
    const covers = (left: number) => coversControlAt({ ...pet, x: left }, null, view, null)

    const started = performance.now()
    const target = pickClearX(pet.x, [0, 900], left => !covers(left), pet.width / 2)
    const elapsed = performance.now() - started

    expect(target).toBeNull()
    // 被挡住的位置在第一个命中控件的取样点就返回，最坏也不超过“取样点数 × 候选数”。
    expect(hits.mock.calls.length).toBeLessThanOrEqual(SAMPLE_COLS * SAMPLE_ROWS * MAX_CLEAR_CANDIDATES)
    expect(hits.mock.calls.length).toBeLessThanOrEqual(MAX_CLEAR_CANDIDATES)
    expect(query).not.toHaveBeenCalled()
    expect(elapsed).toBeLessThan(5)
  })
})
