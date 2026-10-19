import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { usePetSettings } from '@/editor/settings'
import type { EditorSnapshot } from '@/editor/api'
import { appearanceOf, normalizeSettings } from '@/stage/settings'
import { normalizePeekAngles } from '@/stage/peek'

function snapshot(): EditorSnapshot {
  return {
    enabled: true,
    settings: { scale: 1.5, speed: 1, roam: 'floor', movement: 'auto' },
    pets: ['alpha', 'beta'].map(key => ({
      key,
      name: key,
      mode: 'stage',
      builtin: false,
      description: '',
      preview: '',
    })),
    pet_settings: { alpha: { scale: 0.8, speed: 1.2 }, beta: { scale: 1.3, speed: 0.7 } },
  }
}

describe('independent appearance drafts', () => {
  it('defaults bottom to zero but retains explicitly saved 35-degree profiles', () => {
    expect(normalizePeekAngles(undefined)).toEqual({ bottom: 0, left: 35, right: 35 })
    const explicit = { scale: 1, speed: 1, peek_angles: { bottom: 35, left: 35, right: 35 } }
    expect(appearanceOf(normalizeSettings(explicit))).toEqual(explicit)
    expect(appearanceOf(normalizeSettings({ scale: 1, speed: 1 }))).toEqual({ scale: 1, speed: 1 })
  })
  it('isolates nested angle drafts and protects a concurrent angle update', () => {
    const state = usePetSettings(ref('alpha'))
    const initial = snapshot()
    initial.pet_settings!.alpha.peek_angles = { bottom: 20, left: 35, right: 35 }
    state.receive(initial)
    state.draft.value = { ...state.draft.value, peek_angles: { bottom: 25, left: 35, right: 35 } }
    expect(state.saved.value.alpha.peek_angles!.bottom).toBe(20)
    expect(state.saved.value.beta.peek_angles).toBeUndefined()
    const changed = snapshot()
    changed.pet_settings!.alpha.peek_angles = { bottom: 30, left: 35, right: 35 }
    state.receive(changed)
    expect(state.draft.value.peek_angles!.bottom).toBe(25)
    expect(state.conflictKeys.value).toEqual(['alpha'])
    state.restore()
    expect(state.draft.value.peek_angles!.bottom).toBe(30)
    expect(state.dirty.value).toBe(false)
  })
  it('keeps scale and speed per key while sharing activity across selections', () => {
    const selected = ref('alpha')
    const state = usePetSettings(selected)
    state.receive(snapshot())
    state.draft.value = { ...state.draft.value, scale: 0.6, roam: 'free' }
    selected.value = 'beta'
    expect(state.draft.value).toMatchObject({ scale: 1.3, speed: 0.7, roam: 'free' })
    state.draft.value = { ...state.draft.value, speed: 1.8 }
    selected.value = 'alpha'
    expect(state.draft.value).toMatchObject({ scale: 0.6, speed: 1.2, roam: 'free' })
    expect(state.dirtyKeys.value).toEqual(['alpha', 'beta'])
    state.restore()
    expect(state.draft.value).toMatchObject({ scale: 0.8, speed: 1.2, roam: 'floor' })
    expect(state.dirty.value).toBe(false)
  })

  it('keeps dirty baselines during refresh and requires undo for a conflicting server value', () => {
    const state = usePetSettings(ref('alpha'))
    state.receive(snapshot())
    state.draft.value = { ...state.draft.value, scale: 0.6 }
    const latest = snapshot()
    latest.pet_settings!.alpha.scale = 1.1
    latest.pet_settings!.beta.speed = 1.9
    state.receive(latest)
    expect(state.draft.value.scale).toBe(0.6)
    expect(state.saved.value.alpha.scale).toBe(0.8)
    expect(state.saved.value.beta.speed).toBe(1.9)
    expect(state.hasConflict.value).toBe(true)
    state.restore()
    expect(state.draft.value.scale).toBe(1.1)
    expect(state.hasConflict.value).toBe(false)
  })

  it('preserves shared conflicts without overwriting per-pet appearance', () => {
    const state = usePetSettings(ref('alpha'))
    state.receive(snapshot())
    state.draft.value = { ...state.draft.value, movement: 'fixed' }
    const latest = snapshot()
    latest.settings.roam = 'free'
    state.receive(latest)
    expect(state.sharedSaved.value.roam).toBe('floor')
    expect(state.hasConflict.value).toBe(true)
    state.restore()
    expect(state.draft.value).toMatchObject({ scale: 0.8, roam: 'free', movement: 'auto' })
  })

  it('uses legacy defaults only for pets without a profile and clears removed keys and instances', () => {
    const state = usePetSettings(ref('beta'))
    const latest = snapshot()
    delete latest.pet_settings!.beta
    state.receive(latest)
    expect(state.draft.value).toMatchObject({ scale: 1.5, speed: 1 })
    state.draft.value = { ...state.draft.value, scale: 0.6 }
    latest.pets = latest.pets.filter(pet => pet.key !== 'beta')
    state.receive(latest)
    expect(state.dirtyKeys.value).toEqual([])
    state.clear()
    expect(state.saved.value).toEqual({})
    expect(state.hasConflict.value).toBe(false)
  })
})
