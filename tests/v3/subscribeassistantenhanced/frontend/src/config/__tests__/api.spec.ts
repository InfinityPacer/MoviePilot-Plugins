import { describe, expect, it, vi } from 'vitest'

import { loadSummary, type PluginApi, type SummaryPayload } from '@/config/api'

describe('summary API helper', () => {
  it('returns null without requesting when the host API is omitted', async () => {
    await expect(loadSummary()).resolves.toBeNull()
  })

  it('requests the plugin summary and returns the payload unchanged', async () => {
    const payload: SummaryPayload = {
      domains: {
        pending: true,
        download_monitor: 'guard',
      },
      pending_count: 3,
      monitored_torrents: 5,
    }
    const get = vi.fn().mockResolvedValue({
      success: true,
      message: '',
      data: payload,
    })
    const api: PluginApi = { get }

    const result = await loadSummary(api)

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('plugin/SubscribeAssistantEnhanced/summary')
    expect(result).toBe(payload)
  })

  it('treats an explicit V3 business failure as unavailable', async () => {
    const get = vi.fn().mockResolvedValue({
      success: false,
      message: 'summary unavailable',
      data: null,
    })
    const api: PluginApi = { get }

    await expect(loadSummary(api)).resolves.toBeNull()
  })

  it('returns null and emits only the fixed warning when the request fails', async () => {
    const rawError = {
      message: 'request failed for a private endpoint',
      config: {
        url: 'plugin/SubscribeAssistantEnhanced/summary',
        headers: { Authorization: 'Bearer private-token' },
      },
    }
    const get = vi.fn().mockRejectedValue(rawError)
    const api: PluginApi = { get }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    await expect(loadSummary(api)).resolves.toBeNull()
    expect(get).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledWith('[SubscribeAssistantEnhanced] summary unavailable')
  })
})
