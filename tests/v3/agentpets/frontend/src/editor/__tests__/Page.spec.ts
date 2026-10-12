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
          name: 'PetPreview',
          props: ['pet', 'settings', 'mappings'],
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
    expect(view.text()).toContain('调整已保存')
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
    expect(view.text()).toContain('调整已保存')
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
  it('keeps mapping drafts per pet, saves only verified mappings and supports undo', async () => {
    const { view, api, click, broadcast } = await setup()
    const selector = view.findComponent({ name: 'VSelect' })
    selector.vm.$emit('update:modelValue', 'kurisu')
    await flushPromises()
    const preview = view.findComponent({ name: 'PetPreview' })
    preview.vm.$emit('pack-ready', { codex_version: 'v2', action_mappings: {} })
    preview.vm.$emit('mappings', { 'stage.think': 'review' })
    await flushPromises()
    expect(api.post).not.toHaveBeenCalled()
    expect(broadcast).not.toHaveBeenCalled()
    selector.vm.$emit('update:modelValue', 'ying')
    await flushPromises()
    expect(preview.props('mappings')).toBeUndefined()
    selector.vm.$emit('update:modelValue', 'kurisu')
    await flushPromises()
    expect(preview.props('mappings')).toEqual({ 'stage.think': 'review' })
    api.post.mockImplementation(async (_path, body) => ({
      success: true,
      data: { id: 'kurisu', mappings: (body as { mappings: unknown }).mappings },
    }))
    await click('保存调整')
    expect(api.post.mock.calls).toEqual([
      [
        'plugin/AgentPets/packs/mappings',
        { id: 'kurisu', mappings: { 'stage.think': 'review' }, expected_mappings: {} },
      ],
    ])
    expect(broadcast).toHaveBeenCalledWith('agentpets.pack.updated', { key: 'kurisu' })
    preview.vm.$emit('mappings', {})
    await flushPromises()
    await click('撤销')
    expect(preview.props('mappings')).toEqual({ 'stage.think': 'review' })
  })

  it('keeps a failed mapping draft and requires discarding it after an external update', async () => {
    const { view, api, click, broadcast } = await setup()
    view.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 'kurisu')
    await flushPromises()
    const preview = () => view.findComponent({ name: 'PetPreview' })
    preview().vm.$emit('pack-ready', { codex_version: 'v2', action_mappings: {} })
    preview().vm.$emit('mappings', { 'stage.think': 'review' })
    await flushPromises()
    api.post.mockResolvedValue({ success: false, message: '动作映射已在其他页面更改' })
    await click('保存调整')
    expect(view.text()).toContain('动作映射已在其他页面更改')
    expect(preview().props('mappings')).toEqual({ 'stage.think': 'review' })
    expect(broadcast).not.toHaveBeenCalled()
    await view.find('[aria-label="刷新形象列表"]').trigger('click')
    await flushPromises()
    preview().vm.$emit('pack-ready', { codex_version: 'v2', action_mappings: { 'stage.think': 'waving' } })
    await flushPromises()
    expect(preview().props('mappings')).toEqual({ 'stage.think': 'review' })
    expect(view.text()).toContain('动作映射已在其他页面更改')
    expect(
      view
        .findAll('button')
        .find(button => button.text() === '保存调整')!
        .attributes('disabled'),
    ).toBeDefined()
    expect(api.post).toHaveBeenCalledTimes(1)
    await click('撤销')
    expect(preview().props('mappings')).toEqual({ 'stage.think': 'waving' })
    preview().vm.$emit('mappings', { 'stage.think': 'running' })
    await flushPromises()
    await click('保存调整')
    expect(api.post.mock.calls.at(-1)?.[1]).toMatchObject({ expected_mappings: { 'stage.think': 'waving' } })
  })

  it.each([{ 'stage.wave': 'jumping' }, { 'stage.think': 'waving' }])(
    'keeps the old baseline and reports conflicting changes after reselecting a Pet: %j',
    async latest => {
      const { view, api, click } = await setup()
      const selector = view.findComponent({ name: 'VSelect' })
      const preview = () => view.findComponent({ name: 'PetPreview' })
      selector.vm.$emit('update:modelValue', 'kurisu')
      await flushPromises()
      preview().vm.$emit('pack-ready', { codex_version: 'v2', action_mappings: {} })
      preview().vm.$emit('mappings', { 'stage.think': 'review' })
      await flushPromises()
      selector.vm.$emit('update:modelValue', 'ying')
      await flushPromises()
      selector.vm.$emit('update:modelValue', 'kurisu')
      await flushPromises()
      preview().vm.$emit('pack-ready', { codex_version: 'v2', action_mappings: latest })
      await flushPromises()
      expect(preview().props('mappings')).toEqual({ 'stage.think': 'review' })
      expect(view.text()).toContain('Kurisu 的动作映射已在其他页面更改')
      expect(
        view
          .findAll('button')
          .find(button => button.text() === '保存调整')!
          .attributes('disabled'),
      ).toBeDefined()
      expect(api.post).not.toHaveBeenCalled()
      preview().vm.$emit('mappings', {})
      await flushPromises()
      expect(
        view
          .findAll('button')
          .find(button => button.text() === '撤销')!
          .attributes('disabled'),
      ).toBeUndefined()
      await click('撤销')
      expect(preview().props('mappings')).toEqual(latest)
      expect(view.text()).not.toContain('动作映射已在其他页面更改')
      preview().vm.$emit('mappings', { ...latest, 'stage.busy': 'running' })
      await flushPromises()
      api.post.mockImplementation(async (_path, body) => ({
        success: true,
        data: { id: 'kurisu', mappings: (body as { mappings: unknown }).mappings },
      }))
      await click('保存调整')
      expect(api.post.mock.calls[0][1]).toEqual({
        id: 'kurisu',
        mappings: { ...latest, 'stage.busy': 'running' },
        expected_mappings: latest,
      })
    },
  )
})
