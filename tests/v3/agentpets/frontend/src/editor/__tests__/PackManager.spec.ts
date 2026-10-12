import { fireEvent, render, waitFor } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
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
