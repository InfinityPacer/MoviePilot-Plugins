import { fireEvent, render } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import PetPreview from '@/editor/PetPreview.vue'
import type { PetChoice } from '@/editor/api'
import legacyJson from '@tests/../fixtures/legacy-codex-v2.json'

async function setup() {
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
        right: 700,
        bottom: 500,
        width: 500,
        height: 400,
        toJSON: () => ({}),
      } as DOMRect
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
    get: vi.fn().mockImplementation(async () => ({
      success: true,
      data: {
        pack: { ...legacyJson, codex_version: 'v2' },
        sheet_src: 'data:image/png;base64,AAAA',
      },
    })),
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

describe('contained live Pet preview', () => {
  it('renders the selected Codex pet inside the canvas and responds to scale and roam drafts without saving', async () => {
    const { view, api } = await setup()
    const canvas = view.container.querySelector('.ap-preview__canvas')!
    const character = canvas.querySelector('.agent-pet-ying__character') as HTMLElement
    expect(character.style.height).toBe('120px')
    expect(canvas.querySelector('.agent-pet-ying--contained')).not.toBeNull()
    expect(api.get.mock.calls).toEqual([['plugin/Clone1/pack?key=kurisu']])
    await view.rerender({ settings: { scale: 1.5, speed: 2, roam: 'free' } })
    await vi.advanceTimersByTimeAsync(32)
    expect(character.style.height).toBe('180px')
    expect(canvas.querySelector('.agent-pet-ying')?.getAttribute('data-roam')).toBe('free')
    expect(api.post).not.toHaveBeenCalled()
    view.unmount()
    await vi.advanceTimersByTimeAsync(32)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('resets a dragged preview position while preserving its activity draft', async () => {
    const { view, api } = await setup()
    await view.rerender({ settings: { scale: 1, speed: 1.5, roam: 'free' } })
    await vi.advanceTimersByTimeAsync(32)
    const character = view.container.querySelector('.agent-pet-ying__character') as HTMLElement
    const initialPosition = character.style.transform
    const pointer = (type: string, clientX: number, clientY: number) => {
      const event = new MouseEvent(type, { bubbles: true, button: 0, clientX, clientY })
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
    expect(view.getByText('此 Pet 加载失败，请点击右上角重置重试。')).toBeInTheDocument()
    expect(view.container.querySelector('[data-pack="projector-cat"]')).toBeNull()
    expect(view.emitted('error').at(-1)).toEqual([true])
  })
})
