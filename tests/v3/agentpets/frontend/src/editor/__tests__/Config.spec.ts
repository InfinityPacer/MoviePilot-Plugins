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
  let persisted = { ...initial }
  const api = {
    get: vi
      .fn()
      .mockImplementation(async (path: string) =>
        path.endsWith('/editor')
          ? { success: true, data: { enabled: persisted.enabled, settings: persisted, pets: [] } }
          : { ...persisted },
      ),
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
  const toggle = async () => {
    await view
      .findAll('.ap-nav .v-list-item')
      .find(item => item.text().includes('基础设置'))!
      .trigger('click')
    view.findComponent({ name: 'VSwitch' }).vm.$emit('update:modelValue', false)
    await flushPromises()
  }
  const save = async () => {
    await view
      .findAll('button')
      .find(button => button.text() === '保存配置')!
      .trigger('click')
    await flushPromises()
  }
  return {
    view,
    initial,
    api,
    toggle,
    save,
    setPersisted: (value: typeof initial) => {
      persisted = value
    },
  }
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
    await flushPromises()
    expect(view.emitted('save')?.[0]).toEqual([{ ...initial, enabled: false }])
    expect(view.emitted('close')).toBeUndefined()
  })

  it('reads fresh complete configuration before saving only the enable switch', async () => {
    const { view, initial, api, toggle, save, setPersisted } = await setup()
    const latest = { ...initial, scale: 1.6, speed: 1.8, roam: 'surfaces', future: { keep: false } }
    setPersisted(latest)
    await toggle()
    await save()
    expect(api.get).toHaveBeenCalledWith('plugin/Clone1')
    expect(view.emitted('save')?.[0]).toEqual([{ ...latest, enabled: false }])
  })

  it('does not emit stale configuration when the fresh read fails', async () => {
    const { view, api, toggle, save } = await setup()
    await toggle()
    api.get.mockRejectedValue(new Error('读取失败'))
    await save()
    expect(view.emitted('save')).toBeUndefined()
    expect(view.text()).toContain('读取失败')
    expect(view.text()).toContain('1 项未保存')
  })

  it('reports a changed enable state instead of silently overwriting another page', async () => {
    const { view, initial, toggle, save, setPersisted } = await setup()
    await toggle()
    setPersisted({ ...initial, enabled: false })
    await save()
    expect(view.emitted('save')).toBeUndefined()
    expect(view.text()).toContain('启用状态已在其他页面更改')
  })

  it('does not emit a deferred read result after the configuration dialog closes', async () => {
    const { view, initial, api, toggle, save } = await setup()
    await toggle()
    let resolve!: (value: typeof initial) => void
    api.get.mockImplementation(
      () =>
        new Promise(done => {
          resolve = done
        }),
    )
    await save()
    view.unmount()
    resolve(initial)
    await flushPromises()
    expect(view.emitted('save')).toBeUndefined()
  })
})
