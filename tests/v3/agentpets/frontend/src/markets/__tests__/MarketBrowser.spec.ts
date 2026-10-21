import { fireEvent, render, waitFor } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

import MarketBrowser from '@/markets/MarketBrowser.vue'

const markets = [
  {
    id: 'codex-pets',
    name: 'Codex Pets',
    description: 'Community pets',
    homepage: 'https://codex-pets.net/',
  },
  { id: 'petdex', name: 'Petdex', description: 'Petdex pets', homepage: null },
]
const item = {
  id: 'author/pet',
  name: 'Test Pet',
  description: 'A companion',
  author: 'Creator',
  license: '',
  preview: null,
  source_url: 'https://example.com/pet',
}

async function setup() {
  const api = {
    get: vi.fn().mockImplementation(async (path: string) => {
      if (path.endsWith('/markets')) return { success: true, data: markets }
      const params = new URLSearchParams(path.split('?')[1])
      return {
        success: true,
        data: {
          market_id: params.get('market_id'),
          page: Number(params.get('page')),
          page_size: 12,
          items: [item],
          total: null,
          has_more: true,
        },
      }
    }),
    post: vi.fn().mockResolvedValue({
      success: true,
      data: { id: 'local-pet', name: 'Test Pet' },
    }),
  }
  const view = render(MarketBrowser, {
    props: { api, pluginId: 'Clone1' },
    global: { plugins: [createVuetify({ components, directives })] },
  })
  await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
  return { api, view }
}

describe('market browsing and import', () => {
  it('joins identical in-flight searches and allows retry after a failure', async () => {
    const { api, view } = await setup()
    let fail!: (reason: Error) => void
    api.get.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          fail = reject
        }),
    )
    const before = api.get.mock.calls.length
    await fireEvent.update(view.getByRole('textbox', { name: '搜索形象' }), 'cat')
    const search = view.getByRole('button', { name: '搜索市场形象' })
    await fireEvent.click(search)
    await fireEvent.click(search)
    await fireEvent.click(search)
    expect(api.get.mock.calls.length - before).toBe(1)
    fail(new Error('temporary failure'))
    await flushPromises()
    await fireEvent.click(view.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
    expect(api.get.mock.calls.length - before).toBe(2)
  })

  it('does not join requests from a previous plugin instance', async () => {
    const { api, view } = await setup()
    let finish!: (data: unknown) => void
    api.get.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve
        }),
    )
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    await view.rerender({ api, pluginId: 'Clone2' })
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
    expect(api.get.mock.calls.at(-1)?.[0]).toContain('plugin/Clone2/')
    finish({ success: false, message: 'old instance failure' })
    await flushPromises()
    expect(view.queryByText('old instance failure')).toBeNull()
  })

  it('joins a still-pending query after switching away and back without displaying another market', async () => {
    const { api, view } = await setup()
    let finish!: (value: unknown) => void
    api.get.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve
        }),
    )
    const before = api.get.mock.calls.length
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    await fireEvent.mouseDown(view.getByRole('combobox'))
    await fireEvent.click(view.getByRole('option', { name: 'Petdex' }))
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
    await fireEvent.mouseDown(view.getByRole('combobox'))
    await fireEvent.click(view.getByRole('option', { name: 'Codex Pets' }))
    expect(api.get.mock.calls.length - before).toBe(2)
    expect(view.queryByRole('button', { name: '导入 Test Pet' })).toBeNull()
    finish({
      success: true,
      data: {
        market_id: 'codex-pets',
        page: 1,
        page_size: 12,
        total: 1,
        has_more: false,
        items: [{ ...item, name: 'Current Pet' }],
      },
    })
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Current Pet' })).toBeInTheDocument())
    expect(view.queryByRole('button', { name: '导入 Test Pet' })).toBeNull()
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
    expect(api.get.mock.calls.length - before).toBe(3)
  })

  it('bounds distinct pending requests and frees capacity when a superseded query fails', async () => {
    const { api, view } = await setup()
    const request = api.get.getMockImplementation()!
    const pending: Array<{ fail: (reason: Error) => void; finish: (value: unknown) => void }> = []
    api.get.mockImplementation(
      () =>
        new Promise((resolve, reject) => {
          pending.push({ fail: reject, finish: resolve })
        }),
    )
    const before = api.get.mock.calls.length
    for (const query of ['one', 'two', 'three', 'four', 'five']) {
      await fireEvent.update(view.getByRole('textbox', { name: '搜索形象' }), query)
      await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    }
    expect(api.get.mock.calls.length - before).toBe(4)
    expect(view.getByText('市场查询正在处理，请稍后重试')).toBeInTheDocument()
    pending[0].fail(new Error('superseded failure'))
    await flushPromises()
    expect(view.queryByText('superseded failure')).toBeNull()
    await fireEvent.click(view.getByRole('button', { name: '重试' }))
    expect(api.get.mock.calls.length - before).toBe(5)
    pending.at(-1)!.finish(await request('plugin/Clone1/markets/items?market_id=codex-pets&keyword=five&page=1'))
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
    pending.slice(1, 4).forEach(entry => entry.fail(new Error('superseded failure')))
    await flushPromises()
    expect(view.queryByText('superseded failure')).toBeNull()
  })

  it('retains the pending capacity boundary across plugin-scope invalidation', async () => {
    const { api, view } = await setup()
    const request = api.get.getMockImplementation()!
    const failures: Array<(reason: Error) => void> = []
    api.get.mockImplementation(path =>
      path.endsWith('/markets')
        ? request(path)
        : new Promise((_resolve, reject) => {
            failures.push(reject)
          }),
    )
    for (const query of ['one', 'two', 'three', 'four']) {
      await fireEvent.update(view.getByRole('textbox', { name: '搜索形象' }), query)
      await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    }
    await view.rerender({ api, pluginId: 'Clone2' })
    await waitFor(() => expect(view.getByText('市场查询正在处理，请稍后重试')).toBeInTheDocument())
    expect(failures).toHaveLength(4)
    failures.forEach(fail => fail(new Error('old instance failure')))
    await flushPromises()
    expect(view.queryByText('old instance failure')).toBeNull()
    api.get.mockImplementation(request)
    await fireEvent.click(view.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
    expect(api.get.mock.calls.at(-1)?.[0]).toContain('plugin/Clone2/')
  })

  it('browses unknown totals and searches with a reset page', async () => {
    const { api, view } = await setup()
    expect(view.getByText(/总量未知/)).toBeInTheDocument()
    await fireEvent.click(view.getByRole('button', { name: '下一页' }))
    await waitFor(() => expect(view.getByText(/第 2 页/)).toBeInTheDocument())
    await fireEvent.update(view.getByRole('textbox', { name: '搜索形象' }), 'cat')
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    await waitFor(() => expect(view.getByText(/第 1 页/)).toBeInTheDocument())
    expect(api.get.mock.calls.at(-1)?.[0]).toContain('keyword=cat&page=1')
    await fireEvent.click(view.getByRole('button', { name: 'Clear 搜索形象' }))
    await waitFor(() => expect(api.get.mock.calls.at(-1)?.[0]).toContain('keyword=&page=1'))
  })

  it('confirms explicit copy import and emits only after success', async () => {
    const { api, view } = await setup()
    await fireEvent.click(view.getByRole('button', { name: '导入 Test Pet' }))
    expect(api.post).not.toHaveBeenCalled()
    await fireEvent.click(view.getByRole('radio', { name: '导入副本' }))
    await fireEvent.click(view.getByRole('button', { name: '确认导入' }))
    await waitFor(() => expect(view.getByText('已导入 Test Pet')).toBeInTheDocument())
    expect(api.post).toHaveBeenCalledWith('plugin/Clone1/markets/import', {
      market_id: 'codex-pets',
      item_id: 'author/pet',
      mode: 'copy',
    })
    expect(view.emitted('imported')).toHaveLength(1)
  })

  it('preserves the review and never reports success on backend failure', async () => {
    const { api, view } = await setup()
    api.post.mockResolvedValue({
      success: false,
      message: '已存在 ID，请导入副本',
    })
    await fireEvent.click(view.getByRole('button', { name: '导入 Test Pet' }))
    await fireEvent.click(view.getByRole('button', { name: '确认导入' }))
    await waitFor(() => expect(view.getByText('已存在 ID，请导入副本')).toBeInTheDocument())
    expect(view.getByRole('button', { name: '确认导入' })).toBeInTheDocument()
    expect(view.emitted('imported')).toBeUndefined()
  })

  it('ignores a late import after switching plugin instances', async () => {
    const { api, view } = await setup()
    let finish!: (value: unknown) => void
    api.post.mockImplementation(
      () =>
        new Promise(resolve => {
          finish = resolve
        }),
    )
    await fireEvent.click(view.getByRole('button', { name: '导入 Test Pet' }))
    await fireEvent.click(view.getByRole('button', { name: '确认导入' }))
    await view.rerender({ api, pluginId: 'Clone2' })
    finish({ success: true, data: { id: 'local-pet', name: 'Test Pet' } })
    await flushPromises()
    expect(view.emitted('imported')).toBeUndefined()
    expect(view.queryByText('已导入 Test Pet')).toBeNull()
  })

  it('switches markets and ignores an older search response', async () => {
    const { api, view } = await setup()
    const original = api.get.getMockImplementation()!
    let finish!: (value: unknown) => void
    api.get.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          finish = resolve
        }),
    )
    await fireEvent.update(view.getByRole('textbox', { name: '搜索形象' }), 'old')
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    expect(view.getByRole('textbox', { name: '形象市场' })).toBeInTheDocument()
    await fireEvent.mouseDown(view.getByRole('combobox'))
    await fireEvent.click(view.getByRole('option', { name: 'Petdex' }))
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
    expect(api.get.mock.calls.at(-1)?.[0]).toContain('market_id=petdex&keyword=&page=1')
    finish({
      success: true,
      data: {
        market_id: 'codex-pets',
        page: 1,
        page_size: 12,
        total: 1,
        has_more: false,
        items: [{ ...item, name: 'Old Pet' }],
      },
    })
    await flushPromises()
    expect(view.queryByText('Old Pet')).toBeNull()
    api.get.mockImplementation(original)
  })

  it('keeps the review on permission failure and prevents duplicate submissions', async () => {
    const { api, view } = await setup()
    let fail!: (error: unknown) => void
    api.post.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          fail = reject
        }),
    )
    await fireEvent.click(view.getByRole('button', { name: '导入 Test Pet' }))
    await fireEvent.click(view.getByRole('button', { name: '确认导入' }))
    expect(view.getByRole('button', { name: '确认导入' })).toBeDisabled()
    expect(api.post).toHaveBeenCalledTimes(1)
    fail({ response: { status: 403 } })
    await waitFor(() => expect(view.getByText('仅管理员可以导入市场形象')).toBeInTheDocument())
    expect(view.emitted('imported')).toBeUndefined()
    expect(view.getByRole('button', { name: '确认导入' })).toBeEnabled()
  })

  it('can retry query failures and distinguishes empty matches from missing markets', async () => {
    const { api, view } = await setup()
    api.get.mockResolvedValueOnce({ success: false, message: '市场暂不可用' })
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    await waitFor(() => expect(view.getByText('市场暂不可用')).toBeInTheDocument())
    await fireEvent.click(view.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(view.getByRole('button', { name: '导入 Test Pet' })).toBeInTheDocument())
    api.get.mockResolvedValueOnce({
      success: true,
      data: {
        market_id: 'codex-pets',
        page: 1,
        page_size: 12,
        total: 0,
        has_more: false,
        items: [],
      },
    })
    await fireEvent.update(view.getByRole('textbox', { name: '搜索形象' }), 'missing')
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    await waitFor(() => expect(view.getByText('没有找到匹配的形象')).toBeInTheDocument())
    api.get.mockResolvedValueOnce({ success: true, data: [] })
    await view.rerender({ api, pluginId: 'Clone2' })
    await waitFor(() => expect(view.getByText('暂未接入形象市场')).toBeInTheDocument())
  })

  it('falls back when a preview image fails and closes the review without writing', async () => {
    const { api, view } = await setup()
    api.get.mockResolvedValueOnce({
      success: true,
      data: {
        market_id: 'codex-pets',
        page: 1,
        page_size: 12,
        total: 1,
        has_more: false,
        items: [{ ...item, preview: 'https://example.com/pet.png' }],
      },
    })
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    await waitFor(() => expect(view.getByRole('img', { name: 'Test Pet' })).toBeInTheDocument())
    await fireEvent.error(view.getByRole('img', { name: 'Test Pet' }))
    expect(view.queryByRole('img', { name: 'Test Pet' })).toBeNull()
    expect(view.getByText(/图片由浏览器直接加载/)).toBeInTheDocument()
    const original = view.getByRole('link', { name: '查看 Test Pet 原图' })
    expect(original).toHaveAttribute('href', 'https://example.com/pet.png')
    expect(original).toHaveAttribute('target', '_blank')
    expect(original).toHaveAttribute('rel', 'noopener noreferrer')
    expect(view.getByRole('link', { name: '市场主页' })).toHaveAttribute('href', 'https://codex-pets.net/')
    await fireEvent.click(view.getByRole('button', { name: '预览 Test Pet' }))
    expect(view.getByText('浏览器无法加载预览图，不影响尝试导入。')).toBeInTheDocument()
    expect(view.getByRole('button', { name: '确认导入' })).toBeEnabled()
    await fireEvent.click(view.getByRole('button', { name: '取消' }))
    expect(api.post).not.toHaveBeenCalled()
    await view.rerender({ api, pluginId: 'Clone2' })
    await waitFor(() => expect(view.queryByText(/图片由浏览器直接加载/)).toBeNull())
    expect(view.queryByRole('link', { name: '查看 Test Pet 原图' })).toBeNull()
  })

  it('keeps the homepage visible when the server rejects a market request', async () => {
    const { api, view } = await setup()
    api.get.mockResolvedValueOnce({
      success: false,
      message: 'Market 地址未通过服务器安全检查',
    })
    await fireEvent.click(view.getByRole('button', { name: '搜索市场形象' }))
    await waitFor(() => expect(view.getByText('Market 地址未通过服务器安全检查')).toBeInTheDocument())
    expect(view.getByRole('link', { name: '市场主页' })).toHaveAttribute('href', 'https://codex-pets.net/')
    expect(view.queryByText(/图片由浏览器直接加载/)).toBeNull()
  })
})
