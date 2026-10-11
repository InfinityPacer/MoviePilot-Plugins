import { strFromU8, unzipSync } from 'fflate'

export const MAX_CODEX_PET_ARCHIVE_BYTES = 8 * 1024 * 1024
const MAX_SPRITESHEET_BYTES = 4 * 1024 * 1024
const MAX_MANIFEST_BYTES = 64 * 1024
const MAX_ARCHIVE_ENTRIES = 256

export interface CodexPetManifest {
  id?: string
  displayName?: string
  description?: string
  spritesheetPath: string
}

export interface ExtractedCodexPet {
  manifest: CodexPetManifest
  spritesheet: File
}

interface ArchiveEntry {
  name: string
  normalizedName: string
}

export function isCodexPetArchive(file: File): boolean {
  return file.name.toLowerCase().endsWith('.codex-pet.zip')
}

function normalizeEntryPath(path: string): string | null {
  const normalized = path.replace(/\\/g, '/')
  if (!normalized || normalized.includes('\0') || normalized.startsWith('/') || /^[a-z]:/i.test(normalized)) {
    return null
  }
  const parts = normalized.split('/')
  if (parts.some(part => part === '..')) return null
  return parts.filter(part => part && part !== '.').join('/')
}

function resolveSpritesheetPath(manifestPath: string, path: string): string {
  const normalized = path.trim().replace(/\\/g, '/')
  if (!normalized || normalized.includes('\0') || normalized.startsWith('/') || /^[a-z]:/i.test(normalized)) {
    throw new Error('pet.json 中的 spritesheetPath 必须是包内相对路径')
  }

  const parts = manifestPath.split('/').slice(0, -1)
  for (const part of normalized.split('/')) {
    if (!part || part === '.') continue
    if (part === '..') {
      if (!parts.length) throw new Error('pet.json 中的 spritesheetPath 不能越出压缩包')
      parts.pop()
    } else parts.push(part)
  }
  if (!parts.length) throw new Error('pet.json 中的 spritesheetPath 无效')
  return parts.join('/')
}

function manifestFromBytes(bytes: Uint8Array): CodexPetManifest {
  let value: unknown
  try {
    value = JSON.parse(strFromU8(bytes))
  } catch {
    throw new Error('pet.json 无法解析，请检查 JSON 格式')
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('pet.json 顶层必须是对象')
  }
  const data = value as Record<string, unknown>
  if (typeof data.spritesheetPath !== 'string' || !data.spritesheetPath.trim()) {
    throw new Error('pet.json 缺少 spritesheetPath')
  }
  return {
    id: typeof data.id === 'string' ? data.id : undefined,
    displayName: typeof data.displayName === 'string' ? data.displayName : undefined,
    description: typeof data.description === 'string' ? data.description : undefined,
    spritesheetPath: data.spritesheetPath,
  }
}

function limitedUnzip(data: Uint8Array, filter: (entry: { name: string; originalSize: number }) => boolean) {
  let entryCount = 0
  let tooManyEntries = false
  let files: ReturnType<typeof unzipSync>
  try {
    files = unzipSync(data, {
      filter: entry => {
        entryCount += 1
        if (entryCount > MAX_ARCHIVE_ENTRIES) {
          tooManyEntries = true
          return false
        }
        return filter(entry)
      },
    })
  } catch {
    throw new Error('Codex Pet ZIP 无法解压，可能已损坏或加密')
  }
  if (tooManyEntries) throw new Error(`压缩包文件数量不能超过 ${MAX_ARCHIVE_ENTRIES} 项`)
  return files
}

function imageType(bytes: Uint8Array): { extension: 'png' | 'webp'; mime: string } {
  if (
    bytes.length >= 8 &&
    bytes[0] === 0x89 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x4e &&
    bytes[3] === 0x47 &&
    bytes[4] === 0x0d &&
    bytes[5] === 0x0a &&
    bytes[6] === 0x1a &&
    bytes[7] === 0x0a
  ) {
    return { extension: 'png', mime: 'image/png' }
  }
  if (
    bytes.length >= 12 &&
    String.fromCharCode(...bytes.subarray(0, 4)) === 'RIFF' &&
    String.fromCharCode(...bytes.subarray(8, 12)) === 'WEBP'
  ) {
    return { extension: 'webp', mime: 'image/webp' }
  }
  throw new Error('Codex Pet 精灵图只支持 PNG 或 WebP')
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
  if (!isCodexPetArchive(file)) throw new Error('压缩包文件名必须以 .codex-pet.zip 结尾')
  if (file.size > MAX_CODEX_PET_ARCHIVE_BYTES) throw new Error('Codex Pet 压缩包不能超过 8MB')

  let archive: Uint8Array
  try {
    archive = await readFileBytes(file)
  } catch {
    throw new Error('无法读取 Codex Pet 压缩包')
  }

  const manifestEntries: ArchiveEntry[] = []
  let oversizedManifest = false
  const manifests = limitedUnzip(archive, entry => {
    const normalizedName = normalizeEntryPath(entry.name)
    if (!normalizedName || normalizedName.split('/').pop()?.toLowerCase() !== 'pet.json') return false
    manifestEntries.push({ name: entry.name, normalizedName })
    if (entry.originalSize > MAX_MANIFEST_BYTES) {
      oversizedManifest = true
      return false
    }
    return true
  })

  if (manifestEntries.length > 1) throw new Error('压缩包包含多个 pet.json，无法确定导入对象')
  if (!manifestEntries.length) throw new Error('Codex Pet 压缩包中缺少 pet.json')
  if (oversizedManifest) throw new Error('pet.json 不能超过 64KB')
  const manifestEntry = manifestEntries[0]
  const manifestBytes = manifests[manifestEntry.name]
  if (!manifestBytes) throw new Error('无法读取 pet.json')

  const manifest = manifestFromBytes(manifestBytes)
  const spritesheetPath = resolveSpritesheetPath(manifestEntry.normalizedName, manifest.spritesheetPath)
  let matchingEntries = 0
  let oversizedSpritesheet = false
  let spritesheetEntryName = ''
  const spritesheets = limitedUnzip(archive, entry => {
    if (normalizeEntryPath(entry.name) !== spritesheetPath) return false
    matchingEntries += 1
    spritesheetEntryName = entry.name
    if (entry.originalSize > MAX_SPRITESHEET_BYTES) {
      oversizedSpritesheet = true
      return false
    }
    return true
  })

  if (matchingEntries > 1) throw new Error('压缩包中存在重复的精灵图路径')
  if (!matchingEntries) throw new Error('找不到 pet.json 指定的精灵图')
  if (oversizedSpritesheet) throw new Error('精灵图不能超过 4MB')

  const spritesheetBytes = spritesheets[spritesheetEntryName]
  if (!spritesheetBytes || spritesheetBytes.length > MAX_SPRITESHEET_BYTES) {
    throw new Error('精灵图内容无效或超过 4MB')
  }
  const type = imageType(spritesheetBytes)
  const filename = spritesheetPath.split('/').pop() || `spritesheet.${type.extension}`
  const spritesheet = new File([spritesheetBytes], filename, { type: type.mime })
  return { manifest, spritesheet }
}
