import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const saeLogo = "data:image/svg+xml,%3csvg%20width='96'%20height='96'%20viewBox='0%200%2096%2096'%20fill='none'%20xmlns='http://www.w3.org/2000/svg'%20role='img'%20aria-label='SubscribeAssistantEnhanced'%3e%3crect%20x='6'%20y='6'%20width='84'%20height='84'%20rx='24'%20fill='url(%23g)'/%3e%3cpath%20d='M24%2066V34c0-4.5%205.5-6.7%208.7-3.5L48%2045.8l15.3-15.3C66.5%2027.3%2072%2029.5%2072%2034v32'%20stroke='white'%20stroke-width='9'%20stroke-linecap='round'%20stroke-linejoin='round'/%3e%3cpath%20d='M38%2053l10%2010%2010-10'%20stroke='white'%20stroke-width='9'%20stroke-linecap='round'%20stroke-linejoin='round'/%3e%3cdefs%3e%3clinearGradient%20id='g'%20x1='18'%20y1='12'%20x2='84'%20y2='88'%20gradientUnits='userSpaceOnUse'%3e%3cstop%20stop-color='%232F64FF'/%3e%3cstop%20offset='1'%20stop-color='%232147E8'/%3e%3c/linearGradient%3e%3c/defs%3e%3c/svg%3e";

async function loadSummary(api) {
  if (!api) return null;
  try {
    return await api.get("plugin/SubscribeAssistantEnhanced/summary");
  } catch {
    console.warn("[SubscribeAssistantEnhanced] summary unavailable");
    return null;
  }
}

const configDefaults = {
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
  "open_tracker_dialog": false,
  "delete_record_retention_hours": 24,
  "subscription_cleanup_history_type": "no",
  "subscription_cleanup_history_scenes": [],
  "recognition_guard_mode": "off",
  "recognition_guard_notify": "off",
  "recognition_guard_notify_interval": 3600,
  "recognition_guard_tmdb_recheck_mode": "balanced_strict",
  "recognition_guard_cache_maxsize": 1e5,
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
  "progress_diagnostic_mode": "off",
  "progress_diagnostic_stalled_rounds": 3,
  "progress_diagnostic_cooldown_hours": 24,
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
};

function normalizeFiniteNumber(current, incoming) {
  if (incoming === null || incoming === void 0) return current;
  if (typeof incoming === "string" && !incoming.trim()) return current;
  const parsed = typeof incoming === "number" ? incoming : Number(incoming);
  return Number.isFinite(parsed) ? parsed : current;
}
function normalizeBoolean(defaultValue, incoming) {
  if (incoming === null || incoming === void 0) return defaultValue;
  if (typeof incoming === "boolean") return incoming;
  if (typeof incoming === "string") {
    return ["true", "on", "yes", "1", "guard"].includes(incoming.trim().toLowerCase());
  }
  if (typeof incoming === "number") return incoming !== 0;
  if (Array.isArray(incoming)) return incoming.length > 0;
  if (typeof incoming === "object") return Object.keys(incoming).length > 0;
  return Boolean(incoming);
}
function normalizeNumber(defaultValue, incoming) {
  if (incoming === null || incoming === void 0) return defaultValue;
  if (typeof incoming === "string" && !incoming.trim()) return defaultValue;
  if (typeof incoming !== "number" && typeof incoming !== "string") return defaultValue;
  const parsed = Number(incoming);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}
function normalizeString(defaultValue, incoming) {
  return incoming === null || incoming === void 0 ? defaultValue : String(incoming);
}
function normalizeStringArray(defaultValue, incoming) {
  if (Array.isArray(incoming)) {
    return incoming.map((value) => String(value).trim()).filter(Boolean);
  }
  if (typeof incoming === "string") {
    return incoming.split(",").map((value) => value.trim()).filter(Boolean);
  }
  return [...defaultValue];
}
function normalizeSaeConfig(input) {
  const source = input !== null && typeof input === "object" && !Array.isArray(input) ? input : {};
  const entries = Object.keys(configDefaults).map((key) => {
    const defaultValue = configDefaults[key];
    const incoming = source[key];
    if (key === "open_tracker_dialog") return [key, false];
    if (Array.isArray(defaultValue)) {
      return [key, normalizeStringArray(defaultValue, incoming)];
    }
    if (typeof defaultValue === "boolean") {
      return [key, normalizeBoolean(defaultValue, incoming)];
    }
    if (typeof defaultValue === "number") {
      return [key, normalizeNumber(defaultValue, incoming)];
    }
    return [key, normalizeString(defaultValue, incoming)];
  });
  return Object.fromEntries(entries);
}

const {computed: computed$1,reactive} = await importShared('vue');
function useConfigDraft(initialConfig) {
  const initialSnapshot = normalizeSaeConfig(initialConfig);
  const draft = reactive(structuredClone(initialSnapshot));
  const configKeys = Object.keys(initialSnapshot);
  const changedCount = computed$1(
    () => configKeys.reduce((count, key) => {
      return JSON.stringify(draft[key]) === JSON.stringify(initialSnapshot[key]) ? count : count + 1;
    }, 0)
  );
  function buildSavePayload() {
    return normalizeSaeConfig(draft);
  }
  return { draft, changedCount, buildSavePayload };
}

const groups = [
  { key: "global", title: "全局运行", icon: "mdi-tune-variant", summary: "插件开关、通知、一次性动作与公共周期" },
  { key: "cleanup", title: "订阅清理", icon: "mdi-delete-sweep-outline", summary: "下载监控、删种、Tracker 与整理记录清理", highRisk: true },
  { key: "pending", title: "订阅待定", icon: "mdi-timer-sand", summary: "下载中与剧集目标未稳定时保持待定" },
  { key: "pause", title: "订阅暂停", icon: "mdi-pause-circle-outline", summary: "按用户、上映播出窗口和无下载策略暂停订阅" },
  { key: "completion", title: "订阅补全", icon: "mdi-radar", summary: "站点集数探测、暂停补搜与无进展诊断" },
  { key: "bestVersion", title: "订阅洗版", icon: "mdi-auto-fix", summary: "洗版范围、时限、回填和分集转全集", highRisk: true },
  { key: "guard", title: "完结信号", icon: "mdi-shield-check-outline", summary: "完结守卫、站点证据、波动节奏和自动纠错" },
  { key: "recognition", title: "识别增强", icon: "mdi-account-search-outline", summary: "候选准入、通知、二次识别和自定义策略" }
];
const fields = [
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
    "key": "open_tracker_dialog",
    "label": "打开Tracker配置窗口",
    "group": "cleanup",
    "kind": "switch",
    "hint": "自定义Tracker配置以实现更精准的种子匹配",
    "legacyUiKey": true,
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
    "label": "识别增强自定义策略",
    "group": "recognition",
    "kind": "textarea",
    "hint": "YAML 策略覆盖；清空表示无自定义覆盖",
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
    "key": "progress_diagnostic_mode",
    "label": "无进展诊断模式",
    "group": "completion",
    "kind": "select",
    "hint": "订阅长期无进展时的诊断处理方式",
    "options": [
      {
        "title": "关闭",
        "value": "off"
      },
      {
        "title": "仅通知",
        "value": "notify"
      }
    ]
  },
  {
    "key": "progress_diagnostic_stalled_rounds",
    "label": "连续无进展轮数",
    "group": "completion",
    "kind": "number",
    "hint": "连续无进展多少轮后处理，0 表示不处理",
    "advanced": true
  },
  {
    "key": "progress_diagnostic_cooldown_hours",
    "label": "诊断冷却（小时）",
    "group": "completion",
    "kind": "number",
    "hint": "同一订阅诊断提醒的最小间隔",
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
];

const supportedLocales = /* @__PURE__ */ new Set(["zh-CN", "zh-TW", "en-US"]);
function normalizeLocale(source) {
  let current = source;
  const visited = /* @__PURE__ */ new Set();
  while (current && typeof current === "object" && "value" in current) {
    if (visited.has(current)) return "zh-CN";
    visited.add(current);
    current = current.value;
  }
  if (typeof current !== "string") return "zh-CN";
  const normalized = current.trim().replace("_", "-").toLowerCase();
  const locale = normalized === "zh-cn" ? "zh-CN" : normalized === "zh-tw" ? "zh-TW" : normalized === "en-us" ? "en-US" : "zh-CN";
  return supportedLocales.has(locale) ? locale : "zh-CN";
}
const messages = {
  "zh-CN": {
    "config.changedCount": "已修改 {count} 项",
    "config.save": "保存修改",
    "config.close": "关闭",
    "config.preview": "配置预览",
    "config.help": "插件帮助",
    "config.plugin": "插件",
    "config.settings": "插件设置",
    "config.selectGroup": "选择配置分组",
    "config.unsaved": "未保存",
    "config.done": "完成",
    "config.edit": "编辑",
    "config.decrease": "减小{label}",
    "config.increase": "增大{label}",
    "config.editLabel": "编辑{label}",
    "config.editYaml": "编辑 YAML 策略",
    "config.yamlTitle": "识别增强自定义策略",
    "config.runtime": "运行概况",
    "config.runtimeLoading": "正在读取运行概况",
    "config.runtimeUnavailable": "运行概况暂不可用",
    "config.pendingCount": "待定订阅",
    "config.monitoredCount": "监控下载任务",
    "config.enabled": "启用",
    "config.off": "关闭",
    "config.cronPlaceholder": "5 位 CRON 表达式",
    "config.title": "订阅助手（增强版）",
    "domain.completionGuard": "完结守卫模式",
    "domain.pending": "待定增强",
    "domain.pause": "暂停优化",
    "domain.bestVersion": "自动洗版",
    "domain.download": "下载管理",
    "domain.verify": "完成后验证",
    "domain.siteTotal": "站点集数探测",
    "domain.siteCompletion": "站点完结信号",
    "domain.recognition": "识别增强",
    "section.running": "运行状态",
    "section.oneTime": "一次性动作",
    "section.schedule": "公共周期",
    "section.download": "下载任务处理",
    "section.timeout": "超时与重试",
    "section.cleanup": "订阅记录清理",
    "section.pending": "待定策略",
    "section.tvDecision": "剧集判定",
    "section.autoPause": "自动暂停",
    "section.airing": "上映与播出窗口",
    "section.noDownload": "无下载处理",
    "section.siteProbe": "站点集数探测",
    "section.diagnostic": "无进展诊断",
    "section.pausedProbe": "暂停订阅补搜",
    "section.bestVersionScope": "洗版范围",
    "section.backfill": "转换与回填",
    "section.guard": "守卫信号",
    "section.cadence": "播出节奏",
    "section.correction": "纠错与释放",
    "section.recognition": "识别策略",
    "section.custom": "自定义规则",
    "preview.disabled.title": "插件未启用",
    "preview.disabled.detail": "保存后不会注册订阅助手定时任务",
    "preview.reset.title": "重置数据",
    "preview.reset.detail": "保存后会清空插件任务数据并自动复位",
    "preview.backfillNow.title": "立即扫描存量并回填",
    "preview.backfillNow.detail": "保存后会扫描存量分集洗版订阅并回填媒体库已有集",
    "preview.general.title": "通用巡检可能运行",
    "preview.general.detail": "周期 {value} 分钟",
    "preview.metadata.title": "元数据检查可能运行",
    "preview.metadata.detail": "周期 {value} 小时",
    "preview.runOnce.title": "立即运行一次",
    "preview.runOnce.detail": "保存后约 3 秒触发一次全量巡检",
    "preview.downloadCheck.title": "下载任务检查可能运行",
    "preview.downloadCheck.detail": "周期 {value} 分钟",
    "preview.bestVersion.title": "可能自动创建洗版订阅",
    "preview.bestVersion.detail": "普通订阅完成后，符合当前洗版范围的媒体可能自动创建洗版订阅",
    "preview.bestVersionCheck.title": "洗版订阅检查可能运行",
    "preview.bestVersionCheck.detail": "CRON {value}",
    "preview.verify.title": "自动纠错可能运行",
    "preview.verify.detail": "周期 {value} 小时",
    "preview.removeTorrent.title": "可能删除下载器任务",
    "preview.removeTorrent.detail": "下载停滞、Tracker 关键字或手动删种场景可能触发删种处理",
    "preview.cleanup.title": "可能清理整理记录或文件",
    "preview.cleanup.detail": "订阅清理范围已启用，请确认清理场景",
    "preview.pause.title": "可能暂停订阅",
    "preview.pause.detail": "无下载策略命中后，电影或剧集订阅可能被暂停",
    "preview.complete.title": "可能完成订阅",
    "preview.complete.detail": "无下载策略命中后，电影或剧集订阅可能被标记完成并移除",
    "preview.delete.title": "可能删除订阅",
    "preview.delete.detail": "无下载策略命中后，电影或剧集订阅可能被直接删除",
    "preview.episodeToFull.title": "可能从分集洗版转为全集洗版",
    "preview.episodeToFull.detail": "订阅目标集满足后，分集洗版可能切换为全集洗版",
    "preview.audit.title": "识别增强可能记录候选风险",
    "preview.audit.detail": "审计模式可能记录判定与通知，但不会过滤或移除候选",
    "preview.filter.title": "识别增强可能过滤候选",
    "preview.filter.detail": "当前模式和生效的自定义策略覆盖可能过滤或移除候选"
  },
  "zh-TW": {
    "config.changedCount": "已修改 {count} 項",
    "config.save": "儲存修改",
    "config.close": "關閉",
    "config.preview": "設定預覽",
    "config.help": "外掛說明",
    "config.plugin": "外掛",
    "config.settings": "外掛設定",
    "config.selectGroup": "選擇設定分組",
    "config.unsaved": "尚未儲存",
    "config.done": "完成",
    "config.edit": "編輯",
    "config.decrease": "減少{label}",
    "config.increase": "增加{label}",
    "config.editLabel": "編輯{label}",
    "config.editYaml": "編輯 YAML 策略",
    "config.yamlTitle": "識別增強自訂策略",
    "config.runtime": "執行概況",
    "config.runtimeLoading": "正在讀取執行概況",
    "config.runtimeUnavailable": "執行概況暫不可用",
    "config.pendingCount": "待定訂閱",
    "config.monitoredCount": "監控下載任務",
    "config.enabled": "啟用",
    "config.off": "關閉",
    "config.cronPlaceholder": "5 位 CRON 表示式",
    "config.title": "訂閱助手（增強版）",
    "domain.completionGuard": "完結守衛模式",
    "domain.pending": "待定增強",
    "domain.pause": "暫停最佳化",
    "domain.bestVersion": "自動洗版",
    "domain.download": "下載管理",
    "domain.verify": "完成後驗證",
    "domain.siteTotal": "站點集數探測",
    "domain.siteCompletion": "站點完結訊號",
    "domain.recognition": "識別增強",
    "section.running": "執行狀態",
    "section.oneTime": "單次操作",
    "section.schedule": "共用週期",
    "section.download": "下載任務處理",
    "section.timeout": "逾時與重試",
    "section.cleanup": "訂閱記錄清理",
    "section.pending": "待定策略",
    "section.tvDecision": "影集判定",
    "section.autoPause": "自動暫停",
    "section.airing": "上映與播出窗口",
    "section.noDownload": "無下載處理",
    "section.siteProbe": "站點集數探測",
    "section.diagnostic": "無進度診斷",
    "section.pausedProbe": "暫停訂閱補搜",
    "section.bestVersionScope": "洗版範圍",
    "section.backfill": "轉換與回填",
    "section.guard": "守衛訊號",
    "section.cadence": "播出節奏",
    "section.correction": "修正與釋放",
    "section.recognition": "識別策略",
    "section.custom": "自訂規則",
    "preview.disabled.title": "外掛未啟用",
    "preview.disabled.detail": "儲存後不會註冊訂閱助手排程任務",
    "preview.reset.title": "重設資料",
    "preview.reset.detail": "儲存後會清除外掛任務資料並自動複位",
    "preview.backfillNow.title": "立即掃描既有並回填",
    "preview.backfillNow.detail": "儲存後會掃描既有分集洗版訂閱並回填媒體庫已有集",
    "preview.general.title": "通用巡檢可能執行",
    "preview.general.detail": "週期 {value} 分鐘",
    "preview.metadata.title": "元資料檢查可能執行",
    "preview.metadata.detail": "週期 {value} 小時",
    "preview.runOnce.title": "立即執行一次",
    "preview.runOnce.detail": "儲存後約 3 秒觸發一次全量巡檢",
    "preview.downloadCheck.title": "下載任務檢查可能執行",
    "preview.downloadCheck.detail": "週期 {value} 分鐘",
    "preview.bestVersion.title": "可能自動建立洗版訂閱",
    "preview.bestVersion.detail": "普通訂閱完成後，符合目前洗版範圍的媒體可能自動建立洗版訂閱",
    "preview.bestVersionCheck.title": "洗版訂閱檢查可能執行",
    "preview.bestVersionCheck.detail": "CRON {value}",
    "preview.verify.title": "自動修正可能執行",
    "preview.verify.detail": "週期 {value} 小時",
    "preview.removeTorrent.title": "可能刪除下載器任務",
    "preview.removeTorrent.detail": "下載停滯、Tracker 關鍵字或手動刪除種子可能觸發處理",
    "preview.cleanup.title": "可能清理整理記錄或檔案",
    "preview.cleanup.detail": "訂閱清理範圍已啟用，請確認清理情境",
    "preview.pause.title": "可能暫停訂閱",
    "preview.pause.detail": "無下載策略命中後，電影或影集訂閱可能被暫停",
    "preview.complete.title": "可能完成訂閱",
    "preview.complete.detail": "無下載策略命中後，電影或影集訂閱可能被標記完成並移除",
    "preview.delete.title": "可能刪除訂閱",
    "preview.delete.detail": "無下載策略命中後，電影或影集訂閱可能被直接刪除",
    "preview.episodeToFull.title": "可能從分集洗版轉為全集洗版",
    "preview.episodeToFull.detail": "訂閱目標集符合後，分集洗版可能切換為全集洗版",
    "preview.audit.title": "識別增強可能記錄候選風險",
    "preview.audit.detail": "稽核模式可能記錄判定與通知，但不會過濾或移除候選",
    "preview.filter.title": "識別增強可能過濾候選",
    "preview.filter.detail": "目前模式和生效的自訂策略可能過濾或移除候選"
  },
  "en-US": {
    "config.changedCount": "{count} changes",
    "config.save": "Save changes",
    "config.close": "Close",
    "config.preview": "Configuration preview",
    "config.help": "Plugin help",
    "config.plugin": "Plugins",
    "config.settings": "Plugin settings",
    "config.selectGroup": "Select settings group",
    "config.unsaved": "Unsaved",
    "config.done": "Done",
    "config.edit": "Edit",
    "config.decrease": "Decrease {label}",
    "config.increase": "Increase {label}",
    "config.editLabel": "Edit {label}",
    "config.editYaml": "Edit YAML policy",
    "config.yamlTitle": "Custom recognition policy",
    "config.runtime": "Runtime summary",
    "config.runtimeLoading": "Loading runtime summary",
    "config.runtimeUnavailable": "Runtime summary unavailable",
    "config.pendingCount": "Pending subscriptions",
    "config.monitoredCount": "Monitored downloads",
    "config.enabled": "Enabled",
    "config.off": "Off",
    "config.cronPlaceholder": "5-field CRON expression",
    "config.title": "Subscribe Assistant (Enhanced)",
    "domain.completionGuard": "Completion guard mode",
    "domain.pending": "Pending enhancement",
    "domain.pause": "Pause optimization",
    "domain.bestVersion": "Automatic upgrades",
    "domain.download": "Download management",
    "domain.verify": "Post-completion verification",
    "domain.siteTotal": "Site episode probe",
    "domain.siteCompletion": "Site completion signal",
    "domain.recognition": "Recognition",
    "section.running": "Runtime state",
    "section.oneTime": "One-time actions",
    "section.schedule": "Shared schedules",
    "section.download": "Download handling",
    "section.timeout": "Timeouts and retries",
    "section.cleanup": "Subscription cleanup",
    "section.pending": "Pending policy",
    "section.tvDecision": "TV decisions",
    "section.autoPause": "Automatic pause",
    "section.airing": "Release and airing windows",
    "section.noDownload": "No-download handling",
    "section.siteProbe": "Site episode probe",
    "section.diagnostic": "Stalled-progress diagnostics",
    "section.pausedProbe": "Paused subscription search",
    "section.bestVersionScope": "Best-version scope",
    "section.backfill": "Conversion and backfill",
    "section.guard": "Guard signals",
    "section.cadence": "Airing cadence",
    "section.correction": "Correction and release",
    "section.recognition": "Recognition policy",
    "section.custom": "Custom rules",
    "preview.disabled.title": "Plugin disabled",
    "preview.disabled.detail": "Saving will not register scheduled assistant tasks",
    "preview.reset.title": "Reset data",
    "preview.reset.detail": "Saving clears plugin task data and resets this action",
    "preview.backfillNow.title": "Scan and backfill now",
    "preview.backfillNow.detail": "Saving scans existing episode upgrades and backfills library episodes",
    "preview.general.title": "General inspection may run",
    "preview.general.detail": "Every {value} minutes",
    "preview.metadata.title": "Metadata checks may run",
    "preview.metadata.detail": "Every {value} hours",
    "preview.runOnce.title": "Run once now",
    "preview.runOnce.detail": "Saving starts one full inspection after about 3 seconds",
    "preview.downloadCheck.title": "Download checks may run",
    "preview.downloadCheck.detail": "Every {value} minutes",
    "preview.bestVersion.title": "May create best-version subscriptions",
    "preview.bestVersion.detail": "Completed standard subscriptions may create upgrades within the selected scope",
    "preview.bestVersionCheck.title": "Best-version checks may run",
    "preview.bestVersionCheck.detail": "CRON {value}",
    "preview.verify.title": "Automatic correction may run",
    "preview.verify.detail": "Every {value} hours",
    "preview.removeTorrent.title": "May remove download tasks",
    "preview.removeTorrent.detail": "Stalled downloads, Tracker keywords, or manual removals may trigger torrent removal",
    "preview.cleanup.title": "May remove transfer records or files",
    "preview.cleanup.detail": "Subscription cleanup is enabled; verify the selected scenarios",
    "preview.pause.title": "May pause subscriptions",
    "preview.pause.detail": "No-download policies may pause movie or TV subscriptions",
    "preview.complete.title": "May complete subscriptions",
    "preview.complete.detail": "No-download policies may complete and remove movie or TV subscriptions",
    "preview.delete.title": "May delete subscriptions",
    "preview.delete.detail": "No-download policies may directly delete movie or TV subscriptions",
    "preview.episodeToFull.title": "May convert episode upgrades to full season",
    "preview.episodeToFull.detail": "Episode upgrades may switch to a full season after reaching the target",
    "preview.audit.title": "Recognition may record candidate risks",
    "preview.audit.detail": "Audit mode records decisions and notifications without filtering candidates",
    "preview.filter.title": "Recognition may filter candidates",
    "preview.filter.detail": "The selected mode and active custom policy may filter or remove candidates"
  }
};
function t(localeSource, key, params = {}) {
  const locale = normalizeLocale(localeSource);
  const template = messages[locale][key] ?? messages["zh-CN"][key];
  if (!template) throw new Error(`Missing translation key: ${key}`);
  return template.replace(/\{(\w+)\}/g, (match, name) => Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match);
}
const groupTranslations = {
  global: { tw: ["全域執行", "外掛開關、通知、單次操作與共用週期"], en: ["General", "Plugin state, notifications, one-time actions, and shared schedules"] },
  cleanup: { tw: ["訂閱清理", "下載監控、刪除種子、Tracker 與整理記錄清理"], en: ["Cleanup", "Download monitoring, torrent removal, Tracker rules, and history cleanup"] },
  pending: { tw: ["訂閱待定", "下載中或集數目標尚未穩定時保持待定"], en: ["Pending", "Keep subscriptions pending while downloads or episode targets are unsettled"] },
  pause: { tw: ["訂閱暫停", "依使用者、播出窗口與無下載策略暫停訂閱"], en: ["Pause", "Pause subscriptions by user, release window, or no-download policy"] },
  completion: { tw: ["訂閱補全", "站點集數探測、暫停補搜與無進度診斷"], en: ["Completion", "Site episode probes, paused searches, and stalled-progress diagnostics"] },
  bestVersion: { tw: ["訂閱洗版", "洗版範圍、時限、回填與分集轉全集"], en: ["Best version", "Upgrade scope, time limits, backfill, and episode-to-season conversion"] },
  guard: { tw: ["完結訊號", "完結守衛、站點證據、波動節奏與自動修正"], en: ["Completion guard", "Completion checks, site evidence, cadence, and automatic correction"] },
  recognition: { tw: ["識別增強", "候選准入、通知、二次識別與自訂策略"], en: ["Recognition", "Candidate checks, notifications, re-identification, and custom policies"] }
};
const englishFields = {
  enabled: ["Enable plugin", "Activate the plugin and register its scheduled tasks"],
  notify: ["Send notifications", "Send notifications when relevant events occur"],
  onlyonce: ["Run once now", "Run a full inspection after saving, then reset automatically"],
  reset_task: ["Reset data", "Reset all pending, paused, and monitored task data, then reset automatically"],
  auto_check_interval_minutes: ["General check interval (minutes)", "Interval for site sampling, pending release, no-download handling, and cleanup"],
  download_check_interval_minutes: ["Download check interval (minutes)", "How often download task status is checked"],
  meta_check_interval_hours: ["Metadata check interval (hours)", "How often subscription metadata is reviewed"],
  best_version_cron: ["Best-version schedule", "CRON schedule for best-version checks, for example 0 15 * * *"],
  download_monitor_enabled: ["Remove stalled downloads", "Automatically remove subscription torrents that time out"],
  manual_delete_listen: ["Watch manual torrent removal", "Record torrents manually removed by the user"],
  tracker_response_listen: ["Watch Tracker response keywords", "Remove torrents when a configured Tracker response keyword matches"],
  auto_search_when_delete: ["Search after removal", "Trigger a completion search after removing a torrent"],
  skip_deletion: ["Skip recently removed releases", "Avoid downloading recently removed torrents again"],
  download_timeout_minutes: ["Download timeout (minutes)", "Observation window used to detect downloads with insufficient progress"],
  download_progress_threshold: ["Download progress threshold", "Remove only when progress increases by less than N% during the timeout window"],
  download_retry_limit: ["Consecutive timeout limit", "Keep the torrent and notify after N consecutive low-progress timeouts"],
  delete_exclude_tags: ["Excluded tags", "Comma-separated tags that must not be processed"],
  default_tracker_response: ["Tracker response keywords", "One keyword per line; case-insensitive regular expressions are supported"],
  open_tracker_dialog: ["Open Tracker settings", "Customize Tracker rules for more accurate torrent matching"],
  delete_record_retention_hours: ["Removal history retention (hours)", "Periodically remove deletion records older than N hours"],
  subscription_cleanup_history_type: ["Cleanup media scope", "Media types whose old transfer records and files are removed before download"],
  subscription_cleanup_history_scenes: ["Cleanup trigger scenarios", "Choose which subscription download scenarios trigger cleanup"],
  recognition_guard_mode: ["Recognition mode", "Review whether a candidate matches the subscription target before automatic download"],
  recognition_guard_notify: ["Recognition notifications", "Control recognition messages without affecting audit logs"],
  recognition_guard_notify_interval: ["Notification rate limit (seconds)", "Minimum interval for the same subscription, action, and reason"],
  recognition_guard_tmdb_recheck_mode: ["Secondary recognition", "Control when secondary recognition is performed"],
  recognition_guard_cache_maxsize: ["Recognition cache size", "Cache secondary recognition results to avoid duplicate requests"],
  recognition_guard_custom_config: ["Custom recognition policy", "YAML policy overrides; clear the value to use no custom overrides"],
  pending_enhanced_enabled: ["Automatically pend TV subscriptions", "Mark TV subscriptions pending to avoid completing them too early"],
  pending_download_enabled: ["Pend active downloads", "Keep subscriptions pending while downloads are in progress"],
  auto_tv_pending_days: ["TV pending days", "Keep pending before the release date plus N days; 0 disables this rule"],
  auto_tv_pending_episodes: ["TV pending episode count", "Keep pending when the episode count is at or below this value; 0 disables this rule"],
  pending_use_volatility: ["Use change rate for pending", "Pend early when the total episode count changes near completion"],
  pause_enhanced_enabled: ["Automatically pause subscriptions", "Pause subscriptions to avoid unnecessary requests"],
  auto_pause_users: ["Auto-pause users (comma-separated)", "Pause new subscriptions from listed users; leave empty to disable"],
  airing_pause_days: ["Upcoming episode pause days", "Pause when the next episode is more than N days away; 0 disables this rule"],
  movie_air_pause_days: ["Movie release pause days", "Pause until N days before the movie release date; 0 disables this rule"],
  tv_air_pause_days: ["TV premiere pause days", "Pause until N days before the TV premiere date; 0 disables this rule"],
  movie_no_download_days: ["Movie no-download days", "Apply the selected policy when no movie download occurs within N days; 0 disables it"],
  tv_no_download_days: ["TV no-download days", "Apply the selected policy when no TV download occurs within N days; 0 disables it"],
  no_download_actions: ["No-download actions", "Choose the actions to apply when no download is found"],
  site_total_probe_enabled: ["Probe site episode totals", "Use cached site releases to detect an incomplete episode target"],
  paused_probe_reasons: ["Paused search scenarios", "Choose pause reasons that allow low-frequency searches"],
  paused_probe_min_pause_days: ["Search after N paused days", "Start searching after this many paused days; 0 disables it"],
  paused_probe_interval_hours: ["Search interval (hours)", "Minimum interval between two searches for the same subscription"],
  progress_diagnostic_mode: ["Stalled-progress diagnostics", "Choose how to handle subscriptions with no progress"],
  progress_diagnostic_stalled_rounds: ["Consecutive stalled rounds", "Handle after this many rounds without progress; 0 disables it"],
  progress_diagnostic_cooldown_hours: ["Diagnostic cooldown (hours)", "Minimum interval between diagnostic notifications for one subscription"],
  best_version_type: ["Best-version type", "Select media types for automatic upgrades; Off disables creation and checks"],
  best_version_movie_remaining_days: ["Movie upgrade time limit (days)", "Stop movie upgrade subscriptions after this period; 0 means unlimited"],
  best_version_tv_remaining_days: ["TV upgrade time limit (days)", "Stop TV upgrade subscriptions after this period; 0 means unlimited"],
  best_version_episode_to_full: ["Convert episodes to full season", "Switch from episode upgrades to a full-season upgrade when the target is met"],
  best_version_backfill_enabled: ["Backfill existing episodes", "Backfill library episodes when creating or converting an episode upgrade"],
  backfill_best_version_now: ["Scan and backfill now", "Backfill existing episode-upgrade subscriptions after saving, then reset automatically"],
  completion_guard_mode: ["Completion guard mode", "Choose the review strength used before completion; Balanced is the default"],
  site_completion_evidence_enabled: ["Use site completion evidence", "Use site release titles as supporting completion evidence"],
  volatility_enabled: ["Episode-count change signal", "Treat recent total episode count changes as unstable"],
  volatility_window_days: ["Change-rate window (days)", "Number of days used to measure total episode count changes"],
  cadence_enabled: ["Airing cadence signal", "Estimate the waiting period from airing intervals without directly marking completion"],
  cadence_multiplier: ["Cadence window multiplier", "Increase the estimated waiting period; higher values wait longer"],
  cadence_min_window_days: ["Minimum cadence window (days)", "The estimated waiting period cannot be shorter than this value"],
  cadence_min_episodes: ["Minimum episodes for cadence", "Calculate airing intervals only after this many episodes have aired"],
  season_cooldown_days: ["Season cooldown (days)", "Continue observing for this many days after the last episode airs"],
  verify_enabled: ["Automatic correction", "Recheck completed episode counts and rebuild subscriptions when the count increases"],
  verify_interval_hours: ["Correction interval (hours)", "Interval for rechecking episode counts after completion"],
  verify_retention_days: ["Snapshot retention (days)", "Retain completion snapshots for this many days; default is 180"],
  timeout_release_days: ["Pre-completion observation days", "Maximum number of days allowed for pre-completion observation"],
  timeout_cadence_acceleration: ["Accelerate release by cadence", "Shorten the observation period after the cadence waiting window ends"]
};
const traditionalPhrases = [
  ["插件", "外掛"],
  ["启用", "啟用"],
  ["发送", "傳送"],
  ["通知", "通知"],
  ["运行", "執行"],
  ["重置", "重設"],
  ["数据", "資料"],
  ["检查", "檢查"],
  ["周期", "週期"],
  ["下载", "下載"],
  ["订阅", "訂閱"],
  ["删除", "刪除"],
  ["记录", "記錄"],
  ["监听", "監聽"],
  ["关键字", "關鍵字"],
  ["进度", "進度"],
  ["连续", "連續"],
  ["时", "時"],
  ["分钟", "分鐘"],
  ["小时", "小時"],
  ["自动", "自動"],
  ["状态", "狀態"],
  ["配置", "設定"],
  ["识别", "識別"],
  ["增强", "增強"],
  ["自定义", "自訂"],
  ["剧集", "影集"],
  ["电影", "電影"],
  ["上映", "上映"],
  ["暂停", "暫停"],
  ["用户", "使用者"],
  ["选择", "選擇"],
  ["范围", "範圍"],
  ["场景", "情境"],
  ["关闭", "關閉"],
  ["全部", "全部"],
  ["严格", "嚴格"],
  ["宽松", "寬鬆"],
  ["平衡", "平衡"],
  ["仅", "僅"],
  ["完结", "完結"],
  ["信号", "訊號"],
  ["纠错", "修正"],
  ["变更", "變更"],
  ["节奏", "節奏"],
  ["间隔", "間隔"],
  ["默认", "預設"],
  ["目标", "目標"],
  ["满足", "符合"],
  ["转换", "轉換"],
  ["转", "轉"],
  ["扫描", "掃描"],
  ["存量", "既有"],
  ["回填", "回填"],
  ["媒体库", "媒體庫"],
  ["整理", "整理"],
  ["文件", "檔案"],
  ["多个", "多個"],
  ["为空", "留空"],
  ["表示", "表示"],
  ["开启", "開啟"],
  ["发生", "發生"],
  ["复核", "複核"],
  ["触发", "觸發"],
  ["清理", "清理"],
  ["待定", "待定"],
  ["完成", "完成"],
  ["总集数", "總集數"],
  ["集数", "集數"],
  ["天数", "天數"],
  ["策略", "策略"],
  ["模式", "模式"],
  ["缓存", "快取"],
  ["大小", "大小"],
  ["支持", "支援"],
  ["处于激活状态", "處於啟用狀態"],
  ["正则表达式", "正規表示式"],
  ["媒体类型", "媒體類型"],
  ["审计", "稽核"],
  ["消息推送", "訊息推送"],
  ["站点", "站點"],
  ["搜索", "搜尋"],
  ["补搜", "補搜"],
  ["巡检", "巡檢"],
  ["种子", "種子"],
  ["任务", "任務"],
  ["标签", "標籤"],
  ["请求", "請求"],
  ["名单", "名單"],
  ["候选", "候選"],
  ["标题", "標題"],
  ["诊断", "診斷"],
  ["类型", "類型"],
  ["创建", "建立"],
  ["终止", "終止"],
  ["守卫", "守衛"],
  ["统计", "統計"],
  ["判断", "判斷"],
  ["预计", "預計"],
  ["参与", "參與"],
  ["观察", "觀察"],
  ["释放", "釋放"],
  ["结果", "結果"],
  ["动作", "動作"],
  ["原因", "原因"],
  ["频", "頻"],
  ["秒数", "秒數"],
  ["资源", "資源"],
  ["辅助", "輔助"],
  ["不足", "不足"],
  ["允许", "允許"],
  ["达到", "達到"],
  ["两次", "兩次"],
  ["轮数", "輪數"],
  ["提醒", "提醒"],
  ["强度", "強度"],
  ["佐证", "佐證"],
  ["稳定", "穩定"],
  ["增加", "增加"],
  ["重新", "重新"],
  ["最后", "最後"],
  ["继续", "繼續"],
  ["结束", "結束"],
  ["缩短", "縮短"],
  ["保存", "儲存"],
  ["采样", "取樣"],
  ["补全", "補全"],
  ["手动", "手動"],
  ["跳过", "略過"],
  ["作为", "作為"],
  ["低于", "低於"],
  ["视为", "視為"],
  ["一个", "一個"],
  ["大小写", "大小寫"],
  ["精准", "精準"],
  ["入库", "入庫"],
  ["日志", "日誌"],
  ["明细", "明細"],
  ["覆盖", "覆蓋"],
  ["进行", "進行"],
  ["设置", "設定"],
  ["等于", "等於"],
  ["参考", "參考"],
  ["意义", "意義"],
  ["逗号", "逗號"],
  ["探测", "探測"],
  ["多少轮", "多少輪"],
  ["计算", "計算"],
  ["新建", "建立"],
  ["切换", "切換"],
  ["于", "於"],
  ["视", "視"],
  ["采", "採"],
  ["补", "補"],
  ["删", "刪"],
  ["轮", "輪"],
  ["算", "算"],
  ["后", "後"],
  ["会", "會"],
  ["将", "將"],
  ["处", "處"],
  ["为", "為"],
  ["与", "與"],
  ["发", "發"],
  ["过", "過"],
  ["这", "這"],
  ["则", "則"],
  ["无", "無"],
  ["设", "設"],
  ["选", "選"],
  ["线", "線"],
  ["响", "響"],
  ["应", "應"],
  ["种", "種"],
  ["从", "從"],
  ["开", "開"],
  ["进", "進"],
  ["间", "間"],
  ["数", "數"],
  ["长", "長"],
  ["现", "現"],
  ["还", "還"],
  ["较", "較"],
  ["达", "達"],
  ["实", "實"],
  ["复", "複"],
  ["对", "對"],
  ["内", "內"],
  ["样", "樣"],
  ["并", "並"],
  ["当", "當"],
  ["监", "監"],
  ["执", "執"],
  ["检", "檢"],
  ["动", "動"],
  ["试", "試"],
  ["阈", "閾"],
  ["值", "值"],
  ["写", "寫"],
  ["号", "號"],
  ["旧", "舊"],
  ["库", "庫"],
  ["坏", "壞"],
  ["记", "記"],
  ["覆", "覆"],
  ["标", "標"],
  ["变化", "變化"],
  ["减", "減"],
  ["满", "滿"],
  ["少", "少"],
  ["低", "低"],
  ["冷却", "冷卻"],
  ["换", "換"],
  ["别", "別"]
];
function toTraditional(text) {
  return traditionalPhrases.reduce((result, [source, target]) => result.replaceAll(source, target), text);
}
const englishOptionTitles = {
  no: "Off",
  off: "Off",
  all: "All",
  movie: "Movies",
  tv: "TV shows",
  tv_episode: "TV shows (individual episodes)",
  normal: "Standard subscriptions",
  best_version: "Best-version subscriptions",
  best_version_episode: "Episode upgrades",
  audit: "Audit",
  loose: "Relaxed",
  balanced: "Balanced",
  strict: "Strict",
  summary: "Summary",
  detail: "Details",
  balanced_strict: "Balanced and strict",
  pause_movie: "Pause movie subscriptions",
  pause_tv: "Pause TV subscriptions",
  complete_movie: "Complete movie subscriptions",
  complete_tv: "Complete TV subscriptions",
  delete_movie: "Delete movie subscriptions",
  delete_tv: "Delete TV subscriptions",
  no_download: "No downloads",
  pre_air: "Before release",
  airing_gap: "Airing gap",
  auto_user: "User rule",
  external: "External pause",
  notify: "Notify only"
};
function localizedOptionTitle(locale, field, value, source) {
  if (locale === "zh-CN") return source;
  if (locale === "zh-TW") return toTraditional(source);
  if (typeof value === "number") {
    if (field.key === "auto_check_interval_minutes" || field.key === "download_check_interval_minutes") return `${value} minutes`;
    if (field.key === "meta_check_interval_hours") return `${value} hours`;
    return String(value);
  }
  const translated = englishOptionTitles[value];
  if (!translated) throw new Error(`Missing option translation: ${field.key}.${value}`);
  return translated;
}
function localizeGroups(localeSource, source = groups) {
  const locale = normalizeLocale(localeSource);
  return source.map((group) => {
    const translation = groupTranslations[group.key];
    if (!translation) throw new Error(`Missing group translation: ${group.key}`);
    const [title, summary] = locale === "zh-CN" ? [group.title, group.summary] : locale === "zh-TW" ? translation.tw : translation.en;
    return { ...group, title, summary };
  });
}
function localizeFields(localeSource, source = fields) {
  const locale = normalizeLocale(localeSource);
  return source.map((field) => {
    const english = englishFields[field.key];
    if (!english) throw new Error(`Missing field translation: ${field.key}`);
    const label = locale === "zh-CN" ? field.label : locale === "zh-TW" ? toTraditional(field.label) : english[0];
    const hint = field.hint ? locale === "zh-CN" ? field.hint : locale === "zh-TW" ? toTraditional(field.hint) : english[1] : void 0;
    if (!label.trim() || field.hint && !hint?.trim()) throw new Error(`Empty field translation: ${field.key}`);
    return {
      ...field,
      label,
      hint,
      options: field.options?.map((option) => ({
        ...option,
        title: localizedOptionTitle(locale, field, option.value, option.title)
      }))
    };
  });
}

function enabled(config, key) {
  const current = config[key];
  if (typeof current === "string") {
    return ["true", "on", "yes", "1", "guard"].includes(current.trim().toLowerCase());
  }
  if (typeof current === "number") return current !== 0;
  return current === true;
}
function value(config, key) {
  return String(config[key] ?? "");
}
function buildImpactPreview(config, locale = "zh-CN") {
  const normalized = normalizeSaeConfig(config);
  const items = [];
  const add = (key, tone, params = {}) => {
    items.push({
      title: t(locale, `preview.${key}.title`, params),
      detail: t(locale, `preview.${key}.detail`, params),
      tone
    });
  };
  if (!enabled(normalized, "enabled")) {
    add("disabled", "info");
  }
  if (enabled(normalized, "reset_task")) {
    add("reset", "error");
  }
  if (enabled(normalized, "backfill_best_version_now")) {
    add("backfillNow", "warning");
  }
  if (enabled(normalized, "enabled")) {
    add("general", "success", { value: value(normalized, "auto_check_interval_minutes") });
    add("metadata", "success", { value: value(normalized, "meta_check_interval_hours") });
    if (enabled(normalized, "onlyonce")) add("runOnce", "warning");
    if (enabled(normalized, "pending_download_enabled") || enabled(normalized, "download_monitor_enabled")) {
      add("downloadCheck", "success", { value: value(normalized, "download_check_interval_minutes") });
    }
    if (value(normalized, "best_version_type") !== "no") {
      add("bestVersion", "warning");
      if (value(normalized, "best_version_cron").trim()) {
        add("bestVersionCheck", "warning", { value: value(normalized, "best_version_cron") });
      }
    }
    if (enabled(normalized, "verify_enabled")) {
      add("verify", "warning", { value: value(normalized, "verify_interval_hours") });
    }
    if (enabled(normalized, "download_monitor_enabled")) {
      add("removeTorrent", "error");
    }
    if (value(normalized, "subscription_cleanup_history_type") !== "no") {
      add("cleanup", "error");
    }
    const actions = normalized.no_download_actions;
    const movieNoDownloadEnabled = normalized.movie_no_download_days !== 0;
    const tvNoDownloadEnabled = normalized.tv_no_download_days !== 0;
    const hasEnabledMediaAction = (movieAction, tvAction) => actions.some(
      (action) => movieNoDownloadEnabled && action === movieAction || tvNoDownloadEnabled && action === tvAction
    );
    if (hasEnabledMediaAction("pause_movie", "pause_tv")) {
      add("pause", "warning");
    }
    if (hasEnabledMediaAction("complete_movie", "complete_tv")) {
      add("complete", "warning");
    }
    if (hasEnabledMediaAction("delete_movie", "delete_tv")) {
      add("delete", "error");
    }
    if (enabled(normalized, "best_version_episode_to_full")) {
      add("episodeToFull", "warning");
    }
    const recognitionMode = value(normalized, "recognition_guard_mode").trim().toLowerCase();
    if (recognitionMode === "audit") {
      add("audit", "info");
    } else if (["loose", "balanced", "strict"].includes(recognitionMode)) {
      add("filter", "warning");
    }
  }
  return items;
}

const {defineComponent:_defineComponent} = await importShared('vue');

const {createElementVNode:_createElementVNode,unref:_unref,resolveComponent:_resolveComponent,createVNode:_createVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,normalizeClass:_normalizeClass,renderList:_renderList,Fragment:_Fragment,createBlock:_createBlock,createSlots:_createSlots,withModifiers:_withModifiers} = await importShared('vue');

const _hoisted_1 = { class: "sae-config" };
const _hoisted_2 = { class: "sae-config-header__brand" };
const _hoisted_3 = ["src"];
const _hoisted_4 = { class: "sae-config-header__identity" };
const _hoisted_5 = { class: "sae-config-header__crumbs" };
const _hoisted_6 = { class: "sae-config-header__title-row" };
const _hoisted_7 = { class: "sae-config-header__title" };
const _hoisted_8 = { class: "sae-config-header__actions" };
const _hoisted_9 = {
  key: 0,
  class: "sae-config-header__change-state"
};
const _hoisted_10 = { class: "sae-config-header__close-label" };
const _hoisted_11 = { class: "sae-config__body" };
const _hoisted_12 = { class: "sae-config-layout" };
const _hoisted_13 = { class: "sae-mobile-group-selector" };
const _hoisted_14 = ["aria-label"];
const _hoisted_15 = { class: "sae-group-nav__heading" };
const _hoisted_16 = { class: "sae-field-surface" };
const _hoisted_17 = { class: "sae-field-surface__heading-copy" };
const _hoisted_18 = { class: "sae-field-section__rows" };
const _hoisted_19 = { class: "sae-field-row__copy" };
const _hoisted_20 = { class: "sae-field-row__label" };
const _hoisted_21 = { key: 0 };
const _hoisted_22 = { class: "sae-field-control" };
const _hoisted_23 = {
  key: 0,
  class: "sae-select-summary__primary"
};
const _hoisted_24 = {
  key: 1,
  class: "sae-select-summary__count"
};
const _hoisted_25 = {
  key: 2,
  class: "sae-number-stepper"
};
const _hoisted_26 = {
  key: 0,
  class: "sae-number-stepper__unit"
};
const _hoisted_27 = {
  key: 0,
  class: "sae-field-section sae-tracker-entry"
};
const _hoisted_28 = { class: "sae-tracker-entry__copy" };
const _hoisted_29 = { class: "sae-impact-preview" };
const _hoisted_30 = { class: "sae-impact-preview__title" };
const _hoisted_31 = {
  key: 0,
  class: "sae-impact-preview__draft-state"
};
const _hoisted_32 = { class: "sae-impact-preview__group" };
const _hoisted_33 = { class: "sae-impact-preview__list" };
const _hoisted_34 = ["aria-label"];
const _hoisted_35 = { class: "sae-runtime-summary__title" };
const _hoisted_36 = {
  key: 0,
  class: "sae-runtime-summary__state"
};
const _hoisted_37 = { class: "sae-runtime-summary__metrics" };
const _hoisted_38 = { class: "sae-runtime-summary__row" };
const _hoisted_39 = { class: "sae-runtime-summary__row" };
const _hoisted_40 = { class: "sae-runtime-summary__domains" };
const _hoisted_41 = {
  key: 2,
  class: "sae-runtime-summary__unavailable"
};
const _hoisted_42 = { class: "sae-mobile-savebar" };
const _hoisted_43 = {
  key: 0,
  class: "sae-mobile-savebar__state"
};
const {computed,getCurrentInstance,nextTick,onBeforeUnmount,onMounted,ref} = await importShared('vue');

const {useTheme} = await importShared('vuetify');
const README_URL = "https://github.com/InfinityPacer/MoviePilot-Plugins/blob/main/plugins.v2/subscribeassistantenhanced/README.md";
const _sfc_main = /* @__PURE__ */ _defineComponent({
  __name: "Config",
  props: {
    initialConfig: {},
    api: {}
  },
  emits: ["save", "close", "switch"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const { draft, changedCount, buildSavePayload } = useConfigDraft(props.initialConfig);
    const instance = getCurrentInstance();
    const locale = computed(() => normalizeLocale(instance?.appContext.config.globalProperties.$i18n?.locale));
    const localizedGroups = computed(() => localizeGroups(locale.value, groups));
    const localizedFields = computed(() => localizeFields(locale.value, fields));
    const fieldsByKey = computed(() => new Map(
      localizedFields.value.filter((field) => !field.legacyUiKey && !field.dialogOnly).map((field) => [field.key, field])
    ));
    const trackerField = computed(() => localizedFields.value.find(
      (field) => field.key === "default_tracker_response" && field.dialogOnly
    ));
    const activeGroup = ref("global");
    const impactItems = computed(() => buildImpactPreview(draft, locale.value));
    const runtimeSummary = ref(null);
    const summaryState = ref("loading");
    const trackerDialogOpen = ref(false);
    const yamlDialogOpen = ref(false);
    const mobileGroupSheet = ref(false);
    const configHeaderSentinel = ref(null);
    const fieldSurfaceHeading = ref(null);
    const headerScrolled = ref(false);
    const theme = useTheme();
    const aceTheme = computed(() => theme.current.value.dark ? "github_dark" : "github");
    let headerObserver;
    let configScrollRoot = null;
    let scrollIdleTimer;
    const sectionDefinitions = {
      global: [
        { titleKey: "section.running", keys: ["enabled", "notify"] },
        { titleKey: "section.oneTime", keys: ["onlyonce", "reset_task"] },
        {
          titleKey: "section.schedule",
          keys: [
            "auto_check_interval_minutes",
            "download_check_interval_minutes",
            "meta_check_interval_hours",
            "best_version_cron"
          ]
        }
      ],
      cleanup: [
        {
          titleKey: "section.download",
          keys: [
            "download_monitor_enabled",
            "manual_delete_listen",
            "tracker_response_listen",
            "auto_search_when_delete",
            "skip_deletion"
          ]
        },
        {
          titleKey: "section.timeout",
          keys: [
            "download_timeout_minutes",
            "download_progress_threshold",
            "download_retry_limit",
            "delete_exclude_tags",
            "delete_record_retention_hours"
          ]
        },
        {
          titleKey: "section.cleanup",
          keys: ["subscription_cleanup_history_type", "subscription_cleanup_history_scenes"]
        }
      ],
      pending: [
        {
          titleKey: "section.pending",
          keys: ["pending_enhanced_enabled", "pending_download_enabled"]
        },
        {
          titleKey: "section.tvDecision",
          keys: ["auto_tv_pending_days", "auto_tv_pending_episodes", "pending_use_volatility"]
        }
      ],
      pause: [
        {
          titleKey: "section.autoPause",
          keys: ["pause_enhanced_enabled", "auto_pause_users"]
        },
        {
          titleKey: "section.airing",
          keys: ["airing_pause_days", "movie_air_pause_days", "tv_air_pause_days"]
        },
        {
          titleKey: "section.noDownload",
          keys: ["movie_no_download_days", "tv_no_download_days", "no_download_actions"]
        }
      ],
      completion: [
        { titleKey: "section.siteProbe", keys: ["site_total_probe_enabled"] },
        {
          titleKey: "section.diagnostic",
          keys: [
            "progress_diagnostic_mode",
            "progress_diagnostic_stalled_rounds",
            "progress_diagnostic_cooldown_hours"
          ]
        },
        {
          titleKey: "section.pausedProbe",
          keys: [
            "paused_probe_reasons",
            "paused_probe_min_pause_days",
            "paused_probe_interval_hours"
          ]
        }
      ],
      bestVersion: [
        {
          titleKey: "section.bestVersionScope",
          keys: [
            "best_version_type",
            "best_version_movie_remaining_days",
            "best_version_tv_remaining_days"
          ]
        },
        {
          titleKey: "section.backfill",
          keys: [
            "best_version_episode_to_full",
            "best_version_backfill_enabled",
            "backfill_best_version_now"
          ]
        }
      ],
      guard: [
        {
          titleKey: "section.guard",
          keys: [
            "completion_guard_mode",
            "site_completion_evidence_enabled",
            "volatility_enabled",
            "volatility_window_days"
          ]
        },
        {
          titleKey: "section.cadence",
          keys: [
            "cadence_enabled",
            "cadence_multiplier",
            "cadence_min_window_days",
            "cadence_min_episodes",
            "season_cooldown_days"
          ]
        },
        {
          titleKey: "section.correction",
          keys: [
            "verify_enabled",
            "verify_interval_hours",
            "verify_retention_days",
            "timeout_release_days",
            "timeout_cadence_acceleration"
          ]
        }
      ],
      recognition: [
        {
          titleKey: "section.recognition",
          keys: [
            "recognition_guard_mode",
            "recognition_guard_notify",
            "recognition_guard_notify_interval",
            "recognition_guard_tmdb_recheck_mode",
            "recognition_guard_cache_maxsize"
          ]
        },
        { titleKey: "section.custom", keys: ["recognition_guard_custom_config"] }
      ]
    };
    const impactToneIcons = {
      info: "mdi-information-outline",
      success: "mdi-check-circle-outline",
      warning: "mdi-alert-outline",
      error: "mdi-alert-circle-outline"
    };
    const activeGroupMeta = computed(
      () => localizedGroups.value.find((group) => group.key === activeGroup.value) ?? localizedGroups.value[0]
    );
    const activeSections = computed(
      () => sectionDefinitions[activeGroup.value].map((section) => ({
        ...section,
        title: t(locale.value, section.titleKey),
        fields: section.keys.map((key) => fieldsByKey.value.get(key)).filter((field) => Boolean(field))
      }))
    );
    const summaryDomains = computed(() => Object.entries(runtimeSummary.value?.domains ?? {}));
    const domainTranslationKeys = {
      "完结守卫模式": "domain.completionGuard",
      "待定增强": "domain.pending",
      "暂停优化": "domain.pause",
      "自动洗版": "domain.bestVersion",
      "下载管理": "domain.download",
      "完成后验证": "domain.verify",
      "站点集数探测": "domain.siteTotal",
      "站点完结信号": "domain.siteCompletion",
      "识别增强": "domain.recognition"
    };
    function handleConfigScroll() {
      if (!configScrollRoot) return;
      configScrollRoot.classList.add("sae-config-scroll-root--active");
      window.clearTimeout(scrollIdleTimer);
      scrollIdleTimer = window.setTimeout(() => {
        configScrollRoot?.classList.remove("sae-config-scroll-root--active");
      }, 600);
    }
    onMounted(() => {
      void loadSummary(props.api).then((payload) => {
        runtimeSummary.value = payload;
        summaryState.value = payload ? "available" : "unavailable";
      });
      const scrollRoot = configHeaderSentinel.value?.closest(".v-card-text") ?? null;
      configScrollRoot = scrollRoot;
      scrollRoot?.classList.add("sae-config-scroll-root");
      scrollRoot?.addEventListener("scroll", handleConfigScroll, { passive: true });
      headerObserver = new IntersectionObserver(
        ([entry]) => {
          headerScrolled.value = !entry?.isIntersecting;
        },
        { root: scrollRoot, threshold: 1 }
      );
      if (configHeaderSentinel.value) headerObserver.observe(configHeaderSentinel.value);
    });
    onBeforeUnmount(() => {
      headerObserver?.disconnect();
      window.clearTimeout(scrollIdleTimer);
      configScrollRoot?.removeEventListener("scroll", handleConfigScroll);
      configScrollRoot?.classList.remove("sae-config-scroll-root", "sae-config-scroll-root--active");
    });
    function formatDomainStatus(value) {
      if (typeof value === "boolean") return t(locale.value, value ? "config.enabled" : "config.off");
      const modeFields = ["completion_guard_mode", "recognition_guard_mode", "best_version_type"];
      for (const key of modeFields) {
        const option = localizedFields.value.find((field) => field.key === key)?.options?.find((item) => String(item.value) === value);
        if (option) return option.title;
      }
      return value;
    }
    function formatDomainName(name) {
      const key = domainTranslationKeys[name];
      return key ? t(locale.value, key) : name;
    }
    function domainIcon(value) {
      if (typeof value !== "boolean") return "mdi-tune-variant";
      return value ? "mdi-check-circle-outline" : "mdi-minus-circle-outline";
    }
    function domainColor(value) {
      if (typeof value !== "boolean") return "info";
      return value ? "success" : void 0;
    }
    function updateNumber(key, incoming) {
      draft[key] = normalizeFiniteNumber(draft[key], incoming);
    }
    function numberStep(key) {
      return key === "cadence_multiplier" ? 0.5 : 1;
    }
    function stepNumber(key, direction) {
      updateNumber(key, draft[key] + numberStep(key) * direction);
    }
    function fieldUnit(field) {
      if (field.key === "download_progress_threshold") return "%";
      return field.label.match(/（([^）]+)）/)?.[1];
    }
    function selectionOverflowCount(key) {
      const value = draft[key];
      return Array.isArray(value) ? Math.max(0, value.length - 1) : 0;
    }
    async function selectMobileGroup(group) {
      activeGroup.value = group;
      mobileGroupSheet.value = false;
      await nextTick();
      fieldSurfaceHeading.value?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    function saveConfig() {
      emit("save", buildSavePayload());
    }
    return (_ctx, _cache) => {
      const _component_VIcon = _resolveComponent("VIcon");
      const _component_VChip = _resolveComponent("VChip");
      const _component_VBtn = _resolveComponent("VBtn");
      const _component_VSpacer = _resolveComponent("VSpacer");
      const _component_VTooltip = _resolveComponent("VTooltip");
      const _component_VListItem = _resolveComponent("VListItem");
      const _component_VList = _resolveComponent("VList");
      const _component_VSwitch = _resolveComponent("VSwitch");
      const _component_VSelect = _resolveComponent("VSelect");
      const _component_VTextField = _resolveComponent("VTextField");
      const _component_VCronField = _resolveComponent("VCronField");
      const _component_VProgressCircular = _resolveComponent("VProgressCircular");
      const _component_VCardTitle = _resolveComponent("VCardTitle");
      const _component_VTextarea = _resolveComponent("VTextarea");
      const _component_VCardText = _resolveComponent("VCardText");
      const _component_VCardActions = _resolveComponent("VCardActions");
      const _component_VCard = _resolveComponent("VCard");
      const _component_VDialog = _resolveComponent("VDialog");
      const _component_VBottomSheet = _resolveComponent("VBottomSheet");
      const _component_VAceEditor = _resolveComponent("VAceEditor");
      return _openBlock(), _createElementBlock("section", _hoisted_1, [
        _createElementVNode("form", {
          class: "sae-config__form",
          onSubmit: _withModifiers(saveConfig, ["prevent"])
        }, [
          _createElementVNode("div", {
            ref_key: "configHeaderSentinel",
            ref: configHeaderSentinel,
            class: "sae-config-header-sentinel",
            "aria-hidden": "true"
          }, null, 512),
          _createElementVNode("header", {
            class: _normalizeClass(["sae-config-header", { "sae-config-header--scrolled": headerScrolled.value }])
          }, [
            _createElementVNode("div", _hoisted_2, [
              _createElementVNode("img", {
                src: _unref(saeLogo),
                alt: "",
                class: "sae-config-header__logo"
              }, null, 8, _hoisted_3),
              _createElementVNode("div", _hoisted_4, [
                _createElementVNode("div", _hoisted_5, [
                  _cache[13] || (_cache[13] = _createElementVNode("span", null, "MoviePilot", -1)),
                  _createVNode(_component_VIcon, {
                    icon: "mdi-chevron-right",
                    size: "14"
                  }),
                  _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.plugin")), 1),
                  _createVNode(_component_VIcon, {
                    icon: "mdi-chevron-right",
                    size: "14"
                  })
                ]),
                _createElementVNode("div", _hoisted_6, [
                  _createElementVNode("h1", _hoisted_7, _toDisplayString(_unref(t)(locale.value, "config.title")), 1),
                  _createVNode(_component_VChip, {
                    color: "primary",
                    size: "x-small",
                    variant: "tonal"
                  }, {
                    default: _withCtx(() => [..._cache[14] || (_cache[14] = [
                      _createTextVNode("BETA", -1)
                    ])]),
                    _: 1
                  })
                ])
              ])
            ]),
            _createElementVNode("div", _hoisted_8, [
              _unref(changedCount) > 0 ? (_openBlock(), _createElementBlock("span", _hoisted_9, [
                _createVNode(_component_VIcon, {
                  color: "success",
                  icon: "mdi-check-circle",
                  size: "16"
                }),
                _createTextVNode(" " + _toDisplayString(_unref(t)(locale.value, "config.changedCount", { count: _unref(changedCount) })), 1)
              ])) : _createCommentVNode("", true),
              _createVNode(_component_VBtn, {
                "aria-label": _unref(t)(locale.value, "config.save"),
                class: "sae-config-header__save",
                color: "primary",
                type: "submit",
                variant: "flat"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_VIcon, {
                    icon: "mdi-content-save",
                    start: ""
                  }),
                  _createTextVNode(" " + _toDisplayString(_unref(t)(locale.value, "config.save")), 1)
                ]),
                _: 1
              }, 8, ["aria-label"]),
              _createVNode(_component_VBtn, {
                "aria-label": _unref(t)(locale.value, "config.close"),
                class: "sae-config-header__close",
                type: "button",
                variant: "outlined",
                onClick: _cache[0] || (_cache[0] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_VIcon, {
                    icon: "mdi-close",
                    start: ""
                  }),
                  _createElementVNode("span", _hoisted_10, _toDisplayString(_unref(t)(locale.value, "config.close")), 1)
                ]),
                _: 1
              }, 8, ["aria-label"])
            ])
          ], 2),
          _createElementVNode("div", _hoisted_11, [
            _createElementVNode("div", _hoisted_12, [
              _createElementVNode("div", _hoisted_13, [
                _createVNode(_component_VBtn, {
                  "aria-expanded": mobileGroupSheet.value,
                  "aria-haspopup": "dialog",
                  class: "sae-mobile-group-trigger",
                  type: "button",
                  variant: "outlined",
                  onClick: _cache[1] || (_cache[1] = ($event) => mobileGroupSheet.value = true)
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VIcon, {
                      icon: activeGroupMeta.value.icon,
                      size: "19",
                      start: ""
                    }, null, 8, ["icon"]),
                    _createElementVNode("span", null, _toDisplayString(activeGroupMeta.value.title), 1),
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VIcon, {
                      icon: "mdi-chevron-up",
                      size: "18"
                    })
                  ]),
                  _: 1
                }, 8, ["aria-expanded"]),
                _createVNode(_component_VBtn, {
                  href: README_URL,
                  "aria-label": _unref(t)(locale.value, "config.help"),
                  class: "sae-mobile-help",
                  icon: "",
                  rel: "noopener noreferrer",
                  size: "small",
                  target: "_blank",
                  variant: "text"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VIcon, {
                      icon: "mdi-help-circle-outline",
                      size: "18"
                    }),
                    _createVNode(_component_VTooltip, {
                      activator: "parent",
                      text: _unref(t)(locale.value, "config.help")
                    }, null, 8, ["text"])
                  ]),
                  _: 1
                }, 8, ["aria-label"])
              ]),
              _createElementVNode("nav", {
                class: "sae-group-nav",
                "aria-label": _unref(t)(locale.value, "config.selectGroup")
              }, [
                _createElementVNode("div", _hoisted_15, _toDisplayString(_unref(t)(locale.value, "config.settings")), 1),
                _createVNode(_component_VList, {
                  class: "sae-group-nav__list",
                  density: "compact",
                  nav: ""
                }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(localizedGroups.value, (group) => {
                      return _openBlock(), _createBlock(_component_VListItem, {
                        key: group.key,
                        active: activeGroup.value === group.key,
                        "prepend-icon": group.icon,
                        title: group.title,
                        color: "primary",
                        rounded: "lg",
                        onClick: ($event) => activeGroup.value = group.key
                      }, null, 8, ["active", "prepend-icon", "title", "onClick"]);
                    }), 128))
                  ]),
                  _: 1
                }),
                _createVNode(_component_VBtn, {
                  href: README_URL,
                  class: "sae-group-nav__help",
                  "append-icon": "mdi-open-in-new",
                  "prepend-icon": "mdi-help-circle-outline",
                  rel: "noopener noreferrer",
                  target: "_blank",
                  variant: "text"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.help")), 1)
                  ]),
                  _: 1
                })
              ], 8, _hoisted_14),
              _createElementVNode("main", _hoisted_16, [
                _createElementVNode("div", {
                  ref_key: "fieldSurfaceHeading",
                  ref: fieldSurfaceHeading,
                  class: "sae-field-surface__heading"
                }, [
                  _createElementVNode("div", _hoisted_17, [
                    _createVNode(_component_VIcon, {
                      icon: activeGroupMeta.value.icon,
                      color: "primary",
                      size: "22"
                    }, null, 8, ["icon"]),
                    _createElementVNode("div", null, [
                      _createElementVNode("h2", null, _toDisplayString(activeGroupMeta.value.title), 1),
                      _createElementVNode("p", null, _toDisplayString(activeGroupMeta.value.summary), 1)
                    ])
                  ])
                ], 512),
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(activeSections.value, (section, sectionIndex) => {
                  return _openBlock(), _createElementBlock("section", {
                    key: section.title,
                    class: "sae-field-section"
                  }, [
                    _createElementVNode("h3", null, _toDisplayString(sectionIndex + 1) + ". " + _toDisplayString(section.title), 1),
                    _createElementVNode("div", _hoisted_18, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(section.fields, (field) => {
                        return _openBlock(), _createElementBlock("div", {
                          key: field.key,
                          class: _normalizeClass(["sae-field-row", { "sae-field-row--switch": field.kind === "switch" }])
                        }, [
                          _createElementVNode("div", _hoisted_19, [
                            _createElementVNode("div", _hoisted_20, _toDisplayString(field.label), 1),
                            field.hint ? (_openBlock(), _createElementBlock("p", _hoisted_21, _toDisplayString(field.hint), 1)) : _createCommentVNode("", true)
                          ]),
                          _createElementVNode("div", _hoisted_22, [
                            field.kind === "switch" ? (_openBlock(), _createBlock(_component_VSwitch, {
                              key: 0,
                              id: `sae-field-${field.key}`,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              color: "primary",
                              density: "compact",
                              "hide-details": ""
                            }, null, 8, ["id", "modelValue", "onUpdate:modelValue", "aria-label"])) : field.kind === "select" || field.kind === "multi-select" ? (_openBlock(), _createBlock(_component_VSelect, {
                              key: 1,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              density: "compact",
                              "hide-details": "",
                              "item-title": "title",
                              "item-value": "value",
                              items: field.options,
                              multiple: field.kind === "multi-select",
                              variant: "outlined"
                            }, _createSlots({ _: 2 }, [
                              field.kind === "multi-select" ? {
                                name: "selection",
                                fn: _withCtx(({ item, index }) => [
                                  index === 0 ? (_openBlock(), _createElementBlock("span", _hoisted_23, _toDisplayString(item.title), 1)) : index === 1 ? (_openBlock(), _createElementBlock("span", _hoisted_24, " +" + _toDisplayString(selectionOverflowCount(field.key)), 1)) : _createCommentVNode("", true)
                                ]),
                                key: "0"
                              } : void 0
                            ]), 1032, ["modelValue", "onUpdate:modelValue", "aria-label", "items", "multiple"])) : field.kind === "number" ? (_openBlock(), _createElementBlock("div", _hoisted_25, [
                              _createVNode(_component_VBtn, {
                                "aria-label": _unref(t)(locale.value, "config.decrease", { label: field.label }),
                                icon: "",
                                type: "button",
                                variant: "text",
                                onClick: ($event) => stepNumber(field.key, -1)
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_VIcon, { icon: "mdi-minus" })
                                ]),
                                _: 1
                              }, 8, ["aria-label", "onClick"]),
                              _createVNode(_component_VTextField, {
                                id: `sae-field-${field.key}`,
                                "aria-label": field.label,
                                density: "compact",
                                "hide-details": "",
                                "model-value": _unref(draft)[field.key],
                                step: numberStep(field.key),
                                type: "number",
                                variant: "plain",
                                "onUpdate:modelValue": ($event) => updateNumber(field.key, $event)
                              }, null, 8, ["id", "aria-label", "model-value", "step", "onUpdate:modelValue"]),
                              _createVNode(_component_VBtn, {
                                "aria-label": _unref(t)(locale.value, "config.increase", { label: field.label }),
                                icon: "",
                                type: "button",
                                variant: "text",
                                onClick: ($event) => stepNumber(field.key, 1)
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_VIcon, { icon: "mdi-plus" })
                                ]),
                                _: 1
                              }, 8, ["aria-label", "onClick"]),
                              fieldUnit(field) ? (_openBlock(), _createElementBlock("span", _hoisted_26, _toDisplayString(fieldUnit(field)), 1)) : _createCommentVNode("", true)
                            ])) : field.kind === "cron" ? (_openBlock(), _createBlock(_component_VCronField, {
                              key: 3,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              density: "compact",
                              "hide-details": "",
                              placeholder: _unref(t)(locale.value, "config.cronPlaceholder"),
                              variant: "outlined"
                            }, null, 8, ["modelValue", "onUpdate:modelValue", "aria-label", "placeholder"])) : field.kind === "text" ? (_openBlock(), _createBlock(_component_VTextField, {
                              key: 4,
                              id: `sae-field-${field.key}`,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              density: "compact",
                              "hide-details": "",
                              variant: "outlined"
                            }, null, 8, ["id", "modelValue", "onUpdate:modelValue", "aria-label"])) : field.kind === "textarea" ? (_openBlock(), _createBlock(_component_VBtn, {
                              key: 5,
                              "aria-label": field.label,
                              block: "",
                              "prepend-icon": "mdi-code-braces",
                              type: "button",
                              variant: "tonal",
                              onClick: _cache[2] || (_cache[2] = ($event) => yamlDialogOpen.value = true)
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.editYaml")), 1)
                              ]),
                              _: 1
                            }, 8, ["aria-label"])) : _createCommentVNode("", true)
                          ])
                        ], 2);
                      }), 128))
                    ])
                  ]);
                }), 128)),
                activeGroup.value === "cleanup" ? (_openBlock(), _createElementBlock("section", _hoisted_27, [
                  _createElementVNode("div", _hoisted_28, [
                    _createVNode(_component_VIcon, {
                      color: "primary",
                      icon: "mdi-message-text-outline",
                      size: "22"
                    }),
                    _createElementVNode("div", null, [
                      _createElementVNode("strong", null, _toDisplayString(trackerField.value.label), 1),
                      _createElementVNode("p", null, _toDisplayString(trackerField.value.hint), 1)
                    ])
                  ]),
                  _createVNode(_component_VBtn, {
                    "aria-label": _unref(t)(locale.value, "config.editLabel", { label: trackerField.value.label }),
                    color: "primary",
                    "prepend-icon": "mdi-pencil-outline",
                    type: "button",
                    variant: "tonal",
                    onClick: _cache[3] || (_cache[3] = ($event) => trackerDialogOpen.value = true)
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.edit")), 1)
                    ]),
                    _: 1
                  }, 8, ["aria-label"])
                ])) : _createCommentVNode("", true)
              ]),
              _createElementVNode("aside", _hoisted_29, [
                _createElementVNode("div", _hoisted_30, [
                  _createVNode(_component_VIcon, {
                    color: "primary",
                    icon: "mdi-eye-outline",
                    size: "20"
                  }),
                  _createElementVNode("h2", null, _toDisplayString(_unref(t)(locale.value, "config.preview")), 1),
                  _unref(changedCount) > 0 ? (_openBlock(), _createElementBlock("span", _hoisted_31, [
                    _createVNode(_component_VIcon, {
                      icon: "mdi-pencil-outline",
                      size: "14"
                    }),
                    _createTextVNode(" " + _toDisplayString(_unref(t)(locale.value, "config.unsaved")), 1)
                  ])) : _createCommentVNode("", true)
                ]),
                _createElementVNode("div", _hoisted_32, [
                  _createVNode(_component_VIcon, {
                    icon: activeGroupMeta.value.icon,
                    size: "22"
                  }, null, 8, ["icon"]),
                  _createElementVNode("div", null, [
                    _createElementVNode("strong", null, _toDisplayString(activeGroupMeta.value.title), 1),
                    _createElementVNode("p", null, _toDisplayString(activeGroupMeta.value.summary), 1)
                  ])
                ]),
                _createElementVNode("ul", _hoisted_33, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(impactItems.value, (item) => {
                    return _openBlock(), _createElementBlock("li", {
                      key: item.title,
                      class: "sae-impact-preview__item"
                    }, [
                      _createVNode(_component_VIcon, {
                        color: item.tone,
                        icon: impactToneIcons[item.tone],
                        size: "20"
                      }, null, 8, ["color", "icon"]),
                      _createElementVNode("div", null, [
                        _createElementVNode("strong", null, _toDisplayString(item.title), 1),
                        _createElementVNode("p", null, _toDisplayString(item.detail), 1)
                      ])
                    ]);
                  }), 128))
                ]),
                _createElementVNode("section", {
                  "aria-label": _unref(t)(locale.value, "config.runtime"),
                  class: "sae-runtime-summary"
                }, [
                  _createElementVNode("div", _hoisted_35, [
                    _createVNode(_component_VIcon, {
                      color: "primary",
                      icon: "mdi-chart-box-outline",
                      size: "19"
                    }),
                    _createElementVNode("h3", null, _toDisplayString(_unref(t)(locale.value, "config.runtime")), 1)
                  ]),
                  summaryState.value === "loading" ? (_openBlock(), _createElementBlock("div", _hoisted_36, [
                    _createVNode(_component_VProgressCircular, {
                      color: "primary",
                      indeterminate: "",
                      size: "18",
                      width: "2"
                    }),
                    _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.runtimeLoading")), 1)
                  ])) : summaryState.value === "available" && runtimeSummary.value ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                    _createElementVNode("div", _hoisted_37, [
                      _createElementVNode("div", _hoisted_38, [
                        _createVNode(_component_VIcon, {
                          icon: "mdi-timer-sand",
                          size: "18"
                        }),
                        _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.pendingCount")), 1),
                        _createElementVNode("strong", null, _toDisplayString(runtimeSummary.value.pending_count), 1)
                      ]),
                      _createElementVNode("div", _hoisted_39, [
                        _createVNode(_component_VIcon, {
                          icon: "mdi-download-network-outline",
                          size: "18"
                        }),
                        _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.monitoredCount")), 1),
                        _createElementVNode("strong", null, _toDisplayString(runtimeSummary.value.monitored_torrents), 1)
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_40, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(summaryDomains.value, ([name, status]) => {
                        return _openBlock(), _createElementBlock("div", {
                          key: name,
                          class: "sae-runtime-summary__row"
                        }, [
                          _createVNode(_component_VIcon, {
                            color: domainColor(status),
                            icon: domainIcon(status),
                            size: "18"
                          }, null, 8, ["color", "icon"]),
                          _createElementVNode("span", null, _toDisplayString(formatDomainName(name)), 1),
                          _createElementVNode("strong", null, _toDisplayString(formatDomainStatus(status)), 1)
                        ]);
                      }), 128))
                    ])
                  ], 64)) : (_openBlock(), _createElementBlock("p", _hoisted_41, _toDisplayString(_unref(t)(locale.value, "config.runtimeUnavailable")), 1))
                ], 8, _hoisted_34)
              ])
            ])
          ]),
          _createElementVNode("div", _hoisted_42, [
            _unref(changedCount) > 0 ? (_openBlock(), _createElementBlock("span", _hoisted_43, [
              _createVNode(_component_VIcon, {
                color: "success",
                icon: "mdi-check-circle",
                size: "16"
              }),
              _createTextVNode(" " + _toDisplayString(_unref(t)(locale.value, "config.changedCount", { count: _unref(changedCount) })), 1)
            ])) : _createCommentVNode("", true),
            _createVNode(_component_VSpacer),
            _createVNode(_component_VBtn, {
              color: "primary",
              disabled: _unref(changedCount) === 0,
              "prepend-icon": "mdi-content-save",
              type: "submit",
              variant: "flat"
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.save")), 1)
              ]),
              _: 1
            }, 8, ["disabled"])
          ])
        ], 32),
        _createVNode(_component_VDialog, {
          modelValue: trackerDialogOpen.value,
          "onUpdate:modelValue": _cache[7] || (_cache[7] = ($event) => trackerDialogOpen.value = $event),
          "max-width": "720",
          scrollable: "",
          width: "calc(100% - 24px)"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCard, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, { class: "sae-tracker-dialog__title" }, {
                  default: _withCtx(() => [
                    _createElementVNode("span", null, _toDisplayString(trackerField.value.label), 1),
                    _createVNode(_component_VBtn, {
                      "aria-label": `${_unref(t)(locale.value, "config.close")} ${trackerField.value.label}`,
                      icon: "",
                      size: "small",
                      variant: "text",
                      onClick: _cache[4] || (_cache[4] = ($event) => trackerDialogOpen.value = false)
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VIcon, { icon: "mdi-close" }),
                        _createVNode(_component_VTooltip, {
                          activator: "parent",
                          text: _unref(t)(locale.value, "config.close")
                        }, null, 8, ["text"])
                      ]),
                      _: 1
                    }, 8, ["aria-label"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardText, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_VTextarea, {
                      modelValue: _unref(draft).default_tracker_response,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => _unref(draft).default_tracker_response = $event),
                      "aria-label": trackerField.value.label,
                      hint: trackerField.value.hint,
                      label: trackerField.value.label,
                      "persistent-hint": "",
                      rows: "10",
                      variant: "outlined"
                    }, null, 8, ["modelValue", "aria-label", "hint", "label"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardActions, { class: "sae-tracker-dialog__actions" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VBtn, {
                      color: "primary",
                      "prepend-icon": "mdi-check",
                      onClick: _cache[6] || (_cache[6] = ($event) => trackerDialogOpen.value = false)
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.done")), 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        _createVNode(_component_VBottomSheet, {
          modelValue: mobileGroupSheet.value,
          "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => mobileGroupSheet.value = $event),
          class: "sae-mobile-group-sheet"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCard, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, null, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.selectGroup")), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_VList, {
                  lines: "two",
                  nav: ""
                }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(localizedGroups.value, (group) => {
                      return _openBlock(), _createBlock(_component_VListItem, {
                        key: group.key,
                        active: activeGroup.value === group.key,
                        "prepend-icon": group.icon,
                        subtitle: group.summary,
                        title: group.title,
                        color: "primary",
                        onClick: ($event) => selectMobileGroup(group.key)
                      }, {
                        append: _withCtx(() => [
                          activeGroup.value === group.key ? (_openBlock(), _createBlock(_component_VIcon, {
                            key: 0,
                            icon: "mdi-check"
                          })) : _createCommentVNode("", true)
                        ]),
                        _: 2
                      }, 1032, ["active", "prepend-icon", "subtitle", "title", "onClick"]);
                    }), 128))
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"]),
        _createVNode(_component_VDialog, {
          modelValue: yamlDialogOpen.value,
          "onUpdate:modelValue": _cache[12] || (_cache[12] = ($event) => yamlDialogOpen.value = $event),
          "max-width": "900",
          scrollable: "",
          width: "calc(100% - 24px)"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCard, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, { class: "sae-tracker-dialog__title" }, {
                  default: _withCtx(() => [
                    _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.yamlTitle")), 1),
                    _createVNode(_component_VBtn, {
                      "aria-label": _unref(t)(locale.value, "config.close"),
                      icon: "",
                      size: "small",
                      variant: "text",
                      onClick: _cache[9] || (_cache[9] = ($event) => yamlDialogOpen.value = false)
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VIcon, { icon: "mdi-close" })
                      ]),
                      _: 1
                    }, 8, ["aria-label"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardText, { class: "sae-yaml-dialog__content" }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VAceEditor, {
                      value: _unref(draft).recognition_guard_custom_config,
                      "onUpdate:value": _cache[10] || (_cache[10] = ($event) => _unref(draft).recognition_guard_custom_config = $event),
                      theme: aceTheme.value,
                      lang: "yaml",
                      options: { fontSize: 14, showPrintMargin: false, tabSize: 2, useSoftTabs: true },
                      class: "sae-yaml-editor"
                    }, null, 8, ["value", "theme"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_VCardActions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_VSpacer),
                    _createVNode(_component_VBtn, {
                      color: "primary",
                      "prepend-icon": "mdi-check",
                      onClick: _cache[11] || (_cache[11] = ($event) => yamlDialogOpen.value = false)
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.done")), 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        }, 8, ["modelValue"])
      ]);
    };
  }
});

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-f8b26e7b"]]);

export { Config as default };
