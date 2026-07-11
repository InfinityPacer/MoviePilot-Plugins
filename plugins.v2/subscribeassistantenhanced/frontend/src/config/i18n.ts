import { type ConfigKey } from './defaults'
import { fields, groups, type FieldMeta, type GroupKey, type GroupMeta } from './fields'

/** MoviePilot Host 当前公开支持的语言。 */
export type SupportedLocale = 'zh-CN' | 'zh-TW' | 'en-US'
export type LocaleSource = unknown | { value?: LocaleSource }
export type TranslationParams = Record<string, string | number>

const supportedLocales = new Set<SupportedLocale>(['zh-CN', 'zh-TW', 'en-US'])

/** 将 Host locale、ref 或嵌套 ref 规范化为插件支持的语言。 */
export function normalizeLocale(source: LocaleSource): SupportedLocale {
  let current = source
  const visited = new Set<object>()
  while (current && typeof current === 'object' && 'value' in current) {
    if (visited.has(current)) return 'zh-CN'
    visited.add(current)
    current = (current as { value?: LocaleSource }).value
  }
  if (typeof current !== 'string') return 'zh-CN'
  const normalized = current.trim().replace('_', '-').toLowerCase()
  const locale = normalized === 'zh-cn'
    ? 'zh-CN'
    : normalized === 'zh-tw'
      ? 'zh-TW'
      : normalized === 'en-us'
        ? 'en-US'
        : 'zh-CN'
  return supportedLocales.has(locale) ? locale : 'zh-CN'
}

const messages: Record<SupportedLocale, Record<string, string>> = {
  'zh-CN': {
    'config.changedCount': '{count} 项待保存',
    'config.changes': '本次修改',
    'config.moreChanges': '另有 {count} 项',
    'config.save': '保存修改',
    'config.close': '关闭',
    'config.cadence': '运行节奏',
    'config.generalInspection': '通用巡检',
    'config.downloadInspection': '下载检查',
    'config.metadataInspection': '元数据检查',
    'config.bestVersionInspection': '洗版检查',
    'config.everyMinutes': '每 {value} 分钟',
    'config.everyHours': '每 {value} 小时',
    'config.notScheduled': '未设置',
    'config.activeDomains': '已启用能力',
    'config.help': '插件帮助',
    'config.plugin': '插件',
    'config.settings': '插件设置',
    'config.selectGroup': '选择配置分组',
    'config.unsaved': '未保存',
    'config.done': '完成',
    'config.edit': '编辑',
    'config.decrease': '减小{label}', 'config.increase': '增大{label}', 'config.editLabel': '编辑{label}',
    'config.yamlTitle': '自定义识别规则',
    'config.runtime': '运行概况',
    'config.runtimeLoading': '正在读取运行概况',
    'config.runtimeUnavailable': '运行概况暂不可用',
    'config.pendingCount': '待定订阅',
    'config.monitoredCount': '下载任务',
    'config.enabled': '启用',
    'config.off': '关闭',
    'config.cronPlaceholder': '5 位 CRON 表达式',
    'config.title': '订阅助手（增强版）',
    'domain.completionGuard': '完结守卫模式', 'domain.pending': '待定增强', 'domain.pause': '暂停优化',
    'domain.bestVersion': '自动洗版', 'domain.download': '下载管理', 'domain.verify': '完成后验证',
    'domain.siteTotal': '站点集数探测', 'domain.siteCompletion': '站点完结信号', 'domain.recognition': '识别增强',
    'section.running': '运行状态',
    'section.oneTime': '一次性动作',
    'section.schedule': '公共周期',
    'section.download': '下载任务处理',
    'section.timeout': '超时与重试',
    'section.cleanup': '订阅记录清理',
    'section.pending': '待定策略',
    'section.tvDecision': '剧集判定',
    'section.autoPause': '自动暂停',
    'section.airing': '上映与播出窗口',
    'section.noDownload': '无下载处理',
    'section.siteProbe': '站点集数探测',
    'section.pausedProbe': '暂停订阅补搜',
    'section.bestVersionScope': '洗版范围',
    'section.backfill': '转换与回填',
    'section.guard': '守卫信号',
    'section.cadence': '播出节奏',
    'section.correction': '纠错与释放',
    'section.recognition': '识别策略',
    'section.custom': '自定义规则',
  },
  'zh-TW': {
    'config.changedCount': '{count} 項待儲存',
    'config.changes': '本次修改',
    'config.moreChanges': '另有 {count} 項',
    'config.save': '儲存修改',
    'config.close': '關閉',
    'config.cadence': '執行節奏',
    'config.generalInspection': '通用巡檢',
    'config.downloadInspection': '下載檢查',
    'config.metadataInspection': '元資料檢查',
    'config.bestVersionInspection': '洗版檢查',
    'config.everyMinutes': '每 {value} 分鐘',
    'config.everyHours': '每 {value} 小時',
    'config.notScheduled': '未設定',
    'config.activeDomains': '已啟用能力',
    'config.help': '外掛說明',
    'config.plugin': '外掛', 'config.settings': '外掛設定', 'config.selectGroup': '選擇設定分組',
    'config.unsaved': '尚未儲存', 'config.done': '完成', 'config.edit': '編輯',
    'config.decrease': '減少{label}', 'config.increase': '增加{label}', 'config.editLabel': '編輯{label}',
    'config.yamlTitle': '自訂識別規則',
    'config.runtime': '執行概況', 'config.runtimeLoading': '正在讀取執行概況',
    'config.runtimeUnavailable': '執行概況暫不可用', 'config.pendingCount': '待定訂閱',
    'config.monitoredCount': '下載任務', 'config.enabled': '啟用', 'config.off': '關閉',
    'config.cronPlaceholder': '5 位 CRON 表示式',
    'config.title': '訂閱助手（增強版）',
    'domain.completionGuard': '完結守衛模式', 'domain.pending': '待定增強', 'domain.pause': '暫停最佳化',
    'domain.bestVersion': '自動洗版', 'domain.download': '下載管理', 'domain.verify': '完成後驗證',
    'domain.siteTotal': '站點集數探測', 'domain.siteCompletion': '站點完結訊號', 'domain.recognition': '識別增強',
    'section.running': '執行狀態', 'section.oneTime': '單次操作', 'section.schedule': '共用週期',
    'section.download': '下載任務處理', 'section.timeout': '逾時與重試', 'section.cleanup': '訂閱記錄清理',
    'section.pending': '待定策略', 'section.tvDecision': '影集判定', 'section.autoPause': '自動暫停',
    'section.airing': '上映與播出窗口', 'section.noDownload': '無下載處理',
    'section.siteProbe': '站點集數探測',
    'section.pausedProbe': '暫停訂閱補搜', 'section.bestVersionScope': '洗版範圍',
    'section.backfill': '轉換與回填', 'section.guard': '守衛訊號', 'section.cadence': '播出節奏',
    'section.correction': '修正與釋放', 'section.recognition': '識別策略', 'section.custom': '自訂規則',
  },
  'en-US': {
    'config.changedCount': '{count} to save',
    'config.changes': 'Changes',
    'config.moreChanges': '{count} more',
    'config.save': 'Save changes',
    'config.close': 'Close',
    'config.cadence': 'Run cadence',
    'config.generalInspection': 'General inspection',
    'config.downloadInspection': 'Download checks',
    'config.metadataInspection': 'Metadata checks',
    'config.bestVersionInspection': 'Best-version checks',
    'config.everyMinutes': 'Every {value} min',
    'config.everyHours': 'Every {value} hr',
    'config.notScheduled': 'Not set',
    'config.activeDomains': 'Active capabilities',
    'config.help': 'Plugin help',
    'config.plugin': 'Plugins', 'config.settings': 'Plugin settings', 'config.selectGroup': 'Select settings group',
    'config.unsaved': 'Unsaved', 'config.done': 'Done', 'config.edit': 'Edit',
    'config.decrease': 'Decrease {label}', 'config.increase': 'Increase {label}', 'config.editLabel': 'Edit {label}',
    'config.yamlTitle': 'Custom recognition rules',
    'config.runtime': 'Runtime summary', 'config.runtimeLoading': 'Loading runtime summary',
    'config.runtimeUnavailable': 'Runtime summary unavailable', 'config.pendingCount': 'Pending subscriptions',
    'config.monitoredCount': 'Downloads', 'config.enabled': 'Enabled', 'config.off': 'Off',
    'config.cronPlaceholder': '5-field CRON expression',
    'config.title': 'Subscribe Assistant (Enhanced)',
    'domain.completionGuard': 'Completion guard mode', 'domain.pending': 'Pending enhancement', 'domain.pause': 'Pause optimization',
    'domain.bestVersion': 'Automatic upgrades', 'domain.download': 'Download management', 'domain.verify': 'Post-completion verification',
    'domain.siteTotal': 'Site episode probe', 'domain.siteCompletion': 'Site completion signal', 'domain.recognition': 'Recognition',
    'section.running': 'Runtime state', 'section.oneTime': 'One-time actions', 'section.schedule': 'Shared schedules',
    'section.download': 'Download handling', 'section.timeout': 'Timeouts and retries', 'section.cleanup': 'Subscription cleanup',
    'section.pending': 'Pending policy', 'section.tvDecision': 'TV decisions', 'section.autoPause': 'Automatic pause',
    'section.airing': 'Release and airing windows', 'section.noDownload': 'No-download handling',
    'section.siteProbe': 'Site episode probe',
    'section.pausedProbe': 'Paused subscription search', 'section.bestVersionScope': 'Best-version scope',
    'section.backfill': 'Conversion and backfill', 'section.guard': 'Guard signals', 'section.cadence': 'Airing cadence',
    'section.correction': 'Correction and release', 'section.recognition': 'Recognition policy', 'section.custom': 'Custom rules',
  },
}

/** 使用稳定 UI key 翻译插件文案；缺键直接报错以阻止静默漏翻。 */
export function t(localeSource: LocaleSource, key: string, params: TranslationParams = {}): string {
  const locale = normalizeLocale(localeSource)
  const template = messages[locale][key] ?? messages['zh-CN'][key]
  if (!template) throw new Error(`Missing translation key: ${key}`)
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match
  ))
}

const groupTranslations: Record<GroupKey, { tw: [string, string], en: [string, string] }> = {
  global: { tw: ['全域執行', '外掛開關、通知、單次操作與共用週期'], en: ['General', 'Plugin state, notifications, one-time actions, and shared schedules'] },
  cleanup: { tw: ['訂閱清理', '下載監控、刪除種子、Tracker 與整理記錄清理'], en: ['Cleanup', 'Download monitoring, torrent removal, Tracker rules, and history cleanup'] },
  pending: { tw: ['訂閱待定', '下載中或集數目標尚未穩定時保持待定'], en: ['Pending', 'Keep subscriptions pending while downloads or episode targets are unsettled'] },
  pause: { tw: ['訂閱暫停', '依使用者、播出窗口與無下載策略暫停訂閱'], en: ['Pause', 'Pause subscriptions by user, release window, or no-download policy'] },
  completion: { tw: ['訂閱補全', '站點集數探測與暫停訂閱補搜'], en: ['Completion', 'Site episode probes and paused subscription searches'] },
  bestVersion: { tw: ['訂閱洗版', '洗版範圍、時限、回填與分集轉全集'], en: ['Best version', 'Upgrade scope, time limits, backfill, and episode-to-season conversion'] },
  guard: { tw: ['完結訊號', '完結守衛、站點證據、波動節奏與自動修正'], en: ['Completion guard', 'Completion checks, site evidence, cadence, and automatic correction'] },
  recognition: { tw: ['識別增強', '候選准入、通知、二次識別與自訂策略'], en: ['Recognition', 'Candidate checks, notifications, re-identification, and custom policies'] },
}

type EnglishFieldText = readonly [label: string, hint: string]

const englishFields: Record<ConfigKey, EnglishFieldText> = {
  enabled: ['Enable plugin', 'Activate the plugin and register its scheduled tasks'],
  notify: ['Send notifications', 'Send notifications when relevant events occur'],
  onlyonce: ['Run once now', 'Run a full inspection after saving, then reset automatically'],
  reset_task: ['Reset data', 'Reset all pending, paused, and monitored task data, then reset automatically'],
  auto_check_interval_minutes: ['General check interval (minutes)', 'Interval for site sampling, pending release, no-download handling, and cleanup'],
  download_check_interval_minutes: ['Download check interval (minutes)', 'How often download task status is checked'],
  meta_check_interval_hours: ['Metadata check interval (hours)', 'How often subscription metadata is reviewed'],
  best_version_cron: ['Best-version schedule', 'CRON schedule for best-version checks, for example 0 15 * * *'],
  download_monitor_enabled: ['Remove stalled downloads', 'Automatically remove subscription torrents that time out'],
  manual_delete_listen: ['Watch manual torrent removal', 'Record torrents manually removed by the user'],
  tracker_response_listen: ['Watch Tracker response keywords', 'Remove torrents when a configured Tracker response keyword matches'],
  auto_search_when_delete: ['Search after removal', 'Trigger a completion search after removing a torrent'],
  skip_deletion: ['Skip recently removed releases', 'Avoid downloading recently removed torrents again'],
  download_timeout_minutes: ['Download timeout (minutes)', 'Observation window used to detect downloads with insufficient progress'],
  download_progress_threshold: ['Download progress threshold', 'Remove only when progress increases by less than N% during the timeout window'],
  download_retry_limit: ['Consecutive timeout limit', 'Keep the torrent and notify after N consecutive low-progress timeouts'],
  delete_exclude_tags: ['Excluded tags', 'Comma-separated tags that must not be processed'],
  default_tracker_response: ['Tracker response keywords', 'One keyword per line; case-insensitive regular expressions are supported'],
  delete_record_retention_hours: ['Removal history retention (hours)', 'Periodically remove deletion records older than N hours'],
  subscription_cleanup_history_type: ['Cleanup media scope', 'Media types whose old transfer records and files are removed before download'],
  subscription_cleanup_history_scenes: ['Cleanup trigger scenarios', 'Choose which subscription download scenarios trigger cleanup'],
  recognition_guard_mode: ['Recognition mode', 'Review whether a candidate matches the subscription target before automatic download'],
  recognition_guard_notify: ['Recognition notifications', 'Control recognition messages without affecting audit logs'],
  recognition_guard_notify_interval: ['Notification rate limit (seconds)', 'Minimum interval for the same subscription, action, and reason'],
  recognition_guard_tmdb_recheck_mode: ['Secondary recognition', 'Control when secondary recognition is performed'],
  recognition_guard_cache_maxsize: ['Recognition cache size', 'Cache secondary recognition results to avoid duplicate requests'],
  recognition_guard_custom_config: ['Custom recognition rules', 'Edit only when built-in rules are insufficient; leave empty to inherit the current mode'],
  pending_enhanced_enabled: ['Automatically pend TV subscriptions', 'Mark TV subscriptions pending to avoid completing them too early'],
  pending_download_enabled: ['Pend active downloads', 'Keep subscriptions pending while downloads are in progress'],
  auto_tv_pending_days: ['TV pending days', 'Keep pending before the release date plus N days; 0 disables this rule'],
  auto_tv_pending_episodes: ['TV pending episode count', 'Keep pending when the episode count is at or below this value; 0 disables this rule'],
  pending_use_volatility: ['Use change rate for pending', 'Pend early when the total episode count changes near completion'],
  pause_enhanced_enabled: ['Automatically pause subscriptions', 'Pause subscriptions to avoid unnecessary requests'],
  auto_pause_users: ['Auto-pause users (comma-separated)', 'Pause new subscriptions from listed users; leave empty to disable'],
  airing_pause_days: ['Upcoming episode pause days', 'Pause when the next episode is more than N days away; 0 disables this rule'],
  movie_air_pause_days: ['Movie release pause days', 'Pause until N days before the movie release date; 0 disables this rule'],
  tv_air_pause_days: ['TV premiere pause days', 'Pause until N days before the TV premiere date; 0 disables this rule'],
  movie_no_download_days: ['Movie no-download days', 'Apply the selected policy when no movie download occurs within N days; 0 disables it'],
  tv_no_download_days: ['TV no-download days', 'Apply the selected policy when no TV download occurs within N days; 0 disables it'],
  no_download_actions: ['No-download actions', 'Choose the actions to apply when no download is found'],
  site_total_probe_enabled: ['Probe site episode totals', 'Use cached site releases to detect an incomplete episode target'],
  paused_probe_reasons: ['Paused search scenarios', 'Choose pause reasons that allow low-frequency searches'],
  paused_probe_min_pause_days: ['Search after N paused days', 'Start searching after this many paused days; 0 disables it'],
  paused_probe_interval_hours: ['Search interval (hours)', 'Minimum interval between two searches for the same subscription'],
  best_version_type: ['Best-version type', 'Select media types for automatic upgrades; Off disables creation and checks'],
  best_version_movie_remaining_days: ['Movie upgrade time limit (days)', 'Stop movie upgrade subscriptions after this period; 0 means unlimited'],
  best_version_tv_remaining_days: ['TV upgrade time limit (days)', 'Stop TV upgrade subscriptions after this period; 0 means unlimited'],
  best_version_episode_to_full: ['Convert episodes to full season', 'Switch from episode upgrades to a full-season upgrade when the target is met'],
  best_version_backfill_enabled: ['Backfill existing episodes', 'Backfill library episodes when creating or converting an episode upgrade'],
  backfill_best_version_now: ['Scan and backfill now', 'Backfill existing episode-upgrade subscriptions after saving, then reset automatically'],
  completion_guard_mode: ['Completion guard mode', 'Choose the review strength used before completion; Balanced is the default'],
  site_completion_evidence_enabled: ['Use site completion evidence', 'Use site release titles as supporting completion evidence'],
  volatility_enabled: ['Episode-count change signal', 'Treat recent total episode count changes as unstable'],
  volatility_window_days: ['Change-rate window (days)', 'Number of days used to measure total episode count changes'],
  cadence_enabled: ['Airing cadence signal', 'Estimate the waiting period from airing intervals without directly marking completion'],
  cadence_multiplier: ['Cadence window multiplier', 'Increase the estimated waiting period; higher values wait longer'],
  cadence_min_window_days: ['Minimum cadence window (days)', 'The estimated waiting period cannot be shorter than this value'],
  cadence_min_episodes: ['Minimum episodes for cadence', 'Calculate airing intervals only after this many episodes have aired'],
  season_cooldown_days: ['Season cooldown (days)', 'Continue observing for this many days after the last episode airs'],
  verify_enabled: ['Automatic correction', 'Recheck completed episode counts and rebuild subscriptions when the count increases'],
  verify_interval_hours: ['Correction interval (hours)', 'Interval for rechecking episode counts after completion'],
  verify_retention_days: ['Snapshot retention (days)', 'Retain completion snapshots for this many days; default is 180'],
  timeout_release_days: ['Pre-completion observation days', 'Maximum number of days allowed for pre-completion observation'],
  timeout_cadence_acceleration: ['Accelerate release by cadence', 'Shorten the observation period after the cadence waiting window ends'],
}

const traditionalPhrases: Array<[string, string]> = [
  ['插件', '外掛'], ['启用', '啟用'], ['发送', '傳送'], ['通知', '通知'], ['运行', '執行'],
  ['重置', '重設'], ['数据', '資料'], ['检查', '檢查'], ['周期', '週期'], ['下载', '下載'],
  ['订阅', '訂閱'], ['删除', '刪除'], ['记录', '記錄'], ['监听', '監聽'], ['关键字', '關鍵字'],
  ['进度', '進度'], ['连续', '連續'], ['时', '時'], ['分钟', '分鐘'], ['小时', '小時'],
  ['自动', '自動'], ['状态', '狀態'], ['配置', '設定'], ['识别', '識別'], ['增强', '增強'],
  ['自定义', '自訂'], ['剧集', '影集'], ['电影', '電影'], ['上映', '上映'], ['暂停', '暫停'],
  ['用户', '使用者'], ['选择', '選擇'], ['范围', '範圍'], ['场景', '情境'], ['关闭', '關閉'],
  ['全部', '全部'], ['严格', '嚴格'], ['宽松', '寬鬆'], ['平衡', '平衡'], ['仅', '僅'],
  ['完结', '完結'], ['信号', '訊號'], ['纠错', '修正'], ['变更', '變更'], ['节奏', '節奏'],
  ['间隔', '間隔'], ['默认', '預設'], ['目标', '目標'], ['满足', '符合'], ['转换', '轉換'],
  ['转', '轉'], ['扫描', '掃描'], ['存量', '既有'], ['回填', '回填'], ['媒体库', '媒體庫'],
  ['整理', '整理'], ['文件', '檔案'], ['多个', '多個'], ['为空', '留空'], ['表示', '表示'],
  ['开启', '開啟'], ['发生', '發生'], ['复核', '複核'], ['触发', '觸發'], ['清理', '清理'],
  ['待定', '待定'], ['完成', '完成'], ['总集数', '總集數'], ['集数', '集數'], ['天数', '天數'],
  ['策略', '策略'], ['模式', '模式'], ['缓存', '快取'], ['大小', '大小'], ['支持', '支援'],
  ['处于激活状态', '處於啟用狀態'], ['正则表达式', '正規表示式'], ['媒体类型', '媒體類型'], ['审计', '稽核'], ['消息推送', '訊息推送'],
  ['站点', '站點'], ['搜索', '搜尋'], ['补搜', '補搜'], ['巡检', '巡檢'], ['种子', '種子'],
  ['任务', '任務'], ['标签', '標籤'], ['请求', '請求'], ['名单', '名單'], ['候选', '候選'],
  ['标题', '標題'], ['诊断', '診斷'], ['类型', '類型'], ['创建', '建立'], ['终止', '終止'],
  ['守卫', '守衛'], ['统计', '統計'], ['判断', '判斷'], ['预计', '預計'], ['参与', '參與'],
  ['观察', '觀察'], ['释放', '釋放'], ['结果', '結果'], ['动作', '動作'], ['原因', '原因'],
  ['频', '頻'], ['秒数', '秒數'], ['资源', '資源'], ['辅助', '輔助'], ['不足', '不足'],
  ['允许', '允許'], ['达到', '達到'], ['两次', '兩次'], ['轮数', '輪數'], ['提醒', '提醒'],
  ['强度', '強度'], ['佐证', '佐證'], ['稳定', '穩定'], ['增加', '增加'], ['重新', '重新'],
  ['最后', '最後'], ['继续', '繼續'], ['结束', '結束'], ['缩短', '縮短'], ['保存', '儲存'],
  ['采样', '取樣'], ['补全', '補全'], ['手动', '手動'], ['跳过', '略過'], ['作为', '作為'],
  ['低于', '低於'], ['视为', '視為'], ['一个', '一個'], ['大小写', '大小寫'], ['精准', '精準'],
  ['入库', '入庫'], ['日志', '日誌'], ['明细', '明細'], ['覆盖', '覆蓋'], ['进行', '進行'],
  ['设置', '設定'], ['等于', '等於'], ['参考', '參考'], ['意义', '意義'], ['逗号', '逗號'],
  ['探测', '探測'], ['多少轮', '多少輪'], ['计算', '計算'], ['新建', '建立'], ['切换', '切換'],
  ['于', '於'], ['视', '視'], ['采', '採'], ['补', '補'], ['删', '刪'], ['轮', '輪'], ['算', '算'],
  ['后', '後'], ['会', '會'], ['将', '將'], ['处', '處'], ['为', '為'], ['与', '與'], ['发', '發'],
  ['过', '過'], ['这', '這'], ['则', '則'], ['无', '無'], ['设', '設'], ['选', '選'], ['线', '線'],
  ['响', '響'], ['应', '應'], ['种', '種'], ['从', '從'], ['开', '開'], ['进', '進'], ['间', '間'], ['数', '數'],
  ['长', '長'], ['现', '現'], ['还', '還'], ['较', '較'], ['达', '達'], ['实', '實'], ['复', '複'],
  ['对', '對'], ['内', '內'], ['样', '樣'], ['并', '並'], ['当', '當'], ['监', '監'], ['执', '執'],
  ['检', '檢'], ['动', '動'], ['试', '試'], ['阈', '閾'], ['值', '值'], ['写', '寫'], ['号', '號'],
  ['旧', '舊'], ['库', '庫'], ['坏', '壞'], ['记', '記'], ['覆', '覆'], ['标', '標'], ['变化', '變化'],
  ['减', '減'], ['满', '滿'], ['少', '少'], ['低', '低'], ['冷却', '冷卻'], ['换', '換'], ['别', '別'],
]

function toTraditional(text: string): string {
  return traditionalPhrases.reduce((result, [source, target]) => result.replaceAll(source, target), text)
}

const englishOptionTitles: Record<string, string> = {
  no: 'Off', off: 'Off', all: 'All', movie: 'Movies', tv: 'TV shows', tv_episode: 'TV shows (individual episodes)',
  normal: 'Standard subscriptions', best_version: 'Best-version subscriptions', best_version_episode: 'Episode upgrades',
  audit: 'Audit', loose: 'Relaxed', balanced: 'Balanced', strict: 'Strict', summary: 'Summary', detail: 'Details',
  balanced_strict: 'Balanced and strict', pause_movie: 'Pause movie subscriptions', pause_tv: 'Pause TV subscriptions',
  complete_movie: 'Complete movie subscriptions', complete_tv: 'Complete TV subscriptions',
  delete_movie: 'Delete movie subscriptions', delete_tv: 'Delete TV subscriptions', no_download: 'No downloads',
  pre_air: 'Before release', airing_gap: 'Airing gap', auto_user: 'User rule', external: 'External pause', notify: 'Notify only',
}

function localizedOptionTitle(locale: SupportedLocale, field: FieldMeta, value: string | number, source: string): string {
  if (locale === 'zh-CN') return source
  if (locale === 'zh-TW') return toTraditional(source)
  if (typeof value === 'number') {
    if (field.key === 'auto_check_interval_minutes' || field.key === 'download_check_interval_minutes') return `${value} minutes`
    if (field.key === 'meta_check_interval_hours') return `${value} hours`
    return String(value)
  }
  const translated = englishOptionTitles[value]
  if (!translated) throw new Error(`Missing option translation: ${field.key}.${value}`)
  return translated
}

/** 返回不修改源元数据的本地化分组副本。 */
export function localizeGroups(localeSource: LocaleSource, source: readonly GroupMeta[] = groups): GroupMeta[] {
  const locale = normalizeLocale(localeSource)
  return source.map(group => {
    const translation = groupTranslations[group.key]
    if (!translation) throw new Error(`Missing group translation: ${group.key}`)
    const [title, summary] = locale === 'zh-CN'
      ? [group.title, group.summary]
      : locale === 'zh-TW'
        ? translation.tw
        : translation.en
    return { ...group, title, summary }
  })
}

/** 返回不修改源元数据的本地化字段与选项副本。 */
export function localizeFields(localeSource: LocaleSource, source: readonly FieldMeta[] = fields): FieldMeta[] {
  const locale = normalizeLocale(localeSource)
  return source.map(field => {
    const english = englishFields[field.key]
    if (!english) throw new Error(`Missing field translation: ${field.key}`)
    const label = locale === 'zh-CN' ? field.label : locale === 'zh-TW' ? toTraditional(field.label) : english[0]
    const hint = field.hint
      ? locale === 'zh-CN'
        ? field.hint
        : locale === 'zh-TW'
          ? field.key === 'recognition_guard_custom_config'
            ? '僅在內建規則無法滿足時編輯，留空則繼承目前模式'
            : toTraditional(field.hint)
          : english[1]
      : undefined
    if (!label.trim() || (field.hint && !hint?.trim())) throw new Error(`Empty field translation: ${field.key}`)
    return {
      ...field,
      label,
      hint,
      options: field.options?.map(option => ({
        ...option,
        title: localizedOptionTitle(locale, field, option.value, option.title),
      })),
    }
  })
}

/** 在测试或启动期验证当前元数据不存在翻译缺口。 */
export function assertTranslationCoverage(): void {
  for (const locale of ['zh-CN', 'zh-TW', 'en-US'] as const) {
    localizeGroups(locale)
    localizeFields(locale)
  }
}
