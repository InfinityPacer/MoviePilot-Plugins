import { fireEvent, render } from '@testing-library/vue'
import { compileStyle, parse } from 'vue/compiler-sfc'
import { describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import PetPreview from '@/editor/PetPreview.vue'
import previewSource from '@/editor/PetPreview.vue?raw'
import type { PetChoice } from '@/editor/api'
import legacyJson from '@tests/../fixtures/legacy-codex-v2.json'
import { parseCalibration } from '@/sprites/calibration'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'

async function setup(size: { width: number; height: number; mobile?: boolean } = { width: 500, height: 400 }) {
  vi.stubGlobal('innerWidth', size.mobile ? 390 : 1024)
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  const original = Element.prototype.getBoundingClientRect
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    if (this.classList.contains('ap-preview__canvas'))
      return {
        x: 200,
        y: 100,
        left: 200,
        top: 100,
        right: 200 + size.width,
        bottom: 100 + size.height,
        width: size.width,
        height: size.height,
        toJSON: () => ({}),
      } as DOMRect
    if (this.classList.contains('ap-preview__surface') && getComputedStyle(this).width) {
      const css = getComputedStyle(this)
      const px = (value: string, reference: number) => parseFloat(value) * (value.endsWith('%') ? reference / 100 : 1)
      const width = Math.max(px(css.width, size.width), parseFloat(css.minWidth) || 0)
      const height = parseFloat(css.height)
      const left =
        200 +
        (css.left && css.left !== 'auto' ? px(css.left, size.width) : size.width - px(css.right, size.width) - width)
      const top = 100 + px(css.top, size.height)
      return {
        x: left,
        y: top,
        left,
        top,
        right: left + width,
        bottom: top + height,
        width,
        height,
        toJSON: () => ({}),
      } as DOMRect
    }
    return original.call(this)
  })
  const pet: PetChoice = {
    key: 'kurisu',
    name: 'Kurisu',
    description: '',
    preview: '',
    mode: 'stage',
    builtin: false,
  }
  const api = {
    get: vi.fn().mockImplementation(async (path: string) => {
      if (path.includes('/packs/calibration?')) {
        const id = new URL(path, 'https://example.test').searchParams.get('key')!
        return { success: true, data: { id, calibration: builtinDefaultCalibration(id) } }
      }
      return {
        success: true,
        data: {
          pack: { ...legacyJson, codex_version: 'v2' },
          sheet_src: 'data:image/png;base64,AAAA',
        },
      }
    }),
    post: vi.fn(),
  }
  const view = render(PetPreview, {
    props: {
      pet,
      settings: { scale: 1, speed: 1, roam: 'floor' },
      api,
      pluginId: 'Clone1',
    },
    global: { plugins: [createVuetify({ components, directives })] },
  })
  await vi.advanceTimersByTimeAsync(48)
  return { view, pet, api }
}

it('edits Codex landmarks on a locked peek frame without mounting the draggable stage or saving', async () => {
  const { view, api } = await setup()
  await view.rerender({ calibration: parseCalibration({}) })
  await fireEvent.click(view.getByRole('tab', { name: '校准' }))
  await vi.advanceTimersByTimeAsync(64)
  expect(view.getByRole('group', { name: '双眼与头顶拖拽校准' })).toBeTruthy()
  expect(view.container.querySelector('.agent-pet-ying')).toBeNull()
  const sprite = view.container.querySelector('.agent-pet-sprites') as HTMLElement
  expect(sprite.dataset.action).toBe('peek')
  const frame = sprite.dataset.frame
  await vi.advanceTimersByTimeAsync(3000)
  expect(sprite.dataset.frame).toBe(frame)
  await fireEvent.click(view.getByRole('button', { name: '放大头部' }))
  expect((view.container.querySelector('.ap-preview__calibration-entry') as HTMLElement).style.transform).toBe(
    'scale(2)',
  )
  await fireEvent.keyDown(view.getByRole('button', { name: /画面左眼校准光圈/ }), { key: 'ArrowRight' })
  expect(view.emitted().calibration).toHaveLength(1)
  expect(api.post).not.toHaveBeenCalled()
})

function applyPreviewStyles() {
  const style = document.createElement('style')
  const scopeId = (PetPreview as typeof PetPreview & { __scopeId: string }).__scopeId
  const { descriptor } = parse(previewSource)
  const compiled = compileStyle({
    source: descriptor.styles[0].content,
    filename: 'PetPreview.vue',
    id: scopeId,
    scoped: true,
  })
  expect(compiled.errors).toEqual([])
  style.textContent = compiled.code
  document.head.append(style)
  return style
}

describe('contained live Pet preview', () => {
  it('keeps a non-shrinking canvas and scrollable workspace on short screens', async () => {
    const { view, api } = await setup({ width: 330, height: 160, mobile: true })
    const style = applyPreviewStyles()
    const mediaStyle = document.createElement('style')
    // jsdom does not apply viewport media queries, so select the real compiled rules for 360 x 640.
    const viewport = { width: 360, height: 640 }
    mediaStyle.textContent = Array.from(style.sheet!.cssRules)
      .filter(rule => rule.type === CSSRule.MEDIA_RULE)
      .map(rule => rule as CSSMediaRule)
      .filter(rule => {
        const limits = Array.from(rule.conditionText.matchAll(/\(max-(width|height):\s*(\d+)px\)/g))
        return limits.length && limits.every(([, axis, limit]) => viewport[axis as keyof typeof viewport] <= +limit)
      })
      .flatMap(rule => Array.from(rule.cssRules).map(child => child.cssText))
      .join('\n')
    document.head.append(mediaStyle)
    try {
      const css = (selector: string) => getComputedStyle(view.container.querySelector(selector)!)
      expect(css('.ap-preview').overflowY).toBe('auto')
      expect(css('.ap-preview__viewer').flexShrink).toBe('0')
      expect(css('.ap-preview__viewer').maxHeight).toBe('none')
      expect(css('.ap-preview__canvases').flexShrink).toBe('0')
      expect(css('.ap-preview__canvases').minHeight).toBe('var(--ap-canvas-height)')
      expect(css('.ap-preview__scroll').overflow).toBe('visible')
      expect(parseFloat(getComputedStyle(view.getByRole('tab', { name: '映射' })).minWidth)).toBe(0)
      expect(parseFloat((view.container.querySelector('.agent-pet-ying__character') as HTMLElement).style.height)).toBe(
        120 * 0.8,
      )
      expect(api.post).not.toHaveBeenCalled()
    } finally {
      view.unmount()
      mediaStyle.remove()
      style.remove()
    }
  })

  it('anchors the character, floor and hint to their own painted preview instead of the host dialog', async () => {
    const { view } = await setup()
    const style = applyPreviewStyles()
    try {
      const canvas = view.container.querySelector('.ap-preview__canvas')!
      const nearestPositionedParent = (element: Element) => {
        let parent = element.parentElement
        while (parent) {
          const position = getComputedStyle(parent).position
          if (position && position !== 'static') return parent
          parent = parent.parentElement
        }
        return null
      }
      for (const selector of ['.agent-pet-ying--contained', '.ap-preview__floor', '.ap-preview__hint']) {
        expect(nearestPositionedParent(canvas.querySelector(selector)!)).toBe(canvas)
      }
      expect(getComputedStyle(canvas).overflow).toBe('hidden')
      expect(getComputedStyle(canvas).contain).toBe('paint')
      await fireEvent.click(view.getByLabelText('对照原始显示'))
      const original = view.getByLabelText('原始显示对照')
      expect(nearestPositionedParent(original.querySelector('.ap-preview__entry')!)).toBe(original)
      expect(getComputedStyle(original).overflow).toBe('hidden')
    } finally {
      style.remove()
    }
  })

  it.each([
    { width: 280, height: 400, key: 'ying' },
    { width: 300, height: 400, key: 'kurisu' },
    { width: 390, height: 180, key: 'ying', mobile: true },
  ])('lands on both CSS-sized platforms in a $width × $height $key preview', async size => {
    const { view, pet, api } = await setup(size)
    const style = applyPreviewStyles()
    try {
      await view.rerender({
        pet: { ...pet, key: size.key, builtin: size.key === 'ying' },
        settings: { scale: 1.3, speed: 1, roam: 'surfaces', movement: 'auto' },
      })
      await fireEvent.click(view.getByRole('button', { name: '运动测试' }))
      await vi.advanceTimersByTimeAsync(48)
      const canvas = view.container.querySelector('.ap-preview__canvas')!
      const platforms = Array.from(canvas.querySelectorAll('.ap-preview__surface'))
      expect(platforms).toHaveLength(2)
      const pointer = (type: string, clientX: number, clientY: number) => {
        const event = new MouseEvent(type, { bubbles: true, button: 0, clientX, clientY })
        Object.defineProperty(event, 'pointerId', { value: 1 })
        return event
      }
      for (const platform of platforms) {
        const character = canvas.querySelector('.agent-pet-ying__character') as HTMLElement
        const position = () =>
          character.style.transform
            .slice('translate3d('.length)
            .split(',')
            .map(value => parseFloat(value))
        const [x, y] = position()
        const width = parseFloat(character.style.width)
        const height = parseFloat(character.style.height)
        const origin = canvas.getBoundingClientRect()
        const target = platform.getBoundingClientRect()
        const targetX = (target.left + target.right) / 2
        const targetY = target.top - height / 2 - 4
        character.dispatchEvent(pointer('pointerdown', origin.left + x + width / 2, origin.top + y + height / 2))
        window.dispatchEvent(pointer('pointermove', targetX, targetY))
        window.dispatchEvent(pointer('pointerup', targetX, targetY))
        await vi.advanceTimersByTimeAsync(500)
        expect(origin.top + position()[1] + height).toBeCloseTo(target.top, 1)
      }
      expect(api.post).not.toHaveBeenCalled()
    } finally {
      view.unmount()
      style.remove()
    }
  })

  it('asks to expand a canvas too narrow for platforms and restores them after resizing', async () => {
    const size = { width: 100, height: 160 }
    const { view, api } = await setup(size)
    await view.rerender({ settings: { scale: 1.3, speed: 1, roam: 'surfaces', movement: 'auto' } })
    await fireEvent.click(view.getByRole('button', { name: '运动测试' }))
    await vi.advanceTimersByTimeAsync(48)
    expect(view.container.querySelectorAll('.ap-preview__surface')).toHaveLength(0)
    expect(view.getByText('预览过窄，请放大后测试平台')).toBeInTheDocument()
    size.width = 300
    window.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(48)
    expect(view.container.querySelectorAll('.ap-preview__surface')).toHaveLength(2)
    expect(view.getByText('拖到平台上方松手 · 测试站立')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('keeps canvas coordinates when the phone visual viewport is resized and panned', async () => {
    const visual = Object.assign(new EventTarget(), {
      offsetTop: 300,
      offsetLeft: 40,
      width: 200,
      height: 200,
    })
    vi.stubGlobal('visualViewport', visual)
    const { view } = await setup()
    const character = view.container.querySelector('.agent-pet-ying__character') as HTMLElement
    const [x, y] = character.style.transform
      .slice('translate3d('.length)
      .split(',')
      .map(value => parseFloat(value))
    expect(x + parseFloat(character.style.width) / 2).toBeCloseTo(250)
    expect(y + parseFloat(character.style.height) / 2).toBeCloseTo(198)
    const initial = character.style.transform
    visual.height = 100
    visual.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(48)
    expect(character.style.transform).toBe(initial)
  })

  it('renders the selected Codex pet inside the canvas and responds to scale and roam drafts without saving', async () => {
    const { view, api } = await setup()
    const canvas = view.container.querySelector('.ap-preview__canvas')!
    const character = canvas.querySelector('.agent-pet-ying__character') as HTMLElement
    expect(character.style.height).toBe('120px')
    expect(canvas.querySelector('.agent-pet-ying--contained')).not.toBeNull()
    expect(api.get.mock.calls).toEqual([['plugin/Clone1/pack?key=kurisu']])
    await fireEvent.click(view.getByRole('button', { name: '运动测试' }))
    await view.rerender({ settings: { scale: 1.5, speed: 2, roam: 'free' } })
    await vi.advanceTimersByTimeAsync(32)
    expect((canvas.querySelector('.agent-pet-ying__character') as HTMLElement).style.height).toBe('180px')
    expect(canvas.querySelector('.agent-pet-ying')?.getAttribute('data-roam')).toBe('free')
    expect(api.post).not.toHaveBeenCalled()
    view.unmount()
    await vi.advanceTimersByTimeAsync(32)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('resets a dragged preview position while preserving its activity draft', async () => {
    const { view, api } = await setup()
    await fireEvent.click(view.getByRole('button', { name: '运动测试' }))
    await view.rerender({ settings: { scale: 1, speed: 1.5, roam: 'free' } })
    await vi.advanceTimersByTimeAsync(32)
    const character = view.container.querySelector('.agent-pet-ying__character') as HTMLElement
    const initialPosition = character.style.transform
    const pointer = (type: string, clientX: number, clientY: number) => {
      const event = new MouseEvent(type, {
        bubbles: true,
        button: 0,
        clientX,
        clientY,
      })
      Object.defineProperty(event, 'pointerId', { value: 1 })
      return event
    }
    character.dispatchEvent(pointer('pointerdown', 600, 400))
    window.dispatchEvent(pointer('pointermove', 400, 240))
    window.dispatchEvent(pointer('pointerup', 400, 240))
    await vi.advanceTimersByTimeAsync(500)
    expect(character.style.transform).not.toBe(initialPosition)
    await fireEvent.click(view.getByRole('button', { name: '重置预览位置' }))
    await vi.advanceTimersByTimeAsync(48)
    const resetCharacter = view.container.querySelector('.agent-pet-ying__character') as HTMLElement
    expect(resetCharacter.style.transform).toBe(initialPosition)
    expect(view.container.querySelector('.agent-pet-ying')?.getAttribute('data-roam')).toBe('free')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('previews speech and thinking on the selected sprite and pauses frames', async () => {
    const { view } = await setup()
    const sprite = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    await fireEvent.click(view.getByRole('tab', { name: '活动姿态' }))
    await fireEvent.click(view.getByRole('button', { name: '说话' }))
    await vi.advanceTimersByTimeAsync(32)
    expect(sprite.dataset.action).toBe('speaking')
    await fireEvent.click(view.getByRole('button', { name: '思考' }))
    await vi.advanceTimersByTimeAsync(32)
    expect(sprite.dataset.action).toBe('thinking')
    await fireEvent.click(view.getByRole('button', { name: '暂停预览' }))
    await vi.advanceTimersByTimeAsync(32)
    const frame = sprite.dataset.frame
    await vi.advanceTimersByTimeAsync(1500)
    expect(sprite.dataset.frame).toBe(frame)
  })

  it('switches from a stage pet to an entry renderer and disposes the old stage', async () => {
    const { view, pet } = await setup()
    await view.rerender({
      pet: { ...pet, key: 'projector-cat', mode: 'renderer', builtin: true },
    })
    await vi.advanceTimersByTimeAsync(32)
    expect(view.container.querySelector('.agent-pet-ying')).toBeNull()
    expect(view.container.querySelector('.ap-preview__entry [data-pack="projector-cat"]')).not.toBeNull()
    view.unmount()
    await vi.advanceTimersByTimeAsync(32)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('reports a failed selected pet instead of showing a different pet as its preview', async () => {
    const { view, pet, api } = await setup()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    api.get.mockRejectedValue(new Error('offline'))
    await view.rerender({ pet: { ...pet, key: 'unavailable' } })
    await vi.advanceTimersByTimeAsync(64)
    expect(view.getByText('此 Pet 加载失败，请点击重置重试。')).toBeInTheDocument()
    expect(view.container.querySelector('[data-pack="projector-cat"]')).toBeNull()
    expect(view.emitted('error').at(-1)).toEqual([true])
  })
  it('shows the full native library and directions without changing runtime mappings', async () => {
    const { view, api } = await setup()
    await view.rerender({
      mappings: { 'stage.idle': 'review', 'stage.think': 'failed' },
    })
    const sprite = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    await fireEvent.click(view.getByRole('button', { name: '等待 · waiting' }))
    await vi.advanceTimersByTimeAsync(32)
    expect(sprite.dataset.action).toBe('waiting')
    await fireEvent.click(view.getByRole('tab', { name: '视线方向' }))
    await fireEvent.click(view.getByRole('button', { name: '337.5°' }))
    await vi.advanceTimersByTimeAsync(32)
    expect(sprite.dataset.action).toBe('look-337-5')
    await fireEvent.click(view.getByRole('tab', { name: '活动姿态' }))
    await fireEvent.click(view.getByRole('button', { name: '思考' }))
    await vi.advanceTimersByTimeAsync(32)
    expect(sprite.dataset.action).toBe('failed')
    expect(api.post).not.toHaveBeenCalled()
  })
  it('keeps the simulated tool phase after a direct animation preview', async () => {
    const { view } = await setup()
    await fireEvent.click(view.getByRole('tab', { name: 'MP 事件' }))
    await fireEvent.click(view.getByRole('tab', { name: '映射' }))
    await fireEvent.click(view.getByRole('button', { name: '会话' }))
    await vi.advanceTimersByTimeAsync(350)
    await fireEvent.click(view.getByRole('button', { name: '试播思考' }))
    expect(view.getByText('正在播放：思考 → 思考')).toBeInTheDocument()
    await fireEvent.click(view.getByRole('tab', { name: '动作试播' }))
    await fireEvent.click(view.getByRole('button', { name: '开始执行工具' }))
    await vi.advanceTimersByTimeAsync(350)
    const sprite = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    expect(sprite.dataset.action).toBe('charge')
  })
  it('keeps a centered animated character mounted while switching and scrolling editor tabs', async () => {
    const { view, api } = await setup()
    await fireEvent.click(view.getByRole('button', { name: '招手 · wave' }))
    await vi.advanceTimersByTimeAsync(32)
    const character = view.container.querySelector('.agent-pet-ying__character') as HTMLElement
    const sprite = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    const position = character.style.transform
    const frame = sprite.dataset.frame
    await vi.advanceTimersByTimeAsync(240)
    expect(sprite.dataset.frame).not.toBe(frame)
    for (const name of ['活动', '校准', '映射', '动作试播']) {
      await fireEvent.click(view.getByRole('tab', { name }))
      const scroll = view.container.querySelector('.ap-preview__scroll')!
      await fireEvent.scroll(scroll, { target: { scrollTop: 400 } })
      expect(view.container.querySelector('.agent-pet-ying__character')).toBe(character)
      expect(sprite.dataset.action).toBe('wave')
    }
    await vi.advanceTimersByTimeAsync(15_000)
    expect(character.style.transform).toBe(position)
    expect(view.getByText('正在播放：招手 · wave')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })
  it.each([
    { width: 300, height: 260 },
    { width: 390, height: 180, mobile: true },
    { width: 100, height: 160 },
  ])('fits a compact $width × $height preview without changing saved scale or remounting on expansion', async size => {
    const { view, api } = await setup(size)
    const settings = { scale: 1.6, speed: 1, roam: 'surfaces' }
    await view.rerender({ settings })
    await vi.advanceTimersByTimeAsync(48)
    const character = view.container.querySelector('.agent-pet-ying__character') as HTMLElement
    expect(parseFloat(character.style.height)).toBeLessThanOrEqual(size.height - 40)
    expect(parseFloat(character.style.width)).toBeLessThanOrEqual(size.width - 32)
    expect(settings).toEqual({ scale: 1.6, speed: 1, roam: 'surfaces' })
    const compactHeight = parseFloat(character.style.height)
    size.height += 200
    size.width += 200
    await fireEvent.click(view.getByRole('button', { name: '放大预览' }))
    window.dispatchEvent(new Event('resize'))
    await vi.advanceTimersByTimeAsync(48)
    expect(view.container.querySelector('.agent-pet-ying__character')).toBe(character)
    expect(parseFloat(character.style.height)).toBeGreaterThanOrEqual(compactHeight)
    expect(parseFloat(character.style.height)).toBeCloseTo(size.mobile ? 153.6 : 192)
    expect(api.post).not.toHaveBeenCalled()
  })
  it('fits very wide calibrated artwork and restores centered debugging after a movement test', async () => {
    const { view, api } = await setup({ width: 300, height: 180, mobile: true })
    const calibration = { left: 0, top: 0, right: 1, bottom: 0.1, baseline: 0.1, offset_x: 0, offset_y: 0 }
    await view.rerender({ calibration, settings: { scale: 1.6, speed: 1, roam: 'surfaces', movement: 'auto' } })
    await vi.advanceTimersByTimeAsync(48)
    let character = view.container.querySelector('.agent-pet-ying__character') as HTMLElement
    expect(parseFloat(character.style.width)).toBeCloseTo(268)
    expect(parseFloat(character.style.height)).toBeLessThan(40)
    expect(view.container.querySelectorAll('.ap-preview__surface')).toHaveLength(0)
    await fireEvent.click(view.getByRole('button', { name: '运动测试' }))
    await vi.advanceTimersByTimeAsync(48)
    expect(view.container.querySelectorAll('.ap-preview__surface')).toHaveLength(2)
    expect(view.container.querySelector('.agent-pet-ying')?.getAttribute('data-roam')).toBe('surfaces')
    await fireEvent.click(view.getByRole('button', { name: '动作调试' }))
    await vi.advanceTimersByTimeAsync(48)
    character = view.container.querySelector('.agent-pet-ying__character') as HTMLElement
    const [x] = character.style.transform
      .slice('translate3d('.length)
      .split(',')
      .map(value => parseFloat(value))
    expect(x + parseFloat(character.style.width) / 2).toBeCloseTo(150)
    const position = character.style.transform
    await vi.advanceTimersByTimeAsync(12_000)
    expect(character.style.transform).toBe(position)
    expect(api.post).not.toHaveBeenCalled()
  })
  it('shows original and calibrated previews beside each other and preserves the calibration draft', async () => {
    const { view, api } = await setup()
    const calibration = {
      left: 0.1,
      top: 0.1,
      right: 0.8,
      bottom: 0.9,
      baseline: 0.8,
      offset_x: 0,
      offset_y: 0,
    }
    await view.rerender({ calibration })
    await fireEvent.click(view.getByRole('tab', { name: '校准' }))
    await fireEvent.click(view.getByRole('checkbox', { name: '对照原始显示' }))
    await vi.advanceTimersByTimeAsync(48)
    expect(view.container.querySelectorAll('.agent-pet-sprites')).toHaveLength(2)
    expect(view.getByLabelText('原始显示对照')).toBeInTheDocument()
    expect(view.container.querySelector('.ap-preview__canvas .agent-pet-sprites__viewport--guides')).not.toBeNull()
    await fireEvent.click(view.getByRole('tab', { name: '映射' }))
    expect(view.container.querySelectorAll('.agent-pet-sprites')).toHaveLength(2)
    expect(calibration.left).toBe(0.1)
    expect(api.post).not.toHaveBeenCalled()
    view.unmount()
    await vi.advanceTimersByTimeAsync(48)
    expect(vi.getTimerCount()).toBe(0)
  })
})
