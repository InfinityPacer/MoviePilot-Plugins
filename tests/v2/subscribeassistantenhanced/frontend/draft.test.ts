import { describe, expect, it } from 'vitest'

import { configDefaults } from '../../../../plugins.v2/subscribeassistantenhanced/src/config/defaults'
import { useConfigDraft } from '../../../../plugins.v2/subscribeassistantenhanced/src/config/draft'

describe('configuration draft contract', () => {
  it('tracks representative and Tracker edits, then emits a complete normalized payload', () => {
    const { draft, changedCount, buildSavePayload } = useConfigDraft({
      ...configDefaults,
      retired_key: 'ignore-me',
      open_tracker_dialog: true,
    })

    expect(changedCount.value).toBe(0)

    draft.site_total_probe_enabled = !draft.site_total_probe_enabled
    expect(changedCount.value).toBe(1)

    draft.default_tracker_response = 'tracker failure, retry later'
    expect(changedCount.value).toBe(2)

    const payload = buildSavePayload()

    expect(Object.keys(payload)).toEqual(Object.keys(configDefaults))
    expect(payload.site_total_probe_enabled).toBe(draft.site_total_probe_enabled)
    expect(payload.default_tracker_response).toBe('tracker failure, retry later')
    expect(payload.open_tracker_dialog).toBe(false)
    expect(payload).not.toHaveProperty('retired_key')
  })

  it('returns the change count to zero when a field is restored', () => {
    const { draft, changedCount } = useConfigDraft(configDefaults)
    const initialNotify = draft.notify

    draft.notify = !initialNotify
    expect(changedCount.value).toBe(1)

    draft.notify = initialNotify
    expect(changedCount.value).toBe(0)
  })
})
