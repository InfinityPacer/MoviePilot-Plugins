import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import StageSettings from '@/stage/StageSettings.vue'
import { DEFAULT_SETTINGS, type YingSettings } from '@/stage/settings'

const cleanups: Array<() => void> = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

function setup(modelValue: YingSettings = { ...DEFAULT_SETTINGS }, petKey = 'builtin-kurisu', disabled = false) {
  const view = mount(StageSettings, {
    props: { modelValue, petKey, disabled, livePreview: true },
    global: { plugins: [createVuetify({ components, directives })] },
  })
  cleanups.push(() => view.unmount())
  const select = (label: string) =>
    view.findAllComponents({ name: 'VSelect' }).find(control => control.props('label') === label)!
  return { view, select }
}

describe('per-Pet dialogue controls', () => {
  it.each(['ying', 'builtin-kurisu'] as const)(
    'shows effective defaults for %s without creating a stored preference',
    key => {
      const value = { ...DEFAULT_SETTINGS }
      const { view, select } = setup(value, key)
      expect(select('话量').props('modelValue')).toBe(key === 'ying' ? 'interaction' : 'off')
      expect(select('语气').props('modelValue')).toBe(key === 'ying' ? 'ying' : 'neutral')
      expect(value).not.toHaveProperty('dialogue')
      expect(view.emitted('update:modelValue')).toBeUndefined()
    },
  )

  it.each(['ying', 'builtin-kurisu', 'imported-pet'])('offers the same four named voices for %s', key => {
    const { select } = setup({ ...DEFAULT_SETTINGS }, key)
    expect(select('语气').props('items')).toEqual([
      { title: '小映', value: 'ying' },
      { title: '自然', value: 'neutral' },
      { title: '软萌', value: 'lively' },
      { title: '傲娇', value: 'wry' },
    ])
  })

  it.each(['ying', 'builtin-kurisu'])(
    'displays the old default for %s by its effective voice without migrating it',
    key => {
      const value: YingSettings = { ...DEFAULT_SETTINGS, dialogue: { mode: 'interaction', voice: 'default' } }
      const { view, select } = setup(value, key)
      expect(select('语气').props('modelValue')).toBe(key === 'ying' ? 'ying' : 'neutral')
      expect(value.dialogue).toEqual({ mode: 'interaction', voice: 'default' })
      expect(view.emitted('update:modelValue')).toBeUndefined()
    },
  )

  it('emits the explicit Ying voice for another Pet without changing activity settings', () => {
    const value: YingSettings = { ...DEFAULT_SETTINGS, dialogue: { mode: 'interaction', voice: 'neutral' } }
    const { view, select } = setup(value)
    select('语气').vm.$emit('update:modelValue', 'ying')
    expect(view.emitted<[YingSettings]>('update:modelValue')![0][0]).toEqual({
      ...value,
      dialogue: { mode: 'interaction', voice: 'ying' },
    })
    expect(value.dialogue!.voice).toBe('neutral')
  })

  it('updates only dialogue through compact controls and keeps activity independent', async () => {
    const value: YingSettings = {
      ...DEFAULT_SETTINGS,
      scale: 1.3,
      speed: 0.8,
      peek_angles: { bottom: 20, left: 35, right: 35 },
    }
    const { view, select } = setup(value)
    expect(select('语气').props('disabled')).toBe(true)
    select('话量').vm.$emit('update:modelValue', 'occasional')
    const first = view.emitted<[YingSettings]>('update:modelValue')![0][0]
    expect(first).toEqual({ ...value, dialogue: { mode: 'occasional', voice: 'neutral' } })
    await view.setProps({ modelValue: first })
    select('语气').vm.$emit('update:modelValue', 'wry')
    const second = view.emitted<[YingSettings]>('update:modelValue')![1][0]
    expect(second).toEqual({ ...value, dialogue: { mode: 'occasional', voice: 'wry' } })
    expect(value).not.toHaveProperty('dialogue')
    expect(select('话量').props()).toMatchObject({ variant: 'outlined', density: 'compact' })
    expect(view.text()).toContain('不影响自主活动或系统通知')
    expect(view.text()).toContain('预览区不说话')
  })

  it('disables both controls while saving and never chooses a character voice on its own', () => {
    const { select } = setup({ ...DEFAULT_SETTINGS, dialogue: { mode: 'interaction', voice: 'lively' } }, 'ying', true)
    expect(select('话量').props('disabled')).toBe(true)
    expect(select('语气').props('disabled')).toBe(true)
    expect(select('语气').props('modelValue')).toBe('lively')
  })

  it('preserves saved dialogue and angles when restoring activity defaults', async () => {
    const value: YingSettings = {
      scale: 0.7,
      speed: 1.7,
      roam: 'free',
      movement: 'fixed',
      dialogue: { mode: 'off', voice: 'wry' },
      peek_angles: { bottom: 20, left: 35, right: 35 },
    }
    const { view } = setup(value)
    await view
      .findAll('button')
      .find(button => button.text() === '恢复默认')!
      .trigger('click')
    expect(view.emitted<[YingSettings]>('update:modelValue')![0][0]).toEqual({
      ...DEFAULT_SETTINGS,
      dialogue: value.dialogue,
      peek_angles: value.peek_angles,
    })
  })
})
