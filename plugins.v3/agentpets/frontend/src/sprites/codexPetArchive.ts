import { runArchiveJob } from './archiveJobs'
import type { CodexPetManifest } from './codexArchiveReader'
export type { CodexPetManifest } from './codexArchiveReader'
export const MAX_CODEX_PET_ARCHIVE_BYTES = 8 * 1024 * 1024
export interface ExtractedCodexPet {
  manifest: CodexPetManifest
  spritesheet: File
}
export function isCodexPetArchive(file: File): boolean {
  return file.name.toLowerCase().endsWith('.zip')
}
function readFileBytes(file: File): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === 'function') {
    return file.arrayBuffer().then(buffer => new Uint8Array(buffer))
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) resolve(new Uint8Array(reader.result))
      else reject(new Error('无法读取 Codex Pet 压缩包'))
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(file)
  })
}

export async function extractCodexPetArchive(file: File): Promise<ExtractedCodexPet> {
  if (!isCodexPetArchive(file)) throw new Error('压缩包文件名必须以 .zip 结尾')
  if (file.size > MAX_CODEX_PET_ARCHIVE_BYTES) throw new Error('Codex Pet 压缩包不能超过 8MB')
  const result = await runArchiveJob<{ manifest: CodexPetManifest; bytes: Uint8Array; filename: string; mime: string }>(
    { kind: 'codex', bytes: await readFileBytes(file) },
  )
  return {
    manifest: result.manifest,
    spritesheet: new File([new Uint8Array(result.bytes)], result.filename, { type: result.mime }),
  }
}
