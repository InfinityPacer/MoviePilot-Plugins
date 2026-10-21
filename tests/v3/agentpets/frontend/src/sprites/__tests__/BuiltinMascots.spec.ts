import { render } from '@testing-library/vue'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPetCodex from '@/stage/AgentPetCodex.vue'
import AgentPetSprite from '@/sprites/AgentPetSprite.vue'
import CalibrationMarkers from '@/editor/CalibrationMarkers.vue'
import { parseCalibration, type Calibration } from '@/sprites/calibration'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import { BUILTIN_PACKS, builtinAsset, resolveAction, validatePack } from '@/sprites/schema'
import { builtinAvatar } from '@/editor/avatars'
import { builtinDefaultCalibration } from '@/sprites/builtinCalibration'
import type { AgentRect } from '@/host'

const keys = ['builtin-chibiterasu', 'builtin-nailong', 'builtin-kurisu'] as const
const sizes = { 'builtin-chibiterasu': [1280, 1390], 'builtin-nailong': [3840, 2484], 'builtin-kurisu': [3072, 3312] }
const hosts: ReturnType<typeof createMockHost>[] = []
afterEach(() => hosts.splice(0).forEach(host => host.dispose()))

describe('offline built-in frame mascots', () => {
  it.each(keys)('mirrors only %s inward when peeking from the left, then restores its native artwork', async key => {
    vi.useFakeTimers()
    vi.stubGlobal('innerWidth', 1280)
    vi.stubGlobal('innerHeight', 800)
    const host = createMockHost('Clone1')
    hosts.push(host)
    host.patch({ motionAllowed: false })
    const anchors: Array<AgentRect | null> = []
    const view = render(AgentPetCodex, {
      props: {
        agent: host,
        pet: createMockPet('stage', key, { onAnchor: rect => anchors.push(rect) }),
        pluginId: 'Clone1',
        api: {
          get: vi.fn().mockResolvedValue({ success: true, data: { scale: 1, speed: 1, roam: 'floor' } }),
          post: vi.fn(),
        },
      },
    })
    await vi.advanceTimersByTimeAsync(32)
    const root = view.container.querySelector('.agent-pet-ying') as HTMLElement
    const sprite = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    const size = { ...anchors.at(-1)! }
    const pointer = (type: string, clientX: number, clientY: number) => {
      const event = new MouseEvent(type, { bubbles: true, button: 0, clientX, clientY })
      Object.defineProperty(event, 'pointerId', { value: 1 })
      return event
    }
    for (const [side, edge] of [
      ['left', 'bottom'],
      ['right', 'bottom'],
      ['left', 'left'],
      ['right', 'right'],
      ['none', 'none'],
    ]) {
      const rect = anchors.at(-1)!
      const x = side === 'left' ? 0 : side === 'right' ? 1280 - size.width : 600
      const y = 800 - size.height - (edge === 'bottom' || edge === 'none' ? 0 : size.height / 2)
      const offset = root.dataset.peekEdge ? { x: size.width / 2, y: size.height * 0.3 } : { x: 10, y: 10 }
      view.getByRole('button').dispatchEvent(pointer('pointerdown', rect.x + 10, rect.y + 10))
      window.dispatchEvent(pointer('pointermove', x + offset.x, y + offset.y))
      window.dispatchEvent(pointer('pointerup', x + offset.x, y + offset.y))
      await vi.advanceTimersByTimeAsync(64)
      expect(root.dataset.peekEdge ?? 'none').toBe(edge)
      const mirrored = key === 'builtin-chibiterasu' && side === 'left'
      expect(sprite.dataset.mirrored).toBe(String(mirrored))
      expect((sprite.querySelector('.agent-pet-sprites__crop') as HTMLElement).style.transform).toBe(
        mirrored ? 'scaleX(-1)' : '',
      )
    }
    expect(view.getByRole('button')).toBeInTheDocument()
  })
  it.each(keys)('registers %s without pretending it is a Codex sheet', key => {
    const pack = BUILTIN_PACKS[key]
    expect(pack.codex_version).toBeUndefined()
    expect(validatePack(pack).errors).toEqual([])
    expect(Object.keys(pack.actions)).toHaveLength(36)
    expect(builtinAvatar(key)).toContain(`/packs/${key}/avatar.png`)
    expect(builtinAsset('sheet.webp', 'https://example.test/assets/remoteEntry.js', key)).toBe(
      `https://example.test/assets/packs/${key}/sheet.webp`,
    )
    expect(resolveAction(pack, 'thinking', null, false, { mappingKey: 'stage.held' }).key).toBe('drag')
    expect(resolveAction(pack, 'jumping', null, false, { mappingKey: 'stage.fall' }).key).toBe('fall')
  })

  it.each(keys)('loads %s from packaged assets and uses its own size and native thinking action', async key => {
    vi.useFakeTimers()
    class LoadedImage {
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      naturalWidth = sizes[key][0]
      naturalHeight = sizes[key][1]
      set src(_value: string) {
        void Promise.resolve().then(() => this.onload?.())
      }
    }
    vi.stubGlobal('Image', LoadedImage)
    const host = createMockHost('Clone1')
    hosts.push(host)
    host.patch({ motionAllowed: false })
    const api = {
      get: vi.fn().mockImplementation(async (path: string) => ({
        success: true,
        data: path.includes('/packs/calibration?')
          ? { id: key, calibration: builtinDefaultCalibration(key) }
          : { scale: 0.8, speed: 1.3, roam: 'floor' },
      })),
      post: vi.fn(),
    }
    const view = render(AgentPetCodex, {
      props: { agent: host, pet: createMockPet('stage', key), api, pluginId: 'Clone1' },
    })
    await vi.advanceTimersByTimeAsync(32)
    expect(api.get.mock.calls).toEqual(
      expect.arrayContaining([[`plugin/Clone1/settings?key=${key}`], [`plugin/Clone1/packs/calibration?key=${key}`]]),
    )
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(api.post).not.toHaveBeenCalled()
    const sprite = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    expect(sprite.dataset.pack).toBe(key)
    expect(view.getByRole('button', { name: `打开助手（${BUILTIN_PACKS[key].name}）` })).toBeInTheDocument()
    host.patch({ phase: 'thinking', thinking: true })
    await vi.advanceTimersByTimeAsync(32)
    expect(sprite.dataset.action).toBe('think')
    expect(sprite.dataset.frame).toBe(BUILTIN_PACKS[key].actions.think.frames[0])
    const baseline = BUILTIN_PACKS[key].action_baselines?.think ?? BUILTIN_PACKS[key].calibration!.baseline
    expect(parseFloat((sprite.querySelector('.agent-pet-sprites__frame') as HTMLElement).style.top)).toBeCloseTo(
      (1 - baseline) * 100,
    )
    const spriteFrame = sprite.querySelector('.agent-pet-sprites__frame') as HTMLElement
    expect(spriteFrame.style.backgroundImage).toContain(`/packs/${key}/sheet.webp`)
  })

  it.each(['builtin-nailong', 'builtin-kurisu'])(
    'keeps a fixed per-action baseline without shifting %s airborne frames',
    async key => {
      vi.useFakeTimers()
      const view = render(AgentPetSprite, { props: { pet: createMockPet('stage', key), nativeAction: 'idle' } })
      await vi.advanceTimersByTimeAsync(0)
      const frame = () => view.container.querySelector('.agent-pet-sprites__frame') as HTMLElement
      const top = frame().style.top
      expect(parseFloat(top)).toBeCloseTo((1 - BUILTIN_PACKS[key].action_baselines!.idle) * 100)
      await vi.advanceTimersByTimeAsync(400)
      expect(frame().style.top).toBe(top)
      for (const action of ['think', 'sleep', 'running-left', 'jump', 'fall', 'drag', 'climb-wall']) {
        await view.rerender({ nativeAction: action })
        const baseline = BUILTIN_PACKS[key].action_baselines?.[action] ?? 1
        expect(parseFloat(frame().style.top)).toBeCloseTo((1 - baseline) * 100)
      }
    },
  )

  it('keeps repeated landmark edits from accumulating a native action baseline', async () => {
    vi.useFakeTimers()
    const key = 'builtin-kurisu'
    const original = builtinDefaultCalibration(key)
    const saved = parseCalibration({ ...original, baseline: original.baseline - 0.02 })
    const view = mount(AgentPetSprite, {
      props: {
        pet: createMockPet('stage', key),
        nativeAction: 'peek',
        editCalibration: true,
        calibrationOverride: saved,
        onCalibrationChange: (value: Calibration) => {
          void view.setProps({ calibrationOverride: value })
        },
      },
    })
    try {
      await vi.advanceTimersByTimeAsync(32)
      const markers = view.getComponent(CalibrationMarkers)
      for (const offset of [0.01, 0.02]) {
        const rendered = markers.props('modelValue')
        markers.vm.$emit('update:modelValue', { ...rendered, offset_x: offset })
        await vi.advanceTimersByTimeAsync(16)
        const emitted = view.emitted('calibration-change')!.at(-1)![0] as Calibration
        expect(emitted.baseline).toBe(saved.baseline)
        expect(emitted.offset_x).toBe(offset)
      }
    } finally {
      view.unmount()
    }
  })

  it('plays different hold times per frame and still stops on a non-looping final frame', async () => {
    vi.useFakeTimers()
    const api = {
      get: vi.fn().mockResolvedValue({
        success: true,
        data: {
          pack: {
            id: 'timed',
            name: 'Timed',
            grid: { cols: 3, rows: 1 },
            frames: { idle: 0, second: 1, last: 2 },
            actions: {
              idle: { frames: ['idle', 'second', 'last'], frame_ms: 70, frame_durations: [70, 250, 400], loop: false },
            },
          },
          sheet_src: 'data:image/png;base64,AAAA',
        },
      }),
      post: vi.fn(),
    }
    const view = render(AgentPetSprite, { props: { pet: createMockPet('renderer', 'timed'), api } })
    const root = view.container.querySelector('.agent-pet-sprites') as HTMLElement
    await vi.advanceTimersByTimeAsync(0)
    expect(root.dataset.frame).toBe('idle')
    await vi.advanceTimersByTimeAsync(70)
    expect(root.dataset.frame).toBe('second')
    await vi.advanceTimersByTimeAsync(249)
    expect(root.dataset.frame).toBe('second')
    await vi.advanceTimersByTimeAsync(1)
    expect(root.dataset.frame).toBe('last')
    await vi.advanceTimersByTimeAsync(4000)
    expect(root.dataset.frame).toBe('last')
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([
    { durations: [40] },
    { durations: [40, 5001] },
    { durations: [false, 80] },
    { durations: [33, 100] },
    { durations: '40,80' },
  ])('rejects invalid per-frame timing %j', ({ durations: frame_durations }) => {
    expect(
      validatePack({
        name: 'Timed',
        grid: { cols: 2, rows: 1 },
        frames: { idle: 0, next: 1 },
        actions: { idle: { frames: ['idle', 'next'], frame_durations } },
      }).errors.length,
    ).toBeGreaterThan(0)
  })
})
