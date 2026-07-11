/** 与 PluginConfig.defaults() 对齐的 Vue 配置持久化契约。 */
export interface SaeConfig {
  /** 启用插件 */
  enabled: boolean
  /** 发送通知 */
  notify: boolean
  /** 立即运行一次 */
  onlyonce: boolean
  /** 重置数据 */
  reset_task: boolean
  /** 通用巡检周期（分钟） */
  auto_check_interval_minutes: number
  /** 下载检查周期（分钟） */
  download_check_interval_minutes: number
  /** 元数据检查周期（小时） */
  meta_check_interval_hours: number
  /** 洗版检查周期 */
  best_version_cron: string
  /** 下载超时自动删除 */
  download_monitor_enabled: boolean
  /** 监听手动删除种子 */
  manual_delete_listen: boolean
  /** 监听Tracker响应关键字 */
  tracker_response_listen: boolean
  /** 删除后触发搜索补全 */
  auto_search_when_delete: boolean
  /** 跳过近期删除资源 */
  skip_deletion: boolean
  /** 下载超时时间（分钟） */
  download_timeout_minutes: number
  /** 下载超时进度阈值 */
  download_progress_threshold: number
  /** 下载连续超时重试次数 */
  download_retry_limit: number
  /** 排除标签 */
  delete_exclude_tags: string
  /** Tracker响应关键字 */
  default_tracker_response: string
  /** 删除记录保留（小时） */
  delete_record_retention_hours: number
  /** 清理整理记录范围 */
  subscription_cleanup_history_type: string
  /** 清理整理记录场景 */
  subscription_cleanup_history_scenes: string[]
  /** 识别增强模式 */
  recognition_guard_mode: string
  /** 识别增强通知 */
  recognition_guard_notify: string
  /** 识别增强通知限频（秒） */
  recognition_guard_notify_interval: number
  /** 识别增强二次识别 */
  recognition_guard_tmdb_recheck_mode: string
  /** 识别增强缓存大小 */
  recognition_guard_cache_maxsize: number
  /** 自定义识别规则 */
  recognition_guard_custom_config: string
  /** 自动待定剧集订阅 */
  pending_enhanced_enabled: boolean
  /** 自动待定下载中订阅 */
  pending_download_enabled: boolean
  /** 剧集待定天数 */
  auto_tv_pending_days: number
  /** 剧集待定集数 */
  auto_tv_pending_episodes: number
  /** 待定参考变更速率 */
  pending_use_volatility: boolean
  /** 自动暂停订阅 */
  pause_enhanced_enabled: boolean
  /** 自动暂停新增订阅的用户（逗号分隔） */
  auto_pause_users: string
  /** 即将播出暂停天数 */
  airing_pause_days: number
  /** 电影上映暂停天数 */
  movie_air_pause_days: number
  /** 剧集上映暂停天数 */
  tv_air_pause_days: number
  /** 电影无下载处理天数 */
  movie_no_download_days: number
  /** 剧集无下载处理天数 */
  tv_no_download_days: number
  /** 无下载处理策略 */
  no_download_actions: string[]
  /** 站点集数探测 */
  site_total_probe_enabled: boolean
  /** 暂停订阅补搜场景 */
  paused_probe_reasons: string[]
  /** 暂停满N天后补搜 */
  paused_probe_min_pause_days: number
  /** 补搜间隔（小时） */
  paused_probe_interval_hours: number
  /** 洗版类型 */
  best_version_type: string
  /** 电影洗版时限（天） */
  best_version_movie_remaining_days: number
  /** 剧集洗版时限（天） */
  best_version_tv_remaining_days: number
  /** 分集转全集 */
  best_version_episode_to_full: boolean
  /** 回填已存在集 */
  best_version_backfill_enabled: boolean
  /** 立即扫描存量并回填 */
  backfill_best_version_now: boolean
  /** 完结守卫模式 */
  completion_guard_mode: string
  /** 站点完结信号 */
  site_completion_evidence_enabled: boolean
  /** 变更速率信号 */
  volatility_enabled: boolean
  /** 变更速率窗口（天） */
  volatility_window_days: number
  /** 播出节奏信号 */
  cadence_enabled: boolean
  /** 节奏窗口系数 */
  cadence_multiplier: number
  /** 节奏窗口下限（天） */
  cadence_min_window_days: number
  /** 节奏参与最少集数 */
  cadence_min_episodes: number
  /** 季冷却期（天） */
  season_cooldown_days: number
  /** 自动纠错 */
  verify_enabled: boolean
  /** 自动纠错间隔（小时） */
  verify_interval_hours: number
  /** 快照保留（天） */
  verify_retention_days: number
  /** 完成前观察天数 */
  timeout_release_days: number
  /** 按节奏加速释放 */
  timeout_cadence_acceleration: boolean
}

/** 所有可持久化配置键。 */
export type ConfigKey = keyof SaeConfig

/** 布尔配置键，用于约束开关类预览规则。 */
export type BooleanConfigKey = {
  [K in ConfigKey]: SaeConfig[K] extends boolean ? K : never
}[ConfigKey]

/** 数值配置键，用于约束动态数值字段写回。 */
export type NumberConfigKey = {
  [K in ConfigKey]: SaeConfig[K] extends number ? K : never
}[ConfigKey]
/** 新配置与缺失字段回填使用的完整默认值。 */
export const configDefaults: SaeConfig = {
  "enabled": false,
  "notify": true,
  "onlyonce": false,
  "reset_task": false,
  "auto_check_interval_minutes": 30,
  "download_check_interval_minutes": 10,
  "meta_check_interval_hours": 3,
  "best_version_cron": "0 15 * * *",
  "download_monitor_enabled": true,
  "manual_delete_listen": true,
  "tracker_response_listen": true,
  "auto_search_when_delete": true,
  "skip_deletion": true,
  "download_timeout_minutes": 120,
  "download_progress_threshold": 10,
  "download_retry_limit": 3,
  "delete_exclude_tags": "H&R",
  "default_tracker_response": "torrent not registered with this tracker\ntorrent banned",
  "delete_record_retention_hours": 24,
  "subscription_cleanup_history_type": "no",
  "subscription_cleanup_history_scenes": [],
  "recognition_guard_mode": "off",
  "recognition_guard_notify": "off",
  "recognition_guard_notify_interval": 3600,
  "recognition_guard_tmdb_recheck_mode": "balanced_strict",
  "recognition_guard_cache_maxsize": 100000,
  "recognition_guard_custom_config": "####### 配置说明 BEGIN #######\n# 1. 本配置只控制识别增强的策略覆盖和关键词，不控制通知、二次识别触发或缓存大小。\n# 2. 未配置或保持注释的项目均继承 recognition_guard_mode 当前模板。\n# 3. actions 的值可选：inherit / observe / soft_block / block：\n#    - inherit：继承当前 recognition_guard_mode 模板，不单独覆盖。\n#    - observe：只记录审计和可选通知，不移除候选，下载选择不受影响。\n#    - soft_block：先从候选池移除；如果整轮候选被清空，且 empty_pool 策略允许，该候选可降级为 observe 恢复。\n#    - block：从候选池移除，集合级保护也不得恢复；用于用户明确不想下载的风险。\n# 4. allow 只能抵消非 hard veto 风险；不能覆盖显式 ID 错配、明确类型/形态互串、目标范围完全不覆盖等 hard veto。\n# 5. block 是普通黑名单风险，动作由 mode 或 actions.user_block 决定；hard_block 才是一律强拦截。\n# 6. 正则使用 Python re 语法；非法正则会跳过对应条目并记录配置告警，不影响其他规则。\n# 7. keywords 下的内置证据词分组如果取消注释配置，表示替换该分组；未配置的分组继续使用内置默认。\n####### 配置说明 END #######\n\nactions:\n  # 候选缺少年份。多站点用户可改为 block，少站点用户建议 inherit 或 observe。\n  # missing_year: block\n\n  # 候选全集范围明显大于目标窗口，例如目标缺 E08-E19，候选是全 60 集。\n  # target_range_oversized: block\n\n  # 命中 keywords.block 时的动作。\n  # user_block: soft_block\n\n  # 二次识别结果与订阅目标不一致。\n  # secondary_identity_conflict: block\n\nempty_pool:\n  # 整轮候选被识别增强清空时的恢复策略：recover_soft_block / never_recover。\n  # policy: recover_soft_block\n\n  # 即使动作是 soft_block，也不允许因整轮候选清空而恢复的原因码。\n  # non_recoverable_codes:\n  #   - target_range_oversized\n  #   - missing_year\n\nkeywords:\n  # 白名单：只抵消非 hard veto 风险。\n  # allow:\n  #   - 官方合集\n\n  # 普通黑名单：动作由 mode 或 actions.user_block 决定。\n  # block:\n  #   - 低可信风险词\n\n  # 强黑名单：所有启用模式下 hard veto；audit 只记录 would block。\n  # hard_block:\n  #   - 强制错误词\n\n  # 以下是内置证据词分组；如需覆盖某一组，取消注释并完整写出该组。\n  # live_action:\n  #   - 真人版\n  #   - 电视剧版\n  #   - 实拍版\n  #   - 真人剧\n  # animation:\n  #   - 动画\n  #   - 动漫\n  #   - 国漫\n  #   - 番剧\n  # movie:\n  #   - 电影版\n  #   - 剧场版\n  #   - 劇場版\n  #   - '\\bMovie\\b'\n  # tv:\n  #   - '\\bS\\d{1,3}(?:E\\d{1,4})?\\b'\n  #   - '第\\s*\\d+\\s*[集季]'\n  #   - '全\\s*\\d+\\s*集'\n",
  "pending_enhanced_enabled": true,
  "pending_download_enabled": true,
  "auto_tv_pending_days": 0,
  "auto_tv_pending_episodes": 1,
  "pending_use_volatility": false,
  "pause_enhanced_enabled": false,
  "auto_pause_users": "",
  "airing_pause_days": 30,
  "movie_air_pause_days": 7,
  "tv_air_pause_days": 14,
  "movie_no_download_days": 365,
  "tv_no_download_days": 180,
  "no_download_actions": [],
  "site_total_probe_enabled": false,
  "paused_probe_reasons": [
    "no_download"
  ],
  "paused_probe_min_pause_days": 14,
  "paused_probe_interval_hours": 72,
  "best_version_type": "no",
  "best_version_movie_remaining_days": 0,
  "best_version_tv_remaining_days": 0,
  "best_version_episode_to_full": false,
  "best_version_backfill_enabled": false,
  "backfill_best_version_now": false,
  "completion_guard_mode": "balanced",
  "site_completion_evidence_enabled": true,
  "volatility_enabled": true,
  "volatility_window_days": 3,
  "cadence_enabled": true,
  "cadence_multiplier": 2.5,
  "cadence_min_window_days": 7,
  "cadence_min_episodes": 3,
  "season_cooldown_days": 14,
  "verify_enabled": false,
  "verify_interval_hours": 12,
  "verify_retention_days": 180,
  "timeout_release_days": 7,
  "timeout_cadence_acceleration": true
}
