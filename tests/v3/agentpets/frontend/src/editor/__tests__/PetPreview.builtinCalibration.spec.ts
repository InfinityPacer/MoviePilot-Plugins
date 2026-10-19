import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import PetPreview from '@/editor/PetPreview.vue'
import CalibrationControls from '@/editor/CalibrationControls.vue'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'
import { BUILTIN_PACKS } from '@/sprites/schema'
import { parseCalibration, type Calibration } from '@/sprites/calibration'

describe('all built-in Pet calibration controls', () => {
  it.each(['ying', ...Object.keys(BUILTIN_PACKS)])(
    'edits and restores %s without saving or changing its mode',
    async key => {
      vi.useFakeTimers()
      const baseline = builtinDefaultCalibration(key)
      const saved = parseCalibration({ ...baseline, offset_x: 0.02 })
      const api = {
        get: vi.fn().mockResolvedValue({ success: true, data: { id: key, calibration: saved } }),
        post: vi.fn(),
      }
      const stage = key !== 'projector-cat'
      const view = mount(PetPreview, {
        props: {
          pet: { key, name: key, description: '', preview: '', builtin: true, mode: stage ? 'stage' : 'renderer' },
          api,
          pluginId: 'Clone1',
          calibration: saved,
          initialTab: 'calibration',
          settings: { scale: 1, speed: 1, roam: 'floor' },
          onCalibration: (calibration: Calibration) => {
            void view.setProps({ calibration })
          },
        },
        global: { plugins: [createVuetify({ components, directives })] },
      })
      try {
        await vi.advanceTimersByTimeAsync(64)
        const controls = view.getComponent(CalibrationControls)
        expect(controls.props('modelValue')).toEqual(saved)
        expect(controls.props('defaultValue')).toEqual(baseline)
        expect(view.find('.ap-preview__error').exists()).toBe(false)
        expect(view.findAllComponents({ name: 'VSelect' }).some(item => item.props('label') === '贴边试览')).toBe(stage)
        if (stage) expect(view.find('.ap-preview__calibration-entry').exists()).toBe(true)
        const frame = () => view.get('.agent-pet-sprites__frame').attributes('style')
        const before = frame()
        const guides = view.findAllComponents({ name: 'VSwitch' }).find(item => item.props('label') === '显示校准光圈')!
        guides.vm.$emit('update:modelValue', false)
        await vi.advanceTimersByTimeAsync(16)
        expect(frame()).toBe(before)
        expect(view.emitted('calibration')).toBeUndefined()
        const reset = controls.findAll('button').find(button => button.text() === '恢复默认')!
        await reset.trigger('click')
        expect(view.emitted('calibration')!.at(-1)).toEqual([baseline])
        expect(api.post).not.toHaveBeenCalled()
      } finally {
        view.unmount()
      }
    },
  )
})
