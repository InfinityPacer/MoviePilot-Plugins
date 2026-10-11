import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import Config from '@/components/Config.vue'

const cleanups: Array<() => void> = []
afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup())
})

async function setup() {
  const initial = {
    enabled: true,
    scale: 1.3,
    speed: 1.2,
    roam: 'free',
    future: { keep: true },
  }
  const api = {
    get: vi.fn().mockResolvedValue({
      success: true,
      data: { enabled: true, settings: initial, pets: [] },
    }),
    post: vi.fn(),
  }
  const view = mount(Config, {
    props: { initialConfig: initial, api, pluginId: 'Clone1' },
    global: {
      plugins: [createVuetify({ components, directives })],
      stubs: { PackManager: true },
    },
  })
  cleanups.push(() => view.unmount())
  await flushPromises()
  return { view, initial }
}

describe('Pet settings layout', () => {
  it('starts on overview and keeps activity edits out of the configuration form', async () => {
    const { view } = await setup()
    expect(view.find('.ap-nav .v-list-item--active').text()).toContain('运行总览')
    expect(view.findAll('input[type="range"]')).toHaveLength(0)
    expect(view.findComponent({ name: 'PackManager' }).exists()).toBe(false)
  })

  it('saves the enable draft while preserving all other configuration', async () => {
    const { view, initial } = await setup()
    await view
      .findAll('.ap-nav .v-list-item')
      .find(item => item.text().includes('基础设置'))!
      .trigger('click')
    view.findComponent({ name: 'VSwitch' }).vm.$emit('update:modelValue', false)
    await flushPromises()
    expect(initial.enabled).toBe(true)
    expect(view.text()).toContain('1 项未保存')
    await view
      .findAll('button')
      .find(button => button.text() === '保存配置')!
      .trigger('click')
    expect(view.emitted('save')?.[0]).toEqual([{ ...initial, enabled: false }])
    expect(view.emitted('close')).toBeUndefined()
  })
})
