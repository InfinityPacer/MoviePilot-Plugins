import type { FieldKey, FieldMeta, FieldSection, SelectOption } from '../types'

/**
 * 完结守卫强度选项，按后端表单与 README 的展示顺序排列。
 */
export const completionGuardModeOptions: SelectOption[] = [
  { title: '关闭', value: 'off' },
  { title: '严格', value: 'strict' },
  { title: '平衡', value: 'balanced' },
  { title: '宽松', value: 'loose' },
]

/**
 * 洗版媒体范围选项，值与后端配置解析保持一致。
 */
export const bestVersionTypeOptions: SelectOption[] = [
  { title: '关闭', value: 'no' },
  { title: '全部', value: 'all' },
  { title: '电影', value: 'movie' },
  { title: '剧集', value: 'tv' },
  { title: '剧集（分集下载）', value: 'tv_episode' },
]

/**
 * 洗版清理整理记录范围选项，清理行为会影响已有记录和文件。
 */
export const bestVersionClearHistoryTypeOptions: SelectOption[] = [
  { title: '关闭', value: 'no' },
  { title: '全部', value: 'all' },
  { title: '电影', value: 'movie' },
  { title: '剧集', value: 'tv' },
]

/**
 * 无下载处理策略选项，按媒体类型区分暂停、完成和删除动作。
 */
export const noDownloadActionOptions: SelectOption[] = [
  { title: '暂停电影订阅', value: 'pause_movie' },
  { title: '暂停剧集订阅', value: 'pause_tv' },
  { title: '完成电影订阅', value: 'complete_movie' },
  { title: '完成剧集订阅', value: 'complete_tv' },
  { title: '删除电影订阅', value: 'delete_movie' },
  { title: '删除剧集订阅', value: 'delete_tv' },
]

/**
 * 下载检查周期选项，保留分钟级高频检查能力。
 */
export const minuteIntervalOptions: SelectOption[] = [
  { title: '5分钟', value: 5 },
  { title: '10分钟', value: 10 },
  { title: '15分钟', value: 15 },
  { title: '30分钟', value: 30 },
  { title: '60分钟', value: 60 },
  { title: '120分钟', value: 120 },
]

/**
 * 通用巡检周期选项，覆盖待定释放、无下载处理和删除记录清理。
 */
export const commonIntervalOptions: SelectOption[] = [
  { title: '30分钟', value: 30 },
  { title: '60分钟', value: 60 },
  { title: '120分钟', value: 120 },
  { title: '240分钟', value: 240 },
]

/**
 * 元数据复核周期选项，按小时级别控制订阅元数据检查频率。
 */
export const metaIntervalOptions: SelectOption[] = [
  { title: '1小时', value: 1 },
  { title: '3小时', value: 3 },
  { title: '6小时', value: 6 },
  { title: '12小时', value: 12 },
  { title: '24小时', value: 24 },
]

/**
 * 现有配置字段元数据，label 和 hint 与后端表单文案保持同一语义层。
 */
export const fields: Record<FieldKey, FieldMeta> = {
  enabled: {
    key: 'enabled',
    kind: 'switch',
    label: '启用插件',
    hint: '开启后插件将处于激活状态',
  },
  notify: {
    key: 'notify',
    kind: 'switch',
    label: '发送通知',
    hint: '是否在特定事件发生时发送通知',
  },
  reset_task: {
    key: 'reset_task',
    kind: 'switch',
    label: '重置数据',
    hint: '将重置所有待定/暂停/监控等任务数据，执行后自动复位',
  },
  onlyonce: {
    key: 'onlyonce',
    kind: 'switch',
    label: '立即运行一次',
    hint: '保存后立即运行一次全量巡检，执行后自动复位',
  },
  auto_check_interval_minutes: {
    key: 'auto_check_interval_minutes',
    kind: 'select',
    label: '通用巡检周期（分钟）',
    hint: '待定释放、无下载处理和删除记录清理的周期',
    options: commonIntervalOptions,
  },
  download_check_interval_minutes: {
    key: 'download_check_interval_minutes',
    kind: 'select',
    label: '下载检查周期（分钟）',
    hint: '下载检查的周期，定时检查下载任务状态',
    options: minuteIntervalOptions,
  },
  meta_check_interval_hours: {
    key: 'meta_check_interval_hours',
    kind: 'select',
    label: '元数据检查周期（小时）',
    hint: '元数据检查的周期，定时复核订阅元数据状态',
    options: metaIntervalOptions,
  },
  best_version_cron: {
    key: 'best_version_cron',
    kind: 'cron',
    label: '洗版检查周期',
    hint: '洗版检查的周期，如 0 15 * * *',
  },
  download_monitor_enabled: {
    key: 'download_monitor_enabled',
    kind: 'switch',
    label: '下载超时自动删除',
    hint: '订阅下载超时将自动删除种子',
  },
  manual_delete_listen: {
    key: 'manual_delete_listen',
    kind: 'switch',
    label: '监听手动删除种子',
    hint: '监听用户手动删除的种子记录',
  },
  tracker_response_listen: {
    key: 'tracker_response_listen',
    kind: 'switch',
    label: '监听Tracker响应关键字',
    hint: '命中Tracker响应关键字时将自动删除种子',
  },
  open_tracker_dialog: {
    key: 'open_tracker_dialog',
    kind: 'switch',
    label: '打开Tracker配置窗口',
    hint: '自定义Tracker配置以实现更精准的种子匹配',
  },
  auto_search_when_delete: {
    key: 'auto_search_when_delete',
    kind: 'switch',
    label: '删除后触发搜索补全',
    hint: '种子删除后将自动触发搜索补全',
  },
  skip_deletion: {
    key: 'skip_deletion',
    kind: 'switch',
    label: '跳过种子删除记录',
    hint: '跳过最近删除的种子，避免再次下载',
  },
  download_timeout_minutes: {
    key: 'download_timeout_minutes',
    kind: 'number',
    label: '下载超时时间（分钟）',
    hint: '作为下载进度观察窗口，窗口内进度增长低于阈值时视为超时',
  },
  download_progress_threshold: {
    key: 'download_progress_threshold',
    kind: 'number',
    label: '下载超时进度阈值',
    hint: '超时窗口内下载进度增长低于N%时才删除',
  },
  download_retry_limit: {
    key: 'download_retry_limit',
    kind: 'number',
    label: '下载连续超时重试次数',
    hint: '连续低进度超时N次后保留种子并通知',
  },
  delete_record_retention_hours: {
    key: 'delete_record_retention_hours',
    kind: 'number',
    label: '种子删除记录保留（小时）',
    hint: '定时清理N小时前的种子删除记录',
  },
  delete_exclude_tags: {
    key: 'delete_exclude_tags',
    kind: 'text',
    label: '排除标签',
    hint: '需要排除的标签，多个标签用逗号分隔',
  },
  default_tracker_response: {
    key: 'default_tracker_response',
    kind: 'textarea',
    label: 'Tracker响应关键字',
    hint: '每一行一个关键字，忽略大小写，支持正则表达式匹配',
  },
  pending_enhanced_enabled: {
    key: 'pending_enhanced_enabled',
    kind: 'switch',
    label: '自动待定剧集订阅',
    hint: '自动标记订阅剧集为待定状态，避免提前完成订阅',
  },
  pending_download_enabled: {
    key: 'pending_download_enabled',
    kind: 'switch',
    label: '自动待定下载中订阅',
    hint: '存在进行中下载时自动标记待定，避免提前完成订阅',
  },
  auto_tv_pending_days: {
    key: 'auto_tv_pending_days',
    kind: 'number',
    label: '剧集待定天数',
    hint: '当前日期小于上映日期加N天，则视为待定，为0时不处理',
  },
  auto_tv_pending_episodes: {
    key: 'auto_tv_pending_episodes',
    kind: 'number',
    label: '剧集待定集数',
    hint: '剧集数小于等于设置的集数，则视为待定，为0时不处理',
  },
  pending_use_volatility: {
    key: 'pending_use_volatility',
    kind: 'switch',
    label: '待定参考变更速率',
    hint: '待定判定参考剧集更新的变更速率信号',
  },
  pause_enhanced_enabled: {
    key: 'pause_enhanced_enabled',
    kind: 'switch',
    label: '自动暂停订阅',
    hint: '自动标记订阅为暂停状态，避免无意义的请求',
  },
  auto_pause_users: {
    key: 'auto_pause_users',
    kind: 'text',
    label: '自动暂停新增订阅的用户（逗号分隔）',
    hint: '名单内用户新增订阅时将自动暂停，多个用户用逗号分隔，为空时不启用',
  },
  airing_pause_days: {
    key: 'airing_pause_days',
    kind: 'number',
    label: '即将播出暂停天数',
    hint: '已存在最新播出集，且下集距当前日期大于N天，则视为暂停，为0时不处理',
  },
  tv_air_pause_days: {
    key: 'tv_air_pause_days',
    kind: 'number',
    label: '剧集上映暂停天数',
    hint: '当前日期小于开播日期减N天，则视为暂停，为0时不处理',
  },
  movie_air_pause_days: {
    key: 'movie_air_pause_days',
    kind: 'number',
    label: '电影上映暂停天数',
    hint: '当前日期小于上映日期减N天，则视为暂停，为0时不处理',
  },
  tv_no_download_days: {
    key: 'tv_no_download_days',
    kind: 'number',
    label: '剧集无下载处理天数',
    hint: '剧集上映后N天内无新的订阅下载，则按策略处理，为0时不处理',
  },
  movie_no_download_days: {
    key: 'movie_no_download_days',
    kind: 'number',
    label: '电影无下载处理天数',
    hint: '电影上映后N天内无新的订阅下载，则按策略处理，为0时不处理',
  },
  no_download_actions: {
    key: 'no_download_actions',
    kind: 'multi-select',
    label: '无下载处理策略',
    hint: '选择无下载时的处理策略',
    options: noDownloadActionOptions,
  },
  best_version_type: {
    key: 'best_version_type',
    kind: 'select',
    label: '洗版类型',
    hint: '选择需要自动洗版的类型，关闭时不自动创建和巡检洗版订阅',
    options: bestVersionTypeOptions,
  },
  best_version_episode_to_full: {
    key: 'best_version_episode_to_full',
    kind: 'switch',
    label: '分集转全集',
    hint: '订阅目标集数满足时，从分集洗版切换为全集洗版',
  },
  best_version_backfill_enabled: {
    key: 'best_version_backfill_enabled',
    kind: 'switch',
    label: '回填已存在集',
    hint: '新建或转洗版时将媒体库已有集标为顶档并跳过',
  },
  backfill_best_version_now: {
    key: 'backfill_best_version_now',
    kind: 'switch',
    label: '立即扫描存量并回填',
    hint: '保存后对存量洗版订阅执行一次回填，执行后自动复位',
  },
  best_version_clear_history_type: {
    key: 'best_version_clear_history_type',
    kind: 'select',
    label: '清理整理记录范围',
    hint: '洗版下载时清理整理记录和文件的范围（破坏性）',
    options: bestVersionClearHistoryTypeOptions,
  },
  best_version_remaining_days: {
    key: 'best_version_remaining_days',
    kind: 'number',
    label: '洗版时限（天）',
    hint: '达到指定天数后自动终止洗版，有下载则按最新时间计算，为0时不限',
  },
  completion_guard_mode: {
    key: 'completion_guard_mode',
    kind: 'select',
    label: '完结守卫模式',
    hint: '选择完成前复核强度，默认使用平衡策略',
    options: completionGuardModeOptions,
  },
  volatility_enabled: {
    key: 'volatility_enabled',
    kind: 'switch',
    label: '变更速率信号',
    hint: '总集数近期变化时视为不稳定',
  },
  volatility_window_days: {
    key: 'volatility_window_days',
    kind: 'number',
    label: '变更速率窗口（天）',
    hint: '统计总集数变化的天数，越长越保守',
  },
  cadence_enabled: {
    key: 'cadence_enabled',
    kind: 'switch',
    label: '播出节奏信号',
    hint: '按已播间隔判断等待期，不会直接判定完结',
  },
  cadence_multiplier: {
    key: 'cadence_multiplier',
    kind: 'number',
    label: '节奏窗口系数',
    hint: '放大预计等待时间，数值越大等待越久',
  },
  cadence_min_window_days: {
    key: 'cadence_min_window_days',
    kind: 'number',
    label: '节奏窗口下限（天）',
    hint: '预计等待时间不得少于设置天数',
  },
  cadence_min_episodes: {
    key: 'cadence_min_episodes',
    kind: 'number',
    label: '节奏参与最少集数',
    hint: '已播集数达到设置值后才计算播出间隔',
  },
  season_cooldown_days: {
    key: 'season_cooldown_days',
    kind: 'number',
    label: '季冷却期（天）',
    hint: '最后一集播出后继续观察的天数',
  },
  verify_enabled: {
    key: 'verify_enabled',
    kind: 'switch',
    label: '自动纠错',
    hint: '完成后检查集数，增加时自动重建订阅',
  },
  verify_interval_hours: {
    key: 'verify_interval_hours',
    kind: 'number',
    label: '自动纠错间隔（小时）',
    hint: '完成后重新检查集数的间隔',
  },
  verify_retention_days: {
    key: 'verify_retention_days',
    kind: 'number',
    label: '快照保留（天）',
    hint: '完成快照按设置天数保留并自动清理，默认180天',
  },
  timeout_release_enabled: {
    key: 'timeout_release_enabled',
    kind: 'switch',
    label: '待定超时释放',
    hint: '完成守卫待定（P）超期后释放，信号不稳定时重新计时',
  },
  timeout_release_days: {
    key: 'timeout_release_days',
    kind: 'number',
    label: '待定超时释放（天）',
    hint: '完成守卫待定（P）允许保留的最长天数',
  },
  timeout_cadence_acceleration: {
    key: 'timeout_cadence_acceleration',
    kind: 'switch',
    label: '按节奏加速释放',
    hint: '等待期结束时将待定期限缩短一半',
  },
}

/**
 * 顶部全局开关字段，承载插件启停和一次性动作。
 */
export const topSwitchFields: FieldMeta[] = [
  { ...fields.enabled, md: 3 },
  { ...fields.notify, md: 3 },
  { ...fields.reset_task, md: 3 },
  { ...fields.onlyonce, md: 3 },
]

/**
 * 公共周期字段，控制各类巡检任务的执行频率。
 */
export const periodFields: FieldMeta[] = [
  { ...fields.auto_check_interval_minutes, md: 3 },
  { ...fields.download_check_interval_minutes, md: 3 },
  { ...fields.meta_check_interval_hours, md: 3 },
  { ...fields.best_version_cron, md: 3 },
]

/**
 * 配置分区布局，按业务域保持与后端表单一致的字段顺序。
 */
export const fieldSections: FieldSection[] = [
  {
    title: '种子删除',
    subtitle: '管理下载超时、Tracker 关键字和删除记录跳过策略。',
    rows: [
      [
        { ...fields.download_monitor_enabled, md: 4 },
        { ...fields.manual_delete_listen, md: 4 },
        { ...fields.tracker_response_listen, md: 4 },
      ],
      [
        { ...fields.open_tracker_dialog, md: 4 },
        { ...fields.auto_search_when_delete, md: 4 },
        { ...fields.skip_deletion, md: 4 },
      ],
      [
        { ...fields.download_timeout_minutes, md: 4 },
        { ...fields.download_progress_threshold, md: 4 },
        { ...fields.download_retry_limit, md: 4 },
      ],
      [
        { ...fields.delete_record_retention_hours, md: 4 },
        { ...fields.delete_exclude_tags, md: 4 },
        { ...fields.default_tracker_response, md: 4 },
      ],
    ],
  },
  {
    title: '订阅待定',
    subtitle: '控制剧集和下载中的订阅进入待定状态的条件。',
    rows: [
      [
        { ...fields.pending_download_enabled, md: 4 },
        { ...fields.pending_enhanced_enabled, md: 4 },
        { ...fields.pending_use_volatility, md: 4 },
      ],
      [
        { ...fields.auto_tv_pending_days, md: 6 },
        { ...fields.auto_tv_pending_episodes, md: 6 },
      ],
    ],
  },
  {
    title: '订阅暂停',
    subtitle: '控制自动暂停、播出前等待和无下载处理动作。',
    rows: [
      [
        { ...fields.pause_enhanced_enabled, md: 4 },
        { ...fields.auto_pause_users, md: 8 },
      ],
      [
        { ...fields.movie_air_pause_days, md: 4 },
        { ...fields.tv_air_pause_days, md: 4 },
        { ...fields.airing_pause_days, md: 4 },
      ],
      [
        { ...fields.movie_no_download_days, md: 4 },
        { ...fields.tv_no_download_days, md: 4 },
        { ...fields.no_download_actions, md: 4 },
      ],
    ],
  },
  {
    title: '订阅洗版',
    subtitle: '控制自动洗版范围、转全集、回填和整理记录清理范围。',
    rows: [
      [
        { ...fields.best_version_type, md: 4 },
        { ...fields.best_version_clear_history_type, md: 4 },
        { ...fields.best_version_remaining_days, md: 4 },
      ],
      [
        { ...fields.best_version_episode_to_full, md: 4 },
        { ...fields.best_version_backfill_enabled, md: 4 },
        { ...fields.backfill_best_version_now, md: 4 },
      ],
    ],
  },
  {
    title: '完结信号',
    subtitle: '控制完成前复核、播出节奏、完成后纠错和待定释放策略。',
    rows: [
      [
        { ...fields.completion_guard_mode, md: 4 },
        { ...fields.volatility_enabled, md: 4 },
        { ...fields.cadence_enabled, md: 4 },
      ],
      [
        { ...fields.verify_enabled, md: 4 },
        { ...fields.timeout_release_enabled, md: 4 },
        { ...fields.timeout_cadence_acceleration, md: 4 },
      ],
      [
        { ...fields.volatility_window_days, md: 4 },
        { ...fields.cadence_multiplier, md: 4 },
        { ...fields.cadence_min_window_days, md: 4 },
      ],
      [
        { ...fields.cadence_min_episodes, md: 4 },
        { ...fields.season_cooldown_days, md: 4 },
        { ...fields.verify_interval_hours, md: 4 },
      ],
      [
        { ...fields.verify_retention_days, md: 4 },
        { ...fields.timeout_release_days, md: 4 },
      ],
    ],
  },
]
