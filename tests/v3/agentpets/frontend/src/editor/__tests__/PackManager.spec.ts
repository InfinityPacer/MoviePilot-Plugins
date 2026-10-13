import { fireEvent, render, waitFor } from '@testing-library/vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strToU8, zipSync } from 'fflate'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import PackManager from '@/sprites/PackManager.vue'
import * as packArchiveApi from '@/sprites/packArchive'
import { parseCalibration } from '@/sprites/calibration'

async function setup() {
  const pack = {
    id: 'rem',
    name: 'Rem',
    description: '',
    builtin: false,
    source: 'upload',
    mode: 'stage',
    preview: '',
    grid: { cols: 8, rows: 9 },
    frame_count: 57,
    action_count: 21,
  }
  const api = {
    get: vi
      .fn()
      .mockResolvedValue({ success: true, data: [pack, { ...pack, id: 'builtin', builtin: true, name: '内置' }] }),
    post: vi.fn().mockImplementation(async (_path, body) => ({ success: true, data: { ...pack, name: body.name } })),
  }
  const view = render(PackManager, {
    props: { api, pluginId: 'Clone1' },
    global: { plugins: [createVuetify({ components, directives })] },
  })
  await waitFor(() => expect(view.getByRole('button', { name: '重命名 Rem' })).toBeInTheDocument())
  return { view, api }
}

describe('imported Pet rename', () => {
  it('renames only the display label with an unchanged id and old-name check', async () => {
    const { view, api } = await setup()
    expect(view.queryByRole('button', { name: '重命名 内置' })).toBeNull()
    await fireEvent.click(view.getByRole('button', { name: '重命名 Rem' }))
    await fireEvent.update(view.getByRole('textbox', { name: '显示名称' }), '  蕾姆  ')
    await fireEvent.click(view.getByRole('button', { name: '保存名称' }))
    await waitFor(() => expect(view.getByRole('button', { name: '重命名 蕾姆' })).toBeInTheDocument())
    expect(api.post).toHaveBeenCalledWith('plugin/Clone1/packs/rename', {
      id: 'rem',
      name: '蕾姆',
      expected_name: 'Rem',
    })
    expect(view.emitted('changed')).toHaveLength(1)
  })
  it('rejects blank names and cancel performs no write', async () => {
    const { view, api } = await setup()
    await fireEvent.click(view.getByRole('button', { name: '重命名 Rem' }))
    await fireEvent.update(view.getByRole('textbox', { name: '显示名称' }), '  ')
    expect(view.getByRole('button', { name: '保存名称' })).toBeDisabled()
    await fireEvent.click(view.getByRole('button', { name: '取消' }))
    expect(api.post).not.toHaveBeenCalled()
  })
  it('preserves the displayed name and edit text when persistence fails', async () => {
    const { view, api } = await setup()
    api.post.mockResolvedValue({ success: false, message: '名称已在其他页面更改' })
    await fireEvent.click(view.getByRole('button', { name: '重命名 Rem' }))
    await fireEvent.update(view.getByRole('textbox', { name: '显示名称' }), '蕾姆')
    await fireEvent.click(view.getByRole('button', { name: '保存名称' }))
    await waitFor(() => expect(view.getByText('名称已在其他页面更改')).toBeInTheDocument())
    expect(view.getByRole('button', { name: '重命名 Rem' })).toBeInTheDocument()
    expect(view.getByRole('textbox', { name: '显示名称' })).toHaveValue('蕾姆')
    expect(view.emitted('changed')).toBeUndefined()
  })
})

describe('Codex import input identity', () => {
  const cleanups: Array<() => void> = []
  afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

  async function importSetup() {
    const bitmap = vi.fn().mockResolvedValue({ width: 1536, height: 1872, close() {} })
    vi.stubGlobal('createImageBitmap', bitmap)
    const api = { get: vi.fn().mockResolvedValue({ success: true, data: [] }), post: vi.fn() }
    const view = mount(PackManager, {
      attachTo: document.body,
      props: { api, pluginId: 'Clone1' },
      global: { plugins: [createVuetify({ components, directives })] },
    })
    cleanups.push(() => view.unmount())
    await flushPromises()
    const choose = async (file: File | null) => {
      view
        .findAllComponents({ name: 'VFileInput' })
        .find(input => input.props('label') === '选择精灵图或 ZIP')!
        .vm.$emit('update:modelValue', file ? [file] : [])
      await flushPromises()
    }
    const button = (label: string) => view.findAll('button').find(item => item.text() === label)!
    const click = async (label: string) => {
      await button(label).trigger('click')
      await flushPromises()
    }
    return { view, api, bitmap, choose, button, click }
  }

  const picture = (name: string) => new File(['image'], name, { type: 'image/png' })
  const archive = () =>
    new File(
      [
        zipSync({
          'pet.json': strToU8(JSON.stringify({ id: 'first-pet', displayName: 'First', spritesheetPath: 'sheet.png' })),
          'sheet.png': new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
        }),
      ],
      'first-pet.zip',
      { type: 'application/zip' },
    )

  it.each(['image', 'zip'])('requires parsing again after changing a %s import to another image', async kind => {
    const { view, api, choose, button, click } = await importSetup()
    await choose(kind === 'zip' ? archive() : picture('first-pet.png'))
    expect(button('添加 Pet').attributes('disabled')).toBeDefined()
    await click('读取 Codex Pet')
    await vi.waitFor(() => expect(button('添加 Pet').attributes('disabled'), view.text()).toBeUndefined())
    await choose(picture('second-pet.png'))
    expect(button('添加 Pet').attributes('disabled')).toBeDefined()
    expect(view.text()).not.toContain('已准备好')
    await click('读取 Codex Pet')
    await vi.waitFor(() => expect(button('添加 Pet').attributes('disabled'), view.text()).toBeUndefined())
    expect(view.text()).toContain('second-pet')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('invalidates a prepared import when the input is cleared or a repeated parse fails', async () => {
    const { bitmap, choose, button, click } = await importSetup()
    await choose(picture('first-pet.png'))
    await click('读取 Codex Pet')
    await choose(null)
    expect(button('添加 Pet').attributes('disabled')).toBeDefined()
    await choose(picture('first-pet.png'))
    await click('读取 Codex Pet')
    bitmap.mockRejectedValueOnce(new Error('图像损坏'))
    await click('读取 Codex Pet')
    expect(button('添加 Pet').attributes('disabled')).toBeDefined()
  })

  it('keeps the Codex draft when visiting the archive option within the shared importer', async () => {
    const { view, api, choose, button, click } = await importSetup()
    await choose(picture('first-pet.png'))
    await click('读取 Codex Pet')
    expect(button('添加 Pet').attributes('disabled')).toBeUndefined()
    await click('AgentPets 素材包')
    const importer = view.get('.agent-pet-sprites-config__import')
    expect(importer.get('.ap-archive-import').isVisible()).toBe(true)
    expect(button('添加 Pet').isVisible()).toBe(false)
    expect(view.text()).not.toContain('恢复 AgentPets 素材包')
    await click('Codex Pet')
    expect(importer.get('.ap-archive-import').isVisible()).toBe(false)
    expect(button('添加 Pet').isVisible()).toBe(true)
    expect(button('添加 Pet').attributes('disabled')).toBeUndefined()
    expect(view.text()).toContain('first-pet')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('preserves the archive review across tabs and locks switching until reading or saving finishes', async () => {
    const { view, api, button, click } = await importSetup()
    let finishRead!: (value: packArchiveApi.PackArchive) => void
    const read = vi.spyOn(packArchiveApi, 'readPackArchive').mockImplementation(
      () =>
        new Promise(resolve => {
          finishRead = resolve
        }),
    )
    await click('AgentPets 素材包')
    view
      .findComponent({ name: 'PackArchiveImport' })
      .findComponent({ name: 'VFileInput' })
      .vm.$emit('update:modelValue', [new File(['zip'], 'saved.agentpets.zip')])
    await flushPromises()
    expect(button('Codex Pet').attributes('disabled')).toBeDefined()
    expect(api.post).not.toHaveBeenCalled()
    finishRead({
      pack: {
        id: 'saved',
        name: 'Saved',
        description: '',
        sheet: '',
        grid: { cols: 1, rows: 1 },
        frames: { idle: 0 },
        actions: {},
        random_actions: [],
        action_mappings: {},
        calibration: parseCalibration({}),
      },
      image: 'data:image/png;base64,aW1hZ2U=',
    })
    await flushPromises()
    const nameField = () =>
      view.findAllComponents({ name: 'VTextField' }).find(field => field.props('label') === '导入后的名称')!
    nameField().vm.$emit('update:modelValue', '我的副本')
    await click('自定义素材')
    await click('AgentPets 素材包')
    expect(nameField().props('modelValue')).toBe('我的副本')
    expect(read).toHaveBeenCalledTimes(1)
    expect(api.post).not.toHaveBeenCalled()
    let finishSave!: (value: unknown) => void
    api.post.mockImplementation(
      () =>
        new Promise(resolve => {
          finishSave = resolve
        }),
    )
    await click('确认导入')
    expect(button('Codex Pet').attributes('disabled')).toBeDefined()
    expect(api.post).toHaveBeenCalledWith(
      'plugin/Clone1/packs/import',
      expect.objectContaining({ mode: 'new', pack: expect.objectContaining({ name: '我的副本' }) }),
    )
    finishSave({ success: true, data: { id: 'saved', name: '我的副本' } })
    await flushPromises()
    expect(button('Codex Pet').attributes('disabled')).toBeUndefined()
    expect(view.emitted('changed')).toHaveLength(1)
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(view.text()).toContain('已导入 我的副本')
  })

  it('discards an image read when the plugin instance changes before submission', async () => {
    const { view, api, choose, click, button } = await importSetup()
    await choose(picture('first-pet.png'))
    await click('读取 Codex Pet')
    let finishRead!: () => void
    vi.spyOn(FileReader.prototype, 'readAsDataURL').mockImplementation(function (this: FileReader) {
      finishRead = () => {
        Object.defineProperty(this, 'result', { value: 'data:image/png;base64,aW1hZ2U=', configurable: true })
        this.onload?.(new ProgressEvent('load') as ProgressEvent<FileReader>)
      }
    })
    await click('添加 Pet')
    await view.setProps({ pluginId: 'Clone2' })
    finishRead()
    await flushPromises()
    expect(api.post).not.toHaveBeenCalled()
    expect(button('添加 Pet').attributes('disabled')).toBeDefined()
    expect(view.text()).not.toContain('已准备好')
  })

  it('ignores a late parsed image after switching away and back to an instance', async () => {
    const { view, bitmap, choose, click, button } = await importSetup()
    let finish!: (value: { width: number; height: number; close: () => void }) => void
    bitmap.mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve
        }),
    )
    await choose(picture('first-pet.png'))
    await click('读取 Codex Pet')
    await view.setProps({ pluginId: 'Clone2' })
    await view.setProps({ pluginId: 'Clone1' })
    finish({ width: 1536, height: 1872, close() {} })
    await flushPromises()
    expect(button('添加 Pet').attributes('disabled')).toBeDefined()
    expect(view.text()).not.toContain('已准备好')
  })

  it('keeps manually supplied custom JSON when replacing its image', async () => {
    const { view, choose, button, click } = await importSetup()
    await click('自定义素材')
    const json = JSON.stringify({ name: 'Custom', grid: { cols: 1, rows: 1 }, frames: { idle: 0 } })
    view.findComponent({ name: 'VTextarea' }).vm.$emit('update:modelValue', json)
    await choose(picture('first.png'))
    await choose(picture('second.png'))
    expect(view.findComponent({ name: 'VTextarea' }).props('modelValue')).toBe(json)
    expect(button('添加 Pet').attributes('disabled')).toBeUndefined()
    await click('Codex Pet')
    expect(button('添加 Pet').attributes('disabled')).toBeDefined()
  })
})
describe('pending material deletion', () => {
  it('does not apply an old confirmation after switching away and back', async () => {
    let confirm!: (value: boolean) => void
    const pack = {
      id: 'rem',
      name: 'Rem',
      builtin: false,
      source: 'upload',
      mode: 'stage',
      preview: '',
      grid: null,
      frame_count: 1,
      action_count: 1,
    }
    const api = { get: vi.fn().mockResolvedValue({ success: true, data: [pack] }), post: vi.fn() }
    const view = mount(PackManager, {
      props: { api, pluginId: 'Clone1' },
      global: {
        plugins: [createVuetify({ components, directives })],
        provide: {
          'moviepilot:confirm': () =>
            new Promise(resolve => {
              confirm = resolve
            }),
        },
      },
    })
    try {
      await flushPromises()
      await view.get('button[aria-label="删除 Rem"]').trigger('click')
      await view.setProps({ pluginId: 'Clone2' })
      await view.setProps({ pluginId: 'Clone1' })
      confirm(true)
      await flushPromises()
      expect(api.post).not.toHaveBeenCalled()
      expect(view.emitted('changed')).toBeUndefined()
    } finally {
      view.unmount()
    }
  })
})
