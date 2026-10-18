import { unwrap } from '@/editor/api'
import type { PluginApi } from '@/host'

/** 后端已注册市场的展示信息。 */
export interface MarketInfo {
  id: string
  name: string
  description: string
  homepage: string | null
}

/** 远程市场内的形象摘要，id 不等同于导入后的本地素材 ID。 */
export interface MarketItem {
  id: string
  name: string
  description: string
  author: string
  license: string
  preview: string | null
  source_url: string | null
}

/** 支持未知总量的统一市场分页结果。 */
export interface MarketPage {
  market_id: string
  page: number
  page_size: number
  items: MarketItem[]
  total: number | null
  has_more: boolean
}

export type MarketImportMode = 'new' | 'copy'

/** 导入成功后供页面更新提示与本地列表使用的最小摘要。 */
export interface ImportedMarketPack {
  id: string
  name: string
}

/** 外链和预览只接受绝对 HTTP(S) 地址，不允许脚本或内嵌执行内容。 */
export function marketUrl(value: string | null | undefined): string {
  if (!value) return ''
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : ''
  } catch {
    return ''
  }
}

/** 返回错误说明，权限失败使用明确的管理员提示，不泄露 HTTP 客户端实现。 */
export function marketError(reason: unknown, fallback: string): string {
  const response = (reason as { response?: { status?: number; data?: { detail?: unknown; message?: unknown } } })
    ?.response
  if (response?.status === 403) return '仅管理员可以导入市场形象'
  const detail = response?.data?.detail ?? response?.data?.message
  if (typeof detail === 'string' && detail) return detail
  return reason instanceof Error && reason.message ? reason.message : fallback
}

function requireConnection(api: PluginApi | null | undefined, pluginId: string): PluginApi {
  if (!api?.get || !api.post || !pluginId) throw new Error('页面连接尚未就绪，请重新打开')
  return api
}

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function isMarket(value: unknown): value is MarketInfo {
  return (
    record(value) &&
    typeof value.id === 'string' &&
    /^[a-z0-9_-]{1,32}$/.test(value.id) &&
    typeof value.name === 'string' &&
    !!value.name.trim() &&
    typeof value.description === 'string' &&
    (value.homepage === null || typeof value.homepage === 'string')
  )
}

function isItem(value: unknown): value is MarketItem {
  return (
    record(value) &&
    typeof value.id === 'string' &&
    !!value.id &&
    typeof value.name === 'string' &&
    !!value.name.trim() &&
    ['description', 'author', 'license'].every(key => typeof value[key] === 'string') &&
    ['preview', 'source_url'].every(key => value[key] === null || typeof value[key] === 'string')
  )
}

/** 读取指定插件实例的市场列表，重复身份视为无效响应。 */
export async function loadMarkets(api: PluginApi | null | undefined, pluginId: string): Promise<MarketInfo[]> {
  const data = unwrap<unknown>(await requireConnection(api, pluginId).get(`plugin/${pluginId}/markets`))
  if (!Array.isArray(data) || !data.every(isMarket) || new Set(data.map(item => item.id)).size !== data.length) {
    throw new Error('市场列表响应无效，请刷新重试')
  }
  return data
}

/** 搜索结果必须与当前市场、页码和页大小一致，避免旧结果被当作当前页。 */
export async function searchMarket(
  api: PluginApi | null | undefined,
  pluginId: string,
  marketId: string,
  keyword: string,
  page: number,
  pageSize = 12,
): Promise<MarketPage> {
  const query = new URLSearchParams({
    market_id: marketId,
    keyword: keyword.trim(),
    page: String(page),
    page_size: String(pageSize),
  })
  const data = unwrap<unknown>(await requireConnection(api, pluginId).get(`plugin/${pluginId}/markets/items?${query}`))
  if (
    !record(data) ||
    data.market_id !== marketId ||
    data.page !== page ||
    data.page_size !== pageSize ||
    !Array.isArray(data.items) ||
    !data.items.every(isItem) ||
    data.items.length > pageSize ||
    new Set(data.items.map(item => item.id)).size !== data.items.length ||
    !(data.total === null || (Number.isInteger(data.total) && Number(data.total) >= data.items.length)) ||
    typeof data.has_more !== 'boolean'
  ) {
    throw new Error('市场搜索响应无效，请重试')
  }
  return data as unknown as MarketPage
}

/** 导入仅提交已注册市场与远程身份；响应未确认时不得报告成功。 */
export async function importMarketPack(
  api: PluginApi | null | undefined,
  pluginId: string,
  marketId: string,
  itemId: string,
  mode: MarketImportMode,
): Promise<ImportedMarketPack> {
  const data = unwrap<unknown>(
    await requireConnection(api, pluginId).post(`plugin/${pluginId}/markets/import`, {
      market_id: marketId,
      item_id: itemId,
      mode,
    }),
  )
  if (
    !record(data) ||
    typeof data.id !== 'string' ||
    !/^[a-z0-9_-]{1,32}$/.test(data.id) ||
    typeof data.name !== 'string' ||
    !data.name.trim()
  ) {
    throw new Error('导入结果未确认，请刷新我的素材后核对')
  }
  return { id: data.id, name: data.name }
}
