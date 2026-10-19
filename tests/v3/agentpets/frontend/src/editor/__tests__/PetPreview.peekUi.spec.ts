import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import PetPreview from '@/editor/PetPreview.vue'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'

const edges = [
  { edge: 'bottom', label: '底边偷看试览' },
  { edge: 'left', label: '左下侧边试览' },
  { edge: 'right', label: '右下侧边试览' },
]
const cases = ['builtin-chibiterasu', 'builtin-nailong', 'builtin-kurisu'].flatMap(key =>
  edges.map(edge => ({ key, ...edge })),
)

describe('effective peek preview feedback', () => {
  it.each(cases)(
    'keeps the $key $edge eye unobstructed and labels the displayed frame',
    async ({ key, edge, label }) => {
      vi.useFakeTimers()
      vi.spyOn(Math, 'random').mockReturnValue(0.5)
      const api = {
        get: vi
          .fn()
          .mockResolvedValue({ success: true, data: { id: key, calibration: builtinDefaultCalibration(key) } }),
        post: vi.fn(),
      }
      const view = mount(PetPreview, {
        props: {
          pet: { key, name: key, description: '', preview: '', mode: 'stage', builtin: true },
          settings: { scale: 1.5, speed: 1, roam: 'floor' },
          api,
          pluginId: 'AgentPets',
        },
        global: { plugins: [createVuetify({ components, directives })] },
      })
      try {
        await vi.advanceTimersByTimeAsync(64)
        await view
          .findAll('button')
          .find(button => button.text() === '睡眠 · sleep')!
          .trigger('click')
        await vi.advanceTimersByTimeAsync(32)
        expect(view.get('[role="status"]').text()).toBe('正在播放：睡眠 · sleep')
        const tab = (name: string) => view.findAll('[role="tab"]').find(item => item.text() === name)!
        await tab('校准').trigger('click')
        const select = view.findAllComponents({ name: 'VSelect' }).find(item => item.props('label') === '贴边试览')!
        select.vm.$emit('update:modelValue', edge)
        await vi.advanceTimersByTimeAsync(48)

        const status = `${label} · 锁定偷看首帧`
        expect(view.get('.agent-pet-ying').attributes('data-peek-edge')).toBe(edge)
        expect(view.get('.agent-pet-sprites').attributes('data-action')).toBe('peek')
        expect(view.find('.ap-preview__canvas .ap-preview__hint').exists()).toBe(false)
        expect(view.get('[role="status"]').text()).toBe(status)

        await view.get('[aria-label="暂停预览"]').trigger('click')
        expect(view.get('[role="status"]').text()).toBe(status)
        await view.get('[aria-label="播放预览"]').trigger('click')
        expect(view.get('[role="status"]').text()).toBe(status)

        await tab('动作试播').trigger('click')
        await vi.advanceTimersByTimeAsync(32)
        expect(view.get('.agent-pet-sprites').attributes('data-action')).toBe('sleep')
        expect(view.find('.ap-preview__canvas .ap-preview__hint').exists()).toBe(true)
        expect(view.get('[role="status"]').text()).toBe('正在播放：睡眠 · sleep')

        await tab('校准').trigger('click')
        expect(view.get('[role="status"]').text()).toBe(status)
        select.vm.$emit('update:modelValue', null)
        await vi.advanceTimersByTimeAsync(32)
        expect(view.find('.ap-preview__canvas .ap-preview__hint').exists()).toBe(true)
        expect(view.get('[role="status"]').text()).toBe('正在播放：睡眠 · sleep')
        expect(api.post).not.toHaveBeenCalled()
        expect(view.emitted('calibration')).toBeUndefined()
        expect(view.emitted('mappings')).toBeUndefined()
      } finally {
        view.unmount()
      }
    },
  )
})
