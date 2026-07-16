import type { PluginApi, SummaryPayload } from '@/config/api'
import { vi } from 'vitest'

export function createSummary(overrides: Partial<SummaryPayload> = {}): SummaryPayload {
  return {
    domains: {
      completion_guard: 'balanced',
      download_monitor: true,
      pending: true,
    },
    pending_count: 2,
    monitored_torrents: 3,
    ...overrides,
  }
}

/** 构造宿主注入的认证 API 边界，并暴露调用记录供行为断言。 */
export function createHostApi(payload: SummaryPayload = createSummary()) {
  const get = vi.fn().mockResolvedValue(payload)
  const api: PluginApi = { get }
  return { api, get }
}
