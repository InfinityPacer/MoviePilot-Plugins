import { computed, ref, type Ref } from 'vue'
import type { EditorSnapshot } from './api'
import {
  appearanceOf,
  DEFAULT_SETTINGS,
  normalizeSettings,
  sameAppearance,
  sameShared,
  sharedOf,
  type PetAppearance,
  type SharedActivity,
  type YingSettings,
} from '@/stage/settings'

export function usePetSettings(selectedKey: Ref<string>) {
  const defaults = ref({ ...DEFAULT_SETTINGS })
  const drafts = ref<Record<string, PetAppearance>>({})
  const saved = ref<Record<string, PetAppearance>>({})
  const conflicts = ref<Record<string, PetAppearance>>({})
  const sharedDraft = ref(sharedOf(DEFAULT_SETTINGS))
  const sharedSaved = ref(sharedOf(DEFAULT_SETTINGS))
  const sharedConflict = ref<SharedActivity | null>(null)
  const dirtyKeys = computed(() =>
    Object.keys(drafts.value).filter(key => !sameAppearance(drafts.value[key], saved.value[key])),
  )
  const sharedDirty = computed(() => !sameShared(sharedDraft.value, sharedSaved.value))
  const dirty = computed(() => sharedDirty.value || dirtyKeys.value.length > 0)
  const conflictKeys = computed(() => Object.keys(conflicts.value))
  const hasConflict = computed(() => !!sharedConflict.value || conflictKeys.value.length > 0)
  const draft = computed<YingSettings>({
    get: () => ({ ...defaults.value, ...sharedDraft.value, ...drafts.value[selectedKey.value] }),
    set: value => {
      const normalized = normalizeSettings(value)
      if (Object.hasOwn(saved.value, selectedKey.value)) drafts.value[selectedKey.value] = appearanceOf(normalized)
      sharedDraft.value = sharedOf(normalized)
    },
  })

  function receive(snapshot: EditorSnapshot, reset = false) {
    defaults.value = { ...snapshot.settings }
    const latestShared = sharedOf(snapshot.settings)
    if (!reset && sharedDirty.value) {
      sharedConflict.value = sameShared(latestShared, sharedSaved.value) ? null : latestShared
    } else {
      sharedSaved.value = latestShared
      sharedDraft.value = { ...latestShared }
      sharedConflict.value = null
    }
    const keys = snapshot.pets.filter(pet => pet.mode === 'stage').map(pet => pet.key)
    for (const values of [drafts, saved, conflicts]) {
      for (const key of Object.keys(values.value)) if (!keys.includes(key)) delete values.value[key]
    }
    for (const key of keys) {
      const latest = appearanceOf(normalizeSettings({ ...snapshot.settings, ...snapshot.pet_settings?.[key] }))
      const baseline = saved.value[key]
      if (!reset && baseline && !sameAppearance(drafts.value[key], baseline)) {
        if (!sameAppearance(latest, baseline)) conflicts.value[key] = latest
        else delete conflicts.value[key]
      } else {
        saved.value[key] = latest
        drafts.value[key] = appearanceOf(latest)
        delete conflicts.value[key]
      }
    }
  }

  function restore() {
    saved.value = { ...saved.value, ...conflicts.value }
    drafts.value = Object.fromEntries(Object.entries(saved.value).map(([key, value]) => [key, appearanceOf(value)]))
    conflicts.value = {}
    if (sharedConflict.value) sharedSaved.value = sharedConflict.value
    sharedDraft.value = { ...sharedSaved.value }
    sharedConflict.value = null
  }

  function clear() {
    drafts.value = {}
    saved.value = {}
    conflicts.value = {}
    defaults.value = { ...DEFAULT_SETTINGS }
    sharedSaved.value = sharedOf(DEFAULT_SETTINGS)
    sharedDraft.value = sharedOf(DEFAULT_SETTINGS)
    sharedConflict.value = null
  }

  return {
    draft,
    drafts,
    saved,
    dirtyKeys,
    sharedDraft,
    sharedSaved,
    sharedDirty,
    dirty,
    conflictKeys,
    hasConflict,
    receive,
    restore,
    clear,
  }
}
