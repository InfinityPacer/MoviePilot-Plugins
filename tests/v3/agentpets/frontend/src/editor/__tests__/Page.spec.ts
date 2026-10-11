import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import Page from '@/components/Page.vue'
import { createMockHost } from '@/dev/mockHost'
import { AGENT_HOST_KEY } from '@/host'
import StageSettings from '@/stage/StageSettings.vue'

const cleanups: Array<() => void> = []
afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup())
  vi.clearAllMocks()
})

async function setup() {
  let saved = { scale: 1, speed: 1, roam: 'floor' }
  let defaultId = 'AgentPets:ying'
  const api = {
    get: vi.fn().mockImplementation(async (path: string) => {
      if (path.endsWith('/editor'))
        return {
          success: true,
          data: {
            enabled: true,
            settings: { ...saved },
            pets: [
              {
                key: 'ying',
                name: '小映',
                description: '',
                mode: 'stage',
                preview: '',
                builtin: true,
              },
              {
                key: 'kurisu',
                name: 'Kurisu',
                description: '',
                mode: 'stage',
                preview: '',
                builtin: false,
              },
            ],
          },
        }
      if (path === 'plugin/agent_pets')
        return [
          { plugin_id: 'AgentPets', key: 'ying' },
          { plugin_id: 'AgentPets', key: 'kurisu' },
        ]
      if (path.startsWith('system/settings'))
        return {
          success: true,
          data: {
            settings: [{ setting_key: 'AI_AGENT_PET', value: defaultId }],
          },
        }
      return { success: true, data: { value: null } }
    }),
    post: vi.fn().mockImplementation(async (path: string, body: unknown) => {
      if (path.endsWith('/settings')) saved = body as typeof saved
      if (path === 'system/env') defaultId = (body as { AI_AGENT_PET: string }).AI_AGENT_PET
      return { success: true, data: path.endsWith('/settings') ? saved : null }
    }),
  }
  const host = createMockHost('AgentPets')
  const broadcast = vi.spyOn(host, 'emit')
  const view = mount(Page, {
    props: { api, pluginId: 'AgentPets' },
    global: {
      plugins: [createVuetify({ components, directives })],
      provide: { [AGENT_HOST_KEY]: host },
      stubs: {
        PetPreview: {
          props: ['pet', 'settings'],
          template: '<div class="preview-stub" :data-scale="settings.scale" :data-pet="pet.key" />',
        },
      },
    },
  })
  cleanups.push(() => {
    view.unmount()
    host.dispose()
  })
  await flushPromises()
  const change = async () => {
    view.findComponent(StageSettings).vm.$emit('update:modelValue', { scale: 1.3, speed: 1.5, roam: 'free' })
    await flushPromises()
  }
  const click = async (text: string) => {
    await view
      .findAll('button')
      .find(button => button.text() === text)!
      .trigger('click')
    await flushPromises()
  }
  return { view, api, host, broadcast, change, click }
}

describe('Pet workspace', () => {
  it('previews a draft without API writes or live broadcasts, and supports undo', async () => {
    const { view, api, broadcast, change, click } = await setup()
    await change()
    expect(view.find('.preview-stub').attributes('data-scale')).toBe('1.3')
    expect(api.post).not.toHaveBeenCalled()
    expect(broadcast).not.toHaveBeenCalled()
    expect(view.text()).toContain('未保存')
    await click('撤销')
    expect(view.find('.preview-stub').attributes('data-scale')).toBe('1')
  })

  it('preserves unsaved adjustments on refresh', async () => {
    const { view, change } = await setup()
    await change()
    await view.find('[aria-label="刷新形象列表"]').trigger('click')
    await flushPromises()
    expect(view.find('.preview-stub').attributes('data-scale')).toBe('1.3')
    expect(view.text()).toContain('未保存')
  })

  it('only publishes verified saved parameters to the active pet', async () => {
    const { api, broadcast, change, click, view } = await setup()
    view.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 'kurisu')
    await change()
    await click('保存调整')
    expect(api.post.mock.calls).toEqual([['plugin/AgentPets/settings', { scale: 1.3, speed: 1.5, roam: 'free' }]])
    expect(broadcast).toHaveBeenCalledWith('agentpets.settings', {
      scale: 1.3,
      speed: 1.5,
      roam: 'free',
    })
    expect(view.text()).toContain('活动调整已保存')
  })

  it('keeps the draft and avoids broadcasts when persistence fails', async () => {
    const { api, broadcast, change, click, view } = await setup()
    await change()
    api.post.mockResolvedValue({ success: false, message: '保存失败' })
    await click('保存调整')
    expect(view.text()).toContain('保存失败')
    expect(view.text()).toContain('未保存')
    expect(broadcast).not.toHaveBeenCalled()
  })

  it('saves activity settings even when the system default cannot be read', async () => {
    const { api, view, change, click } = await setup()
    const read = api.get.getMockImplementation()!
    api.get.mockImplementation((path: string) =>
      path.startsWith('system/settings') ? Promise.reject(new Error('denied')) : read(path),
    )
    await view.find('[aria-label="刷新形象列表"]').trigger('click')
    await flushPromises()
    expect(view.text()).toContain('仍可预览和保存调整')
    await change()
    await click('保存调整')
    expect(api.post.mock.calls).toEqual([['plugin/AgentPets/settings', { scale: 1.3, speed: 1.5, roam: 'free' }]])
    expect(view.text()).toContain('活动调整已保存')
  })

  it('does not broadcast a save result after the page has closed', async () => {
    const { api, view, broadcast, change, click } = await setup()
    await change()
    let resolve!: (value: unknown) => void
    api.post.mockImplementation(
      () =>
        new Promise(done => {
          resolve = done
        }),
    )
    await click('保存调整')
    view.unmount()
    resolve({ success: true, data: { scale: 1.3, speed: 1.5, roam: 'free' } })
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(broadcast).not.toHaveBeenCalled()
  })
})
