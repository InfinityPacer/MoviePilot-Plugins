/**
 * 插件配置项允许保存的基础值类型。
 */
export type ConfigValue = string | number | boolean | string[] | number[] | null

/**
 * 订阅助手增强插件的配置模型。
 */
export interface PluginConfigModel {
  /** 是否启用插件主开关。 */
  enabled?: boolean

  /** 允许保存未显式声明但由后端模型提供的配置字段。 */
  [key: string]: ConfigValue | undefined
}

/**
 * 表单选择项的展示和值定义。
 */
export interface SelectOption {
  /** 选项显示文案。 */
  title: string

  /** 选项保存值。 */
  value: ConfigValue
}

/**
 * 后端配置模型当前公开的字段键集合。
 */
export type FieldKey =
  | 'enabled'
  | 'notify'
  | 'reset_task'
  | 'onlyonce'
  | 'auto_check_interval_minutes'
  | 'download_check_interval_minutes'
  | 'meta_check_interval_hours'
  | 'best_version_cron'
  | 'download_monitor_enabled'
  | 'manual_delete_listen'
  | 'tracker_response_listen'
  | 'open_tracker_dialog'
  | 'auto_search_when_delete'
  | 'skip_deletion'
  | 'download_timeout_minutes'
  | 'download_progress_threshold'
  | 'download_retry_limit'
  | 'delete_record_retention_hours'
  | 'delete_exclude_tags'
  | 'default_tracker_response'
  | 'pending_enhanced_enabled'
  | 'pending_download_enabled'
  | 'auto_tv_pending_days'
  | 'auto_tv_pending_episodes'
  | 'pending_use_volatility'
  | 'pause_enhanced_enabled'
  | 'auto_pause_users'
  | 'airing_pause_days'
  | 'tv_air_pause_days'
  | 'movie_air_pause_days'
  | 'tv_no_download_days'
  | 'movie_no_download_days'
  | 'no_download_actions'
  | 'best_version_type'
  | 'best_version_episode_to_full'
  | 'best_version_backfill_enabled'
  | 'backfill_best_version_now'
  | 'best_version_clear_history_type'
  | 'best_version_remaining_days'
  | 'completion_guard_mode'
  | 'volatility_enabled'
  | 'volatility_window_days'
  | 'cadence_enabled'
  | 'cadence_multiplier'
  | 'cadence_min_window_days'
  | 'cadence_min_episodes'
  | 'season_cooldown_days'
  | 'verify_enabled'
  | 'verify_interval_hours'
  | 'verify_retention_days'
  | 'timeout_release_enabled'
  | 'timeout_release_days'
  | 'timeout_cadence_acceleration'

/**
 * 配置字段的元信息，供字段渲染组件复用。
 */
export interface FieldMeta {
  /** 配置字段名。 */
  key: FieldKey

  /** 字段渲染控件类型。 */
  kind: 'switch' | 'number' | 'text' | 'select' | 'multi-select' | 'cron' | 'textarea'

  /** 字段显示名称。 */
  label: string

  /** 字段辅助说明。 */
  hint?: string

  /** 字段可选项。 */
  options?: SelectOption[]

  /** 栅格列宽，遵循 Vuetify 12 列布局。 */
  md?: number
}

/**
 * 配置分组内的一行字段，用于保持表单区域的展示顺序。
 */
export type FieldRow = FieldMeta[]

/**
 * 配置分组描述，供配置页按业务域渲染字段集合。
 */
export interface FieldSection {
  /** 分组标题。 */
  title: string

  /** 分组说明。 */
  subtitle?: string

  /** 分组字段行。 */
  rows: FieldRow[]
}
