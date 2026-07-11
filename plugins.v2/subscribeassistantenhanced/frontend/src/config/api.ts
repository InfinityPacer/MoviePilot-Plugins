/** `/summary` 返回的粗粒度运行概况，不包含配置明细或私密数据。 */
export interface SummaryPayload {
  /** 各业务域的启用状态或当前模式。 */
  domains: Record<string, boolean | string>
  /** 当前待定订阅数量。 */
  pending_count: number
  /** 当前受监控种子数量。 */
  monitored_torrents: number
}

/** MoviePilot 宿主注入给联邦组件的最小只读 API 契约。 */
export interface PluginApi {
  /** 使用宿主登录态发起 GET 请求。 */
  get<T = unknown>(url: string, config?: unknown): Promise<T>
}

/** 读取可选运行概况；宿主或请求不可用时配置页继续以本地草稿渲染。 */
export async function loadSummary(api?: PluginApi): Promise<SummaryPayload | null> {
  if (!api) return null
  try {
    return await api.get<SummaryPayload>('plugin/SubscribeAssistantEnhanced/summary')
  } catch {
    console.warn('[SubscribeAssistantEnhanced] summary unavailable')
    return null
  }
}
