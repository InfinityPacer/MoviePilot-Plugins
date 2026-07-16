import { describe, expect, it } from 'vitest'

import { configDefaults } from '@/config/defaults'
import {
  normalizeFiniteNumber,
  normalizeSaeConfig,
} from '@/config/values'

describe('normalizeFiniteNumber', () => {
  it('将整数字符串转换为 number', () => {
    expect(normalizeFiniteNumber(10, '45')).toBe(45)
  })

  it('将小数字符串转换为 number', () => {
    expect(normalizeFiniteNumber(10, '3.75')).toBe(3.75)
  })

  it('保留已有数值输入的 number 类型和值', () => {
    const result = normalizeFiniteNumber(10, 2.5)

    expect(result).toBe(2.5)
    expect(typeof result).toBe('number')
  })

  it.each([null, undefined, '', '   ', Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    '非法输入 %s 保留最近一次有效值',
    incoming => {
      expect(normalizeFiniteNumber(10, incoming)).toBe(10)
    },
  )
})

describe('normalizeSaeConfig', () => {
  it('将动态 Host 模型规范化为精确完整的 SaeConfig', () => {
    const input = {
      ...configDefaults,
      _tab: 'cleanup',
      retired_key: 'legacy',
      enabled: 'false',
      notify: 'yes',
      onlyonce: 'guard',
      reset_task: -1,
      auto_check_interval_minutes: '45',
      download_check_interval_minutes: '',
      meta_check_interval_hours: 'Infinity',
      download_timeout_minutes: Number.NaN,
      cadence_multiplier: '3.75',
      best_version_movie_remaining_days: Number.POSITIVE_INFINITY,
      subscription_cleanup_history_scenes: ' normal, best_version, , ',
      no_download_actions: [' pause_movie ', '', 'delete_tv'],
      paused_probe_reasons: [' no_download ', ' ', 'pre_air'],
      best_version_cron: null,
      default_tracker_response: undefined,
      open_tracker_dialog: true,
    }
    const before = structuredClone(input)

    const result = normalizeSaeConfig(input)

    expect(Object.keys(result)).toEqual(Object.keys(configDefaults))
    expect(result).not.toHaveProperty('_tab')
    expect(result).not.toHaveProperty('retired_key')
    expect(result.enabled).toBe(false)
    expect(result.notify).toBe(true)
    expect(result.onlyonce).toBe(true)
    expect(result.reset_task).toBe(true)
    expect(result.auto_check_interval_minutes).toBe(45)
    expect(result.download_check_interval_minutes).toBe(
      configDefaults.download_check_interval_minutes,
    )
    expect(result.meta_check_interval_hours).toBe(configDefaults.meta_check_interval_hours)
    expect(result.download_timeout_minutes).toBe(configDefaults.download_timeout_minutes)
    expect(result.cadence_multiplier).toBe(3.75)
    expect(result.best_version_movie_remaining_days).toBe(
      configDefaults.best_version_movie_remaining_days,
    )
    expect(result.subscription_cleanup_history_scenes).toEqual(['normal', 'best_version'])
    expect(result.no_download_actions).toEqual(['pause_movie', 'delete_tv'])
    expect(result.paused_probe_reasons).toEqual(['no_download', 'pre_air'])
    expect(result.best_version_cron).toBe(configDefaults.best_version_cron)
    expect(result.default_tracker_response).toBe(configDefaults.default_tracker_response)
    expect(result).not.toHaveProperty('open_tracker_dialog')
    expect(
      Object.entries(result)
        .filter(([, value]) => typeof value === 'number')
        .every(([, value]) => Number.isFinite(value)),
    ).toBe(true)
    expect(input).toEqual(before)
  })

  it('缺失列表字段使用独立的默认数组', () => {
    const result = normalizeSaeConfig({})

    expect(result.subscription_cleanup_history_scenes).toEqual(
      configDefaults.subscription_cleanup_history_scenes,
    )
    expect(result.subscription_cleanup_history_scenes).not.toBe(
      configDefaults.subscription_cleanup_history_scenes,
    )
    expect(result.no_download_actions).not.toBe(configDefaults.no_download_actions)
    expect(result.paused_probe_reasons).not.toBe(configDefaults.paused_probe_reasons)
  })
})
