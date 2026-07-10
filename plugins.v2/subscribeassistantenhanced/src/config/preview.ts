import type { BooleanConfigKey, SaeConfig } from './defaults'
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
export function buildImpactPreview(config: SaeConfig): PreviewItem[] {
  const normalized = normalizeSaeConfig(config)
  const items: PreviewItem[] = []
  if (!enabled(normalized, 'enabled')) {
    items.push({ title: '插件未启用', detail: '保存后不会注册订阅助手定时任务。', tone: 'info' })
  }
  if (enabled(normalized, 'reset_task')) {
    items.push({ title: '重置数据', detail: '保存后会清空插件任务数据并自动复位。', tone: 'error' })
  }
  if (enabled(normalized, 'backfill_best_version_now')) {
    items.push({ title: '立即扫描存量并回填', detail: '保存后会扫描存量分集洗版订阅并回填媒体库已有集。', tone: 'warning' })
  }
  if (enabled(normalized, 'enabled')) {
    items.push({ title: '通用巡检可能运行', detail: `周期 ${value(normalized, 'auto_check_interval_minutes')} 分钟。`, tone: 'success' })
    items.push({ title: '元数据检查可能运行', detail: `周期 ${value(normalized, 'meta_check_interval_hours')} 小时。`, tone: 'success' })
    if (enabled(normalized, 'onlyonce')) items.push({ title: '立即运行一次', detail: '保存后约 3 秒触发一次全量巡检。', tone: 'warning' })
    if (enabled(normalized, 'pending_download_enabled') || enabled(normalized, 'download_monitor_enabled')) {
      items.push({ title: '下载任务检查可能运行', detail: `周期 ${value(normalized, 'download_check_interval_minutes')} 分钟。`, tone: 'success' })
    }
    if (value(normalized, 'best_version_type') !== 'no' && value(normalized, 'best_version_cron').trim()) {
      items.push({ title: '洗版订阅检查可能运行', detail: `CRON ${value(normalized, 'best_version_cron')}。`, tone: 'warning' })
    }
    if (enabled(normalized, 'verify_enabled')) {
      items.push({ title: '自动纠错可能运行', detail: `周期 ${value(normalized, 'verify_interval_hours')} 小时。`, tone: 'warning' })
    }
    if (enabled(normalized, 'download_monitor_enabled')) {
      items.push({ title: '可能删除下载器任务', detail: '下载停滞、Tracker 关键字或手动删种场景可能触发删种处理。', tone: 'error' })
    }
    if (value(normalized, 'subscription_cleanup_history_type') !== 'no') {
      items.push({ title: '可能清理整理记录或文件', detail: '订阅清理范围已启用，请确认清理场景。', tone: 'error' })
    }
    const actions = normalized.no_download_actions
    if (actions.some(action => action === 'pause_movie' || action === 'pause_tv')) {
      items.push({ title: '可能暂停订阅', detail: '无下载策略命中后，电影或剧集订阅可能被暂停。', tone: 'warning' })
    }
    if (actions.some(action => action === 'complete_movie' || action === 'complete_tv')) {
      items.push({ title: '可能完成订阅', detail: '无下载策略命中后，电影或剧集订阅可能被标记完成并移除。', tone: 'warning' })
    }
    if (actions.some(action => action === 'delete_movie' || action === 'delete_tv')) {
      items.push({ title: '可能删除订阅', detail: '无下载策略命中后，电影或剧集订阅可能被直接删除。', tone: 'error' })
    }
    if (enabled(normalized, 'best_version_episode_to_full')) {
      items.push({ title: '可能从分集洗版转为全集洗版', detail: '订阅目标集满足后，分集洗版可能切换为全集洗版。', tone: 'warning' })
    }
    const recognitionMode = value(normalized, 'recognition_guard_mode')
    if (recognitionMode === 'audit') {
      items.push({ title: '识别增强可能记录候选风险', detail: '审计模式可能记录判定与通知，但不会过滤或移除候选。', tone: 'info' })
    } else if (['loose', 'balanced', 'strict'].includes(recognitionMode)) {
      items.push({ title: '识别增强可能过滤候选', detail: '当前模式和生效的自定义策略覆盖可能过滤或移除候选。', tone: 'warning' })
    }
  }
  return items
}
