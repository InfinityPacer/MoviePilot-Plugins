import { strToU8, zipSync } from 'fflate'
import { describe, expect, it } from 'vitest'

import { extractCodexPetArchive } from '@/sprites/codexPetArchive'

const WEBP_BYTES = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0x04, 0x00, 0x00, 0x00, 0x57, 0x45, 0x42, 0x50])

function readFileBytes(file: File): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer))
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(file)
  })
}

function petArchive(
  manifest: Record<string, unknown>,
  spritesheet = WEBP_BYTES,
  manifestPath = 'cute-rem/pet.json',
  sheetEntryPath = 'cute-rem/spritesheet.webp',
) {
  const archive = zipSync({
    [manifestPath]: strToU8(JSON.stringify(manifest)),
    [sheetEntryPath]: spritesheet,
  })
  return new File([archive], 'cute-rem.codex-pet.zip', { type: 'application/zip' })
}

describe('Codex Pet ZIP importer', () => {
  it('reads a nested package and extracts the manifest-declared WebP sheet', async () => {
    const file = petArchive({
      id: 'cute-rem',
      displayName: 'Cute Rem',
      description: 'A community pet',
      spritesheetPath: './spritesheet.webp',
    })

    const result = await extractCodexPetArchive(file)

    expect(result.manifest).toMatchObject({
      id: 'cute-rem',
      displayName: 'Cute Rem',
      description: 'A community pet',
    })
    expect(result.spritesheet.name).toBe('spritesheet.webp')
    expect(result.spritesheet.type).toBe('image/webp')
    expect(await readFileBytes(result.spritesheet)).toEqual(WEBP_BYTES)
  })

  it('accepts the flat package layout', async () => {
    const file = petArchive(
      { id: 'cute-rem', spritesheetPath: 'spritesheet.webp' },
      WEBP_BYTES,
      'pet.json',
      'spritesheet.webp',
    )

    await expect(extractCodexPetArchive(file)).resolves.toMatchObject({
      manifest: { id: 'cute-rem' },
      spritesheet: { name: 'spritesheet.webp', type: 'image/webp' },
    })
  })

  it('rejects missing or ambiguous manifests', async () => {
    const missingManifest = new File([zipSync({ 'cute-rem/spritesheet.webp': WEBP_BYTES })], 'cute-rem.codex-pet.zip')
    const duplicateManifests = new File(
      [
        zipSync({
          'a/pet.json': strToU8('{"spritesheetPath":"spritesheet.webp"}'),
          'a/spritesheet.webp': WEBP_BYTES,
          'b/pet.json': strToU8('{"spritesheetPath":"spritesheet.webp"}'),
          'b/spritesheet.webp': WEBP_BYTES,
        }),
      ],
      'cute-rem.codex-pet.zip',
    )

    await expect(extractCodexPetArchive(missingManifest)).rejects.toThrow('缺少 pet.json')
    await expect(extractCodexPetArchive(duplicateManifests)).rejects.toThrow('包含多个 pet.json')
  })

  it('rejects paths that escape the package', async () => {
    const file = petArchive({ spritesheetPath: '../../outside.webp' })

    await expect(extractCodexPetArchive(file)).rejects.toThrow('不能越出压缩包')
  })

  it('rejects oversized archives and extracted sheets', async () => {
    const oversizedArchive = new File([new Uint8Array(8 * 1024 * 1024 + 1)], 'cute-rem.codex-pet.zip')
    const oversizedSheet = petArchive(
      { spritesheetPath: 'spritesheet.webp' },
      new Uint8Array(4 * 1024 * 1024 + 1),
      'pet.json',
      'spritesheet.webp',
    )

    await expect(extractCodexPetArchive(oversizedArchive)).rejects.toThrow('压缩包不能超过 8MB')
    await expect(extractCodexPetArchive(oversizedSheet)).rejects.toThrow('精灵图不能超过 4MB')
  })

  it('rejects package files with a non-image spritesheet', async () => {
    const file = petArchive(
      { spritesheetPath: 'spritesheet.webp' },
      strToU8('not an image'),
      'pet.json',
      'spritesheet.webp',
    )

    await expect(extractCodexPetArchive(file)).rejects.toThrow('只支持 PNG 或 WebP')
  })
})
