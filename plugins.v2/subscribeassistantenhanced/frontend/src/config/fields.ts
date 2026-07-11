import { type ConfigKey } from './defaults'

/** Vue 字段对应的 Vuetify 控件类别。 */
export type FieldKind = 'switch' | 'number' | 'text' | 'select' | 'multi-select' | 'cron' | 'textarea'
/** 配置项对订阅生命周期和数据的影响等级。 */
export type RiskLevel = 'none' | 'notice' | 'danger'

/** 下拉或多选项的展示值与持久化值。 */
export interface FieldOption {
  /** 用户可见名称。 */
  title: string
  /** 写入插件配置的稳定值。 */
  value: string | number
}

/** 配置页业务分组键。 */
export type GroupKey =
  | 'global'
  | 'cleanup'
  | 'pending'
  | 'pause'
  | 'completion'
  | 'bestVersion'
  | 'guard'
  | 'recognition'

/** 单个配置字段的渲染与风险元数据。 */
export interface FieldMeta {
  /** 与 PluginConfig.defaults() 一致的持久化键。 */
  key: ConfigKey
  /** 来自现有 Form/README 契约的中文名称。 */
  label: string
  /** 字段所属配置分组。 */
  group: GroupKey
  /** 字段使用的 Vuetify 控件类别。 */
  kind: FieldKind
  /** 来自现有 Form 的简短说明。 */
  hint?: string
  /** 在窄屏或默认视图中可折叠。 */
  advanced?: boolean
  /** 用于影响提示的风险等级。 */
  risk?: RiskLevel
  /** select 与 multi-select 的稳定候选值。 */
  options?: FieldOption[]
  /** 仅保留在完整保存 payload 中，不渲染为 Vue 控件。 */
  legacyUiKey?: boolean
  /** 只在专用弹窗中编辑，不进入普通字段列表。 */
  dialogOnly?: boolean
}

/** 左侧业务分组导航与摘要元数据。 */
export interface GroupMeta {
  /** 与 FieldMeta.group 对齐的稳定分组键。 */
  key: GroupKey
  /** 用户可见分组名。 */
  title: string
  /** MoviePilot 已提供的 Material Design 图标名。 */
  icon: string
  /** 分组涉及的业务范围摘要。 */
  summary: string
  /** 分组是否包含明显破坏性配置。 */
  highRisk?: boolean
}

export const groups: GroupMeta[] = [
  { key: 'global', title: '全局运行', icon: 'mdi-tune-variant', summary: '插件开关、通知、一次性动作与公共周期' },
  { key: 'cleanup', title: '订阅清理', icon: 'mdi-delete-sweep-outline', summary: '下载监控、删种、Tracker 与整理记录清理', highRisk: true },
  { key: 'pending', title: '订阅待定', icon: 'mdi-timer-sand', summary: '下载中与剧集目标未稳定时保持待定' },
  { key: 'pause', title: '订阅暂停', icon: 'mdi-pause-circle-outline', summary: '按用户、上映播出窗口和无下载策略暂停订阅' },
  { key: 'completion', title: '订阅补全', icon: 'mdi-radar', summary: '站点集数探测与暂停订阅补搜' },
  { key: 'bestVersion', title: '订阅洗版', icon: 'mdi-auto-fix', summary: '洗版范围、时限、回填和分集转全集', highRisk: true },
  { key: 'guard', title: '完结信号', icon: 'mdi-shield-check-outline', summary: '完结守卫、站点证据、波动节奏和自动纠错' },
  { key: 'recognition', title: '识别增强', icon: 'mdi-account-search-outline', summary: '候选准入、通知、二次识别和自定义策略' },
]

export const fields: FieldMeta[] = [
  {
    "key": "enabled",
    "label": "启用插件",
    "group": "global",
    "kind": "switch",
    "hint": "开启后插件将处于激活状态"
  },
  {
    "key": "notify",
    "label": "发送通知",
    "group": "global",
    "kind": "switch",
    "hint": "是否在特定事件发生时发送通知"
  },
  {
    "key": "onlyonce",
    "label": "立即运行一次",
    "group": "global",
    "kind": "switch",
    "hint": "保存后立即运行一次全量巡检，执行后自动复位"
  },
  {
    "key": "reset_task",
    "label": "重置数据",
    "group": "global",
    "kind": "switch",
    "hint": "将重置所有待定/暂停/监控等任务数据，执行后自动复位",
    "risk": "danger"
  },
  {
    "key": "auto_check_interval_minutes",
    "label": "通用巡检周期（分钟）",
    "group": "global",
    "kind": "select",
    "hint": "站点采样、待定释放、无下载处理和清理周期",
    "options": [
      {
        "title": "10分钟",
        "value": 10
      },
      {
        "title": "20分钟",
        "value": 20
      },
      {
        "title": "30分钟",
        "value": 30
      },
      {
        "title": "60分钟",
        "value": 60
      },
      {
        "title": "120分钟",
        "value": 120
      },
      {
        "title": "240分钟",
        "value": 240
      }
    ],
    "advanced": true
  },
  {
    "key": "download_check_interval_minutes",
    "label": "下载检查周期（分钟）",
    "group": "global",
    "kind": "select",
    "hint": "下载检查的周期，定时检查下载任务状态",
    "options": [
      {
        "title": "5分钟",
        "value": 5
      },
      {
        "title": "10分钟",
        "value": 10
      },
      {
        "title": "15分钟",
        "value": 15
      },
      {
        "title": "30分钟",
        "value": 30
      },
      {
        "title": "60分钟",
        "value": 60
      },
      {
        "title": "120分钟",
        "value": 120
      }
    ],
    "advanced": true
  },
  {
    "key": "meta_check_interval_hours",
    "label": "元数据检查周期（小时）",
    "group": "global",
    "kind": "select",
    "hint": "元数据检查的周期，定时复核订阅元数据状态",
    "options": [
      {
        "title": "1小时",
        "value": 1
      },
      {
        "title": "3小时",
        "value": 3
      },
      {
        "title": "6小时",
        "value": 6
      },
      {
        "title": "12小时",
        "value": 12
      },
      {
        "title": "24小时",
        "value": 24
      }
    ],
    "advanced": true
  },
  {
    "key": "best_version_cron",
    "label": "洗版检查周期",
    "group": "global",
    "kind": "cron",
    "hint": "洗版检查的周期，如 0 15 * * *"
  },
  {
    "key": "download_monitor_enabled",
    "label": "下载超时自动删除",
    "group": "cleanup",
    "kind": "switch",
    "hint": "订阅下载超时将自动删除种子",
    "risk": "danger"
  },
  {
    "key": "manual_delete_listen",
    "label": "监听手动删除种子",
    "group": "cleanup",
    "kind": "switch",
    "hint": "监听用户手动删除的种子记录",
    "risk": "danger"
  },
  {
    "key": "tracker_response_listen",
    "label": "监听Tracker响应关键字",
    "group": "cleanup",
    "kind": "switch",
    "hint": "命中Tracker响应关键字时将自动删除种子",
    "risk": "danger"
  },
  {
    "key": "auto_search_when_delete",
    "label": "删除后触发搜索补全",
    "group": "cleanup",
    "kind": "switch",
    "hint": "删种后将自动触发搜索补全"
  },
  {
    "key": "skip_deletion",
    "label": "跳过近期删除资源",
    "group": "cleanup",
    "kind": "switch",
    "hint": "跳过最近删除的种子，避免再次下载"
  },
  {
    "key": "download_timeout_minutes",
    "label": "下载超时时间（分钟）",
    "group": "cleanup",
    "kind": "number",
    "hint": "作为下载进度观察窗口，窗口内进度增长低于阈值时视为超时",
    "advanced": true
  },
  {
    "key": "download_progress_threshold",
    "label": "下载超时进度阈值",
    "group": "cleanup",
    "kind": "number",
    "hint": "超时窗口内下载进度增长低于N%时才删除",
    "advanced": true
  },
  {
    "key": "download_retry_limit",
    "label": "下载连续超时重试次数",
    "group": "cleanup",
    "kind": "number",
    "hint": "连续低进度超时N次后保留种子并通知",
    "advanced": true
  },
  {
    "key": "delete_exclude_tags",
    "label": "排除标签",
    "group": "cleanup",
    "kind": "text",
    "hint": "需要排除的标签，多个标签用逗号分隔"
  },
  {
    "key": "default_tracker_response",
    "label": "Tracker响应关键字",
    "group": "cleanup",
    "kind": "textarea",
    "hint": "每一行一个关键字，忽略大小写，支持正则表达式匹配",
    "dialogOnly": true,
    "advanced": true
  },
  {
    "key": "delete_record_retention_hours",
    "label": "删除记录保留（小时）",
    "group": "cleanup",
    "kind": "number",
    "hint": "定时清理N小时前的删除记录",
    "advanced": true
  },
  {
    "key": "subscription_cleanup_history_type",
    "label": "清理整理记录范围",
    "group": "cleanup",
    "kind": "select",
    "hint": "订阅下载前清理旧整理记录、源文件和入库前目标文件的媒体类型范围（破坏性）",
    "options": [
      {
        "title": "关闭",
        "value": "no"
      },
      {
        "title": "全部",
        "value": "all"
      },
      {
        "title": "电影",
        "value": "movie"
      },
      {
        "title": "剧集",
        "value": "tv"
      }
    ],
    "risk": "danger"
  },
  {
    "key": "subscription_cleanup_history_scenes",
    "label": "清理整理记录场景",
    "group": "cleanup",
    "kind": "multi-select",
    "hint": "选择普通订阅、洗版订阅或分集洗版下载时触发订阅清理",
    "options": [
      {
        "title": "普通订阅",
        "value": "normal"
      },
      {
        "title": "洗版订阅",
        "value": "best_version"
      },
      {
        "title": "分集洗版",
        "value": "best_version_episode"
      }
    ],
    "risk": "danger"
  },
  {
    "key": "recognition_guard_mode",
    "label": "识别增强模式",
    "group": "recognition",
    "kind": "select",
    "hint": "在自动下载前复核订阅候选是否像当前订阅目标",
    "options": [
      {
        "title": "关闭",
        "value": "off"
      },
      {
        "title": "审计",
        "value": "audit"
      },
      {
        "title": "宽松",
        "value": "loose"
      },
      {
        "title": "平衡",
        "value": "balanced"
      },
      {
        "title": "严格",
        "value": "strict"
      }
    ],
    "risk": "danger"
  },
  {
    "key": "recognition_guard_notify",
    "label": "识别增强通知",
    "group": "recognition",
    "kind": "select",
    "hint": "控制识别增强消息推送，不影响审计日志",
    "options": [
      {
        "title": "关闭",
        "value": "off"
      },
      {
        "title": "摘要",
        "value": "summary"
      },
      {
        "title": "明细",
        "value": "detail"
      },
      {
        "title": "全部",
        "value": "all"
      }
    ]
  },
  {
    "key": "recognition_guard_notify_interval",
    "label": "识别增强通知限频（秒）",
    "group": "recognition",
    "kind": "number",
    "hint": "同订阅同动作同原因的通知限频秒数",
    "advanced": true
  },
  {
    "key": "recognition_guard_tmdb_recheck_mode",
    "label": "识别增强二次识别",
    "group": "recognition",
    "kind": "select",
    "hint": "控制二次识别触发范围",
    "options": [
      {
        "title": "关闭",
        "value": "off"
      },
      {
        "title": "全部",
        "value": "all"
      },
      {
        "title": "严格",
        "value": "strict"
      },
      {
        "title": "平衡和严格",
        "value": "balanced_strict"
      }
    ]
  },
  {
    "key": "recognition_guard_cache_maxsize",
    "label": "识别增强缓存大小",
    "group": "recognition",
    "kind": "number",
    "hint": "缓存二次识别结果，避免重复识别",
    "advanced": true
  },
  {
    "key": "recognition_guard_custom_config",
    "label": "自定义识别规则",
    "group": "recognition",
    "kind": "textarea",
    "hint": "仅在内置规则无法满足时编辑，留空则继承当前模式",
    "risk": "danger"
  },
  {
    "key": "pending_enhanced_enabled",
    "label": "自动待定剧集订阅",
    "group": "pending",
    "kind": "switch",
    "hint": "自动标记订阅剧集为待定状态，避免提前完成订阅"
  },
  {
    "key": "pending_download_enabled",
    "label": "自动待定下载中订阅",
    "group": "pending",
    "kind": "switch",
    "hint": "存在进行中下载时自动标记待定，避免提前完成订阅"
  },
  {
    "key": "auto_tv_pending_days",
    "label": "剧集待定天数",
    "group": "pending",
    "kind": "number",
    "hint": "当前日期小于上映日期加N天，则视为待定，为0时不处理",
    "advanced": true
  },
  {
    "key": "auto_tv_pending_episodes",
    "label": "剧集待定集数",
    "group": "pending",
    "kind": "number",
    "hint": "剧集数小于等于设置的集数，则视为待定，为0时不处理"
  },
  {
    "key": "pending_use_volatility",
    "label": "待定参考变更速率",
    "group": "pending",
    "kind": "switch",
    "hint": "接近完结且总集数变化时提前待定"
  },
  {
    "key": "pause_enhanced_enabled",
    "label": "自动暂停订阅",
    "group": "pause",
    "kind": "switch",
    "hint": "自动标记订阅为暂停状态，避免无意义的请求"
  },
  {
    "key": "auto_pause_users",
    "label": "自动暂停新增订阅的用户（逗号分隔）",
    "group": "pause",
    "kind": "text",
    "hint": "名单内用户新增订阅时将自动暂停，多个用户用逗号分隔，为空时不启用"
  },
  {
    "key": "airing_pause_days",
    "label": "即将播出暂停天数",
    "group": "pause",
    "kind": "number",
    "hint": "已存在最新播出集，且下集距当前日期大于N天，则视为暂停，为0时不处理",
    "advanced": true
  },
  {
    "key": "movie_air_pause_days",
    "label": "电影上映暂停天数",
    "group": "pause",
    "kind": "number",
    "hint": "当前日期小于上映日期减N天，则视为暂停，为0时不处理",
    "advanced": true
  },
  {
    "key": "tv_air_pause_days",
    "label": "剧集上映暂停天数",
    "group": "pause",
    "kind": "number",
    "hint": "当前日期小于开播日期减N天，则视为暂停，为0时不处理",
    "advanced": true
  },
  {
    "key": "movie_no_download_days",
    "label": "电影无下载处理天数",
    "group": "pause",
    "kind": "number",
    "hint": "电影上映后N天内无新的订阅下载，则按策略处理，为0时不处理",
    "advanced": true
  },
  {
    "key": "tv_no_download_days",
    "label": "剧集无下载处理天数",
    "group": "pause",
    "kind": "number",
    "hint": "剧集上映后N天内无新的订阅下载，则按策略处理，为0时不处理",
    "advanced": true
  },
  {
    "key": "no_download_actions",
    "label": "无下载处理策略",
    "group": "pause",
    "kind": "multi-select",
    "hint": "选择无下载时的处理策略",
    "options": [
      {
        "title": "暂停电影订阅",
        "value": "pause_movie"
      },
      {
        "title": "暂停剧集订阅",
        "value": "pause_tv"
      },
      {
        "title": "完成电影订阅",
        "value": "complete_movie"
      },
      {
        "title": "完成剧集订阅",
        "value": "complete_tv"
      },
      {
        "title": "删除电影订阅",
        "value": "delete_movie"
      },
      {
        "title": "删除剧集订阅",
        "value": "delete_tv"
      }
    ],
    "risk": "danger"
  },
  {
    "key": "site_total_probe_enabled",
    "label": "站点集数探测",
    "group": "completion",
    "kind": "switch",
    "hint": "用站点缓存资源辅助发现目标集数不足"
  },
  {
    "key": "paused_probe_reasons",
    "label": "暂停订阅补搜场景",
    "group": "completion",
    "kind": "multi-select",
    "hint": "选择允许低频补搜的暂停原因",
    "options": [
      {
        "title": "无下载",
        "value": "no_download"
      },
      {
        "title": "上映/开播",
        "value": "pre_air"
      },
      {
        "title": "播出间隔",
        "value": "airing_gap"
      },
      {
        "title": "用户名",
        "value": "auto_user"
      },
      {
        "title": "外部暂停",
        "value": "external"
      },
      {
        "title": "全部",
        "value": "all"
      }
    ]
  },
  {
    "key": "paused_probe_min_pause_days",
    "label": "暂停满N天后补搜",
    "group": "completion",
    "kind": "number",
    "hint": "暂停达到天数后开始补搜，0 表示不处理",
    "advanced": true
  },
  {
    "key": "paused_probe_interval_hours",
    "label": "补搜间隔（小时）",
    "group": "completion",
    "kind": "select",
    "hint": "同一订阅两次补搜的最小间隔",
    "options": [
      {
        "title": "24",
        "value": 24
      },
      {
        "title": "48",
        "value": 48
      },
      {
        "title": "72",
        "value": 72
      },
      {
        "title": "96",
        "value": 96
      },
      {
        "title": "120",
        "value": 120
      },
      {
        "title": "144",
        "value": 144
      }
    ],
    "advanced": true
  },
  {
    "key": "best_version_type",
    "label": "洗版类型",
    "group": "bestVersion",
    "kind": "select",
    "hint": "选择需要自动洗版的类型，关闭时不自动创建和巡检洗版订阅",
    "options": [
      {
        "title": "关闭",
        "value": "no"
      },
      {
        "title": "全部",
        "value": "all"
      },
      {
        "title": "电影",
        "value": "movie"
      },
      {
        "title": "剧集",
        "value": "tv"
      },
      {
        "title": "剧集（分集下载）",
        "value": "tv_episode"
      }
    ],
    "risk": "danger"
  },
  {
    "key": "best_version_movie_remaining_days",
    "label": "电影洗版时限（天）",
    "group": "bestVersion",
    "kind": "number",
    "hint": "电影洗版订阅达到指定天数后自动终止，有下载则按最新时间计算，为0时不限",
    "advanced": true
  },
  {
    "key": "best_version_tv_remaining_days",
    "label": "剧集洗版时限（天）",
    "group": "bestVersion",
    "kind": "number",
    "hint": "剧集洗版订阅达到指定天数后自动终止，有下载则按最新时间计算，为0时不限",
    "advanced": true
  },
  {
    "key": "best_version_episode_to_full",
    "label": "分集转全集",
    "group": "bestVersion",
    "kind": "switch",
    "hint": "订阅目标集数满足时，从分集洗版切换为全集洗版",
    "risk": "danger"
  },
  {
    "key": "best_version_backfill_enabled",
    "label": "回填已存在集",
    "group": "bestVersion",
    "kind": "switch",
    "hint": "新建或转分集洗版时回填媒体库已有集，避免重复下载"
  },
  {
    "key": "backfill_best_version_now",
    "label": "立即扫描存量并回填",
    "group": "bestVersion",
    "kind": "switch",
    "hint": "保存后对存量分集洗版订阅执行一次回填，执行后自动复位",
    "risk": "danger"
  },
  {
    "key": "completion_guard_mode",
    "label": "完结守卫模式",
    "group": "guard",
    "kind": "select",
    "hint": "选择完成前复核强度，默认使用平衡策略",
    "options": [
      {
        "title": "关闭",
        "value": "off"
      },
      {
        "title": "严格",
        "value": "strict"
      },
      {
        "title": "平衡",
        "value": "balanced"
      },
      {
        "title": "宽松",
        "value": "loose"
      }
    ]
  },
  {
    "key": "site_completion_evidence_enabled",
    "label": "站点完结信号",
    "group": "guard",
    "kind": "switch",
    "hint": "使用站点资源标题佐证完结信号"
  },
  {
    "key": "volatility_enabled",
    "label": "变更速率信号",
    "group": "guard",
    "kind": "switch",
    "hint": "总集数近期变化时视为不稳定"
  },
  {
    "key": "volatility_window_days",
    "label": "变更速率窗口（天）",
    "group": "guard",
    "kind": "number",
    "hint": "统计总集数变化的天数，越长越保守",
    "advanced": true
  },
  {
    "key": "cadence_enabled",
    "label": "播出节奏信号",
    "group": "guard",
    "kind": "switch",
    "hint": "按已播间隔判断等待期，不会直接判定完结"
  },
  {
    "key": "cadence_multiplier",
    "label": "节奏窗口系数",
    "group": "guard",
    "kind": "number",
    "hint": "放大预计等待时间，数值越大等待越久"
  },
  {
    "key": "cadence_min_window_days",
    "label": "节奏窗口下限（天）",
    "group": "guard",
    "kind": "number",
    "hint": "预计等待时间不得少于设置天数",
    "advanced": true
  },
  {
    "key": "cadence_min_episodes",
    "label": "节奏参与最少集数",
    "group": "guard",
    "kind": "number",
    "hint": "已播集数达到设置值后才计算播出间隔"
  },
  {
    "key": "season_cooldown_days",
    "label": "季冷却期（天）",
    "group": "guard",
    "kind": "number",
    "hint": "最后一集播出后继续观察的天数",
    "advanced": true
  },
  {
    "key": "verify_enabled",
    "label": "自动纠错",
    "group": "guard",
    "kind": "switch",
    "hint": "完成后检查集数，增加时自动重建订阅"
  },
  {
    "key": "verify_interval_hours",
    "label": "自动纠错间隔（小时）",
    "group": "guard",
    "kind": "number",
    "hint": "完成后重新检查集数的间隔",
    "advanced": true
  },
  {
    "key": "verify_retention_days",
    "label": "快照保留（天）",
    "group": "guard",
    "kind": "number",
    "hint": "完成快照按设置天数保留并自动清理，默认180天",
    "advanced": true
  },
  {
    "key": "timeout_release_days",
    "label": "完成前观察天数",
    "group": "guard",
    "kind": "number",
    "hint": "完成前观察允许保留的最长天数",
    "advanced": true
  },
  {
    "key": "timeout_cadence_acceleration",
    "label": "按节奏加速释放",
    "group": "guard",
    "kind": "switch",
    "hint": "等待期结束时缩短观察期限"
  }
]
