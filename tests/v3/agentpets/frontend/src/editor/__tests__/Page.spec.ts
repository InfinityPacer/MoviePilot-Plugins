import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import Page from '@/components/Page.vue'
import { createMockHost } from '@/dev/mockHost'
import { AGENT_HOST_KEY } from '@/host'
import StageSettings from '@/stage/StageSettings.vue'
import { appearanceOf, type PetAppearance, type YingSettings } from '@/stage/settings'
import { normalizePeekAngles } from '@/stage/peek'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'
import { parseCalibration, type Calibration } from '@/sprites/calibration'

const cleanups: Array<() => void> = []

it.each([false, true])('notifies once per pack after a multi-field save (partial failure: %s)', async failure => {
  const { view, api, click, broadcast } = await setup()
  view.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 'kurisu')
  await flushPromises()
  const preview = view.findComponent({ name: 'PetPreview' })
  preview.vm.$emit('pack-ready', { id: 'kurisu', codex_version: 'v2', action_mappings: {}, calibration: {} })
  preview.vm.$emit('mappings', { 'stage.think': 'review' })
  preview.vm.$emit('calibration', { ...parseCalibration(undefined), left: 0.1 })
  api.post.mockImplementation(async (path, body) => {
    const data = body as { mappings: unknown; calibration: unknown }
    if (failure && path.endsWith('/calibration')) return { success: false, data: null }
    return { success: true, data: { id: 'kurisu', mappings: data.mappings, calibration: data.calibration } }
  })
  await flushPromises()
  await click('保存调整')
  expect(api.post).toHaveBeenCalledTimes(2)
  expect(broadcast).toHaveBeenCalledTimes(1)
  expect(broadcast).toHaveBeenCalledWith('agentpets.pack.updated', { key: 'kurisu' })
})
afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup())
  vi.clearAllMocks()
})

async function setup(props: { show_switch?: boolean } = {}, builtinKey = 'ying') {
  let saved = { scale: 1, speed: 1, roam: 'floor', movement: 'auto' }
  const profiles: Record<string, PetAppearance> = {}
  let defaultId = `AgentPets:${builtinKey}`
  const api = {
    get: vi.fn().mockImplementation(async (path: string) => {
      if (path.endsWith('/editor'))
        return {
          success: true,
          data: {
            enabled: true,
            settings: { ...saved },
            pet_settings: structuredClone(profiles),
            pets: [
              {
                key: builtinKey,
                name: '小映',
                description: '',
                mode: builtinKey === 'projector-cat' ? 'renderer' : 'stage',
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
          { plugin_id: 'AgentPets', key: builtinKey },
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
      const value = body as YingSettings & { key: string }
      if (path.endsWith('/settings/shared')) {
        saved = { ...saved, roam: value.roam, movement: value.movement ?? 'auto' }
        return { success: true, data: { roam: saved.roam, movement: saved.movement } }
      }
      if (path.endsWith('/settings/pet')) {
        profiles[value.key] = appearanceOf(value)
        return { success: true, data: { key: value.key, ...profiles[value.key] } }
      }
      if (path === 'system/env') defaultId = (body as { AI_AGENT_PET: string }).AI_AGENT_PET
      return { success: true, data: path.endsWith('/settings') ? saved : null }
    }),
  }
  const host = createMockHost('AgentPets')
  const broadcast = vi.spyOn(host, 'emit')
  const view = mount(Page, {
    props: { api, pluginId: 'AgentPets', ...props },
    global: {
      plugins: [createVuetify({ components, directives })],
      provide: { [AGENT_HOST_KEY]: host },
      stubs: {
        PetPreview: {
          name: 'PetPreview',
          props: ['pet', 'settings', 'mappings', 'calibration'],
          template:
            '<div class="preview-stub" :data-scale="settings.scale" :data-pet="pet.key"><slot name="activity" /></div>',
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
    view
      .findComponent(StageSettings)
      .vm.$emit('update:modelValue', { scale: 1.3, speed: 1.5, roam: 'free', movement: 'auto' })
    await flushPromises()
  }
  const click = async (text: string) => {
    await view
      .findAll('button')
      .find(button => button.text() === text)!
      .trigger('click')
    await flushPromises()
  }
  return { view, api, host, broadcast, change, click, profiles }
}

describe('Pet workspace', () => {
  it('saves angle-only edits, refreshes them, and restores defaults without leaking to another pet', async () => {
    const { view, api, click, profiles, broadcast } = await setup()
    const angles = { bottom: 20, left: 15, right: 35 }
    const preview = view.findComponent({ name: 'PetPreview' })
    preview.vm.$emit('settings', { ...preview.props('settings'), peek_angles: angles })
    await flushPromises()
    expect(view.text()).toContain('未保存')
    expect(view.text()).toContain('1 只 Pet 的独立设置')
    expect(api.post).not.toHaveBeenCalled()
    await click('撤销')
    expect(preview.props('settings').peek_angles).toBeUndefined()
    preview.vm.$emit('settings', { ...preview.props('settings'), peek_angles: angles })
    await flushPromises()
    await click('保存调整')
    expect(profiles.ying.peek_angles).toEqual(angles)
    expect(profiles.kurisu).toBeUndefined()
    expect(api.post.mock.calls.map(([path]) => path)).toEqual(['plugin/AgentPets/settings/pet'])
    await view.get('[aria-label="刷新形象列表"]').trigger('click')
    await flushPromises()
    const refreshed = view.findComponent({ name: 'PetPreview' })
    expect(refreshed.props('settings').peek_angles).toEqual(angles)
    refreshed.vm.$emit('settings', { ...refreshed.props('settings'), peek_angles: normalizePeekAngles(undefined) })
    await flushPromises()
    await click('保存调整')
    expect(profiles.ying.peek_angles).toBeUndefined()
    expect(broadcast).toHaveBeenLastCalledWith('agentpets.settings', {
      key: 'ying',
      scale: 1,
      speed: 1,
      peek_angles: normalizePeekAngles(undefined),
    })
  })
  it('keeps configuration switching when the host supports it', async () => {
    const { view, api } = await setup()
    expect(view.attributes()).toHaveProperty('data-agentpets-editor')
    await view.get('[aria-label="打开插件配置"]').trigger('click')
    expect(view.emitted('switch')).toHaveLength(1)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('does not offer dead configuration links in a quick-access host', async () => {
    const { view, api } = await setup({ show_switch: false })
    expect(view.find('[aria-label="打开插件配置"]').exists()).toBe(false)
    expect(view.attributes('show_switch')).toBeUndefined()
    api.get.mockResolvedValue({
      success: true,
      data: { enabled: true, settings: { scale: 1, speed: 1, roam: 'floor' }, pets: [] },
    })
    await view.get('[aria-label="刷新形象列表"]').trigger('click')
    await flushPromises()
    expect(view.text()).toContain('请从「插件 → 助手形象 → 设置」打开素材管理。')
    expect(view.findAll('button').some(button => button.text() === '前往素材管理')).toBe(false)
    expect(view.emitted('switch')).toBeUndefined()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('saves two appearance drafts by key without changing shared activity or the legacy defaults', async () => {
    const { view, api, click, profiles } = await setup()
    const selector = view.findComponent({ name: 'VSelect' })
    const update = async (scale: number, speed: number) => {
      view.findComponent(StageSettings).vm.$emit('update:modelValue', { scale, speed, roam: 'floor', movement: 'auto' })
      await flushPromises()
    }
    await update(0.7, 1.4)
    selector.vm.$emit('update:modelValue', 'kurisu')
    await flushPromises()
    expect(view.findComponent(StageSettings).props('modelValue')).toMatchObject({ scale: 1, speed: 1 })
    await update(1.5, 0.6)
    selector.vm.$emit('update:modelValue', 'ying')
    await flushPromises()
    expect(view.findComponent(StageSettings).props('modelValue')).toMatchObject({ scale: 0.7, speed: 1.4 })
    await click('保存调整')
    expect(api.post.mock.calls.map(([path]) => path)).toEqual([
      'plugin/AgentPets/settings/pet',
      'plugin/AgentPets/settings/pet',
    ])
    expect(profiles).toEqual({ ying: { scale: 0.7, speed: 1.4 }, kurisu: { scale: 1.5, speed: 0.6 } })
    await view.find('[aria-label="刷新形象列表"]').trigger('click')
    await flushPromises()
    selector.vm.$emit('update:modelValue', 'kurisu')
    await flushPromises()
    expect(view.findComponent(StageSettings).props('modelValue')).toMatchObject({
      scale: 1.5,
      speed: 0.6,
      roam: 'floor',
    })
  })

  it('does not resend an already saved pet when a later pet fails', async () => {
    const { view, api, click, profiles } = await setup()
    const selector = view.findComponent({ name: 'VSelect' })
    for (const key of ['ying', 'kurisu']) {
      selector.vm.$emit('update:modelValue', key)
      await flushPromises()
      view
        .findComponent(StageSettings)
        .vm.$emit('update:modelValue', { scale: 0.7, speed: 1, roam: 'floor', movement: 'auto' })
      await flushPromises()
    }
    const persist = api.post.getMockImplementation()!
    api.post.mockImplementation(async (path, body) =>
      (body as { key: string }).key === 'kurisu' ? { success: false, message: '保存失败' } : persist(path, body),
    )
    await click('保存调整')
    expect(profiles).toEqual({ ying: { scale: 0.7, speed: 1 } })
    expect(view.text()).toContain('未保存')
    api.post.mockImplementation(persist)
    api.post.mockClear()
    await click('保存调整')
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post.mock.calls[0][1]).toMatchObject({ key: 'kurisu' })
  })

  it('blocks a stale pet draft after refresh until the user explicitly discards it', async () => {
    const { view, click, profiles } = await setup()
    view
      .findComponent(StageSettings)
      .vm.$emit('update:modelValue', { scale: 0.7, speed: 1, roam: 'floor', movement: 'auto' })
    await flushPromises()
    profiles.ying = { scale: 1.4, speed: 1.3 }
    await view.find('[aria-label="刷新形象列表"]').trigger('click')
    await flushPromises()
    expect(view.findComponent(StageSettings).props('modelValue').scale).toBe(0.7)
    expect(
      view
        .findAll('button')
        .find(button => button.text() === '保存调整')!
        .attributes('disabled'),
    ).toBeDefined()
    await click('撤销')
    expect(view.findComponent(StageSettings).props('modelValue')).toMatchObject({ scale: 1.4, speed: 1.3 })
  })

  it('keeps calibration drafts isolated, saves verified values and detects external changes', async () => {
    const { view, api, broadcast, click } = await setup()
    view.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 'kurisu')
    await flushPromises()
    const preview = view.findComponent({ name: 'PetPreview' })
    preview.vm.$emit('pack-ready', { id: 'kurisu', calibration: {} })
    await flushPromises()
    const baseline = { ...preview.props('calibration') }
    const adjusted = { ...baseline, left: 0.1, right: 0.9 }
    preview.vm.$emit('calibration', adjusted)
    await flushPromises()
    expect(api.post).not.toHaveBeenCalled()
    expect(broadcast).not.toHaveBeenCalled()
    api.post.mockImplementation(async (_path, value) => ({
      success: true,
      data: { id: 'kurisu', calibration: value.calibration },
    }))
    await click('保存调整')
    expect(api.post).toHaveBeenCalledWith('plugin/AgentPets/packs/calibration', {
      id: 'kurisu',
      calibration: adjusted,
      expected_calibration: baseline,
    })
    expect(broadcast).toHaveBeenCalledWith('agentpets.pack.updated', { key: 'kurisu' })
    preview.vm.$emit('calibration', { ...adjusted, top: 0.1 })
    preview.vm.$emit('pack-ready', { id: 'kurisu', calibration: { ...adjusted, left: 0.2 } })
    await flushPromises()
    expect(view.text()).toContain('素材调整已在其他页面更改')
    expect(preview.props('calibration').top).toBe(0.1)
    await click('撤销')
    expect(preview.props('calibration').left).toBe(0.2)
  })

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
    expect(api.post.mock.calls).toEqual([
      [
        'plugin/AgentPets/settings/shared',
        { roam: 'free', movement: 'auto', expected: { roam: 'floor', movement: 'auto' } },
      ],
      [
        'plugin/AgentPets/settings/pet',
        {
          key: 'kurisu',
          scale: 1.3,
          speed: 1.5,
          peek_angles: normalizePeekAngles(undefined),
          expected: { scale: 1, speed: 1, peek_angles: normalizePeekAngles(undefined) },
        },
      ],
    ])
    expect(broadcast).toHaveBeenCalledWith('agentpets.settings', {
      key: 'kurisu',
      scale: 1.3,
      speed: 1.5,
      peek_angles: normalizePeekAngles(undefined),
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
    expect(api.post.mock.calls).toEqual([
      [
        'plugin/AgentPets/settings/shared',
        { roam: 'free', movement: 'auto', expected: { roam: 'floor', movement: 'auto' } },
      ],
      [
        'plugin/AgentPets/settings/pet',
        {
          key: 'ying',
          scale: 1.3,
          speed: 1.5,
          peek_angles: normalizePeekAngles(undefined),
          expected: { scale: 1, speed: 1, peek_angles: normalizePeekAngles(undefined) },
        },
      ],
    ])
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
    resolve({ success: true, data: { scale: 1.3, speed: 1.5, roam: 'free', movement: 'auto' } })
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
      expect(view.text()).toContain('Kurisu 的素材调整已在其他页面更改')
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

describe('built-in calibration save workflow', () => {
  it.each(['ying', 'projector-cat', 'builtin-chibiterasu', 'builtin-nailong', 'builtin-kurisu', 'builtin-kurisu-z256'])(
    'saves and resets %s calibration without exposing built-in action mappings',
    async key => {
      const { view, api, click, broadcast } = await setup({}, key)
      const preview = view.findComponent({ name: 'PetPreview' })
      const baseline = builtinDefaultCalibration(key)
      preview.vm.$emit('pack-ready', { id: key, calibration: baseline })
      await flushPromises()
      expect(preview.props('calibration')).toEqual(baseline)
      expect(view.text()).not.toContain('未保存')
      const value = parseCalibration({ ...baseline, offset_x: 0.02 })
      preview.vm.$emit('calibration', value)
      await flushPromises()
      api.post.mockImplementation(async (_path, body) => ({
        success: true,
        data: { id: key, calibration: (body as { calibration: Calibration }).calibration },
      }))
      await click('保存调整')
      expect(api.post.mock.calls).toEqual([
        ['plugin/AgentPets/packs/calibration', { id: key, calibration: value, expected_calibration: baseline }],
      ])
      expect(broadcast).toHaveBeenCalledWith('agentpets.pack.updated', { key })
      expect(preview.props('mappings')).toBeUndefined()
      preview.vm.$emit('pack-ready', { id: key, calibration: value })
      await flushPromises()
      expect(view.text()).not.toContain('未保存')
      preview.vm.$emit('calibration', baseline)
      await flushPromises()
      await click('保存调整')
      expect(api.post.mock.calls.at(-1)?.[1]).toEqual({ id: key, calibration: baseline, expected_calibration: value })
    },
  )

  it('keeps a built-in draft on conflict and restores the latest external value', async () => {
    const { view, api, click } = await setup()
    const preview = view.findComponent({ name: 'PetPreview' })
    const baseline = builtinDefaultCalibration('ying')
    const draft = parseCalibration({ ...baseline, offset_x: 0.02 })
    const latest = parseCalibration({ ...baseline, offset_x: 0.03 })
    preview.vm.$emit('pack-ready', { id: 'ying', calibration: baseline })
    await flushPromises()
    preview.vm.$emit('calibration', draft)
    await flushPromises()
    preview.vm.$emit('pack-ready', { id: 'ying', calibration: latest })
    await flushPromises()
    expect(view.text()).toContain('素材调整已在其他页面更改')
    expect(preview.props('calibration')).toEqual(draft)
    await click('保存调整')
    expect(api.post).not.toHaveBeenCalled()
    await click('撤销')
    expect(preview.props('calibration')).toEqual(latest)
    expect(view.text()).not.toContain('未保存')
  })
})
