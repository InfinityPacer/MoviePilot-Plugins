import { describe, expect, it } from 'vitest'

import { fields } from '@/config/fields'
import {
  displayFieldLabel,
  numberFieldUnit,
} from '@/config/presentation'

describe('number field presentation', () => {
  it('gives every number stepper an explicit unit', () => {
    const numberFields = fields.filter(field => field.kind === 'number')

    expect(numberFields).not.toHaveLength(0)
    for (const locale of ['zh-CN', 'zh-TW', 'en-US'] as const) {
      for (const field of numberFields) {
        expect(numberFieldUnit(field.key, locale), `${locale}:${field.key}`).toBeTruthy()
      }
    }
  })

  it('removes parenthesized units from number field headings', () => {
    const numberFields = fields.filter(field => field.kind === 'number')

    for (const field of numberFields) {
      expect(displayFieldLabel(field)).not.toMatch(/[（(][^）)]+[）)]/)
    }
  })

  it('preserves non-number field headings', () => {
    const field = fields.find(item => item.key === 'auto_check_interval_minutes')!

    expect(displayFieldLabel(field)).toBe(field.label)
  })
})
