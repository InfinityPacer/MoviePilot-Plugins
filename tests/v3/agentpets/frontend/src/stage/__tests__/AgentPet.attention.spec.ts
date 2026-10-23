import { fireEvent, render } from '@testing-library/vue'
import { flushPromises } from '@vue/test-utils'
import { h } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentPet from '@/stage/AgentPet.vue'
import { createMockHost, createMockPet } from '@/dev/mockHost'
import { registerEditor } from '@/editor/presence'
import type { AgentRect } from '@/host'

const hosts: ReturnType<typeof createMockHost>[] = []
const editors: Array<() => void> = []
const surfaces: HTMLElement[] = []

afterEach(() => {
  editors.splice(0).forEach(close => close())
  hosts.splice(0).forEach(host => host.dispose())
  surfaces.splice(0).forEach(surface => surface.remove())
})

async function setup(
  directions = true,
  previewRoot: HTMLElement | null = null,
  fixed = true,
  roam: 'free' | 'surfaces' = 'free',
) {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-22T00:00:00Z'))
  vi.spyOn(Math, 'random').mockReturnValue(0.5)
  const host = createMockHost('AgentPets')
  hosts.push(host)
  host.patch({ isMobile: false })
  const anchors: Array<AgentRect | null> = []
  const pet = createMockPet('stage', 'attention', { onAnchor: rect => anchors.push(rect) })
  if (roam === 'surfaces') await pet.storage.set({ xRatio: 0.5, yRatio: 0.1 })
  const save = vi.spyOn(pet.storage, 'set')
  const view = render(AgentPet, {
    props: {
      agent: host,
      pet,
      pluginId: 'AgentPets',
      lookDirections: directions,
      artworkReady: true,
      aspectRatio: 0.8,
      previewRoot,
      settingsOverride: { scale: 1, speed: 1, roam, movement: fixed ? 'fixed' : 'auto' },
    },
    slots: { default: ({ gazeAction }: { gazeAction?: string }) => h('span', { 'data-native-look': gazeAction }) },
  })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(32)
  await fireEvent(window, new Event('pointerdown'))
  const root = view.container.querySelector<HTMLElement>('.agent-pet-ying')!
  const button = view.getByRole('button')
  const rect = () => anchors.at(-1)!
  const point = (side: 'right' | 'left' | 'up' = 'right') => {
    const r = rect()
    return side === 'right'
      ? { x: r.x + r.width + 30, y: r.y + r.height / 2 }
      : side === 'left'
        ? { x: r.x - 30, y: r.y + r.height / 2 }
        : { x: r.x + r.width / 2, y: r.y - 30 }
  }
  const inside = () => {
    const r = rect()
    return { x: r.x + r.width * 0.8, y: r.y + r.height / 2 }
  }
  async function pointer(type: string, p = point(), kind = 'mouse', target: Element | Window = window, extra = {}) {
    const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: p.x, clientY: p.y })
    Object.defineProperties(event, {
      pointerId: { value: 1 },
      pointerType: { value: kind },
      isPrimary: { value: true },
      ...Object.fromEntries(Object.entries(extra).map(([key, value]) => [key, { value }])),
    })
    await fireEvent(target, event)
    return event
  }
  async function advance(ms: number) {
    await vi.advanceTimersByTimeAsync(ms)
    await flushPromises()
  }
  return {
    host,
    pet,
    save,
    view,
    root,
    button,
    rect,
    point,
    inside,
    pointer,
    advance,
    gaze: () => root.dataset.gaze,
    attention: () => root.dataset.attention,
    pose: () => root.dataset.pose,
  }
}

describe('stage nearby attention', () => {
  it('waits 350ms and keeps looking without moving or timing out for a stationary pointer', async () => {
    const pet = await setup(true, null, false)
    const position = pet.button.style.transform
    await pet.pointer('pointermove')
    await pet.advance(349)
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1)
    expect(pet.gaze()).toBe('look-090')
    expect(pet.attention()).toBe('mouse')
    expect(pet.button.style.transform).toBe(position)
    await pet.advance(120000)
    expect(pet.gaze()).toBe('look-090')
    expect(pet.attention()).toBe('mouse')
    expect(pet.root.dataset.motion).toBe('idle')
    expect(pet.button.style.transform).toBe(position)
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('accepts movement within the nearby region without restarting the dwell', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(200)
    const near = pet.point()
    await pet.pointer('pointermove', { x: near.x + 10, y: near.y })
    await pet.advance(149)
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1)
    expect(pet.gaze()).toBe('look-090')
  })

  it('rejects a fast pass and starts a fresh dwell after leaving', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(200)
    await pet.pointer('pointermove', { x: 0, y: 0 })
    await pet.advance(1000)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointermove')
    await pet.advance(349)
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1)
    expect(pet.gaze()).toBe('look-090')
  })

  it('updates only an active gaze with rate limiting and resets on leaving the viewport', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
    await pet.pointer('pointermove', pet.point('up'))
    expect(pet.gaze()).toBe('look-090')
    await pet.advance(120)
    expect(pet.gaze()).toBe('look-000')
    await fireEvent(window, new MouseEvent('pointerout', { relatedTarget: null }))
    expect(pet.gaze()).toBeUndefined()
  })

  it('flushes the latest rate-limited position even when the mouse stops moving', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.pointer('pointermove', pet.point('up'))
    await pet.advance(60)
    await pet.pointer('pointermove', pet.point('left'))
    await pet.advance(59)
    expect(pet.gaze()).toBe('look-090')
    await pet.advance(1)
    expect(pet.gaze()).toBe('look-270')
    await pet.advance(10000)
    expect(pet.gaze()).toBe('look-270')
  })

  it('holds its gaze for a 300ms exit grace without following distant motion or extending the deadline', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.pointer('pointermove', pet.point('up'))
    await pet.pointer('pointermove', { x: 0, y: 0 })
    await pet.advance(200)
    await pet.pointer('pointermove', { x: 20, y: 20 })
    await pet.advance(99)
    expect(pet.gaze()).toBe('look-090')
    await pet.advance(1)
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1000)
    expect(pet.attention()).toBeUndefined()
  })

  it('cancels an exit when the pointer returns and respects the distance hysteresis band', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    const r = pet.rect()
    const radius = Math.min(96, Math.max(48, r.height / 2))
    await pet.pointer('pointermove', { x: r.x + r.width + radius + 16, y: r.y + r.height / 2 })
    await pet.advance(500)
    expect(pet.gaze()).toBe('look-090')
    await pet.pointer('pointermove', { x: 0, y: 0 })
    await pet.advance(299)
    await pet.pointer('pointermove', pet.point('left'))
    await pet.advance(1000)
    expect(pet.gaze()).toBe('look-270')
    expect(pet.attention()).toBe('mouse')
  })

  it('resumes autonomous exploration after leaving without storing the gaze or its position', async () => {
    const pet = await setup(true, null, false)
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.advance(12000)
    expect(pet.root.dataset.motion).toBe('idle')
    await pet.pointer('pointermove', { x: 0, y: 0 })
    await pet.advance(300)
    expect(pet.attention()).toBeUndefined()
    for (let elapsed = 0; elapsed < 14000 && pet.root.dataset.motion !== 'walk'; elapsed += 50) await pet.advance(50)
    expect(pet.root.dataset.motion).toBe('walk')
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('can rearm after an initial center dead zone without requiring a distant exit', async () => {
    const pet = await setup()
    const r = pet.rect()
    await pet.pointer('pointermove', { x: r.x + r.width / 2, y: r.y + r.height / 2 })
    await pet.advance(350)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
  })

  it.each(['moves', 'disappears'] as const)(
    'rechecks a stationary pointer when its supporting card %s',
    async cause => {
      let top = 400
      const card = document.createElement('div')
      card.className = 'v-card'
      card.getBoundingClientRect = () => new DOMRect(0, top, 1024, 100)
      surfaces.push(card)
      document.body.append(card)
      const pet = await setup(true, null, false, 'surfaces')
      expect(pet.rect().y + pet.rect().height).toBe(top)
      await pet.pointer('pointermove')
      await pet.advance(350)
      expect(pet.gaze()).toBe('look-090')
      if (cause === 'moves') {
        top -= 40
        await fireEvent(window, new Event('scroll'))
        await pet.advance(600)
        expect(pet.rect().y + pet.rect().height).toBe(top)
        expect(pet.gaze()).toBe('look-112-5')
        top = 150
      } else card.remove()
      await fireEvent(window, new Event('scroll'))
      await pet.advance(1000)
      expect(pet.gaze()).toBeUndefined()
      expect(pet.attention()).toBeUndefined()
      expect(pet.save).not.toHaveBeenCalled()
    },
  )

  it('waves at low frequency without directional art and never invents a look frame', async () => {
    const pet = await setup(false)
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.pose()).toBe('wave')
    expect(pet.attention()).toBe('mouse')
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1200)
    expect(pet.attention()).toBeUndefined()
    await pet.pointer('pointermove')
    await pet.advance(10000)
    expect(pet.attention()).toBeUndefined()
  })

  it.each(['touch', 'pen'])('does not use %s pointer movement as desktop hover', async kind => {
    const pet = await setup()
    await pet.pointer('pointermove', pet.point(), kind)
    await pet.advance(1000)
    expect(pet.gaze()).toBeUndefined()
  })

  it('ignores pressed buttons, non-primary pointers and compatibility mouse movement on mobile', async () => {
    const pet = await setup()
    await pet.pointer('pointermove', pet.point(), 'mouse', window, { buttons: 1 })
    await pet.advance(400)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointermove', pet.point(), 'mouse', window, { isPrimary: false })
    await pet.advance(400)
    expect(pet.gaze()).toBeUndefined()
    pet.host.patch({ isMobile: true })
    await pet.pointer('pointermove')
    await pet.advance(400)
    expect(pet.gaze()).toBeUndefined()
  })

  it.each(['busy', 'hidden', 'reduced', 'editor', 'blur'] as const)(
    'cleans a pending dwell when %s interrupts and does not replay it',
    async cause => {
      const pet = await setup()
      await pet.pointer('pointermove')
      await pet.advance(200)
      if (cause === 'busy') pet.host.patch({ phase: 'thinking', thinking: true })
      if (cause === 'hidden') pet.host.patch({ pageVisible: false })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: false, reducedMotion: true })
      if (cause === 'editor') editors.push(registerEditor())
      if (cause === 'blur') await fireEvent(window, new Event('blur'))
      await pet.advance(1000)
      expect(pet.gaze()).toBeUndefined()
      if (cause === 'busy') pet.host.patch({ phase: 'idle', thinking: false })
      if (cause === 'hidden') pet.host.patch({ pageVisible: true })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: true, reducedMotion: false })
      if (cause === 'editor') editors.pop()!()
      await pet.advance(1000)
      expect(pet.gaze()).toBeUndefined()
    },
  )

  it('never overrides host completion feedback and releases timers when unmounted', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    pet.host.fire('agent.done')
    await flushPromises()
    expect(pet.gaze()).toBeUndefined()
    expect(pet.pose()).toBe('victory')
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBeUndefined()
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps fallback waves on the shared cooldown instead of repeatedly greeting on reentry', async () => {
    const pet = await setup(false)
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.pointer('pointermove', { x: 0, y: 0 })
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.attention()).toBeUndefined()
    await pet.pointer('pointerdown', pet.inside(), 'mouse', pet.button)
    await pet.advance(450)
    expect(pet.root.dataset.reaction).toBeUndefined()
    await pet.pointer('pointerup', pet.inside())
  })

  it('does not consume long-press feedback and can gaze again during that feedback cooldown', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.pointer('pointermove', { x: 0, y: 0 })
    await pet.advance(300)
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
    await pet.pointer('pointerdown', pet.inside(), 'mouse', pet.button)
    await pet.advance(450)
    expect(pet.gaze()).toBeUndefined()
    expect(pet.root.dataset.reaction).toBe('wave')
    await pet.pointer('pointerup', pet.inside())
    await pet.advance(1200)
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
  })

  it.each(['busy', 'hidden', 'reduced', 'editor', 'blur', 'resize', 'mobile', 'artwork', 'settings'] as const)(
    'clears sustained gaze and any trailing update across %s without replay',
    async cause => {
      const pet = await setup()
      await pet.pointer('pointermove')
      await pet.advance(350)
      expect(pet.gaze()).toBe('look-090')
      await pet.pointer('pointermove', pet.point('up'))
      if (cause === 'busy') pet.host.patch({ phase: 'tool' })
      if (cause === 'hidden') pet.host.patch({ pageVisible: false })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: false })
      if (cause === 'editor') editors.push(registerEditor())
      if (cause === 'blur') await fireEvent(window, new Event('blur'))
      if (cause === 'resize') await fireEvent(window, new Event('resize'))
      if (cause === 'mobile') pet.host.patch({ isMobile: true })
      if (cause === 'artwork') await pet.view.rerender({ artworkReady: false })
      if (cause === 'settings')
        await pet.view.rerender({ settingsOverride: { scale: 1, speed: 1.5, roam: 'free', movement: 'fixed' } })
      await flushPromises()
      expect(pet.gaze()).toBeUndefined()
      pet.host.patch({ phase: 'idle', pageVisible: true, motionAllowed: true, isMobile: false })
      if (cause === 'editor') editors.pop()!()
      if (cause === 'artwork') await pet.view.rerender({ artworkReady: true })
      await pet.advance(1000)
      expect(pet.gaze()).toBeUndefined()
      pet.view.unmount()
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it('lets mouse dragging interrupt sustained gaze without a trailing frame taking over', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.pointer('pointermove', pet.point('up'))
    const point = pet.inside()
    await pet.pointer('pointerdown', point, 'mouse', pet.button)
    await pet.pointer('pointermove', { x: point.x + 10, y: point.y })
    await pet.advance(500)
    expect(pet.root.dataset.motion).toBe('drag')
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointercancel', point)
    expect(pet.gaze()).toBeUndefined()
  })

  it('clears a gaze when direction capability is removed and ignores contained previews', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.view.rerender({ lookDirections: false })
    expect(pet.gaze()).toBeUndefined()
    pet.view.unmount()
    const preview = document.createElement('div')
    const next = await setup(true, preview)
    await next.pointer('pointermove')
    await next.advance(350)
    expect(next.gaze()).toBeUndefined()
  })

  it('does not replay attention or pass it to another pet after an instance/key switch', async () => {
    const pet = await setup()
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
    await pet.view.rerender({ pluginId: 'Clone2', pet: createMockPet('stage', 'another') })
    await flushPromises()
    expect(pet.gaze()).toBeUndefined()
    await pet.advance(1200)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointermove')
    await pet.advance(350)
    expect(pet.gaze()).toBe('look-090')
  })

  it('ends gaze on a page click and leaves normal keyboard-style clicks available', async () => {
    const pet = await setup()
    const open = vi.spyOn(pet.host, 'open')
    await pet.pointer('pointermove')
    await pet.advance(350)
    await pet.pointer('pointerdown', { x: 0, y: 0 })
    expect(pet.gaze()).toBeUndefined()
    await fireEvent.click(pet.button, { detail: 0 })
    expect(open).toHaveBeenCalledTimes(1)
  })
})

async function setupTouch(directions = true, fixed = true, previewRoot: HTMLElement | null = null) {
  const pet = await setup(directions, previewRoot, fixed)
  pet.host.patch({
    isMobile: true,
    viewport: { width: 390, height: 768, keyboardInset: 0, safeArea: { top: 0, right: 0, bottom: 0, left: 0 } },
  })
  await pet.advance(32)
  const background = document.createElement('div')
  document.body.append(background)
  surfaces.push(background)
  const point = () => ({ x: pet.rect().x + pet.rect().width / 2, y: 20 })
  const tap = async (p = point(), target: Element = background, duration = 80) => {
    const down = await pet.pointer('pointerdown', p, 'touch', target)
    await pet.advance(duration)
    const up = await pet.pointer('pointerup', p, 'touch', target)
    return { down, up }
  }
  return { ...pet, background, farPoint: point, tap }
}

describe('stage page touch attention', () => {
  it('looks at a distant background tap for two seconds after release without consuming page input', async () => {
    const pet = await setupTouch()
    const open = vi.spyOn(pet.host, 'open')
    const pageClick = vi.fn()
    pet.background.addEventListener('click', pageClick)
    const p = pet.farPoint()
    const position = pet.button.style.transform
    const down = await pet.pointer('pointerdown', p, 'touch', pet.background)
    await pet.advance(300)
    expect(pet.gaze()).toBeUndefined()
    const up = await pet.pointer('pointerup', p, 'touch', pet.background)
    expect(pet.gaze()).toBe('look-000')
    expect(pet.attention()).toBe('touch')
    expect(down.defaultPrevented).toBe(false)
    expect(up.defaultPrevented).toBe(false)
    await fireEvent.click(pet.background)
    expect(pageClick).toHaveBeenCalledTimes(1)
    expect(open).not.toHaveBeenCalled()
    await pet.advance(1999)
    expect(pet.gaze()).toBe('look-000')
    await pet.advance(1)
    expect(pet.gaze()).toBeUndefined()
    expect(pet.button.style.transform).toBe(position)
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('updates every completed tap immediately and renews the deadline without shared cooldown', async () => {
    const pet = await setupTouch()
    await pet.tap()
    await pet.tap(pet.point('left'), pet.background, 10)
    expect(pet.gaze()).toBe('look-270')
    for (let i = 0; i < 12; i++) {
      await pet.tap(pet.farPoint(), pet.background, 10)
      expect(pet.gaze()).toBe('look-000')
      await pet.tap(pet.point('left'), pet.background, 10)
      expect(pet.gaze()).toBe('look-270')
    }
    await pet.advance(1999)
    expect(pet.gaze()).toBe('look-270')
    await pet.advance(1)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    await pet.advance(450)
    expect(pet.root.dataset.reaction).toBe('wave')
    await pet.pointer('pointerup', pet.inside(), 'touch', pet.button)
  })

  it('tolerates small finger jitter without requiring a precise hold duration', async () => {
    const pet = await setupTouch()
    const p = pet.farPoint()
    await pet.pointer('pointerdown', p, 'touch', pet.background)
    await pet.pointer('pointermove', { x: p.x + 9, y: p.y }, 'touch', pet.background)
    await pet.advance(400)
    await pet.pointer('pointerup', p, 'touch', pet.background)
    expect(pet.gaze()).toBe('look-000')
  })

  it.each(['drag', 'release-moved', 'hold', 'cancel', 'scroll', 'contextmenu', 'multitouch'] as const)(
    'does not mistake %s for a background tap or replay it later',
    async cause => {
      const pet = await setupTouch()
      const p = pet.farPoint()
      await pet.pointer('pointerdown', p, 'touch', pet.background)
      if (cause === 'drag') {
        await pet.pointer('pointermove', { x: p.x + 10, y: p.y }, 'touch', pet.background)
        await pet.pointer('pointermove', p, 'touch', pet.background)
      }
      if (cause === 'hold') await pet.advance(450)
      if (cause === 'cancel') await pet.pointer('pointercancel', p, 'touch', pet.background)
      if (cause === 'scroll') await fireEvent(pet.background, new Event('scroll'))
      if (cause === 'contextmenu') await fireEvent.contextMenu(pet.background)
      if (cause === 'multitouch')
        await pet.pointer('pointerdown', p, 'touch', pet.background, { pointerId: 2, isPrimary: false })
      await pet.pointer('pointerup', cause === 'release-moved' ? { x: p.x + 10, y: p.y } : p, 'touch', pet.background)
      expect(pet.gaze()).toBeUndefined()
      await pet.advance(2100)
      expect(pet.gaze()).toBeUndefined()
      await pet.tap()
      expect(pet.gaze()).toBe('look-000')
    },
  )

  it.each([
    '<button><span>button</span></button>',
    '<a href="#"><span>link</span></a>',
    '<input>',
    '<textarea></textarea>',
    '<select><option>option</option></select>',
    '<label><span>label</span></label>',
    '<summary><span>summary</span></summary>',
    '<div contenteditable="true"><span>editor</span></div>',
    '<div tabindex="0"><span>focusable</span></div>',
    '<div role="switch"><span>switch</span></div>',
    '<div role="slider"><span>slider</span></div>',
    '<div role="tab"><span>tab</span></div>',
    '<div class="v-card--link"><span>card</span></div>',
    '<div class="v-list-item"><span>item</span></div>',
    '<div class="v-field"><span>field</span></div>',
    '<div class="v-overlay__scrim"></div>',
    '<div role="dialog"><span>dialog</span></div>',
    '<div draggable="true"><span>drag</span></div>',
  ])('ignores controls and their descendants: %s', async html => {
    const pet = await setupTouch()
    pet.background.innerHTML = html
    const target = pet.background.querySelector('span') ?? pet.background.firstElementChild!
    await pet.tap(pet.farPoint(), target)
    expect(pet.gaze()).toBeUndefined()
  })

  it('honors cancelled page input, detached targets and controls introduced during a gesture', async () => {
    const pet = await setupTouch()
    pet.background.addEventListener('pointerdown', event => event.preventDefault(), { once: true })
    const { down } = await pet.tap()
    expect(down.defaultPrevented).toBe(true)
    expect(pet.gaze()).toBeUndefined()
    pet.background.addEventListener('pointerup', event => event.preventDefault(), { once: true })
    const { up } = await pet.tap()
    expect(up.defaultPrevented).toBe(true)
    expect(pet.gaze()).toBeUndefined()
    await pet.pointer('pointerdown', pet.farPoint(), 'touch', pet.background)
    pet.background.remove()
    await pet.pointer('pointerup', pet.farPoint(), 'touch', document.body)
    expect(pet.gaze()).toBeUndefined()
    document.body.append(pet.background)
    await pet.pointer('pointerdown', pet.farPoint(), 'touch', pet.background)
    pet.background.setAttribute('role', 'button')
    await pet.pointer('pointerup', pet.farPoint(), 'touch', pet.background)
    expect(pet.gaze()).toBeUndefined()
  })

  it('clears active touch gaze for scroll and controls even when a control stops propagation', async () => {
    const pet = await setupTouch()
    await pet.tap()
    await fireEvent(pet.background, new Event('scroll'))
    expect(pet.gaze()).toBeUndefined()
    await pet.tap()
    const control = document.createElement('button')
    pet.background.append(control)
    control.addEventListener('pointerdown', event => event.stopPropagation())
    await pet.tap(pet.farPoint(), control)
    expect(pet.gaze()).toBeUndefined()
  })

  it.each(['busy', 'hidden', 'reduced', 'editor', 'blur', 'resize', 'artwork', 'switch'] as const)(
    'discards an unfinished tap when %s interrupts',
    async cause => {
      const pet = await setupTouch()
      await pet.pointer('pointerdown', pet.farPoint(), 'touch', pet.background)
      if (cause === 'busy') pet.host.patch({ phase: 'thinking', thinking: true })
      if (cause === 'hidden') pet.host.patch({ pageVisible: false })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: false, reducedMotion: true })
      if (cause === 'editor') editors.push(registerEditor())
      if (cause === 'blur') await fireEvent(window, new Event('blur'))
      if (cause === 'resize') await fireEvent(window, new Event('resize'))
      if (cause === 'artwork') await pet.view.rerender({ lookDirections: false })
      if (cause === 'switch') await pet.view.rerender({ pluginId: 'Clone2', pet: createMockPet('stage', 'another') })
      await pet.advance(1)
      if (cause === 'busy') pet.host.patch({ phase: 'idle', thinking: false })
      if (cause === 'hidden') pet.host.patch({ pageVisible: true })
      if (cause === 'reduced') pet.host.patch({ motionAllowed: true, reducedMotion: false })
      if (cause === 'editor') editors.pop()!()
      if (cause === 'artwork') await pet.view.rerender({ lookDirections: true })
      await pet.pointer('pointerup', pet.farPoint(), 'touch', pet.background)
      expect(pet.gaze()).toBeUndefined()
      await pet.advance(2100)
      expect(pet.gaze()).toBeUndefined()
    },
  )

  it('does not steal working feedback or touch gestures inside the assistant panel', async () => {
    const pet = await setupTouch()
    pet.host.patch({ panelRect: { x: 0, y: 0, width: 390, height: 300 } })
    await pet.tap()
    expect(pet.gaze()).toBeUndefined()
    pet.host.patch({ panelRect: null })
    await pet.tap()
    expect(pet.gaze()).toBe('look-000')
    pet.host.fire('agent.done')
    await flushPromises()
    expect(pet.gaze()).toBeUndefined()
    expect(pet.pose()).toBe('victory')
    await pet.tap()
    expect(pet.gaze()).toBeUndefined()
  })

  it('pauses autonomous walking for a tap and resumes after its gaze expires', async () => {
    const pet = await setupTouch(true, false)
    for (let elapsed = 0; elapsed < 14000 && pet.root.dataset.motion !== 'walk'; elapsed += 50) await pet.advance(50)
    expect(pet.root.dataset.motion).toBe('walk')
    await pet.tap()
    expect(pet.attention()).toBe('touch')
    expect(pet.root.dataset.motion).toBe('idle')
    await pet.advance(2000)
    expect(pet.gaze()).toBeUndefined()
    for (let elapsed = 0; elapsed < 14000 && pet.root.dataset.motion !== 'walk'; elapsed += 50) await pet.advance(50)
    expect(pet.root.dataset.motion).toBe('walk')
    expect(pet.save).not.toHaveBeenCalled()
  })

  it('keeps character taps, holds and drags on their original paths without a touch preview', async () => {
    const pet = await setupTouch()
    const open = vi.spyOn(pet.host, 'open')
    await pet.tap(pet.inside(), pet.button)
    expect(pet.gaze()).toBeUndefined()
    await fireEvent.click(pet.button, { detail: 1 })
    expect(open).toHaveBeenCalledTimes(1)
    pet.host.close()
    await pet.advance(2000)
    await pet.pointer('pointerdown', pet.inside(), 'touch', pet.button)
    await pet.advance(450)
    expect(pet.root.dataset.reaction).toBe('wave')
    await pet.pointer('pointerup', pet.inside(), 'touch', pet.button)
    await fireEvent.click(pet.button, { detail: 1 })
    expect(open).toHaveBeenCalledTimes(1)
    await pet.advance(6000)
    const p = pet.inside()
    await pet.pointer('pointerdown', p, 'touch', pet.button)
    await pet.pointer('pointermove', { x: p.x + 6, y: p.y }, 'touch')
    expect(pet.root.dataset.motion).toBe('drag')
    await pet.pointer('pointerup', p, 'touch')
    expect(pet.gaze()).toBeUndefined()
  })

  it('requires directional art, excludes previews and releases global listeners on unmount', async () => {
    const legacy = await setupTouch(false)
    await legacy.tap()
    expect(legacy.gaze()).toBeUndefined()
    legacy.view.unmount()
    const preview = await setupTouch(true, true, document.createElement('div'))
    await preview.tap({ x: 200, y: 20 })
    expect(preview.gaze()).toBeUndefined()
    preview.view.unmount()
    const pet = await setupTouch()
    await pet.tap()
    const point = pet.farPoint()
    pet.view.unmount()
    expect(vi.getTimerCount()).toBe(0)
    await pet.tap(point)
    expect(vi.getTimerCount()).toBe(0)
  })
})
