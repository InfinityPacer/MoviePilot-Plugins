import { render } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import type { AgentRect } from '@/host'
import type { RoamMode } from '@/stage/geometry'
import { SETTINGS_EVENT } from '@/stage/settings'

function pointer(type: string, clientX: number, clientY: number) {
  const event = new MouseEvent(type, { bubbles: true, button: 0, clientX, clientY })
  Object.defineProperty(event, 'pointerId', { value: 1 })
  return event
}

async function setup(
  motionAllowed = false,
  fixed = false,
  storedEdge?: string,
  storedPosition = { xRatio: 0.5, yRatio: 0.5 },
  roam: RoamMode = 'free',
) {
  vi.useFakeTimers()
  vi.spyOn(Math, 'random').mockReturnValue(0.9)
  vi.stubGlobal('innerWidth', 1280)
  vi.stubGlobal('innerHeight', 800)
  const visual = Object.assign(new EventTarget(), { width: 1280, height: 800, offsetLeft: 0, offsetTop: 0 })
  vi.stubGlobal('visualViewport', visual)
  const host = createMockHost('AgentPets')
  host.patch({ motionAllowed })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'ying', { onAnchor: rect => anchors.push(rect) })
  await pet.storage.set({ ...storedPosition, ...(storedEdge ? { peekEdge: storedEdge } : {}) })
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      aspectRatio: 1,
      peekEye: { x: 0.35, y: 0.3 },
      settingsOverride: { scale: 1, speed: 1, roam, movement: fixed ? 'fixed' : 'auto' },
    },
  })
  await vi.advanceTimersByTimeAsync(64)
  const button = view.container.querySelector('button')!
  const root = view.container.querySelector('.agent-pet-ying')!
  const rect = () => anchors.at(-1)!
  const drop = (x: number, y: number) => {
    const peeking = !!root.getAttribute('data-peek-edge')
    button.dispatchEvent(pointer('pointerdown', rect().x + 10, rect().y + 10))
    window.dispatchEvent(pointer('pointermove', x + (peeking ? 60 : 10), y + (peeking ? 36 : 10)))
    window.dispatchEvent(pointer('pointerup', x + (peeking ? 60 : 10), y + (peeking ? 36 : 10)))
  }
  return {
    host,
    pet,
    view,
    button,
    root,
    rect,
    drop,
    visual,
    unmount() {
      view.unmount()
      host.dispose()
    },
  }
}

describe('stable bottom-corner peeking', () => {
  it('applies saved angles to the formal stage and receives matching-pet saves including reset', async () => {
    const stage = await setup(false, false, 'bottom', { xRatio: 0, yRatio: 1 })
    try {
      const artwork = () => stage.root.querySelector<HTMLElement>('.agent-pet-ying__artwork')!.style.transform
      await stage.view.rerender({
        settingsOverride: { scale: 1, speed: 1, roam: 'free', peek_angles: { bottom: 20, left: 25, right: 30 } },
      })
      await vi.advanceTimersByTimeAsync(32)
      expect(artwork()).toContain('rotate(-20deg)')
      stage.host.emit(SETTINGS_EVENT, { key: 'other', peek_angles: { bottom: 10, left: 35, right: 35 } })
      await vi.advanceTimersByTimeAsync(32)
      expect(artwork()).toContain('rotate(-20deg)')
      stage.host.emit(SETTINGS_EVENT, { key: 'ying', peek_angles: { bottom: 35, left: 35, right: 35 } })
      await vi.advanceTimersByTimeAsync(32)
      expect(artwork()).toContain('rotate(-35deg)')
      stage.host.emit(SETTINGS_EVENT, { key: 'ying', peek_angles: { bottom: 0, left: 35, right: 35 } })
      await vi.advanceTimersByTimeAsync(32)
      expect(artwork()).toContain('rotate(0deg)')
    } finally {
      stage.unmount()
    }
  })
  it('ignores preview angle overrides outside a contained preview', async () => {
    const stage = await setup(false, false, 'bottom', { xRatio: 0, yRatio: 1 })
    try {
      const artwork = stage.root.querySelector<HTMLElement>('.agent-pet-ying__artwork')!
      expect(artwork.style.transform).toContain('rotate(0deg)')
      await stage.view.rerender({ previewPeekAngle: 20 })
      expect(artwork.style.transform).toContain('rotate(0deg)')
    } finally {
      stage.unmount()
    }
  })

  it.each([
    { corner: 'left', sideRoll: 0.75, edge: 'left' },
    { corner: 'right', sideRoll: 0.75, edge: 'right' },
    { corner: 'left', sideRoll: 0.25, edge: 'bottom' },
    { corner: 'right', sideRoll: 0.25, edge: 'bottom' },
  ])(
    'automatically peeks from $edge at the $corner corner and exits without becoming pinned',
    async ({ corner, sideRoll, edge }) => {
      const stage = await setup(true, false, undefined, { xRatio: corner === 'left' ? 0 : 1, yRatio: 1 }, 'floor')
      try {
        // The initial 0.9 draw schedules the idle decision at 13.2 seconds, between blink timers.
        await vi.advanceTimersByTimeAsync(13_135)
        expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
        vi.mocked(Math.random)
          .mockReturnValueOnce(0.1)
          .mockReturnValueOnce(corner === 'left' ? 0.1 : 0.9)
          .mockReturnValueOnce(sideRoll)
        await vi.advanceTimersByTimeAsync(33)
        expect(stage.root.getAttribute('data-peek-edge')).toBe(edge)
        await vi.advanceTimersByTimeAsync(3000)
        expect(stage.root.getAttribute('data-peek-phase')).toBe('look')
        expect(stage.root.getAttribute('data-peek-edge')).toBe(edge)
        await vi.advanceTimersByTimeAsync(6000)
        expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
        expect(stage.root.getAttribute('data-motion')).not.toBe('peek')
      } finally {
        stage.unmount()
      }
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it.each(['fixed', 'free', 'motion-off'])('does not randomly peek in %s mode', async mode => {
    const stage = await setup(
      mode !== 'motion-off',
      mode === 'fixed',
      undefined,
      { xRatio: 0, yRatio: 1 },
      mode === 'free' ? 'free' : 'floor',
    )
    const seen = new Set<string>()
    const watch = window.setInterval(() => {
      const edge = stage.root.getAttribute('data-peek-edge')
      if (edge) seen.add(edge)
    }, 32)
    try {
      vi.mocked(Math.random).mockReturnValue(0.1)
      await vi.advanceTimersByTimeAsync(40000)
      expect(seen.size).toBe(0)
    } finally {
      window.clearInterval(watch)
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it('cancels a pending side peek if the agent becomes busy while walking to the corner', async () => {
    const stage = await setup(true, false, undefined, { xRatio: 0.5, yRatio: 1 }, 'floor')
    try {
      await vi.advanceTimersByTimeAsync(13_135)
      vi.mocked(Math.random).mockReturnValueOnce(0.1).mockReturnValueOnce(0.1).mockReturnValueOnce(0.75)
      await vi.advanceTimersByTimeAsync(33)
      expect(stage.root.getAttribute('data-motion')).toBe('walk')
      stage.host.patch({ phase: 'thinking', thinking: true })
      await vi.advanceTimersByTimeAsync(10000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.root.getAttribute('data-motion')).not.toBe('walk')
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([
    ['left', 0, 680],
    ['right', 1160, 680],
  ] as const)('parks at the %s bottom corner and restores the whole body on drag', async (_side, x, y) => {
    const stage = await setup()
    try {
      stage.drop(x, y)
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.root.getAttribute('data-peek-edge')).toBe('bottom')
      expect(stage.root.getAttribute('data-motion')).toBe('peek')
      expect(stage.root.getAttribute('data-pose')).toBe('alert')
      expect(stage.root.getAttribute('data-peek-phase')).toBe('look')
      expect(parseFloat(stage.button.style.width)).toBeGreaterThanOrEqual(48)
      expect(parseFloat(stage.button.style.height)).toBeGreaterThanOrEqual(48)
      expect(stage.button.style.clipPath).toBe('')
      const stable = { ...stage.rect() }
      await vi.advanceTimersByTimeAsync(30000)
      expect(stage.rect()).toEqual(stable)
      stage.drop(300, 250)
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.rect()).toEqual({ x: 300, y: 250, width: 120, height: 120 })
    } finally {
      stage.unmount()
    }
  })

  it('finishes tilting while hidden, then rises vertically with fixed angle and horizontal position', async () => {
    const stage = await setup(true)
    try {
      await stage.view.rerender({
        settingsOverride: { scale: 1, speed: 1, roam: 'free', peek_angles: { bottom: 35, left: 35, right: 35 } },
      })
      stage.drop(0, 680)
      await vi.advanceTimersByTimeAsync(400)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('tuck')
      const artwork = stage.root.querySelector('.agent-pet-ying__artwork') as HTMLElement
      expect(artwork.style.transform).toBe('rotate(0deg)')
      await vi.advanceTimersByTimeAsync(300)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('pause')
      expect(artwork.style.transform).toBe('rotate(0deg)')
      const clip = stage.root.querySelector('.agent-pet-ying__clip') as HTMLElement
      expect(clip.style.height).toBe('0px')
      const tucked = { ...stage.rect() }
      await vi.advanceTimersByTimeAsync(200)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('pause')
      expect(clip.style.height).toBe('0px')
      expect(stage.rect()).toEqual(tucked)
      await vi.advanceTimersByTimeAsync(250)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('tilt')
      const tilt = () => Number(artwork.style.transform.slice(7, -4))
      expect(tilt()).toBeLessThan(0)
      expect(tilt()).toBeGreaterThan(-35)
      expect(clip.style.height).toBe('0px')
      await vi.advanceTimersByTimeAsync(350)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('look')
      expect(artwork.style.transform).toBe('rotate(-35deg)')
      const horizontal = artwork.style.left
      const anchorX = stage.rect().x
      await vi.advanceTimersByTimeAsync(400)
      expect(artwork.style.transform).toBe('rotate(-35deg)')
      expect(artwork.style.left).toBe(horizontal)
      expect(stage.rect().x).toBe(anchorX)
      expect(parseFloat(clip.style.height)).toBeGreaterThan(0)
      const risingHeight = parseFloat(clip.style.height)
      await vi.advanceTimersByTimeAsync(1400)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('look')
      expect(artwork.style.transform).toBe('rotate(-35deg)')
      expect(artwork.style.left).toBe(horizontal)
      expect(stage.rect().x).toBe(anchorX)
      expect(parseFloat(clip.style.height)).toBeGreaterThan(risingHeight)
      const stable = { ...stage.rect() }
      await vi.advanceTimersByTimeAsync(16000)
      expect(stage.rect()).toEqual(stable)
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([400, 800, 1200, 1700])('returns continuously when the agent interrupts peeking at %d ms', async delay => {
    const stage = await setup(true)
    try {
      stage.drop(0, 680)
      await vi.advanceTimersByTimeAsync(delay)
      const artwork = stage.root.querySelector('.agent-pet-ying__artwork') as HTMLElement
      const before = artwork.style.cssText
      stage.host.patch({ phase: 'thinking', thinking: true })
      await vi.advanceTimersByTimeAsync(0)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('leave')
      expect(artwork.style.cssText).toBe(before)
      await vi.advanceTimersByTimeAsync(800)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(artwork.style.transform).toBe('rotate(0deg)')
      const clip = stage.root.querySelector('.agent-pet-ying__clip') as HTMLElement
      expect(clip.style.height).toBe('120px')
      expect(Math.round(stage.rect().height)).toBe(120)
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([400, 1200, 1700])('clears the hide or reveal phase when dragged away at %d ms', async delay => {
    const stage = await setup(true)
    try {
      stage.drop(0, 680)
      await vi.advanceTimersByTimeAsync(delay)
      stage.drop(300, 250)
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.rect()).toEqual({ x: 300, y: 250, width: 120, height: 120 })
      const artwork = stage.root.querySelector('.agent-pet-ying__artwork') as HTMLElement
      expect(artwork.style.transform).toBe('rotate(0deg)')
      stage.drop(0, 680)
      await vi.advanceTimersByTimeAsync(400)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('tuck')
      expect(artwork.style.transform).toBe('rotate(0deg)')
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each([400, 1200, 1700])('settles into the final eye pose when motion is disabled at %d ms', async delay => {
    const stage = await setup(true)
    try {
      stage.drop(0, 680)
      await vi.advanceTimersByTimeAsync(delay)
      stage.host.patch({ motionAllowed: false })
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('look')
      const artwork = stage.root.querySelector('.agent-pet-ying__artwork') as HTMLElement
      expect(artwork.style.transform).toBe('rotate(0deg)')
      const stable = { ...stage.rect() }
      await vi.advanceTimersByTimeAsync(16000)
      expect(stage.rect()).toEqual(stable)
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps a saved bottom corner across keyboard and orientation changes', async () => {
    const stage = await setup(false, false, 'bottom')
    try {
      expect(stage.root.getAttribute('data-peek-edge')).toBe('bottom')
      stage.visual.width = 390
      stage.visual.height = 420
      stage.visual.offsetTop = 40
      stage.visual.dispatchEvent(new Event('resize'))
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.rect().x).toBeCloseTo(0)
      expect(stage.rect().y).toBeGreaterThanOrEqual(40)
      expect(stage.rect().y + stage.rect().height).toBeLessThanOrEqual(460)
      expect(stage.root.getAttribute('data-motion')).toBe('peek')
    } finally {
      stage.unmount()
    }
  })

  it.each(['left', 'right'] as const)('hides into the lower %s side and remains draggable', async edge => {
    const stage = await setup(true)
    try {
      stage.drop(edge === 'left' ? 0 : 1160, 600)
      await vi.advanceTimersByTimeAsync(700)
      expect(stage.root.getAttribute('data-peek-edge')).toBe(edge)
      expect(stage.root.getAttribute('data-peek-phase')).toBe('pause')
      const clip = stage.root.querySelector('.agent-pet-ying__clip') as HTMLElement
      expect(clip.style.width).toBe('0px')
      expect(parseFloat(stage.button.style.width)).toBeGreaterThanOrEqual(48)
      await vi.advanceTimersByTimeAsync(2100)
      const artwork = stage.root.querySelector('.agent-pet-ying__artwork') as HTMLElement
      expect(artwork.style.transform).toBe(edge === 'left' ? 'rotate(35deg)' : 'rotate(-35deg)')
      expect(parseFloat(clip.style.width)).toBeGreaterThan(0)
      const stable = { ...stage.rect() }
      await vi.advanceTimersByTimeAsync(10000)
      expect(stage.rect()).toEqual(stable)
      stage.drop(300, 250)
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.rect()).toEqual({ x: 300, y: 250, width: 120, height: 120 })
    } finally {
      stage.unmount()
    }
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['left', 'right'] as const)('restores a saved lower %s side through viewport changes', async edge => {
    const stage = await setup(false, false, edge, { xRatio: edge === 'left' ? 0 : 1, yRatio: 0.9 })
    try {
      expect(stage.root.getAttribute('data-peek-edge')).toBe(edge)
      stage.visual.width = 390
      stage.visual.height = 420
      stage.visual.offsetTop = 40
      stage.visual.dispatchEvent(new Event('resize'))
      await vi.advanceTimersByTimeAsync(64)
      expect(stage.root.getAttribute('data-peek-edge')).toBe(edge)
      expect(stage.rect().y).toBeGreaterThanOrEqual(40)
      expect(stage.rect().y + stage.rect().height).toBeLessThanOrEqual(460)
      if (edge === 'left') expect(stage.rect().x).toBeCloseTo(0)
      else expect(stage.rect().x + stage.rect().width).toBeCloseTo(390)
    } finally {
      stage.unmount()
    }
  })

  it('lands after leaving a side peek in floor mode instead of hovering', async () => {
    const stage = await setup(true)
    try {
      await stage.view.rerender({ settingsOverride: { scale: 1, speed: 1, roam: 'floor', movement: 'auto' } })
      await vi.advanceTimersByTimeAsync(1500)
      stage.drop(0, 600)
      await vi.advanceTimersByTimeAsync(2800)
      expect(stage.root.getAttribute('data-peek-edge')).toBe('left')
      stage.host.patch({ phase: 'thinking', thinking: true })
      await vi.advanceTimersByTimeAsync(2000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(Math.round(stage.rect().y + stage.rect().height)).toBe(800)
    } finally {
      stage.unmount()
    }
  })

  it.each(['top', 'left', 'right'])('does not revive old %s docking outside the lower corners', async edge => {
    const stage = await setup(false, false, edge)
    try {
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.rect().height).toBe(120)
    } finally {
      stage.unmount()
    }
  })

  it.each([
    [120, 0],
    [0, 250],
    [1160, 250],
    [300, 680],
  ])('does not hide when dropped away from a bottom corner at %d, %d', async (x, y) => {
    const stage = await setup(true)
    try {
      stage.drop(x, y)
      await vi.advanceTimersByTimeAsync(2200)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.rect()).toEqual({ x, y, width: 120, height: 120 })
    } finally {
      stage.unmount()
    }
  })

  it('does not auto-peek in fixed mode, even with a stored edge', async () => {
    const stage = await setup(false, true, 'bottom')
    try {
      stage.drop(120, 680)
      await vi.advanceTimersByTimeAsync(20000)
      expect(stage.root.getAttribute('data-peek-edge')).toBeNull()
      expect(stage.rect().height).toBe(120)
    } finally {
      stage.unmount()
    }
  })
})
