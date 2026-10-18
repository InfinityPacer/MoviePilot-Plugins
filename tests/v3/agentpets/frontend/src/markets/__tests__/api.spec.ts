import { describe, expect, it, vi } from 'vitest'

import { importMarketPack, loadMarkets, marketError, marketUrl, searchMarket } from '@/markets/api'

const item = {
  id: 'author/pet',
  name: 'Pet',
  description: '',
  author: '',
  license: '',
  preview: null,
  source_url: null,
}

describe('online market API', () => {
  it('uses the current instance and encodes remote ids only in the import payload', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        success: true,
        data: [{ id: 'petdex', name: 'Petdex', description: '', homepage: null }],
      }),
      post: vi.fn().mockResolvedValue({
        success: true,
        data: { id: 'local-pet', name: 'Pet' },
      }),
    }
    expect(await loadMarkets(api, 'Clone1')).toHaveLength(1)
    expect(api.get).toHaveBeenCalledWith('plugin/Clone1/markets')
    await expect(importMarketPack(api, 'Clone1', 'petdex', 'author/pet', 'copy')).resolves.toEqual({
      id: 'local-pet',
      name: 'Pet',
    })
    expect(api.post).toHaveBeenCalledWith('plugin/Clone1/markets/import', {
      market_id: 'petdex',
      item_id: 'author/pet',
      mode: 'copy',
    })
  })

  it('validates pagination identity and keeps unknown totals', async () => {
    const page = {
      market_id: 'petdex',
      page: 2,
      page_size: 12,
      total: null,
      has_more: true,
      items: [item],
    }
    const api = {
      get: vi.fn().mockResolvedValue({ success: true, data: page }),
      post: vi.fn(),
    }
    expect(await searchMarket(api, 'Clone1', 'petdex', '  cat & dog  ', 2)).toEqual(page)
    const path = api.get.mock.calls[0]![0] as string
    const params = new URLSearchParams(path.split('?')[1])
    expect(params.get('keyword')).toBe('cat & dog')
    api.get.mockResolvedValue({
      success: true,
      data: { ...page, market_id: 'other' },
    })
    await expect(searchMarket(api, 'Clone1', 'petdex', '', 2)).rejects.toThrow('响应无效')
  })

  it('rejects malformed success responses and preserves backend failure messages', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({ success: true, data: [{}] }),
      post: vi.fn().mockResolvedValue({ success: true, data: {} }),
    }
    await expect(loadMarkets(api, 'Clone1')).rejects.toThrow('响应无效')
    await expect(importMarketPack(api, 'Clone1', 'petdex', 'pet', 'new')).rejects.toThrow('未确认')
    api.post.mockResolvedValue({
      success: false,
      message: '已存在此素材，请导入副本',
    })
    await expect(importMarketPack(api, 'Clone1', 'petdex', 'pet', 'new')).rejects.toThrow('导入副本')
    await expect(loadMarkets(api, '')).rejects.toThrow('连接尚未就绪')
  })

  it('limits external links and translates permission errors', () => {
    expect(marketUrl('javascript:alert(1)')).toBe('')
    expect(marketUrl('https://user:secret@example.com/image')).toBe('')
    expect(marketUrl('https://example.com/pet')).toBe('https://example.com/pet')
    expect(marketError({ response: { status: 403 } }, '失败')).toBe('仅管理员可以导入市场形象')
    expect(marketError(new Error('格式不支持'), '失败')).toBe('格式不支持')
  })
})
