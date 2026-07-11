import type { ConfigKey } from './defaults'
import type { FieldMeta } from './fields'
import type { SupportedLocale } from './i18n'

const unitLabels: Record<SupportedLocale, Record<string, string>> = {
  'zh-CN': {
    count: '次', day: '天', episode: '集', hour: '小时', item: '条', minute: '分钟',
    multiplier: '倍', percent: '%', round: '轮', second: '秒',
  },
  'zh-TW': {
    count: '次', day: '天', episode: '集', hour: '小時', item: '條', minute: '分鐘',
    multiplier: '倍', percent: '%', round: '輪', second: '秒',
  },
  'en-US': {
    count: 'x', day: 'd', episode: 'ep', hour: 'hr', item: 'items', minute: 'min',
    multiplier: 'x', percent: '%', round: 'rounds', second: 'sec',
  },
}

/** 返回数字步进器的紧凑单位，字段后缀承载通用时间语义。 */
export function numberFieldUnit(key: ConfigKey, locale: SupportedLocale = 'zh-CN'): string | undefined {
  const units = unitLabels[locale]
  if (key === 'cadence_min_episodes') return units.episode
  if (key === 'cadence_multiplier') return units.multiplier
  if (key === 'download_progress_threshold') return units.percent
  if (key === 'download_retry_limit') return units.count
  if (key === 'recognition_guard_cache_maxsize') return units.item
  if (key === 'recognition_guard_notify_interval') return units.second
  if (key.endsWith('_minutes')) return units.minute
  if (key.endsWith('_hours')) return units.hour
  if (key.endsWith('_days')) return units.day
  if (key.endsWith('_episodes')) return units.episode
  return undefined
}

/** 数字字段的单位由步进器展示，标题只保留业务名称。 */
export function displayFieldLabel(field: FieldMeta): string {
  if (field.kind !== 'number') return field.label
  return field.label.replace(/\s*[（(][^）)]+[）)]\s*/g, '').trim()
}
