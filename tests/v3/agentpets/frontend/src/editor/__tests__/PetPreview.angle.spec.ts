import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import PetPreview from '@/editor/PetPreview.vue'
import type { PetChoice } from '@/editor/api'
import { parseCalibration } from '@/sprites/calibration'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'
import { DEFAULT_PEEK_ANGLES, PEEK_TILT, type PeekEdge } from '@/stage/peek'
import type { YingSettings } from '@/stage/settings'
import legacyJson from '@tests/../fixtures/legacy-codex-v2.json'

async function setup(key = 'builtin-nailong', disabled = false) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  const pet: PetChoice = { key, name: key, description: '', preview: '', mode: 'stage', builtin: key !== 'custom' }
  const api = {
    get: vi.fn().mockImplementation(async (path: string) => {
      if (path.includes('/packs/calibration?')) {
        const id = new URL(path, 'https://example.test').searchParams.get('key')!
        return { success: true, data: { id, calibration: builtinDefaultCalibration(id) } }
      }
      return {
        success: true,
        data: { pack: { ...legacyJson, codex_version: 'v2' }, sheet_src: 'data:image/png;base64,AAAA' },
      }
    }),
    post: vi.fn(),
  }
  const view = mount(PetPreview, {
    props: {
      pet,
      settings: { scale: 1.5, speed: 1, roam: 'floor', movement: 'auto' },
      api,
      pluginId: 'AgentPets',
      initialTab: 'calibration',
      calibration: pet.builtin ? undefined : parseCalibration({}),
      disabled,
      onSettings: (settings: YingSettings) => {
        void view.setProps({ settings })
      },
    },
    global: { plugins: [createVuetify({ components, directives })] },
  })
  await vi.advanceTimersByTimeAsync(64)
  const edge = async (value: PeekEdge | null) => {
    view
      .findAllComponents({ name: 'VSelect' })
      .find(item => item.props('label') === '贴边试览')!
      .vm.$emit('update:modelValue', value)
    await vi.advanceTimersByTimeAsync(48)
  }
  const setAngle = async (value: number) => {
    view.findComponent({ name: 'VSlider' }).vm.$emit('update:modelValue', value)
    await vi.advanceTimersByTimeAsync(32)
  }
  const rotation = () => {
    const artwork = view.get('.agent-pet-ying__artwork').element as HTMLElement
    return Math.abs(Number(artwork.style.transform.match(/rotate\((-?[\d.]+)deg\)/)?.[1]))
  }
  return { view, pet, api, edge, setAngle, rotation }
}

const cases = ['ying', 'builtin-chibiterasu', 'builtin-nailong', 'builtin-kurisu', 'custom'].flatMap(key =>
  (['bottom', 'left', 'right'] as const).map(edge => ({ key, edge })),
)

describe('peek angle drafts and calibration guides', () => {
  it.each(cases)(
    'updates the $key $edge settings draft without directly saving or changing calibration',
    async ({ key, edge }) => {
      const preview = await setup(key)
      try {
        expect(preview.view.find('.ap-preview__angle').exists()).toBe(false)
        await preview.edge(edge)
        expect(preview.rotation()).toBe(DEFAULT_PEEK_ANGLES[edge])
        await preview.setAngle(20)
        expect(preview.rotation()).toBe(20)
        expect(preview.view.emitted('settings')?.at(-1)?.[0]).toMatchObject({ peek_angles: { [edge]: 20 } })
        expect(preview.view.get('output').text()).toBe('20°')
        expect(preview.view.get('.agent-pet-ying').attributes('data-peek-edge')).toBe(edge)
        expect(preview.view.find('.ap-preview__canvas .ap-preview__hint').exists()).toBe(false)
        await preview.view.get('[aria-label="恢复默认偷看角度"]').trigger('click')
        await vi.advanceTimersByTimeAsync(32)
        expect(preview.rotation()).toBe(DEFAULT_PEEK_ANGLES[edge])
        expect(preview.api.post).not.toHaveBeenCalled()
        expect(preview.view.emitted('calibration')).toBeUndefined()
        expect(preview.view.emitted('mappings')).toBeUndefined()
      } finally {
        preview.view.unmount()
      }
    },
  )

  it('keeps edges independent and follows the parent settings when changing pet or plugin', async () => {
    const preview = await setup()
    try {
      await preview.edge('bottom')
      await preview.setAngle(20)
      await preview.edge('left')
      expect(preview.rotation()).toBe(PEEK_TILT)
      await preview.setAngle(15)
      await preview.edge('bottom')
      expect(preview.rotation()).toBe(20)
      await preview.view.setProps({ pluginId: 'Clone1', settings: { scale: 1.5, speed: 1, roam: 'floor' } })
      expect(preview.rotation()).toBe(0)
      await preview.setAngle(25)
      await preview.view.setProps({
        pet: { ...preview.pet, key: 'builtin-kurisu' },
        settings: { scale: 1.5, speed: 1, roam: 'floor' },
      })
      await vi.advanceTimersByTimeAsync(64)
      expect(preview.view.find('.ap-preview__angle').exists()).toBe(false)
      await preview.edge('bottom')
      expect(preview.rotation()).toBe(0)
      await preview.edge(null)
      expect(preview.view.find('.ap-preview__angle').exists()).toBe(false)
      expect(preview.rotation()).toBe(0)
      expect(preview.api.post).not.toHaveBeenCalled()
    } finally {
      preview.view.unmount()
    }
  })

  it('clamps trial values and respects the editor disabled state', async () => {
    const preview = await setup()
    try {
      await preview.edge('bottom')
      expect(preview.view.findComponent({ name: 'VSlider' }).props('thumbLabel')).toBeFalsy()
      for (const [input, expected] of [
        [-10, 0],
        [100, 45],
        [Number.NaN, 0],
      ]) {
        await preview.setAngle(input!)
        expect(preview.rotation()).toBe(expected)
      }
      await preview.setAngle(20)
      await preview.view.setProps({ disabled: true })
      expect(preview.view.findComponent({ name: 'VSlider' }).props('disabled')).toBe(true)
      expect(preview.view.get('[aria-label="恢复默认偷看角度"]').attributes()).toHaveProperty('disabled')
    } finally {
      preview.view.unmount()
    }
  })

  it('hides and restores calibration rings without remounting the image or altering coordinates', async () => {
    const preview = await setup('custom')
    try {
      const frame = preview.view.get('.agent-pet-sprites__frame').element
      const calibration = { ...preview.view.props('calibration') }
      expect(preview.view.findAll('.ap-landmarks__point')).toHaveLength(3)
      const toggle = preview.view
        .findAllComponents({ name: 'VSwitch' })
        .find(item => item.props('label') === '显示校准光圈')!
      toggle.vm.$emit('update:modelValue', false)
      await vi.advanceTimersByTimeAsync(32)
      expect(preview.view.find('.ap-landmarks').exists()).toBe(false)
      expect(preview.view.find('.agent-pet-sprites__viewport--guides').exists()).toBe(false)
      expect(preview.view.get('.agent-pet-sprites__frame').element).toBe(frame)
      toggle.vm.$emit('update:modelValue', true)
      await vi.advanceTimersByTimeAsync(32)
      expect(preview.view.findAll('.ap-landmarks__point')).toHaveLength(3)
      expect(preview.view.get('.agent-pet-sprites__frame').element).toBe(frame)
      expect(preview.view.props('calibration')).toEqual(calibration)
      expect(preview.view.emitted('calibration')).toBeUndefined()
      expect(preview.view.emitted('settings')).toBeUndefined()
      expect(preview.api.post).not.toHaveBeenCalled()
      await preview.view.setProps({
        calibration: parseCalibration({
          left_eye_x: 0.35,
          left_eye_y: 0.3,
          right_eye_x: 0.65,
          right_eye_y: 0.3,
          head_top_x: 0.5,
          head_top_y: 0.05,
        }),
      })
      await preview.edge('bottom')
      expect(preview.view.findAll('.agent-pet-sprites__eye').length).toBeGreaterThan(0)
      toggle.vm.$emit('update:modelValue', false)
      await vi.advanceTimersByTimeAsync(32)
      expect(preview.view.findAll('.agent-pet-sprites__eye')).toHaveLength(0)
      expect(preview.view.get('.agent-pet-ying').attributes('data-peek-edge')).toBe('bottom')
    } finally {
      preview.view.unmount()
    }
  })
})
