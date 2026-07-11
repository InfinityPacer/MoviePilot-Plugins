import { describe, expect, it } from 'vitest'

import { fields, groups } from '../../../../plugins.v2/subscribeassistantenhanced/src/config/fields'
import {
  assertTranslationCoverage,
  localizeFields,
  localizeGroups,
  normalizeLocale,
  t,
} from '../../../../plugins.v2/subscribeassistantenhanced/src/config/i18n'

describe('SAE i18n adapter', () => {
  it('normalizes Host locale values and ref-like values', () => {
    expect(normalizeLocale('zh-CN')).toBe('zh-CN')
    expect(normalizeLocale('zh_TW')).toBe('zh-TW')
    expect(normalizeLocale('en-us')).toBe('en-US')
    expect(normalizeLocale({ value: 'en-US' })).toBe('en-US')
    expect(normalizeLocale({ value: { value: 'zh-TW' } })).toBe('zh-TW')
  })

  it('falls back unknown and invalid locale values to zh-CN', () => {
    expect(normalizeLocale('ja-JP')).toBe('zh-CN')
    expect(normalizeLocale(undefined)).toBe('zh-CN')
    expect(normalizeLocale({ value: null })).toBe('zh-CN')
  })

  it('translates stable UI keys and interpolates named parameters', () => {
    expect(t('zh-CN', 'config.changedCount', { count: 3 })).toBe('3 项待保存')
    expect(t('zh-TW', 'config.changedCount', { count: 3 })).toBe('3 項待儲存')
    expect(t('en-US', 'config.changedCount', { count: 3 })).toBe('3 to save')
    expect(t('zh-CN', 'config.changes')).toBe('本次修改')
    expect(t('zh-TW', 'config.moreChanges', { count: 2 })).toBe('另有 2 項')
    expect(t('en-US', 'config.moreChanges', { count: 2 })).toBe('2 more')
    expect(t('zh-CN', 'config.monitoredCount')).toBe('下载任务')
    expect(t('zh-TW', 'config.monitoredCount')).toBe('下載任務')
    expect(t('en-US', 'config.monitoredCount')).toBe('Downloads')
    expect(() => t('en-US', 'config.missing')).toThrow(/Missing translation key/)
  })

  it('provides complete localized groups without mutating source metadata', () => {
    const source = structuredClone(groups)

    for (const locale of ['zh-CN', 'zh-TW', 'en-US'] as const) {
      const localized = localizeGroups(locale, groups)
      expect(localized).toHaveLength(groups.length)
      expect(localized.every(group => group.title.trim() && group.summary.trim())).toBe(true)
    }

    expect(localizeGroups('zh-TW', groups)[0].title).toBe('全域執行')
    expect(localizeGroups('en-US', groups)[0].title).toBe('General')
    expect(groups).toEqual(source)
  })

  it('covers all 64 field labels, hints, and option titles in every locale', () => {
    expect(fields).toHaveLength(64)
    expect(() => assertTranslationCoverage()).not.toThrow()

    for (const locale of ['zh-CN', 'zh-TW', 'en-US'] as const) {
      const localized = localizeFields(locale, fields)
      expect(localized).toHaveLength(fields.length)
      expect(localized.every(field => field.label.trim())).toBe(true)
      expect(localized.filter(field => field.hint).length).toBe(fields.filter(field => field.hint).length)
      expect(
        localized.every(field => field.options?.every(option => option.title.trim()) ?? true),
      ).toBe(true)
    }

    const traditional = localizeFields('zh-TW', fields)
    const english = localizeFields('en-US', fields)
    const traditionalText = traditional
      .flatMap(field => [field.label, field.hint, ...(field.options?.map(option => option.title) ?? [])])
      .filter(Boolean)
      .join('')
    expect(traditionalText).not.toMatch(/[后会将处为与发过这则无设选线响应种从开进间数长现还较达实复对内样并当]/)
    expect(traditional.find(field => field.key === 'enabled')?.label).toBe('啟用外掛')
    expect(english.find(field => field.key === 'enabled')?.label).toBe('Enable plugin')
    expect(
      english.find(field => field.key === 'completion_guard_mode')?.options?.map(option => option.title),
    ).toEqual(['Off', 'Strict', 'Balanced', 'Relaxed'])
    expect(
      localizeFields('zh-CN', fields).find(field => field.key === 'recognition_guard_custom_config')?.hint,
    ).toBe('仅在内置规则无法满足时编辑，留空则继承当前模式')
    expect(
      traditional.find(field => field.key === 'recognition_guard_custom_config')?.hint,
    ).toBe('僅在內建規則無法滿足時編輯，留空則繼承目前模式')
    expect(
      english.find(field => field.key === 'recognition_guard_custom_config')?.hint,
    ).toBe('Edit only when built-in rules are insufficient; leave empty to inherit the current mode')
  })
})
