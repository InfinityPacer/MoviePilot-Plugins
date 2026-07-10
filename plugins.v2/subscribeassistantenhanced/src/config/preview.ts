import type { BooleanConfigKey, SaeConfig } from './defaults'

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
  const items: PreviewItem[] = []
  if (!enabled(config, 'enabled')) {
    items.push({ title: '插件未启用', detail: '保存后不会注册订阅助手定时任务。', tone: 'info' })
  }
  if (enabled(config, 'reset_task')) {
    items.push({ title: '重置数据', detail: '保存后会清空插件任务数据并自动复位。', tone: 'error' })
  }
  if (enabled(config, 'backfill_best_version_now')) {
    items.push({ title: '立即扫描存量并回填', detail: '保存后会扫描存量分集洗版订阅并回填媒体库已有集。', tone: 'warning' })
  }
  if (enabled(config, 'enabled')) {
    items.push({ title: '通用巡检可能运行', detail: `周期 ${value(config, 'auto_check_interval_minutes')} 分钟。`, tone: 'success' })
    items.push({ title: '元数据检查可能运行', detail: `周期 ${value(config, 'meta_check_interval_hours')} 小时。`, tone: 'success' })
    if (enabled(config, 'onlyonce')) items.push({ title: '立即运行一次', detail: '保存后约 3 秒触发一次全量巡检。', tone: 'warning' })
    if (enabled(config, 'pending_download_enabled') || enabled(config, 'download_monitor_enabled')) {
      items.push({ title: '下载任务检查可能运行', detail: `周期 ${value(config, 'download_check_interval_minutes')} 分钟。`, tone: 'success' })
    }
    if (value(config, 'best_version_type') !== 'no' && value(config, 'best_version_cron').trim()) {
      items.push({ title: '洗版订阅检查可能运行', detail: `CRON ${value(config, 'best_version_cron')}。`, tone: 'warning' })
    }
    if (enabled(config, 'verify_enabled')) {
      items.push({ title: '自动纠错可能运行', detail: `周期 ${value(config, 'verify_interval_hours')} 小时。`, tone: 'warning' })
    }
    if (enabled(config, 'download_monitor_enabled')) {
      items.push({ title: '可能删除下载器任务', detail: '下载停滞、Tracker 关键字或手动删种场景可能触发删种处理。', tone: 'error' })
    }
    if (value(config, 'subscription_cleanup_history_type') !== 'no') {
      items.push({ title: '可能清理整理记录或文件', detail: '订阅清理范围已启用，请确认清理场景。', tone: 'error' })
    }
  }
  return items
}
