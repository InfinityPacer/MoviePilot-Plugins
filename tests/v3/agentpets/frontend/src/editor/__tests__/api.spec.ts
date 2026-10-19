import { describe, expect, it, vi } from 'vitest'
import { normalizePeekAngles } from '@/stage/peek'

import {
  applyDefaultPet,
  checkAvailablePet,
  loadEditor,
  petImage,
  prepareEnabledConfig,
  saveSettings,
  savePetSettings,
  saveSharedSettings,
} from '@/editor/api'

const settings = { scale: 1, speed: 1, roam: 'floor' as const }

function mockHost() {
  let defaultId = 'Other:pet'
  let user: unknown = { plugin_id: 'Other', key: 'personal' }
  const api = {
    get: vi.fn().mockImplementation(async (path: string) => {
      if (path === 'plugin/agent_pets') return [{ plugin_id: 'Clone1', key: 'kurisu' }]
      if (path.startsWith('system/settings'))
        return {
          success: true,
          data: {
            settings: [{ setting_key: 'AI_AGENT_PET', value: defaultId }],
          },
        }
      if (path === 'user/config/AgentPet') return { success: true, data: { value: user } }
      return { success: true, data: { enabled: true, settings, pets: [] } }
    }),
    post: vi.fn().mockImplementation(async (path: string, body: unknown) => {
      if (path === 'system/env') defaultId = (body as { AI_AGENT_PET: string }).AI_AGENT_PET
      if (path === 'user/config/AgentPet') user = body
      return { success: true, data: path.endsWith('/settings') ? body : null }
    }),
  }
  return api
}

describe('Pet editor API', () => {
  it('requires a matching pet identity and verified values before accepting an appearance save', async () => {
    const api = mockHost()
    const values = { scale: 0.7, speed: 1.4 }
    const expected = { scale: 1, speed: 1 }
    api.post.mockResolvedValue({ success: true, data: { key: 'another', ...values } })
    await expect(savePetSettings(api, 'Clone1', 'ying', values, expected)).rejects.toThrow('回读不一致')
    api.post.mockResolvedValue({ success: true, data: { key: 'ying', ...values } })
    expect(await savePetSettings(api, 'Clone1', 'ying', values, expected)).toEqual(values)
    expect(api.post).toHaveBeenLastCalledWith('plugin/Clone1/settings/pet', {
      key: 'ying',
      ...values,
      peek_angles: normalizePeekAngles(undefined),
      expected: { ...expected, peek_angles: normalizePeekAngles(undefined) },
    })
  })

  it('rejects angle readback mismatch and explicitly sends defaults when resetting angles', async () => {
    const api = mockHost()
    const values = { scale: 1, speed: 1, peek_angles: { bottom: 20, left: 30, right: 40 } }
    api.post.mockResolvedValue({ success: true, data: { key: 'ying', scale: 1, speed: 1 } })
    await expect(savePetSettings(api, 'Clone1', 'ying', values, { scale: 1, speed: 1 })).rejects.toThrow('回读不一致')
    expect(await savePetSettings(api, 'Clone1', 'ying', { scale: 1, speed: 1 }, values)).toEqual({ scale: 1, speed: 1 })
    expect(api.post).toHaveBeenLastCalledWith('plugin/Clone1/settings/pet', {
      key: 'ying',
      scale: 1,
      speed: 1,
      peek_angles: normalizePeekAngles(undefined),
      expected: values,
    })
  })

  it('never includes scale or speed in a shared-activity write', async () => {
    const api = mockHost()
    const values = { roam: 'free' as const, movement: 'fixed' as const }
    const expected = { roam: 'floor' as const, movement: 'auto' as const }
    api.post.mockResolvedValue({ success: true, data: values })
    expect(await saveSharedSettings(api, 'Clone1', values, expected)).toEqual(values)
    expect(api.post).toHaveBeenCalledWith('plugin/Clone1/settings/shared', { ...values, expected })
  })

  it('does not send per-pet angles through the legacy shared defaults endpoint', async () => {
    const api = mockHost()
    await saveSettings(api, 'Clone1', { ...settings, peek_angles: { bottom: 20, left: 35, right: 35 } })
    expect(api.post).toHaveBeenCalledWith('plugin/Clone1/settings', { ...settings, movement: 'auto' })
  })

  it('uses bundled builtin avatars and keeps uploaded previews intact', () => {
    const pet = {
      key: 'ying',
      name: '小映',
      description: '',
      mode: 'stage' as const,
      preview: 'ying/avatar.png',
      builtin: true,
    }
    expect(petImage(pet)).toMatch(/\/ying\/avatar\.png$/)
    expect(petImage({ ...pet, builtin: false, preview: 'data:image/png;base64,AAAA' })).toBe(
      'data:image/png;base64,AAAA',
    )
  })

  it('reads an instance-specific editor and saves only activity fields', async () => {
    const api = mockHost()
    expect((await loadEditor(api, 'Clone1')).enabled).toBe(true)
    expect(api.get).toHaveBeenCalledWith('plugin/Clone1/editor')
    expect(await saveSettings(api, 'Clone1', { ...settings, scale: 1.2 })).toEqual({
      ...settings,
      scale: 1.2,
      movement: 'auto',
    })
    expect(api.post).toHaveBeenCalledWith('plugin/Clone1/settings', {
      ...settings,
      scale: 1.2,
      movement: 'auto',
    })
  })

  it('recognizes the bare host catalogue and rejects another instance or missing pet', async () => {
    const api = mockHost()
    await checkAvailablePet(api, 'Clone1', 'kurisu')
    await expect(checkAvailablePet(api, 'AgentPets', 'kurisu')).rejects.toThrow('不可用')
    await expect(checkAvailablePet(api, 'Clone1', 'removed')).rejects.toThrow('不可用')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('sets the system default without changing a personal selection when not requested', async () => {
    const api = mockHost()
    const result = await applyDefaultPet(api, 'Clone1', 'kurisu', false)
    expect(result).toEqual({
      defaultId: 'Clone1:kurisu',
      user: { plugin_id: 'Other', key: 'personal' },
    })
    expect(api.post.mock.calls).toEqual([['system/env', { AI_AGENT_PET: 'Clone1:kurisu' }]])
    expect(api.get.mock.calls.filter(([path]) => path.startsWith('system/settings'))).toHaveLength(2)
  })

  it('only clears the current user override when explicitly requested and verifies it', async () => {
    const api = mockHost()
    expect(await applyDefaultPet(api, 'Clone1', 'kurisu', true)).toEqual({
      defaultId: 'Clone1:kurisu',
      user: null,
    })
    expect(api.post.mock.calls).toEqual([
      ['system/env', { AI_AGENT_PET: 'Clone1:kurisu' }],
      ['user/config/AgentPet', null],
    ])
    expect(api.get.mock.calls.filter(([path]) => path === 'user/config/AgentPet')).toHaveLength(2)
    api.post.mockClear()
    await applyDefaultPet(api, 'Clone1', 'kurisu', true)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('does not change personal preferences after a failed or mismatched default write', async () => {
    const api = mockHost()
    api.post.mockResolvedValue({ success: true, data: null })
    await expect(applyDefaultPet(api, 'Clone1', 'kurisu', true)).rejects.toThrow('尚未确认生效')
    expect(api.post.mock.calls).toEqual([['system/env', { AI_AGENT_PET: 'Clone1:kurisu' }]])
    expect(api.get).not.toHaveBeenCalledWith('user/config/AgentPet')
  })

  it('reports a partial application when personal preference persistence fails', async () => {
    const api = mockHost()
    const original = api.post.getMockImplementation()!
    api.post.mockImplementation(async (path: string, body: unknown) =>
      path === 'user/config/AgentPet' ? { success: false, message: 'denied' } : original(path, body),
    )
    await expect(applyDefaultPet(api, 'Clone1', 'kurisu', true)).rejects.toThrow('系统默认形象已设置')
  })

  it('does not start a write after the page or instance has changed', async () => {
    const api = mockHost()
    let current = true
    const original = api.get.getMockImplementation()!
    api.get.mockImplementation(async (path: string) => {
      const result = await original(path)
      current = false
      return result
    })
    await expect(applyDefaultPet(api, 'Clone1', 'kurisu', true, () => current)).rejects.toHaveProperty(
      'name',
      'AbortError',
    )
    expect(api.post).not.toHaveBeenCalled()
  })

  it('keeps a failed save distinct from success', async () => {
    const api = mockHost()
    api.post.mockResolvedValue({ success: false, message: '不能保存' })
    await expect(saveSettings(api, 'Clone1', settings)).rejects.toThrow('不能保存')
  })
})

describe('enable configuration preparation', () => {
  it.each([null, [], 'invalid'])('rejects invalid full configuration: %j', async value => {
    const api = { get: vi.fn().mockResolvedValue(value), post: vi.fn() }
    await expect(prepareEnabledConfig(api, 'Clone1', false, true)).rejects.toThrow()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('preserves opaque fields and supports an unset enable flag', async () => {
    const latest = { scale: 1.3, future: { keep: true } }
    const api = { get: vi.fn().mockResolvedValue(latest), post: vi.fn() }
    expect(await prepareEnabledConfig(api, 'Clone1', true, false)).toEqual({ ...latest, enabled: true })
    expect(api.post).not.toHaveBeenCalled()
  })
})
