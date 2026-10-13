import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import PackArchiveImport from '@/sprites/PackArchiveImport.vue'
import { readPackArchive } from '@/sprites/packArchive'
import { parseCalibration } from '@/sprites/calibration'

vi.mock('@/sprites/packArchive', () => ({ readPackArchive: vi.fn() }))
const cleanups: Array<() => void> = []
afterEach(() => cleanups.splice(0).forEach(fn => fn()))
const imported = {
  pack: {
    id: 'pet',
    name: 'Saved',
    description: '',
    sheet: '',
    grid: { cols: 2, rows: 1 },
    frames: { idle: 0 },
    actions: {},
    random_actions: [],
    action_mappings: {},
    calibration: parseCalibration({}),
  },
  image: 'image',
}

async function setup() {
  vi.mocked(readPackArchive).mockResolvedValue(structuredClone(imported))
  const target = {
    id: 'pet',
    name: 'Existing',
    builtin: false,
    revision: 'before',
    grid: { cols: 2, rows: 1 },
    action_count: 0,
    frame_count: 1,
  }
  const api = { get: vi.fn(), post: vi.fn().mockResolvedValue({ success: true, data: { id: 'pet-1', name: 'Saved' } }) }
  const view = mount(PackArchiveImport, {
    props: { api, pluginId: 'Clone1', targets: [target] },
    global: { plugins: [createVuetify({ components, directives })] },
  })
  cleanups.push(() => view.unmount())
  view.findComponent({ name: 'VFileInput' }).vm.$emit('update:modelValue', [new File(['zip'], 'pet.zip')])
  await flushPromises()
  const button = (label: string) => view.findAll('button').find(item => item.text() === label)!
  return { view, api, target, button }
}
describe('archive conflict review', () => {
  it('defaults a duplicate ID to a copy and performs no write during preview', async () => {
    const { view, api, button } = await setup()
    expect(view.findComponent({ name: 'VSelect' }).props('modelValue')).toBe('copy')
    expect(api.post).not.toHaveBeenCalled()
    await button('确认导入').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith(
      'plugin/Clone1/packs/import',
      expect.objectContaining({ mode: 'copy', image: 'image' }),
    )
    expect(view.emitted('changed')).toHaveLength(1)
  })
  it('shows replacement scope and blocks a stale target without losing the import', async () => {
    const { view, api, target, button } = await setup()
    view.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 'replace')
    await flushPromises()
    expect(view.text()).toContain('原记录与已上传原图会保留恢复副本')
    await view.setProps({ targets: [{ ...target, revision: 'changed' }] })
    expect(button('确认覆盖此素材').attributes('disabled')).toBeDefined()
    expect(api.post).not.toHaveBeenCalled()
    expect(view.text()).toContain('当前素材已变化')
  })
  it('sends the reviewed revision and keeps the draft when the server refuses an overwrite', async () => {
    const { view, api, button } = await setup()
    view.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 'replace')
    await flushPromises()
    api.post.mockResolvedValue({ success: false, message: '素材已在其他页面更改' })
    await button('确认覆盖此素材').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith(
      'plugin/Clone1/packs/import',
      expect.objectContaining({ mode: 'replace', expected_revision: 'before' }),
    )
    expect(view.text()).toContain('素材已在其他页面更改')
    expect(
      view
        .findAllComponents({ name: 'VTextField' })
        .find(field => field.props('label') === '导入后的名称')!
        .props('modelValue'),
    ).toBe('Saved')
    expect(view.emitted('changed')).toBeUndefined()
  })
})
