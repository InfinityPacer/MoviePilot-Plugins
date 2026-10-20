import type { ArchiveJob } from './archiveCodec'

let active = 0

/** Dedicated, bounded workers; a blocked worker never falls back to the UI thread. */
export function runArchiveJob<T>(job: ArchiveJob): Promise<T> {
  if (active >= 2) return Promise.reject(new Error('素材任务正在处理，请稍后重试'))
  return new Promise((resolve, reject) => {
    let worker: Worker
    try {
      worker = new Worker(new URL('./archive.worker.ts', import.meta.url), { type: 'module' })
    } catch {
      reject(new Error('无法启动素材处理线程，请检查浏览器权限后重试'))
      return
    }
    active++
    let finished = false
    const finish = (error?: string, result?: T) => {
      if (finished) return
      finished = true
      window.clearTimeout(timer)
      worker.terminate()
      active--
      if (error) reject(new Error(error))
      else resolve(result as T)
    }
    const timer = window.setTimeout(() => finish('素材处理超时，请重试'), 15000)
    worker.onmessage = ({ data }) => finish(data.success ? undefined : data.error || '素材包处理失败', data.result)
    worker.onerror = () => finish('素材处理线程加载失败，请刷新后重试')
    worker.onmessageerror = () => finish('素材处理结果无法读取，请重试')
    try {
      worker.postMessage(job)
    } catch {
      finish('无法提交素材任务，请重试')
    }
  })
}
