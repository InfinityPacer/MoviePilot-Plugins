import { strFromU8, strToU8 } from 'fflate'
import { runArchiveJob } from './archiveJobs'
import type { PluginApi } from '@/host'
import { unwrap } from '@/editor/api'
import { validatePack, type SpritePack } from './schema'

const MAX_ARCHIVE = 8 * 1024 * 1024
const MAX_IMAGE = 4 * 1024 * 1024
const MAX_MANIFEST = 64 * 1024
// 与后端预览图和头像的容量契约一致，容纳高细节的 128×128 PNG。
const MAX_THUMB = 128 * 1024

export interface PortablePack extends SpritePack {
  preview?: string
  avatar?: string
}
export interface PackArchive {
  pack: PortablePack
  image: string
}
export interface ArchiveTarget {
  id: string
  name: string
  builtin: boolean
  revision?: string
  grid: { cols: number; rows: number } | null
  frame_count: number
  action_count: number
  mapping_count?: number
  calibrated?: boolean
}

function imageMime(bytes: Uint8Array): string {
  if (bytes[0] === 137 && strFromU8(bytes.subarray(1, 4)) === 'PNG') return 'image/png'
  if (strFromU8(bytes.subarray(0, 4)) === 'RIFF' && strFromU8(bytes.subarray(8, 12)) === 'WEBP') return 'image/webp'
  if (strFromU8(bytes.subarray(0, 3)) === 'GIF') return 'image/gif'
  if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) return 'image/jpeg'
  throw new Error('包内图片格式无效')
}

export async function imageDataUrl(bytes: Uint8Array): Promise<string> {
  return runArchiveJob<string>({ kind: 'encode', bytes, mime: imageMime(bytes) })
}

async function imageBytes(src: string, limit: number): Promise<Uint8Array> {
  if (src.startsWith('data:')) {
    const bytes = await runArchiveJob<Uint8Array>({ kind: 'decode', data: src, limit })
    imageMime(bytes)
    return bytes
  }
  if (!/^https?:\/\/\S+$/.test(src)) throw new Error('图片地址无效')
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 12000)
  try {
    const response = await fetch(src, { signal: controller.signal, credentials: 'omit' })
    if (!response.ok || !response.body) throw new Error('远程图片读取失败')
    const reader = response.body.getReader()
    const chunks: Uint8Array[] = []
    let length = 0
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        length += value.length
        if (length > limit) {
          await reader.cancel()
          throw new Error('图片超过大小限制')
        }
        chunks.push(value)
      }
    } finally {
      reader.releaseLock()
    }
    const bytes = new Uint8Array(length)
    let offset = 0
    for (const chunk of chunks) {
      bytes.set(chunk, offset)
      offset += chunk.length
    }
    imageMime(bytes)
    return bytes
  } finally {
    window.clearTimeout(timeout)
  }
}

async function verifyImage(bytes: Uint8Array, pack?: SpritePack) {
  const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: imageMime(bytes) }))
  try {
    if (!bitmap.width || !bitmap.height || bitmap.width > 4096 || bitmap.height > 4096)
      throw new Error('图片尺寸无效或超过 4096 像素')
    if (pack && (bitmap.width % pack.grid.cols || bitmap.height % pack.grid.rows))
      throw new Error('精灵图尺寸不能被素材网格整除')
  } finally {
    bitmap.close()
  }
}

/** API 返回原始帧与动作，导出不能使用预览时补齐过的动作副本。 */
export async function exportPackArchive(api: PluginApi, pluginId: string, key: string): Promise<Blob> {
  const data = unwrap<{ pack: PortablePack; sheet_src: string; builtin: boolean }>(
    await api.get(`plugin/${pluginId}/pack?key=${encodeURIComponent(key)}`),
  )
  if (!data || data.builtin || data.pack?.id !== key) throw new Error('只能导出已导入的素材')
  const { pack, errors } = validatePack(data.pack)
  if (!pack) throw new Error(errors.join('；'))
  const sheet = await imageBytes(data.sheet_src, MAX_IMAGE)
  await verifyImage(sheet, pack)
  const files: Record<string, Uint8Array> = { 'sheet.img': sheet }
  const images: Record<string, string> = { sheet: 'sheet.img' }
  for (const field of ['preview', 'avatar'] as const) {
    if (!data.pack[field]) continue
    const bytes = await imageBytes(data.pack[field]!, MAX_THUMB)
    await verifyImage(bytes)
    files[`${field}.img`] = bytes
    images[field] = `${field}.img`
  }
  const metadata = { ...pack, sheet: '' }
  delete metadata.preview
  delete metadata.avatar
  const manifest = strToU8(JSON.stringify({ format: 'agentpets', version: 1, pack: metadata, images }))
  if (manifest.length > MAX_MANIFEST) throw new Error('素材描述超过 64KB，未生成备份')
  files['agentpets.json'] = manifest
  const archive = await runArchiveJob<Uint8Array>({ kind: 'zip', files })
  if (archive.length > MAX_ARCHIVE) throw new Error('素材包超过 8MB')
  return new Blob([new Uint8Array(archive)], { type: 'application/zip' })
}

function fileBytes(file: File): Promise<Uint8Array> {
  if (file.arrayBuffer) return file.arrayBuffer().then(value => new Uint8Array(value))
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer))
    reader.onerror = () => reject(new Error('无法读取素材包'))
    reader.readAsArrayBuffer(file)
  })
}

export async function readPackArchive(file: File): Promise<PackArchive> {
  if (file.size > MAX_ARCHIVE) throw new Error('素材包不能超过 8MB')
  const files = await runArchiveJob<Record<string, Uint8Array>>({ kind: 'unzip', bytes: await fileBytes(file) })
  if (!files['agentpets.json'] || !files['sheet.img'])
    throw new Error('不是完整的 AgentPets 素材包；Codex Pet ZIP 请切换到“Codex Pet”导入类型')
  const manifest = JSON.parse(strFromU8(files['agentpets.json']))
  if (manifest?.format !== 'agentpets' || manifest?.version !== 1 || manifest?.images?.sheet !== 'sheet.img')
    throw new Error('素材包格式或版本不支持')
  const { pack, errors } = validatePack(manifest.pack)
  if (!pack) throw new Error(errors.join('；'))
  pack.sheet = ''
  pack.preview = ''
  pack.avatar = ''
  await verifyImage(files['sheet.img'], pack)
  for (const field of ['preview', 'avatar'] as const) {
    const path = manifest.images[field]
    if (path === undefined) continue
    if (path !== `${field}.img` || !files[path]) throw new Error('素材包缺少头像或预览图片')
    await verifyImage(files[path])
    pack[field] = await imageDataUrl(files[path])
  }
  return { pack, image: await imageDataUrl(files['sheet.img']) }
}
