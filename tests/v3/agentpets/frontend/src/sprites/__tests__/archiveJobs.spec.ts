import { expect, it, vi } from 'vitest'
import { runArchiveJob } from '@/sprites/archiveJobs'

it('bounds concurrency and terminates stalled workers without synchronous fallback', async () => {
  vi.useFakeTimers()
  const terminate = vi.fn()
  vi.stubGlobal(
    'Worker',
    class {
      terminate = terminate
      postMessage() {}
    },
  )
  const first = runArchiveJob({ kind: 'zip', files: {} })
  const second = runArchiveJob({ kind: 'zip', files: {} })
  const checked = Promise.all([expect(first).rejects.toThrow('超时'), expect(second).rejects.toThrow('超时')])
  await expect(runArchiveJob({ kind: 'zip', files: {} })).rejects.toThrow('正在处理')
  await vi.advanceTimersByTimeAsync(15000)
  await checked
  expect(terminate).toHaveBeenCalledTimes(2)
  vi.stubGlobal(
    'Worker',
    class {
      constructor() {
        throw new Error('CSP blocked')
      }
    },
  )
  await expect(runArchiveJob({ kind: 'zip', files: {} })).rejects.toThrow('无法启动')
  expect(vi.getTimerCount()).toBe(0)
})
