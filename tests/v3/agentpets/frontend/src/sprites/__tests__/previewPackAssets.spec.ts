import { render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import { createMockPet } from '@/dev/mockHost'
import { loadImage, withLoadTimeout } from '@/loading'
import { PreviewPackAssets, providePreviewPackAssets } from '@/sprites/previewPackAssets'

vi.mock('@/loading', async importOriginal => ({
  ...(await importOriginal<typeof import('@/loading')>()),
  loadImage: vi.fn(),
}))

const scopes: PreviewPackAssets[] = []
function scope() {
  const assets = new PreviewPackAssets()
  scopes.push(assets)
  return assets
}
function payload(key = 'mine', revision = 'r1', source = 'data:image/png;base64,AAAA') {
  return {
    success: true,
    data: {
      pack: { id: key, name: key, grid: { cols: 1, rows: 1 }, frames: { idle: 0 }, actions: {} },
      sheet_src: source,
      sheet_revision: revision,
    },
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => (resolve = done))
  return { promise, resolve }
}
function api() {
  return { get: vi.fn().mockResolvedValue(payload()), post: vi.fn() }
}
beforeEach(() => {
  vi.mocked(loadImage).mockResolvedValue({ width: 192, height: 208 })
})
afterEach(() => {
  for (const assets of scopes.splice(0)) assets.dispose()
})

describe('editor-scoped pack images', () => {
  it('shares a simultaneous initial request and image load, then revalidates metadata on remount', async () => {
    const assets = scope()
    const client = api()
    const first = deferred<ReturnType<typeof payload>>()
    client.get.mockReturnValueOnce(first.promise)
    const left = assets.load(client, 'Clone1', 'mine')
    const right = assets.load(client, 'Clone1', 'mine')
    expect(right).toBe(left)
    expect(client.get).toHaveBeenCalledTimes(1)
    first.resolve(payload())
    await left
    expect(loadImage).toHaveBeenCalledTimes(1)

    const updated = payload('mine', 'r1', '')
    updated.data.pack.name = 'Renamed'
    updated.data.pack.grid.cols = 2
    client.get.mockResolvedValueOnce(updated)
    const reloaded = await assets.load(client, 'Clone1', 'mine')
    expect(client.get).toHaveBeenLastCalledWith('plugin/Clone1/pack?key=mine&known_sheet=r1')
    expect(reloaded.pack.name).toBe('Renamed')
    expect(reloaded.pack.grid.cols).toBe(2)
    expect(reloaded.dimensions).toEqual({ width: 192, height: 208 })
    expect(loadImage).toHaveBeenCalledTimes(1)
  })

  it('reloads a changed sheet and refuses a missing image with a different revision', async () => {
    const assets = scope()
    const client = api()
    await assets.load(client, 'Clone1', 'mine')
    client.get.mockResolvedValueOnce(payload('mine', 'r2', 'data:image/png;base64,BBBB'))
    expect((await assets.load(client, 'Clone1', 'mine')).sheetRevision).toBe('r2')
    expect(loadImage).toHaveBeenCalledTimes(2)
    client.get.mockResolvedValueOnce(payload('mine', 'r3', ''))
    await expect(assets.load(client, 'Clone1', 'mine')).rejects.toThrow('invalid pack')
    expect(loadImage).toHaveBeenCalledTimes(2)
  })

  it('isolates APIs, plugin instances and Pet IDs', async () => {
    const assets = scope()
    const one = api()
    const two = api()
    one.get.mockImplementation(async (path: string) =>
      payload(new URL(path, 'https://mp.test/').searchParams.get('key')!),
    )
    await assets.load(one, 'Clone1', 'mine')
    await assets.load(two, 'Clone1', 'mine')
    await assets.load(one, 'Clone2', 'mine')
    await assets.load(one, 'Clone1', 'other')
    expect(loadImage).toHaveBeenCalledTimes(4)
    expect(
      [...one.get.mock.calls, ...two.get.mock.calls].every(([path]) => !String(path).includes('known_sheet')),
    ).toBe(true)
  })

  it('does not retain unversioned URL images and permits retry after failure', async () => {
    const assets = scope()
    const client = api()
    client.get
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(payload('mine', '', 'https://mp.test/sheet.png'))
    await expect(assets.load(client, 'Clone1', 'mine')).rejects.toThrow('offline')
    await assets.load(client, 'Clone1', 'mine')
    await assets.load(client, 'Clone1', 'mine')
    expect(client.get).toHaveBeenCalledTimes(3)
    expect(loadImage).toHaveBeenCalledTimes(2)
    expect(client.get.mock.calls.every(([path]) => !String(path).includes('known_sheet'))).toBe(true)
  })

  it('evicts older images instead of retaining every visited Pet', async () => {
    const assets = scope()
    const client = api()
    client.get.mockImplementation(async (path: string) =>
      payload(new URL(path, 'https://mp.test/').searchParams.get('key')!),
    )
    for (const key of ['one', 'two', 'three', 'four', 'five']) await assets.load(client, 'Clone1', key)
    await assets.load(client, 'Clone1', 'one')
    expect(client.get).toHaveBeenLastCalledWith('plugin/Clone1/pack?key=one')
    expect(loadImage).toHaveBeenCalledTimes(6)
  })

  it('keeps real pending requests counted after consumer timeouts and frees capacity on settlement', async () => {
    vi.useFakeTimers()
    const assets = scope()
    const client = api()
    const responses = Array.from({ length: 5 }, () => deferred<ReturnType<typeof payload>>())
    responses.forEach(response => client.get.mockReturnValueOnce(response.promise))
    const pending = ['one', 'two', 'three', 'four'].map(key => assets.load(client, 'Clone1', key))
    const timed = pending.map(operation =>
      withLoadTimeout(operation, new AbortController().signal).catch(() => 'timed out'),
    )
    await vi.advanceTimersByTimeAsync(5100)
    expect(await Promise.all(timed)).toEqual(['timed out', 'timed out', 'timed out', 'timed out'])
    await expect(assets.load(client, 'Clone1', 'five')).rejects.toThrow('busy')
    expect(client.get).toHaveBeenCalledTimes(4)
    responses[0].resolve(payload('one'))
    await pending[0]
    const fifth = assets.load(client, 'Clone1', 'five')
    expect(client.get).toHaveBeenCalledTimes(5)
    ;['two', 'three', 'four', 'five'].forEach((key, index) => responses[index + 1].resolve(payload(key)))
    await Promise.all([...pending, fifth])
  })

  it('prevents late image loading after the editor closes and starts a new editor without old state', async () => {
    const assets = scope()
    const client = api()
    const response = deferred<ReturnType<typeof payload>>()
    client.get.mockReturnValueOnce(response.promise)
    const pending = assets.load(client, 'Clone1', 'mine')
    assets.dispose()
    response.resolve(payload())
    await expect(pending).rejects.toThrow('closed')
    expect(loadImage).not.toHaveBeenCalled()
    await expect(assets.load(client, 'Clone1', 'mine')).rejects.toThrow('closed')
    await scope().load(client, 'Clone1', 'mine')
    expect(client.get).toHaveBeenLastCalledWith('plugin/Clone1/pack?key=mine')
    expect(loadImage).toHaveBeenCalledTimes(1)
  })

  it('lets one preview unmount while its sibling finishes the shared request', async () => {
    const client = api()
    const response = deferred<ReturnType<typeof payload>>()
    client.get.mockReturnValueOnce(response.promise)
    const left = ref(true)
    const Owner = defineComponent({
      setup() {
        providePreviewPackAssets()
        return () =>
          h('div', [
            left.value
              ? h(AgentPetSprite, {
                  key: 'left',
                  api: client,
                  pluginId: 'Clone1',
                  pet: createMockPet('renderer', 'mine'),
                  strictPreview: true,
                  motionActive: false,
                })
              : null,
            h(AgentPetSprite, {
              key: 'right',
              api: client,
              pluginId: 'Clone1',
              pet: createMockPet('renderer', 'mine'),
              strictPreview: true,
              motionActive: false,
            }),
          ])
      },
    })
    const view = render(Owner)
    left.value = false
    await flushPromises()
    response.resolve(payload())
    await flushPromises()
    expect(client.get).toHaveBeenCalledTimes(1)
    expect(loadImage).toHaveBeenCalledTimes(1)
    expect(view.container.querySelector('[data-pack="mine"]')).not.toBeNull()
  })
})

it('bounds retained image data even when fewer than five Pets are visited', async () => {
  const assets = scope()
  const client = api()
  const large = 'data:image/png;base64,' + 'A'.repeat(5 * 1024 * 1024)
  client.get.mockImplementation(async (path: string) =>
    payload(new URL(path, 'https://mp.test/').searchParams.get('key')!, 'r1', large),
  )
  for (const key of ['one', 'two', 'three', 'four']) await assets.load(client, 'Clone1', key)
  await assets.load(client, 'Clone1', 'one')
  expect(client.get).toHaveBeenLastCalledWith('plugin/Clone1/pack?key=one')
  expect(loadImage).toHaveBeenCalledTimes(5)
})
