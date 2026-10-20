import { executeArchiveJob, type ArchiveJob } from './archiveCodec'

self.onmessage = (event: MessageEvent<ArchiveJob>) => {
  try {
    self.postMessage({ success: true, result: executeArchiveJob(event.data) })
  } catch (error) {
    self.postMessage({ success: false, error: error instanceof Error ? error.message : '素材包处理失败' })
  }
}
