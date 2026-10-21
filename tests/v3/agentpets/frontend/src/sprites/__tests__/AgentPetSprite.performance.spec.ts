import { render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import { createMockPet } from '@/dev/mockHost'
import { createMockHost } from '@/dev/mockHost'
import { PACK_UPDATED_EVENT } from '@/sprites/mappings'

it('does not stringify or rewrite the sheet while advancing frames', async () => {
  vi.useFakeTimers()
  const sheet = `data:image/png;base64,${'A'.repeat(3 * 1024 * 1024)}`
  const api = {
    get: vi.fn().mockResolvedValue({
      success: true,
      data: {
        pack: {
          id: 'mine',
          name: 'Mine',
          grid: { cols: 2, rows: 1 },
          frames: { idle: 0, next: 1 },
          actions: { idle: { frames: ['idle', 'next'], frame_ms: 100, loop: true } },
        },
        sheet_src: sheet,
      },
    }),
    post: vi.fn(),
  }
  const view = render(AgentPetSprite, { props: { api, pluginId: 'AgentPets', pet: createMockPet('renderer', 'mine') } })
  await flushPromises()
  const frame = view.container.querySelector<HTMLElement>('.agent-pet-sprites__frame')!
  const original = frame.style.backgroundImage
  expect(original.includes(sheet)).toBe(true)
  expect(frame.style.backgroundSize).toBe('200% 100%')
  const spy = vi.spyOn(JSON, 'stringify')
  const writes = vi.spyOn(frame.style, 'setProperty')
  await vi.advanceTimersByTimeAsync(350)
  expect(frame.style.backgroundPosition).toBe('100% 0%')
  expect(frame.style.backgroundImage === original).toBe(true)
  expect(spy.mock.calls.filter(([value]) => value === sheet)).toHaveLength(0)
  expect(writes.mock.calls.filter(([key]) => key === 'background-image' || key === 'background-size')).toHaveLength(0)
})

it.each(['renderer', 'stage'] as const)(
  'draws a large %s sheet when the browser rejects oversized custom properties',
  async mode => {
    const nativeSetProperty = CSSStyleDeclaration.prototype.setProperty
    vi.spyOn(CSSStyleDeclaration.prototype, 'setProperty').mockImplementation(function (
      this: CSSStyleDeclaration,
      property,
      value,
      priority,
    ) {
      // The target Chromium drops this value; jsdom otherwise accepts it and masks blank sprites.
      if (property.startsWith('--') && (value?.length ?? 0) > 2 * 1024 * 1024) return
      nativeSetProperty.call(this, property, value, priority)
    })
    const sheet = `data:image/webp;base64,${'A'.repeat(3 * 1024 * 1024)}`
    const api = {
      get: vi.fn().mockResolvedValue({
        success: true,
        data: {
          pack: { id: 'large', name: 'Large', grid: { cols: 1, rows: 1 }, frames: { idle: 0 }, actions: {} },
          sheet_src: sheet,
        },
      }),
      post: vi.fn(),
    }
    const view = render(AgentPetSprite, { props: { api, pluginId: 'AgentPets', pet: createMockPet(mode, 'large') } })
    await flushPromises()
    const frame = view.container.querySelector<HTMLElement>('.agent-pet-sprites__frame')!
    expect(view.container.querySelector('[data-pack="large"]')).not.toBeNull()
    expect(frame.style.backgroundImage.includes(sheet)).toBe(true)
    expect(frame.style.backgroundSize).toBe('100% 100%')
    expect(
      view.container
        .querySelector<HTMLElement>('.agent-pet-sprites__viewport')!
        .style.getPropertyValue('--agent-pet-sprites-sheet'),
    ).toBe('')
  },
)

it('keeps a confirmed image when a metadata response reports the same revision', async () => {
  const host = createMockHost('AgentPets')
  const data = {
    pack: { id: 'mine', name: 'Mine', grid: { cols: 1, rows: 1 }, frames: { idle: 0 }, actions: {} },
    sheet_src: 'data:image/png;base64,AAAA',
    sheet_revision: 'revision-1',
  }
  const api = { get: vi.fn().mockResolvedValue({ success: true, data }), post: vi.fn() }
  const view = render(AgentPetSprite, {
    props: { api, agent: host, pluginId: 'AgentPets', pet: createMockPet('renderer', 'mine') },
  })
  await flushPromises()
  const frame = view.container.querySelector<HTMLElement>('.agent-pet-sprites__frame')!
  const original = frame.style.backgroundImage
  expect(original.includes(data.sheet_src)).toBe(true)
  const writes = vi.spyOn(frame.style, 'setProperty')
  const image = vi.spyOn(globalThis, 'Image')
  api.get.mockResolvedValue({ success: true, data: { ...data, sheet_src: '' } })
  host.emit(PACK_UPDATED_EVENT, { key: 'mine' })
  await flushPromises()
  expect(api.get).toHaveBeenLastCalledWith('plugin/AgentPets/pack?key=' + 'mine' + '&known_sheet=' + 'revision-1')
  expect(image).not.toHaveBeenCalled()
  expect(view.container.querySelector('[data-pack="mine"]')).not.toBeNull()
  expect(frame.style.backgroundImage).toBe(original)
  expect(writes.mock.calls.filter(([key]) => key === 'background-image')).toHaveLength(0)
  view.unmount()
  host.dispose()
})

it('updates the direct image once when a new sheet revision is confirmed', async () => {
  vi.useFakeTimers()
  const host = createMockHost('AgentPets')
  const pack = {
    id: 'mine',
    name: 'Mine',
    grid: { cols: 2, rows: 1 },
    frames: { idle: 0, next: 1 },
    actions: { idle: { frames: ['idle', 'next'], frame_ms: 100, loop: true } },
  }
  const api = {
    get: vi.fn().mockResolvedValue({
      success: true,
      data: { pack, sheet_src: 'data:image/png;base64,AAAA', sheet_revision: 'revision-1' },
    }),
    post: vi.fn(),
  }
  const view = render(AgentPetSprite, {
    props: { api, agent: host, pluginId: 'AgentPets', pet: createMockPet('renderer', 'mine') },
  })
  await flushPromises()
  const frame = view.container.querySelector<HTMLElement>('.agent-pet-sprites__frame')!
  const writes = vi.spyOn(frame.style, 'setProperty')
  api.get.mockResolvedValue({
    success: true,
    data: { pack, sheet_src: 'data:image/png;base64,BBBB', sheet_revision: 'revision-2' },
  })
  host.emit(PACK_UPDATED_EVENT, { key: 'mine' })
  await flushPromises()
  expect(frame.style.backgroundImage).toContain('data:image/png;base64,BBBB')
  await vi.advanceTimersByTimeAsync(350)
  expect(writes.mock.calls.filter(([key]) => key === 'background-image')).toHaveLength(1)
  expect(writes.mock.calls.filter(([key]) => key === 'background-size')).toHaveLength(0)
  view.unmount()
  host.dispose()
})
