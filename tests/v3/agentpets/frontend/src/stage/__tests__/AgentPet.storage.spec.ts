import { render, waitFor } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'

async function setup() {
  const host = createMockHost('AgentPets')
  host.patch({ motionAllowed: false })
  const pet = createMockPet('stage', 'ying')
  const api = {
    get: vi.fn().mockResolvedValue({
      success: true,
      message: '',
      data: { scale: 1, speed: 1, roam: 'floor', movement: 'fixed' },
    }),
  }
  const view = render(AgentPet, {
    props: { agent: host, pet, api, pluginId: 'AgentPets' },
  })
  await waitFor(() => expect(view.getByRole('button', { name: '打开助手（小映）' })).toBeInTheDocument())
  await flushPromises()
  return {
    host,
    pet,
    api,
    view,
    close() {
      view.unmount()
      host.dispose()
    },
  }
}

async function hideAgain(host: ReturnType<typeof createMockHost>) {
  host.patch({ pageVisible: true })
  await flushPromises()
  host.patch({ pageVisible: false })
  await flushPromises()
}

describe('confirmed position persistence', () => {
  it('retries the same position after a failure and deduplicates only after success', async () => {
    const f = await setup()
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const save = vi.spyOn(f.pet.storage, 'set').mockRejectedValueOnce(new Error('offline'))
    try {
      f.host.patch({ pageVisible: false })
      await flushPromises()
      expect(save).toHaveBeenCalledTimes(1)
      expect(await f.pet.storage.get()).toBeNull()
      await hideAgain(f.host)
      expect(save).toHaveBeenCalledTimes(2)
      expect(await f.pet.storage.get()).toEqual(save.mock.calls[1][0])
      await hideAgain(f.host)
      expect(save).toHaveBeenCalledTimes(2)
      expect(warning).toHaveBeenCalledWith('[AgentPets] position not saved')
    } finally {
      f.close()
    }
  })

  it('does not start overlapping writes, then honours the next requested save after failure', async () => {
    const f = await setup()
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    let reject!: (reason: Error) => void
    const save = vi.spyOn(f.pet.storage, 'set').mockImplementationOnce(
      () =>
        new Promise<void>((_resolve, fail) => {
          reject = fail
        }),
    )
    try {
      f.host.patch({ pageVisible: false })
      await flushPromises()
      await hideAgain(f.host)
      expect(save).toHaveBeenCalledTimes(1)
      reject(new Error('offline'))
      await flushPromises()
      expect(save).toHaveBeenCalledTimes(2)
      expect(await f.pet.storage.get()).toEqual(save.mock.calls[1][0])
    } finally {
      f.close()
    }
  })

  it('old completion cannot mark the next Pet as saved', async () => {
    const f = await setup()
    let resolve!: () => void
    const oldSave = vi.spyOn(f.pet.storage, 'set').mockImplementationOnce(
      () =>
        new Promise<void>(done => {
          resolve = done
        }),
    )
    const next = createMockPet('stage', 'ying')
    const nextSave = vi.spyOn(next.storage, 'set')
    try {
      f.host.patch({ pageVisible: false })
      await flushPromises()
      await f.view.rerender({ pet: next, pluginId: 'AnotherInstance' })
      resolve()
      await flushPromises()
      expect(nextSave).not.toHaveBeenCalled()
      await hideAgain(f.host)
      expect(nextSave).toHaveBeenCalledTimes(1)
      await hideAgain(f.host)
      expect(nextSave).toHaveBeenCalledTimes(1)
      expect(oldSave).toHaveBeenCalledTimes(1)
    } finally {
      f.close()
    }
  })
  it('does not start a queued save when the component has unmounted', async () => {
    const f = await setup()
    let finish!: () => void
    const save = vi.spyOn(f.pet.storage, 'set').mockImplementationOnce(
      () =>
        new Promise<void>(resolve => {
          finish = resolve
        }),
    )
    try {
      f.host.patch({ pageVisible: false })
      await flushPromises()
      await hideAgain(f.host)
      expect(save).toHaveBeenCalledTimes(1)
      f.view.unmount()
      finish()
      await flushPromises()
      expect(save).toHaveBeenCalledTimes(1)
    } finally {
      f.host.dispose()
    }
  })
})
