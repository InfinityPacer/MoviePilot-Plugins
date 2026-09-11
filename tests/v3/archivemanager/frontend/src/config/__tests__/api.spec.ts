import { describe, expect, it, vi } from 'vitest'

import { listBatches, listFiles, loadSummary, pollPreview, runTask, startPreview, stopTask } from '@/config/api'
import type { PluginApi } from '@/config/api'
import type { ArchiveTask } from '@/config/types'

const task = { id: 'task-1', name: '归档' } as ArchiveTask

describe('ArchiveManager API helpers', () => {
  it('uses the relative plugin endpoint and preserves summary data', async () => {
    const summary = { archived_files: 2 }
    const get = vi.fn().mockResolvedValue({ success: true, message: '', data: summary })
    const api: PluginApi = { get, post: vi.fn(), put: vi.fn() }

    await expect(loadSummary(api)).resolves.toBe(summary)
    expect(get).toHaveBeenCalledWith('plugin/ArchiveManager/summary')
  })

  it('encodes list filters and keeps empty responses usable', async () => {
    const get = vi.fn().mockResolvedValue({ success: true, message: '', data: { items: [], total: 0 } })
    const api: PluginApi = { get, post: vi.fn(), put: vi.fn() }

    await listBatches(api, { task_id: 'task/1', page: 2, page_size: 30, status: 'failed' })
    expect(get).toHaveBeenCalledWith('plugin/ArchiveManager/batches?task_id=task%2F1&page=2&page_size=30&status=failed')
  })

  it('submits preview and operation bodies without leaking credentials', async () => {
    const post = vi.fn().mockResolvedValue({ success: true, message: '', data: { job_id: 'job-1', queued: true } })
    const get = vi
      .fn()
      .mockResolvedValue({ success: true, message: '', data: { status: 'running', data: null, message: '' } })
    const api: PluginApi = { get, post, put: vi.fn() }

    await startPreview(api, { ...task, password: 'secret' })
    await runTask(api, task.id)
    await stopTask(api, task.id)
    await pollPreview(api, 'job/1')

    expect(post).toHaveBeenNthCalledWith(1, 'plugin/ArchiveManager/preview', { task: { ...task, password: 'secret' } })
    expect(post).toHaveBeenNthCalledWith(2, 'plugin/ArchiveManager/run', { task_id: task.id })
    expect(post).toHaveBeenNthCalledWith(3, 'plugin/ArchiveManager/stop', { task_id: task.id })
    expect(get).toHaveBeenCalledWith('plugin/ArchiveManager/preview?job_id=job%2F1')
  })

  it('returns safe fallbacks and a fixed warning on request failure', async () => {
    const get = vi.fn().mockRejectedValue(new Error('private details'))
    const api: PluginApi = { get, post: vi.fn(), put: vi.fn() }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    await expect(loadSummary(api)).resolves.toBeNull()
    await expect(listFiles(api, {})).resolves.toEqual({ items: [], directories: [], total: 0 })
    expect(warn).toHaveBeenCalledWith('[ArchiveManager] summary unavailable')
    expect(document.body).not.toHaveTextContent('private details')
  })
})
