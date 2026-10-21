import { render } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import { BUILTIN_PACKS, withCodexStageActions } from '@/sprites/schema'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'
import { builtinAvatar } from '@/editor/avatars'
import { createMockPet } from '@/dev/mockHost'
import source from '@/assets/packs/builtin-kurisu-z256/pack.json'

const KEY = 'builtin-kurisu-z256'

describe('Z256 Kurisu packaged Codex Pet', () => {
  it('retains original actions and uses the same stage adaptation as imported Codex Pets', () => {
    const pack = BUILTIN_PACKS[KEY]
    expect(pack.codex_version).toBe('v2')
    expect(pack.description).toBe('z256专属')
    for (const [key, action] of Object.entries(source.actions)) {
      expect(pack.actions[key]).toMatchObject(action)
    }
    for (const key of ['peek', 'running-left', 'running-right', 'waving', 'jumping', 'review']) {
      expect(pack.actions[key].frames.length).toBeGreaterThan(0)
    }
    expect(withCodexStageActions(pack)).toEqual(pack)
    expect(builtinAvatar(KEY)).toContain(`/packs/${KEY}/avatar.png`)
  })

  it('loads the lossless WebP render and reads only instance-scoped calibration', async () => {
    vi.useFakeTimers()
    const calibration = builtinDefaultCalibration(KEY)
    const api = {
      get: vi.fn().mockResolvedValue({ success: true, data: { id: KEY, calibration } }),
      post: vi.fn(),
    }
    const view = render(AgentPetSprite, {
      props: {
        pet: createMockPet('stage', KEY),
        api,
        pluginId: 'Clone1',
        mappingKey: 'stage.walk-left',
        action: 'running-left',
      },
    })
    await vi.advanceTimersByTimeAsync(32)
    const root = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    expect(root.dataset.pack).toBe(KEY)
    expect(root.dataset.action).toBe('running-left')
    const frame = root.querySelector('.agent-pet-sprites__frame') as HTMLElement
    expect(frame.style.backgroundImage).toContain(`/packs/${KEY}/sheet.webp`)
    expect(api.get).toHaveBeenCalledExactlyOnceWith(`plugin/Clone1/packs/calibration?key=${KEY}`)
    expect(api.post).not.toHaveBeenCalled()
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
