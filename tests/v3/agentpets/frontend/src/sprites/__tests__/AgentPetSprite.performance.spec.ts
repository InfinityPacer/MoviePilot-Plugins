import { render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import { createMockPet } from '@/dev/mockHost'

it('does not stringify or rewrite the sheet while advancing frames', async () => {
  vi.useFakeTimers()
  const sheet = `data:image/png;base64,${'A'.repeat(1024 * 1024)}`
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
  const viewport = view.container.querySelector<HTMLElement>('.agent-pet-sprites__viewport')!
  const frame = view.container.querySelector<HTMLElement>('.agent-pet-sprites__frame')!
  const original = viewport.style.getPropertyValue('--agent-pet-sprites-sheet')
  const spy = vi.spyOn(JSON, 'stringify')
  const writes = vi.spyOn(viewport.style, 'setProperty')
  await vi.advanceTimersByTimeAsync(350)
  expect(frame.style.backgroundPosition).toBe('100% 0%')
  expect(viewport.style.getPropertyValue('--agent-pet-sprites-sheet')).toBe(original)
  expect(spy.mock.calls.filter(([value]) => value === sheet)).toHaveLength(0)
  expect(writes.mock.calls.filter(([key]) => key === '--agent-pet-sprites-sheet')).toHaveLength(0)
})
