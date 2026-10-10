import { afterEach, describe, expect, it, vi } from 'vitest'

import { querySurfaces, surfaceUnobstructed } from '@/stage/surfaces'

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
