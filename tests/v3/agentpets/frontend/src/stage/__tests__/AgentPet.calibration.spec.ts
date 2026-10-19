import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'
import { calibrationLayout, parseCalibration } from '@/sprites/calibration'
import { PACK_UPDATED_EVENT } from '@/sprites/mappings'

describe('Ying calibration on the real stage renderer', () => {
  it('reads its own instance, updates after save events and preserves other Pet events', async () => {
    vi.useFakeTimers()
    const host = createMockHost('Clone1')
    host.patch({ motionAllowed: false })
    const initial = builtinDefaultCalibration('ying')
    let saved = parseCalibration({ ...initial, left: 0.1, right: 0.9, offset_x: 0.02 })
    const api = {
      get: vi.fn().mockImplementation(async () => ({ success: true, data: { id: 'ying', calibration: saved } })),
      post: vi.fn(),
    }
    const view = mount(AgentPet, {
      props: {
        agent: host,
        pet: createMockPet('stage', 'ying'),
        api,
        pluginId: 'Clone1',
        settingsOverride: { scale: 1, speed: 1, roam: 'floor', movement: 'auto' },
      },
    })
    const crop = () => view.get('.agent-pet-ying__frame-crop').element as HTMLElement
    try {
      await vi.advanceTimersByTimeAsync(64)
      expect(api.get).toHaveBeenCalledExactlyOnceWith('plugin/Clone1/packs/calibration?key=ying')
      expect(crop().style.width).toBe('125%')
      expect(crop().style.left).toBe(calibrationLayout(saved, 198 / 240).frame.left)
      expect(view.emitted('pack-ready')!.at(-1)![0]).toMatchObject({ id: 'ying', calibration: saved })
      host.emit(PACK_UPDATED_EVENT, { key: 'builtin-kurisu' })
      await vi.advanceTimersByTimeAsync(16)
      expect(api.get).toHaveBeenCalledTimes(1)
      saved = initial
      host.emit(PACK_UPDATED_EVENT, { key: 'ying' })
      await vi.advanceTimersByTimeAsync(32)
      expect(crop().style.width).toBe('100%')
      expect(crop().style.left).toBe('0%')
      expect(api.post).not.toHaveBeenCalled()
    } finally {
      view.unmount()
      host.dispose()
    }
  })

  it('uses preview calibration without saving and never loads Ying for a slotted stage', async () => {
    vi.useFakeTimers()
    const host = createMockHost('Clone1')
    const api = { get: vi.fn(), post: vi.fn() }
    const props = {
      agent: host,
      api,
      pluginId: 'Clone1',
      pet: createMockPet('stage', 'custom'),
      settingsOverride: { scale: 1, speed: 1, roam: 'floor' as const },
    }
    const custom = mount(AgentPet, { props, slots: { default: '<span class="custom-art" />' } })
    try {
      await vi.advanceTimersByTimeAsync(64)
      expect(api.get).not.toHaveBeenCalled()
      expect(custom.find('.custom-art').exists()).toBe(true)
      expect(custom.find('.agent-pet-ying__frame-crop').exists()).toBe(false)
    } finally {
      custom.unmount()
      host.dispose()
    }
  })

  it('clears the previous instance calibration and ignores its late refresh', async () => {
    vi.useFakeTimers()
    const initial = builtinDefaultCalibration('ying')
    const edited = parseCalibration({ ...initial, left: 0.1, right: 0.9 })
    const host = createMockHost('Clone1')
    host.patch({ motionAllowed: false })
    let finishOld!: (value: unknown) => void
    const api = {
      get: vi.fn().mockResolvedValue({ success: true, data: { id: 'ying', calibration: edited } }),
      post: vi.fn(),
    }
    const view = mount(AgentPet, {
      props: {
        agent: host,
        api,
        pluginId: 'Clone1',
        pet: createMockPet('stage', 'ying'),
        settingsOverride: { scale: 1, speed: 1, roam: 'floor' },
      },
    })
    const crop = () => view.get('.agent-pet-ying__frame-crop').element as HTMLElement
    try {
      await vi.advanceTimersByTimeAsync(32)
      expect(crop().style.width).toBe('125%')
      api.get.mockImplementationOnce(
        () =>
          new Promise(resolve => {
            finishOld = resolve
          }),
      )
      host.emit(PACK_UPDATED_EVENT, { key: 'ying' })
      await vi.advanceTimersByTimeAsync(16)
      api.get.mockRejectedValueOnce(new Error('unavailable'))
      await view.setProps({ pluginId: 'Clone2' })
      await vi.advanceTimersByTimeAsync(32)
      expect(crop().style.width).toBe('100%')
      finishOld({ success: true, data: { id: 'ying', calibration: edited } })
      await vi.advanceTimersByTimeAsync(32)
      expect(crop().style.width).toBe('100%')
      expect(api.get).toHaveBeenLastCalledWith('plugin/Clone2/packs/calibration?key=ying')
      expect(api.post).not.toHaveBeenCalled()
    } finally {
      view.unmount()
      host.dispose()
    }
  })
})
