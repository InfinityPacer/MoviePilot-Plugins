import type { BooleanConfigKey, SaeConfig } from './defaults'
import { t, type LocaleSource, type TranslationParams } from './i18n'
import { normalizeSaeConfig } from './values'

/** 配置保存前可见的潜在运行与数据影响。 */
export interface PreviewItem {
  /** 影响项标题。 */
  title: string
  /** 初始化期动作使用确定口径，条件性影响使用“可能”口径。 */
  detail: string
  /** 映射到 MoviePilot/Vuetify 语义色的提示等级。 */
  tone: 'info' | 'success' | 'warning' | 'error'
}

/** 兼容后端布尔配置的字符串与数值表示，确保预览判断与持久化配置语义一致。 */
function enabled(config: SaeConfig, key: BooleanConfigKey): boolean {
  const current = config[key] as boolean | number | string
  if (typeof current === 'string') {
    return ['true', 'on', 'yes', '1', 'guard'].includes(current.trim().toLowerCase())
  }
  if (typeof current === 'number') return current !== 0
  return current === true
}

function value(config: SaeConfig, key: keyof SaeConfig): string {
  return String(config[key] ?? '')
}

/** 根据当前草稿生成影响预览，不承诺定时任务或破坏性动作一定执行。 */
export function buildImpactPreview(config: SaeConfig, locale: LocaleSource = 'zh-CN'): PreviewItem[] {
  const normalized = normalizeSaeConfig(config)
  const items: PreviewItem[] = []
  const add = (key: string, tone: PreviewItem['tone'], params: TranslationParams = {}) => {
    items.push({
      title: t(locale, `preview.${key}.title`, params),
      detail: t(locale, `preview.${key}.detail`, params),
      tone,
    })
  }
  if (!enabled(normalized, 'enabled')) {
    add('disabled', 'info')
  }
  if (enabled(normalized, 'reset_task')) {
    add('reset', 'error')
  }
  if (enabled(normalized, 'backfill_best_version_now')) {
    add('backfillNow', 'warning')
  }
  if (enabled(normalized, 'enabled')) {
    add('general', 'success', { value: value(normalized, 'auto_check_interval_minutes') })
    add('metadata', 'success', { value: value(normalized, 'meta_check_interval_hours') })
    if (enabled(normalized, 'onlyonce')) add('runOnce', 'warning')
    if (enabled(normalized, 'pending_download_enabled') || enabled(normalized, 'download_monitor_enabled')) {
      add('downloadCheck', 'success', { value: value(normalized, 'download_check_interval_minutes') })
    }
    if (value(normalized, 'best_version_type') !== 'no') {
      add('bestVersion', 'warning')
      if (value(normalized, 'best_version_cron').trim()) {
        add('bestVersionCheck', 'warning', { value: value(normalized, 'best_version_cron') })
      }
    }
    if (enabled(normalized, 'verify_enabled')) {
      add('verify', 'warning', { value: value(normalized, 'verify_interval_hours') })
    }
    if (enabled(normalized, 'download_monitor_enabled')) {
      add('removeTorrent', 'error')
    }
    if (value(normalized, 'subscription_cleanup_history_type') !== 'no') {
      add('cleanup', 'error')
    }
    const actions = normalized.no_download_actions
    // 后端仅将 0 视为该媒体类型禁用，负数仍保留原有运行时语义。
    const movieNoDownloadEnabled = normalized.movie_no_download_days !== 0
    const tvNoDownloadEnabled = normalized.tv_no_download_days !== 0
    const hasEnabledMediaAction = (movieAction: string, tvAction: string) =>
      actions.some(action =>
        (movieNoDownloadEnabled && action === movieAction)
        || (tvNoDownloadEnabled && action === tvAction),
      )
    if (hasEnabledMediaAction('pause_movie', 'pause_tv')) {
      add('pause', 'warning')
    }
    if (hasEnabledMediaAction('complete_movie', 'complete_tv')) {
      add('complete', 'warning')
    }
    if (hasEnabledMediaAction('delete_movie', 'delete_tv')) {
      add('delete', 'error')
    }
    if (enabled(normalized, 'best_version_episode_to_full')) {
      add('episodeToFull', 'warning')
    }
    const recognitionMode = value(normalized, 'recognition_guard_mode').trim().toLowerCase()
    if (recognitionMode === 'audit') {
      add('audit', 'info')
    } else if (['loose', 'balanced', 'strict'].includes(recognitionMode)) {
      add('filter', 'warning')
    }
  }
  return items
}
