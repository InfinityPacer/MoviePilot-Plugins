import { render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { registerEditor } from '@/editor/presence'
import { createMockHost, createMockPet } from '@/dev/mockHost'

it('suspends global stage work without saving or losing position and resumes after the last editor', async () => {
  vi.useFakeTimers()
  const host = createMockHost('AgentPets'),
    pet = createMockPet('stage', 'ying')
  const save = vi.spyOn(pet.storage!, 'set')
  const view = render(AgentPet, {
    props: { agent: host, pet, settingsOverride: { scale: 1, speed: 1, movement: 'auto', roam: 'free' } },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(50)
  const button = view.container.querySelector<HTMLElement>('button')!
  const position = button.style.transform
  const close = registerEditor(),
    closeSecond = registerEditor()
  const writes = save.mock.calls.length
  expect(vi.getTimerCount()).toBe(0)
  await vi.advanceTimersByTimeAsync(60000)
  expect(button.style.transform).toBe(position)
  expect(save).toHaveBeenCalledTimes(writes)
  close()
  expect(vi.getTimerCount()).toBe(0)
  closeSecond()
  expect(vi.getTimerCount()).toBeGreaterThan(0)
  expect(button.style.transform).toBe(position)
  view.unmount()
  host.dispose()
  expect(vi.getTimerCount()).toBe(0)
})
