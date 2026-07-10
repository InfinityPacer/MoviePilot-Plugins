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
function buildImpactPreview(config) {
  const normalized = normalizeSaeConfig(config);
  const items = [];
  if (!enabled(normalized, "enabled")) {
    items.push({ title: "插件未启用", detail: "保存后不会注册订阅助手定时任务。", tone: "info" });
  }
  if (enabled(normalized, "reset_task")) {
    items.push({ title: "重置数据", detail: "保存后会清空插件任务数据并自动复位。", tone: "error" });
  }
  if (enabled(normalized, "backfill_best_version_now")) {
    items.push({ title: "立即扫描存量并回填", detail: "保存后会扫描存量分集洗版订阅并回填媒体库已有集。", tone: "warning" });
  }
  if (enabled(normalized, "enabled")) {
    items.push({ title: "通用巡检可能运行", detail: `周期 ${value(normalized, "auto_check_interval_minutes")} 分钟。`, tone: "success" });
    items.push({ title: "元数据检查可能运行", detail: `周期 ${value(normalized, "meta_check_interval_hours")} 小时。`, tone: "success" });
    if (enabled(normalized, "onlyonce")) items.push({ title: "立即运行一次", detail: "保存后约 3 秒触发一次全量巡检。", tone: "warning" });
    if (enabled(normalized, "pending_download_enabled") || enabled(normalized, "download_monitor_enabled")) {
      items.push({ title: "下载任务检查可能运行", detail: `周期 ${value(normalized, "download_check_interval_minutes")} 分钟。`, tone: "success" });
    }
    if (value(normalized, "best_version_type") !== "no") {
      items.push({ title: "可能自动创建洗版订阅", detail: "普通订阅完成后，符合当前洗版范围的媒体可能自动创建洗版订阅。", tone: "warning" });
      if (value(normalized, "best_version_cron").trim()) {
        items.push({ title: "洗版订阅检查可能运行", detail: `CRON ${value(normalized, "best_version_cron")}。`, tone: "warning" });
      }
    }
    if (enabled(normalized, "verify_enabled")) {
      items.push({ title: "自动纠错可能运行", detail: `周期 ${value(normalized, "verify_interval_hours")} 小时。`, tone: "warning" });
    }
    if (enabled(normalized, "download_monitor_enabled")) {
      items.push({ title: "可能删除下载器任务", detail: "下载停滞、Tracker 关键字或手动删种场景可能触发删种处理。", tone: "error" });
    }
    if (value(normalized, "subscription_cleanup_history_type") !== "no") {
      items.push({ title: "可能清理整理记录或文件", detail: "订阅清理范围已启用，请确认清理场景。", tone: "error" });
    }
    const actions = normalized.no_download_actions;
    const movieNoDownloadEnabled = normalized.movie_no_download_days !== 0;
    const tvNoDownloadEnabled = normalized.tv_no_download_days !== 0;
    const hasEnabledMediaAction = (movieAction, tvAction) => actions.some(
      (action) => movieNoDownloadEnabled && action === movieAction || tvNoDownloadEnabled && action === tvAction
    );
    if (hasEnabledMediaAction("pause_movie", "pause_tv")) {
      items.push({ title: "可能暂停订阅", detail: "无下载策略命中后，电影或剧集订阅可能被暂停。", tone: "warning" });
    }
    if (hasEnabledMediaAction("complete_movie", "complete_tv")) {
      items.push({ title: "可能完成订阅", detail: "无下载策略命中后，电影或剧集订阅可能被标记完成并移除。", tone: "warning" });
    }
    if (hasEnabledMediaAction("delete_movie", "delete_tv")) {
      items.push({ title: "可能删除订阅", detail: "无下载策略命中后，电影或剧集订阅可能被直接删除。", tone: "error" });
    }
    if (enabled(normalized, "best_version_episode_to_full")) {
      items.push({ title: "可能从分集洗版转为全集洗版", detail: "订阅目标集满足后，分集洗版可能切换为全集洗版。", tone: "warning" });
    }
    const recognitionMode = value(normalized, "recognition_guard_mode").trim().toLowerCase();
    if (recognitionMode === "audit") {
      items.push({ title: "识别增强可能记录候选风险", detail: "审计模式可能记录判定与通知，但不会过滤或移除候选。", tone: "info" });
    } else if (["loose", "balanced", "strict"].includes(recognitionMode)) {
      items.push({ title: "识别增强可能过滤候选", detail: "当前模式和生效的自定义策略覆盖可能过滤或移除候选。", tone: "warning" });
    }
  }
  return items;
}

const {defineComponent:_defineComponent} = await importShared('vue');

const {unref:_unref,createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,normalizeClass:_normalizeClass,withModifiers:_withModifiers} = await importShared('vue');

const _hoisted_1 = { class: "sae-config" };
const _hoisted_2 = { class: "sae-config-header" };
const _hoisted_3 = { class: "sae-config-header__brand" };
const _hoisted_4 = ["src"];
const _hoisted_5 = { class: "sae-config-header__identity" };
const _hoisted_6 = { class: "sae-config-header__crumbs" };
const _hoisted_7 = { class: "sae-config-header__title-row" };
const _hoisted_8 = { class: "sae-config-header__actions" };
const _hoisted_9 = { class: "sae-config-header__change-state" };
const _hoisted_10 = { class: "sae-config__body" };
const _hoisted_11 = { class: "sae-config-layout" };
const _hoisted_12 = { class: "sae-mobile-group-selector" };
const _hoisted_13 = {
  class: "sae-group-nav",
  "aria-label": "配置分组"
};
const _hoisted_14 = { class: "sae-field-surface" };
const _hoisted_15 = { class: "sae-field-surface__heading" };
const _hoisted_16 = { class: "sae-field-surface__heading-copy" };
const _hoisted_17 = { class: "sae-field-section__rows" };
const _hoisted_18 = { class: "sae-field-row__copy" };
const _hoisted_19 = { class: "sae-field-row__label" };
const _hoisted_20 = { key: 0 };
const _hoisted_21 = { class: "sae-field-control" };
const _hoisted_22 = {
  key: 3,
  class: "sae-number-stepper"
};
const _hoisted_23 = {
  key: 0,
  class: "sae-number-stepper__unit"
};
const _hoisted_24 = {
  key: 0,
  class: "sae-field-section sae-tracker-entry"
};
const _hoisted_25 = { class: "sae-tracker-entry__copy" };
const _hoisted_26 = { class: "sae-impact-preview" };
const _hoisted_27 = { class: "sae-impact-preview__title" };
const _hoisted_28 = { class: "sae-impact-preview__group" };
const _hoisted_29 = { class: "sae-impact-preview__list" };
const _hoisted_30 = {
  "aria-label": "运行概况",
  class: "sae-runtime-summary"
};
const _hoisted_31 = { class: "sae-runtime-summary__title" };
const _hoisted_32 = {
  key: 0,
  class: "sae-runtime-summary__state"
};
const _hoisted_33 = { class: "sae-runtime-summary__metrics" };
const _hoisted_34 = { class: "sae-runtime-summary__row" };
const _hoisted_35 = { class: "sae-runtime-summary__row" };
const _hoisted_36 = { class: "sae-runtime-summary__domains" };
const _hoisted_37 = {
  key: 2,
  class: "sae-runtime-summary__unavailable"
};
const _hoisted_38 = { class: "sae-mobile-savebar" };
const {computed,onMounted,ref} = await importShared('vue');
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
    const renderedFields = fields.filter((field) => !field.legacyUiKey && !field.dialogOnly);
    const fieldsByKey = new Map(renderedFields.map((field) => [field.key, field]));
    const trackerField = fields.find(
      (field) => field.key === "default_tracker_response" && field.dialogOnly
    );
    const activeGroup = ref("global");
    const impactItems = computed(() => buildImpactPreview(draft));
    const runtimeSummary = ref(null);
    const summaryState = ref("loading");
    const trackerDialogOpen = ref(false);
    const sectionDefinitions = {
      global: [
        { title: "运行状态", keys: ["enabled", "notify"] },
        { title: "一次性动作", keys: ["onlyonce", "reset_task"] },
        {
          title: "公共周期",
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
          title: "下载任务处理",
          keys: [
            "download_monitor_enabled",
            "manual_delete_listen",
            "tracker_response_listen",
            "auto_search_when_delete",
            "skip_deletion"
          ]
        },
        {
          title: "超时与重试",
          keys: [
            "download_timeout_minutes",
            "download_progress_threshold",
            "download_retry_limit",
            "delete_exclude_tags",
            "delete_record_retention_hours"
          ]
        },
        {
          title: "订阅记录清理",
          keys: ["subscription_cleanup_history_type", "subscription_cleanup_history_scenes"]
        }
      ],
      pending: [
        {
          title: "待定策略",
          keys: ["pending_enhanced_enabled", "pending_download_enabled"]
        },
        {
          title: "剧集判定",
          keys: ["auto_tv_pending_days", "auto_tv_pending_episodes", "pending_use_volatility"]
        }
      ],
      pause: [
        {
          title: "自动暂停",
          keys: ["pause_enhanced_enabled", "auto_pause_users"]
        },
        {
          title: "上映与播出窗口",
          keys: ["airing_pause_days", "movie_air_pause_days", "tv_air_pause_days"]
        },
        {
          title: "无下载处理",
          keys: ["movie_no_download_days", "tv_no_download_days", "no_download_actions"]
        }
      ],
      completion: [
        { title: "站点集数探测", keys: ["site_total_probe_enabled"] },
        {
          title: "无进展诊断",
          keys: [
            "progress_diagnostic_mode",
            "progress_diagnostic_stalled_rounds",
            "progress_diagnostic_cooldown_hours"
          ]
        },
        {
          title: "暂停订阅补搜",
          keys: [
            "paused_probe_reasons",
            "paused_probe_min_pause_days",
            "paused_probe_interval_hours"
          ]
        }
      ],
      bestVersion: [
        {
          title: "洗版范围",
          keys: [
            "best_version_type",
            "best_version_movie_remaining_days",
            "best_version_tv_remaining_days"
          ]
        },
        {
          title: "转换与回填",
          keys: [
            "best_version_episode_to_full",
            "best_version_backfill_enabled",
            "backfill_best_version_now"
          ]
        }
      ],
      guard: [
        {
          title: "守卫信号",
          keys: [
            "completion_guard_mode",
            "site_completion_evidence_enabled",
            "volatility_enabled",
            "volatility_window_days"
          ]
        },
        {
          title: "播出节奏",
          keys: [
            "cadence_enabled",
            "cadence_multiplier",
            "cadence_min_window_days",
            "cadence_min_episodes",
            "season_cooldown_days"
          ]
        },
        {
          title: "纠错与释放",
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
          title: "识别策略",
          keys: [
            "recognition_guard_mode",
            "recognition_guard_notify",
            "recognition_guard_notify_interval",
            "recognition_guard_tmdb_recheck_mode",
            "recognition_guard_cache_maxsize"
          ]
        },
        { title: "自定义规则", keys: ["recognition_guard_custom_config"] }
      ]
    };
    const impactToneIcons = {
      info: "mdi-information-outline",
      success: "mdi-check-circle-outline",
      warning: "mdi-alert-outline",
      error: "mdi-alert-circle-outline"
    };
    const activeGroupMeta = computed(
      () => groups.find((group) => group.key === activeGroup.value) ?? groups[0]
    );
    const activeSections = computed(
      () => sectionDefinitions[activeGroup.value].map((section) => ({
        ...section,
        fields: section.keys.map((key) => fieldsByKey.get(key)).filter((field) => Boolean(field))
      }))
    );
    const summaryDomains = computed(() => Object.entries(runtimeSummary.value?.domains ?? {}));
    onMounted(() => {
      void loadSummary(props.api).then((payload) => {
        runtimeSummary.value = payload;
        summaryState.value = payload ? "available" : "unavailable";
      });
    });
    function formatDomainStatus(value) {
      if (typeof value === "boolean") return value ? "启用" : "关闭";
      return value;
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
    function isOptionSelected(field, value) {
      const selected = draft[field.key];
      return Array.isArray(selected) && selected.includes(String(value));
    }
    function saveConfig() {
      emit("save", buildSavePayload());
    }
    return (_ctx, _cache) => {
      const _component_VIcon = _resolveComponent("VIcon");
      const _component_VChip = _resolveComponent("VChip");
      const _component_VBtn = _resolveComponent("VBtn");
      const _component_VAlert = _resolveComponent("VAlert");
      const _component_VTab = _resolveComponent("VTab");
      const _component_VTabs = _resolveComponent("VTabs");
      const _component_VListItem = _resolveComponent("VListItem");
      const _component_VList = _resolveComponent("VList");
      const _component_VSwitch = _resolveComponent("VSwitch");
      const _component_VBtnToggle = _resolveComponent("VBtnToggle");
      const _component_VTextField = _resolveComponent("VTextField");
      const _component_VTextarea = _resolveComponent("VTextarea");
      const _component_VProgressCircular = _resolveComponent("VProgressCircular");
      const _component_VTooltip = _resolveComponent("VTooltip");
      const _component_VCardTitle = _resolveComponent("VCardTitle");
      const _component_VCardText = _resolveComponent("VCardText");
      const _component_VSpacer = _resolveComponent("VSpacer");
      const _component_VCardActions = _resolveComponent("VCardActions");
      const _component_VCard = _resolveComponent("VCard");
      const _component_VDialog = _resolveComponent("VDialog");
      return _openBlock(), _createElementBlock("section", _hoisted_1, [
        _createElementVNode("form", {
          class: "sae-config__form",
          onSubmit: _withModifiers(saveConfig, ["prevent"])
        }, [
          _createElementVNode("header", _hoisted_2, [
            _createElementVNode("div", _hoisted_3, [
              _createElementVNode("img", {
                src: _unref(saeLogo),
                alt: "",
                class: "sae-config-header__logo"
              }, null, 8, _hoisted_4),
              _createElementVNode("div", _hoisted_5, [
                _createElementVNode("div", _hoisted_6, [
                  _cache[7] || (_cache[7] = _createElementVNode("span", null, "MoviePilot", -1)),
                  _createVNode(_component_VIcon, {
                    icon: "mdi-chevron-right",
                    size: "14"
                  }),
                  _cache[8] || (_cache[8] = _createElementVNode("span", null, "插件", -1)),
                  _createVNode(_component_VIcon, {
                    icon: "mdi-chevron-right",
                    size: "14"
                  })
                ]),
                _createElementVNode("div", _hoisted_7, [
                  _cache[10] || (_cache[10] = _createElementVNode("h1", { class: "sae-config-header__title" }, "订阅助手（增强版）", -1)),
                  _createVNode(_component_VChip, {
                    color: "primary",
                    size: "x-small",
                    variant: "tonal"
                  }, {
                    default: _withCtx(() => [..._cache[9] || (_cache[9] = [
                      _createTextVNode("BETA", -1)
                    ])]),
                    _: 1
                  })
                ])
              ])
            ]),
            _createElementVNode("div", _hoisted_8, [
              _createElementVNode("span", _hoisted_9, [
                _cache[11] || (_cache[11] = _createElementVNode("span", { class: "sae-config-header__change-dot" }, null, -1)),
                _createTextVNode(" " + _toDisplayString(_unref(changedCount) ? `已修改 ${_unref(changedCount)} 项` : "暂无修改"), 1)
              ]),
              _createVNode(_component_VBtn, {
                "aria-label": "保存更改",
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
                  _cache[12] || (_cache[12] = _createTextVNode(" 保存更改 ", -1))
                ]),
                _: 1
              }),
              _createVNode(_component_VBtn, {
                "aria-label": "关闭配置",
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
                  _cache[13] || (_cache[13] = _createElementVNode("span", { class: "sae-config-header__close-label" }, "关闭", -1))
                ]),
                _: 1
              })
            ])
          ]),
          _createElementVNode("div", _hoisted_10, [
            _createVNode(_component_VAlert, {
              class: "sae-config-warning",
              density: "compact",
              icon: "mdi-alert-outline",
              type: "warning",
              variant: "tonal"
            }, {
              default: _withCtx(() => [..._cache[14] || (_cache[14] = [
                _createTextVNode(" 高级功能：部分操作会影响订阅状态、下载任务和媒体文件，请谨慎修改配置。 ", -1)
              ])]),
              _: 1
            }),
            _createElementVNode("div", _hoisted_11, [
              _createElementVNode("div", _hoisted_12, [
                _createVNode(_component_VTabs, {
                  modelValue: activeGroup.value,
                  "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => activeGroup.value = $event),
                  "aria-label": "选择配置分组",
                  class: "sae-mobile-group-tabs",
                  density: "compact"
                }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(groups), (group) => {
                      return _openBlock(), _createBlock(_component_VTab, {
                        key: group.key,
                        value: group.key
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_VIcon, {
                            icon: group.icon,
                            size: "17",
                            start: ""
                          }, null, 8, ["icon"]),
                          _createTextVNode(" " + _toDisplayString(group.title), 1)
                        ]),
                        _: 2
                      }, 1032, ["value"]);
                    }), 128))
                  ]),
                  _: 1
                }, 8, ["modelValue"]),
                _createVNode(_component_VBtn, {
                  href: README_URL,
                  "aria-label": "查看插件 README",
                  icon: "mdi-help-circle-outline",
                  rel: "noopener noreferrer",
                  target: "_blank",
                  variant: "outlined"
                })
              ]),
              _createElementVNode("nav", _hoisted_13, [
                _cache[16] || (_cache[16] = _createElementVNode("div", { class: "sae-group-nav__heading" }, "插件设置", -1)),
                _createVNode(_component_VList, {
                  class: "sae-group-nav__list",
                  density: "compact",
                  nav: ""
                }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(_unref(groups), (group) => {
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
                  "prepend-icon": "mdi-help-circle-outline",
                  rel: "noopener noreferrer",
                  target: "_blank",
                  variant: "text"
                }, {
                  default: _withCtx(() => [..._cache[15] || (_cache[15] = [
                    _createTextVNode(" 插件帮助 ", -1)
                  ])]),
                  _: 1
                })
              ]),
              _createElementVNode("main", _hoisted_14, [
                _createElementVNode("div", _hoisted_15, [
                  _createElementVNode("div", _hoisted_16, [
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
                ]),
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(activeSections.value, (section, sectionIndex) => {
                  return _openBlock(), _createElementBlock("section", {
                    key: section.title,
                    class: "sae-field-section"
                  }, [
                    _createElementVNode("h3", null, _toDisplayString(sectionIndex + 1) + ". " + _toDisplayString(section.title), 1),
                    _createElementVNode("div", _hoisted_17, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(section.fields, (field) => {
                        return _openBlock(), _createElementBlock("div", {
                          key: field.key,
                          class: _normalizeClass(["sae-field-row", { "sae-field-row--switch": field.kind === "switch" }])
                        }, [
                          _createElementVNode("div", _hoisted_18, [
                            _createElementVNode("div", _hoisted_19, _toDisplayString(field.label), 1),
                            field.hint ? (_openBlock(), _createElementBlock("p", _hoisted_20, _toDisplayString(field.hint), 1)) : _createCommentVNode("", true)
                          ]),
                          _createElementVNode("div", _hoisted_21, [
                            field.kind === "switch" ? (_openBlock(), _createBlock(_component_VSwitch, {
                              key: 0,
                              id: `sae-field-${field.key}`,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              color: "primary",
                              density: "compact",
                              "hide-details": ""
                            }, null, 8, ["id", "modelValue", "onUpdate:modelValue", "aria-label"])) : field.kind === "select" ? (_openBlock(), _createBlock(_component_VBtnToggle, {
                              key: 1,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              class: "sae-choice-group",
                              color: "primary",
                              mandatory: "",
                              variant: "outlined"
                            }, {
                              default: _withCtx(() => [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(field.options, (option) => {
                                  return _openBlock(), _createBlock(_component_VBtn, {
                                    key: String(option.value),
                                    value: option.value
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(_toDisplayString(option.title), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["value"]);
                                }), 128))
                              ]),
                              _: 2
                            }, 1032, ["modelValue", "onUpdate:modelValue", "aria-label"])) : field.kind === "multi-select" ? (_openBlock(), _createBlock(_component_VBtnToggle, {
                              key: 2,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              class: "sae-choice-group sae-choice-group--multiple",
                              color: "primary",
                              multiple: "",
                              variant: "outlined"
                            }, {
                              default: _withCtx(() => [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(field.options, (option) => {
                                  return _openBlock(), _createBlock(_component_VBtn, {
                                    key: String(option.value),
                                    value: option.value
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_VIcon, {
                                        icon: isOptionSelected(field, option.value) ? "mdi-check-circle" : "mdi-circle-outline",
                                        size: "15",
                                        start: ""
                                      }, null, 8, ["icon"]),
                                      _createTextVNode(" " + _toDisplayString(option.title), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["value"]);
                                }), 128))
                              ]),
                              _: 2
                            }, 1032, ["modelValue", "onUpdate:modelValue", "aria-label"])) : field.kind === "number" ? (_openBlock(), _createElementBlock("div", _hoisted_22, [
                              _createVNode(_component_VBtn, {
                                "aria-label": `减小${field.label}`,
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
                                "aria-label": `增大${field.label}`,
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
                              fieldUnit(field) ? (_openBlock(), _createElementBlock("span", _hoisted_23, _toDisplayString(fieldUnit(field)), 1)) : _createCommentVNode("", true)
                            ])) : field.kind === "text" || field.kind === "cron" ? (_openBlock(), _createBlock(_component_VTextField, {
                              key: 4,
                              id: `sae-field-${field.key}`,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              density: "compact",
                              "hide-details": "",
                              variant: "outlined"
                            }, null, 8, ["id", "modelValue", "onUpdate:modelValue", "aria-label"])) : field.kind === "textarea" ? (_openBlock(), _createBlock(_component_VTextarea, {
                              key: 5,
                              id: `sae-field-${field.key}`,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              "auto-grow": "",
                              "hide-details": "",
                              rows: "7",
                              variant: "outlined"
                            }, null, 8, ["id", "modelValue", "onUpdate:modelValue", "aria-label"])) : _createCommentVNode("", true)
                          ])
                        ], 2);
                      }), 128))
                    ])
                  ]);
                }), 128)),
                activeGroup.value === "cleanup" ? (_openBlock(), _createElementBlock("section", _hoisted_24, [
                  _createElementVNode("div", _hoisted_25, [
                    _createVNode(_component_VIcon, {
                      color: "primary",
                      icon: "mdi-message-text-outline",
                      size: "22"
                    }),
                    _createElementVNode("div", null, [
                      _createElementVNode("strong", null, _toDisplayString(_unref(trackerField).label), 1),
                      _createElementVNode("p", null, _toDisplayString(_unref(trackerField).hint), 1)
                    ])
                  ]),
                  _createVNode(_component_VBtn, {
                    "aria-label": `编辑${_unref(trackerField).label}`,
                    color: "primary",
                    "prepend-icon": "mdi-pencil-outline",
                    type: "button",
                    variant: "tonal",
                    onClick: _cache[2] || (_cache[2] = ($event) => trackerDialogOpen.value = true)
                  }, {
                    default: _withCtx(() => [..._cache[17] || (_cache[17] = [
                      _createTextVNode(" 编辑 ", -1)
                    ])]),
                    _: 1
                  }, 8, ["aria-label"])
                ])) : _createCommentVNode("", true)
              ]),
              _createElementVNode("aside", _hoisted_26, [
                _createElementVNode("div", _hoisted_27, [
                  _createVNode(_component_VIcon, {
                    color: "primary",
                    icon: "mdi-eye-outline",
                    size: "20"
                  }),
                  _cache[18] || (_cache[18] = _createElementVNode("h2", null, "配置影响预览", -1))
                ]),
                _createElementVNode("div", _hoisted_28, [
                  _createVNode(_component_VIcon, {
                    icon: activeGroupMeta.value.icon,
                    size: "22"
                  }, null, 8, ["icon"]),
                  _createElementVNode("div", null, [
                    _createElementVNode("strong", null, _toDisplayString(activeGroupMeta.value.title), 1),
                    _createElementVNode("p", null, _toDisplayString(activeGroupMeta.value.summary), 1)
                  ])
                ]),
                _createElementVNode("ul", _hoisted_29, [
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
                _createElementVNode("section", _hoisted_30, [
                  _createElementVNode("div", _hoisted_31, [
                    _createVNode(_component_VIcon, {
                      color: "primary",
                      icon: "mdi-chart-box-outline",
                      size: "19"
                    }),
                    _cache[19] || (_cache[19] = _createElementVNode("h3", null, "运行概况", -1))
                  ]),
                  summaryState.value === "loading" ? (_openBlock(), _createElementBlock("div", _hoisted_32, [
                    _createVNode(_component_VProgressCircular, {
                      color: "primary",
                      indeterminate: "",
                      size: "18",
                      width: "2"
                    }),
                    _cache[20] || (_cache[20] = _createElementVNode("span", null, "正在读取运行概况", -1))
                  ])) : summaryState.value === "available" && runtimeSummary.value ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                    _createElementVNode("div", _hoisted_33, [
                      _createElementVNode("div", _hoisted_34, [
                        _createVNode(_component_VIcon, {
                          icon: "mdi-timer-sand",
                          size: "18"
                        }),
                        _cache[21] || (_cache[21] = _createElementVNode("span", null, "待定订阅", -1)),
                        _createElementVNode("strong", null, _toDisplayString(runtimeSummary.value.pending_count), 1)
                      ]),
                      _createElementVNode("div", _hoisted_35, [
                        _createVNode(_component_VIcon, {
                          icon: "mdi-download-network-outline",
                          size: "18"
                        }),
                        _cache[22] || (_cache[22] = _createElementVNode("span", null, "监控下载任务", -1)),
                        _createElementVNode("strong", null, _toDisplayString(runtimeSummary.value.monitored_torrents), 1)
                      ])
                    ]),
                    _createElementVNode("div", _hoisted_36, [
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
                          _createElementVNode("span", null, _toDisplayString(name), 1),
                          _createElementVNode("strong", null, _toDisplayString(formatDomainStatus(status)), 1)
                        ]);
                      }), 128))
                    ])
                  ], 64)) : (_openBlock(), _createElementBlock("p", _hoisted_37, "运行概况暂不可用"))
                ])
              ])
            ])
          ]),
          _createElementVNode("div", _hoisted_38, [
            _createElementVNode("span", null, [
              _cache[23] || (_cache[23] = _createElementVNode("span", { class: "sae-config-header__change-dot" }, null, -1)),
              _createTextVNode(" " + _toDisplayString(_unref(changedCount) ? `已修改 ${_unref(changedCount)} 项` : "暂无修改"), 1)
            ]),
            _createVNode(_component_VBtn, {
              color: "primary",
              "prepend-icon": "mdi-content-save",
              type: "submit",
              variant: "flat"
            }, {
              default: _withCtx(() => [..._cache[24] || (_cache[24] = [
                _createTextVNode(" 保存更改 ", -1)
              ])]),
              _: 1
            })
          ])
        ], 32),
        _createVNode(_component_VDialog, {
          modelValue: trackerDialogOpen.value,
          "onUpdate:modelValue": _cache[6] || (_cache[6] = ($event) => trackerDialogOpen.value = $event),
          "max-width": "720",
          scrollable: "",
          width: "calc(100% - 24px)"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VCard, null, {
              default: _withCtx(() => [
                _createVNode(_component_VCardTitle, { class: "sae-tracker-dialog__title" }, {
                  default: _withCtx(() => [
                    _createElementVNode("span", null, _toDisplayString(_unref(trackerField).label), 1),
                    _createVNode(_component_VBtn, {
                      "aria-label": `关闭${_unref(trackerField).label}`,
                      icon: "",
                      size: "small",
                      variant: "text",
                      onClick: _cache[3] || (_cache[3] = ($event) => trackerDialogOpen.value = false)
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VIcon, { icon: "mdi-close" }),
                        _createVNode(_component_VTooltip, {
                          activator: "parent",
                          text: "关闭"
                        })
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
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => _unref(draft).default_tracker_response = $event),
                      "aria-label": _unref(trackerField).label,
                      hint: _unref(trackerField).hint,
                      label: _unref(trackerField).label,
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
                      onClick: _cache[5] || (_cache[5] = ($event) => trackerDialogOpen.value = false)
                    }, {
                      default: _withCtx(() => [..._cache[25] || (_cache[25] = [
                        _createTextVNode(" 完成 ", -1)
                      ])]),
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

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-faa3719f"]]);

export { Config as default };
