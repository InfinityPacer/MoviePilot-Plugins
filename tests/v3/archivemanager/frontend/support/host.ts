import type { PluginApi, ApiResponse } from '@/config/api'
import type { ArchiveConfig, SummaryPayload } from '@/config/types'
import { vi } from 'vitest'

export function createConfig(overrides: Partial<ArchiveConfig> = {}): ArchiveConfig {
  return {
    enabled: false,
    notify: false,
    notify_events: ['failure'],
    tasks: [],
    ...overrides,
  }
}

export function createSummary(overrides: Partial<SummaryPayload> = {}): SummaryPayload {
  return {
    archived_files: 12,
    archive_count: 3,
    source_bytes: 1024 * 1024 * 80,
    archive_bytes: 1024 * 1024 * 42,
    deleted_files: 8,
    failed_batches: 0,
    pending_files: 2,
    running: null,
    queued: [],
    config_error: '',
    last_error: null,
    tasks: [],
    ...overrides,
  }
}

export function createHostApi(summary: SummaryPayload = createSummary()) {
  const get = vi.fn().mockImplementation(async (path: string): Promise<ApiResponse<unknown>> => {
    if (path === 'plugin/ArchiveManager/summary') return { success: true, message: '', data: summary }
    return { success: true, message: '', data: { items: [], directories: [], total: 0 } }
  })
  const post = vi.fn().mockResolvedValue({ success: true, message: '', data: { queued: true, job_id: 'job-1' } })
  const put = vi.fn().mockResolvedValue({ success: true, message: '', data: null })
  const api: PluginApi = { get, post, put }
  return { api, get, post, put }
}
