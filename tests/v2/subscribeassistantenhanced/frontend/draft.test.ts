import { describe, expect, it } from 'vitest'

import { configDefaults } from '../../../../plugins.v2/subscribeassistantenhanced/src/config/defaults'
import { useConfigDraft } from '../../../../plugins.v2/subscribeassistantenhanced/src/config/draft'
import { fields } from '../../../../plugins.v2/subscribeassistantenhanced/src/config/fields'

describe('configuration draft contract', () => {
  it('tracks representative and Tracker edits, then emits a complete normalized payload', () => {
    const { draft, changedCount, changedKeys, buildSavePayload } = useConfigDraft({
      ...configDefaults,
      retired_key: 'ignore-me',
      open_tracker_dialog: true,
    })

    expect(changedCount.value).toBe(0)

    draft.site_total_probe_enabled = !draft.site_total_probe_enabled
    expect(changedCount.value).toBe(1)
    expect(changedKeys.value).toEqual(['site_total_probe_enabled'])

    draft.default_tracker_response = 'tracker failure, retry later'
    expect(changedCount.value).toBe(2)
    expect(changedKeys.value).toEqual(['default_tracker_response', 'site_total_probe_enabled'])

    const payload = buildSavePayload()

    expect(Object.keys(payload)).toEqual(Object.keys(configDefaults))
    expect(payload.site_total_probe_enabled).toBe(draft.site_total_probe_enabled)
    expect(payload.default_tracker_response).toBe('tracker failure, retry later')
    expect(payload).not.toHaveProperty('open_tracker_dialog')
    expect(payload).not.toHaveProperty('retired_key')
  })

  it('returns the change count to zero when a field is restored', () => {
    const { draft, changedCount, changedKeys } = useConfigDraft(configDefaults)
    const initialNotify = draft.notify

    draft.notify = !initialNotify
    expect(changedCount.value).toBe(1)

    draft.notify = initialNotify
    expect(changedCount.value).toBe(0)
    expect(changedKeys.value).toEqual([])
  })

  it('round-trips every editable field through the complete save payload', () => {
    const { draft, changedCount, changedKeys, buildSavePayload } = useConfigDraft(configDefaults)
    const editableFields = fields.filter(field => !field.legacyUiKey)
    const draftValues = draft as unknown as Record<string, unknown>

    for (const field of editableFields) {
      const current = draftValues[field.key]
      const optionValues = field.options?.map(option => option.value)

      if (field.kind === 'multi-select') {
        const candidates = optionValues?.map(String) ?? []
        draftValues[field.key] = JSON.stringify(current) === JSON.stringify([candidates[0]])
          ? [candidates[1]]
          : [candidates[0]]
      } else if (optionValues?.length) {
        draftValues[field.key] = optionValues.find(value => value !== current)
      } else if (typeof current === 'boolean') {
        draftValues[field.key] = !current
      } else if (typeof current === 'number') {
        draftValues[field.key] = current + (field.key === 'cadence_multiplier' ? 0.5 : 1)
      } else if (field.key === 'best_version_cron') {
        draftValues[field.key] = '5 4 * * *'
      } else {
        draftValues[field.key] = `${String(current)}\n# sae-config-round-trip`
      }
    }

    const payload = buildSavePayload()

    expect(editableFields).toHaveLength(64)
    expect(changedCount.value).toBe(64)
    expect(changedKeys.value).toEqual(editableFields.map(field => field.key))
    expect(Object.keys(payload)).toEqual(Object.keys(configDefaults))
    expect(payload).not.toHaveProperty('open_tracker_dialog')
    for (const field of editableFields) {
      expect(payload[field.key]).toEqual(draft[field.key])
    }
  })
})
