import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { strToU8, zipSync } from 'fflate'
import { exportPackArchive, readPackArchive } from '@/sprites/packArchive'
import { parseCalibration } from '@/sprites/calibration'

const image =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg=='
const pack = {
  id: 'pet',
  name: '自定义名称',
  description: 'Test',
  grid: { cols: 2, rows: 1 },
  sheet: '',
  frames: { idle: 0, blink: 1 },
  actions: { blink: { frames: ['blink', 'idle'], frame_ms: 200, loop: true } },
  random_actions: [],
  action_mappings: { 'intent.thinking': 'blink' },
  calibration: parseCalibration({ left: 0.1 }),
  preview: image,
  avatar: image,
}
beforeEach(() =>
  vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 200, height: 100, close: vi.fn() })),
)
describe('portable AgentPets archive', () => {
  it('preserves high-detail thumbnails beyond the old 49000-byte limit', async () => {
    const bytes = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../../fixtures/texture.png'))
    expect(bytes.length).toBeGreaterThan(49000)
    const texture = `data:image/png;base64,${bytes.toString('base64')}`
    const detailed = { ...pack, preview: texture, avatar: texture }
    const api = {
      get: vi.fn().mockResolvedValue({ success: true, data: { pack: detailed, sheet_src: image, builtin: false } }),
      post: vi.fn(),
    }
    const blob = await exportPackArchive(api, 'AgentPets', 'pet')
    const restored = await readPackArchive(new File([blob], 'texture.agentpets.zip'))
    expect(restored.pack).toEqual(detailed)
  })
  it('roundtrips raw actions, metadata, calibration and exact image bytes', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({ success: true, data: { pack, sheet_src: image, builtin: false } }),
      post: vi.fn(),
    }
    const blob = await exportPackArchive(api, 'AgentPets', 'pet')
    const restored = await readPackArchive(new File([blob], 'pet.agentpets.zip'))
    expect(restored.pack).toEqual(pack)
    expect(restored.image).toBe(image)
    expect(Object.keys(restored.pack.actions)).toEqual(['blink'])
  })
  it('uses only embedded images and removes manifest external image references', async () => {
    const manifest = {
      format: 'agentpets',
      version: 1,
      pack: {
        ...pack,
        sheet: 'https://example.test/sheet.png',
        preview: 'https://example.test/preview.png',
        avatar: 'https://example.test/avatar.png',
      },
      images: { sheet: 'sheet.img' },
    }
    const sheet = Uint8Array.from(atob(image.split(',')[1]), char => char.charCodeAt(0))
    const zip = zipSync({ 'agentpets.json': strToU8(JSON.stringify(manifest)), 'sheet.img': sheet })
    const restored = await readPackArchive(new File([new Uint8Array(zip)], 'pet.zip'))
    expect(restored.pack.sheet).toBe('')
    expect(restored.pack.preview).toBe('')
    expect(restored.pack.avatar).toBe('')
    expect(restored.image).toBe(image)
  })
  it('fails the complete export if a remote image cannot be obtained', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('CORS denied')))
    const api = {
      get: vi.fn().mockResolvedValue({
        success: true,
        data: { pack, sheet_src: 'https://example.test/image.png', builtin: false },
      }),
      post: vi.fn(),
    }
    await expect(exportPackArchive(api, 'AgentPets', 'pet')).rejects.toThrow('CORS denied')
    expect(fetch).toHaveBeenCalledWith(
      'https://example.test/image.png',
      expect.objectContaining({ credentials: 'omit' }),
    )
  })
  it.each(['../sheet.img', 'unknown.bin'])('rejects an unexpected archive path %s', async path => {
    const zip = zipSync({ [path]: new Uint8Array([1]) })
    await expect(readPackArchive(new File([new Uint8Array(zip)], 'bad.zip'))).rejects.toThrow()
  })
  it('rejects missing image, unsupported format and oversized entries', async () => {
    const cases: Record<string, Uint8Array>[] = [
      { 'agentpets.json': strToU8('{}') },
      { 'agentpets.json': strToU8('{"format":"agentpets","version":9}'), 'sheet.img': new Uint8Array([1]) },
      { 'agentpets.json': new Uint8Array(65537), 'sheet.img': new Uint8Array([1]) },
      {
        'agentpets.json': strToU8('{}'),
        'sheet.img': new Uint8Array([1]),
        'preview.img': new Uint8Array(128 * 1024 + 1),
      },
    ]
    for (const entries of cases) {
      await expect(readPackArchive(new File([new Uint8Array(zipSync(entries))], 'bad.zip'))).rejects.toThrow()
    }
  })
})
