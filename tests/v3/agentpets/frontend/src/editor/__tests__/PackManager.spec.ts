import { fireEvent, render, waitFor } from '@testing-library/vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { strToU8, zipSync } from 'fflate'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import PackManager from '@/sprites/PackManager.vue'

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
