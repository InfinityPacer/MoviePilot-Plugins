import { unzipSync, zipSync } from 'fflate'
import { readCodexArchiveBytes } from './codexArchiveReader'

export type ArchiveJob =
  | { kind: 'zip'; files: Record<string, Uint8Array> }
  | { kind: 'unzip'; bytes: Uint8Array }
  | { kind: 'codex'; bytes: Uint8Array }
  | { kind: 'decode'; data: string; limit: number }
  | { kind: 'encode'; bytes: Uint8Array; mime: string }

const MAX_IMAGE = 4 * 1024 * 1024
const MAX_ARCHIVE = 8 * 1024 * 1024
const limits: Record<string, number> = {
  'agentpets.json': 64 * 1024,
  'sheet.img': MAX_IMAGE,
  'preview.img': 128 * 1024,
  'avatar.img': 128 * 1024,
}

/** Runs only inside the worker (or isolated codec tests). */
export function executeArchiveJob(job: ArchiveJob) {
  if (job.kind === 'codex') return readCodexArchiveBytes(job.bytes)
  if (job.kind === 'unzip') {
    if (job.bytes.length > MAX_ARCHIVE) throw new Error('素材包不能超过 8MB')
    const seen = new Set<string>()
    return unzipSync(job.bytes, {
      filter: entry => {
        if (!Object.hasOwn(limits, entry.name) || seen.has(entry.name)) throw new Error('素材包包含未知或重复文件')
        seen.add(entry.name)
        if (entry.originalSize > limits[entry.name]) throw new Error('包内文件超过大小限制')
        return true
      },
    })
  }
  if (job.kind === 'zip') {
    for (const [name, bytes] of Object.entries(job.files))
      if (!Object.hasOwn(limits, name) || bytes.length > limits[name]) throw new Error('包内文件超过大小限制')
    return zipSync(job.files)
  }
  if (job.kind === 'decode') {
    const limit = Math.min(job.limit, MAX_IMAGE)
    const match = /^data:image\/[a-z0-9.+-]+;base64,([a-zA-Z0-9+/=]+)$/.exec(job.data)
    if (!match || match[1].length > Math.ceil(limit / 3) * 4) throw new Error('图片内容无效或超过大小限制')
    const binary = atob(match[1])
    if (binary.length > limit) throw new Error('图片超过大小限制')
    const bytes = new Uint8Array(binary.length)
    for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index)
    return bytes
  }
  if (job.bytes.length > MAX_IMAGE) throw new Error('图片超过大小限制')
  const parts: string[] = []
  for (let start = 0; start < job.bytes.length; start += 8192)
    parts.push(String.fromCharCode(...job.bytes.subarray(start, start + 8192)))
  return `data:${job.mime};base64,${btoa(parts.join(''))}`
}
