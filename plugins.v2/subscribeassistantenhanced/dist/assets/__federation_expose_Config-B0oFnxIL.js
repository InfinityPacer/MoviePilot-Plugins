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
  const changedKeys = computed$1(
    () => configKeys.filter((key) => JSON.stringify(draft[key]) !== JSON.stringify(initialSnapshot[key]))
  );
  const changedCount = computed$1(() => changedKeys.value.length);
  function buildSavePayload() {
    return normalizeSaeConfig(draft);
  }
  return { draft, changedCount, changedKeys, buildSavePayload };
}

const groups = [
  { key: "global", title: "全局运行", icon: "mdi-tune-variant", summary: "插件开关、通知、一次性动作与公共周期" },
  { key: "cleanup", title: "订阅清理", icon: "mdi-delete-sweep-outline", summary: "下载监控、删种、Tracker 与整理记录清理", highRisk: true },
  { key: "pending", title: "订阅待定", icon: "mdi-timer-sand", summary: "下载中与剧集目标未稳定时保持待定" },
  { key: "pause", title: "订阅暂停", icon: "mdi-pause-circle-outline", summary: "按用户、上映播出窗口和无下载策略暂停订阅" },
  { key: "completion", title: "订阅补全", icon: "mdi-radar", summary: "站点集数探测与暂停订阅补搜" },
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
    "config.changedCount": "{count} 项待保存",
    "config.changes": "本次修改",
    "config.moreChanges": "另有 {count} 项",
    "config.save": "保存修改",
    "config.close": "关闭",
    "config.cadence": "运行节奏",
    "config.generalInspection": "通用巡检",
    "config.downloadInspection": "下载检查",
    "config.metadataInspection": "元数据检查",
    "config.bestVersionInspection": "洗版检查",
    "config.everyMinutes": "每 {value} 分钟",
    "config.everyHours": "每 {value} 小时",
    "config.notScheduled": "未设置",
    "config.activeDomains": "已启用能力",
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
    "config.yamlTitle": "自定义识别规则",
    "config.runtime": "运行概况",
    "config.runtimeLoading": "正在读取运行概况",
    "config.runtimeUnavailable": "运行概况暂不可用",
    "config.pendingCount": "待定订阅",
    "config.monitoredCount": "下载任务",
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
    "section.pausedProbe": "暂停订阅补搜",
    "section.bestVersionScope": "洗版范围",
    "section.backfill": "转换与回填",
    "section.guard": "守卫信号",
    "section.cadence": "播出节奏",
    "section.correction": "纠错与释放",
    "section.recognition": "识别策略",
    "section.custom": "自定义规则"
  },
  "zh-TW": {
    "config.changedCount": "{count} 項待儲存",
    "config.changes": "本次修改",
    "config.moreChanges": "另有 {count} 項",
    "config.save": "儲存修改",
    "config.close": "關閉",
    "config.cadence": "執行節奏",
    "config.generalInspection": "通用巡檢",
    "config.downloadInspection": "下載檢查",
    "config.metadataInspection": "元資料檢查",
    "config.bestVersionInspection": "洗版檢查",
    "config.everyMinutes": "每 {value} 分鐘",
    "config.everyHours": "每 {value} 小時",
    "config.notScheduled": "未設定",
    "config.activeDomains": "已啟用能力",
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
    "config.yamlTitle": "自訂識別規則",
    "config.runtime": "執行概況",
    "config.runtimeLoading": "正在讀取執行概況",
    "config.runtimeUnavailable": "執行概況暫不可用",
    "config.pendingCount": "待定訂閱",
    "config.monitoredCount": "下載任務",
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
    "section.pausedProbe": "暫停訂閱補搜",
    "section.bestVersionScope": "洗版範圍",
    "section.backfill": "轉換與回填",
    "section.guard": "守衛訊號",
    "section.cadence": "播出節奏",
    "section.correction": "修正與釋放",
    "section.recognition": "識別策略",
    "section.custom": "自訂規則"
  },
  "en-US": {
    "config.changedCount": "{count} to save",
    "config.changes": "Changes",
    "config.moreChanges": "{count} more",
    "config.save": "Save changes",
    "config.close": "Close",
    "config.cadence": "Run cadence",
    "config.generalInspection": "General inspection",
    "config.downloadInspection": "Download checks",
    "config.metadataInspection": "Metadata checks",
    "config.bestVersionInspection": "Best-version checks",
    "config.everyMinutes": "Every {value} min",
    "config.everyHours": "Every {value} hr",
    "config.notScheduled": "Not set",
    "config.activeDomains": "Active capabilities",
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
    "config.yamlTitle": "Custom recognition rules",
    "config.runtime": "Runtime summary",
    "config.runtimeLoading": "Loading runtime summary",
    "config.runtimeUnavailable": "Runtime summary unavailable",
    "config.pendingCount": "Pending subscriptions",
    "config.monitoredCount": "Downloads",
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
    "section.pausedProbe": "Paused subscription search",
    "section.bestVersionScope": "Best-version scope",
    "section.backfill": "Conversion and backfill",
    "section.guard": "Guard signals",
    "section.cadence": "Airing cadence",
    "section.correction": "Correction and release",
    "section.recognition": "Recognition policy",
    "section.custom": "Custom rules"
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
  completion: { tw: ["訂閱補全", "站點集數探測與暫停訂閱補搜"], en: ["Completion", "Site episode probes and paused subscription searches"] },
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
  delete_record_retention_hours: ["Removal history retention (hours)", "Periodically remove deletion records older than N hours"],
  subscription_cleanup_history_type: ["Cleanup media scope", "Media types whose old transfer records and files are removed before download"],
  subscription_cleanup_history_scenes: ["Cleanup trigger scenarios", "Choose which subscription download scenarios trigger cleanup"],
  recognition_guard_mode: ["Recognition mode", "Review whether a candidate matches the subscription target before automatic download"],
  recognition_guard_notify: ["Recognition notifications", "Control recognition messages without affecting audit logs"],
  recognition_guard_notify_interval: ["Notification rate limit (seconds)", "Minimum interval for the same subscription, action, and reason"],
  recognition_guard_tmdb_recheck_mode: ["Secondary recognition", "Control when secondary recognition is performed"],
  recognition_guard_cache_maxsize: ["Recognition cache size", "Cache secondary recognition results to avoid duplicate requests"],
  recognition_guard_custom_config: ["Custom recognition rules", "Edit only when built-in rules are insufficient; leave empty to inherit the current mode"],
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
    const hint = field.hint ? locale === "zh-CN" ? field.hint : locale === "zh-TW" ? field.key === "recognition_guard_custom_config" ? "僅在內建規則無法滿足時編輯，留空則繼承目前模式" : toTraditional(field.hint) : english[1] : void 0;
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

const unitLabels = {
  "zh-CN": {
    count: "次",
    day: "天",
    episode: "集",
    hour: "小时",
    item: "条",
    minute: "分钟",
    multiplier: "倍",
    percent: "%",
    round: "轮",
    second: "秒"
  },
  "zh-TW": {
    count: "次",
    day: "天",
    episode: "集",
    hour: "小時",
    item: "條",
    minute: "分鐘",
    multiplier: "倍",
    percent: "%",
    round: "輪",
    second: "秒"
  },
  "en-US": {
    count: "x",
    day: "d",
    episode: "ep",
    hour: "hr",
    item: "items",
    minute: "min",
    multiplier: "x",
    percent: "%",
    round: "rounds",
    second: "sec"
  }
};
function numberFieldUnit(key, locale = "zh-CN") {
  const units = unitLabels[locale];
  if (key === "cadence_min_episodes") return units.episode;
  if (key === "cadence_multiplier") return units.multiplier;
  if (key === "download_progress_threshold") return units.percent;
  if (key === "download_retry_limit") return units.count;
  if (key === "recognition_guard_cache_maxsize") return units.item;
  if (key === "recognition_guard_notify_interval") return units.second;
  if (key.endsWith("_minutes")) return units.minute;
  if (key.endsWith("_hours")) return units.hour;
  if (key.endsWith("_days")) return units.day;
  if (key.endsWith("_episodes")) return units.episode;
  return void 0;
}
function displayFieldLabel(field) {
  if (field.kind !== "number") return field.label;
  return field.label.replace(/\s*[（(][^）)]+[）)]\s*/g, "").trim();
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
const _hoisted_10 = { class: "sae-config__body" };
const _hoisted_11 = { class: "sae-config-layout" };
const _hoisted_12 = ["aria-label"];
const _hoisted_13 = { class: "sae-group-nav__heading" };
const _hoisted_14 = { class: "sae-field-surface" };
const _hoisted_15 = { class: "sae-field-surface__heading-copy" };
const _hoisted_16 = { class: "sae-field-surface__mobile-actions" };
const _hoisted_17 = { class: "sae-field-section__rows" };
const _hoisted_18 = { class: "sae-field-row__copy" };
const _hoisted_19 = { class: "sae-field-row__label" };
const _hoisted_20 = { key: 0 };
const _hoisted_21 = { class: "sae-field-control" };
const _hoisted_22 = {
  key: 0,
  class: "sae-select-summary__primary"
};
const _hoisted_23 = {
  key: 1,
  class: "sae-select-summary__count"
};
const _hoisted_24 = {
  key: 2,
  class: "sae-number-stepper"
};
const _hoisted_25 = {
  key: 0,
  class: "sae-number-stepper__unit"
};
const _hoisted_26 = {
  key: 0,
  class: "sae-field-section sae-tracker-entry"
};
const _hoisted_27 = { class: "sae-tracker-entry__copy" };
const _hoisted_28 = {
  key: 1,
  class: "sae-field-section sae-tracker-entry"
};
const _hoisted_29 = { class: "sae-tracker-entry__copy" };
const _hoisted_30 = { class: "sae-impact-preview" };
const _hoisted_31 = { class: "sae-impact-preview__title sae-summary-section__title" };
const _hoisted_32 = { class: "sae-impact-preview__list" };
const _hoisted_33 = {
  key: 0,
  class: "sae-change-summary"
};
const _hoisted_34 = { class: "sae-change-summary__title sae-summary-section__title" };
const _hoisted_35 = { key: 0 };
const _hoisted_36 = ["aria-label"];
const _hoisted_37 = { class: "sae-runtime-summary__title sae-summary-section__title" };
const _hoisted_38 = {
  key: 0,
  class: "sae-runtime-summary__state"
};
const _hoisted_39 = {
  key: 1,
  class: "sae-runtime-summary__metrics"
};
const _hoisted_40 = { class: "sae-runtime-summary__row" };
const _hoisted_41 = { class: "sae-runtime-summary__row" };
const _hoisted_42 = { class: "sae-runtime-summary__row" };
const _hoisted_43 = {
  key: 2,
  class: "sae-runtime-summary__unavailable"
};
const _hoisted_44 = {
  key: 0,
  class: "sae-mobile-save-dock"
};
const _hoisted_45 = { class: "sae-mobile-save-dock__state" };
const {computed,getCurrentInstance,onBeforeUnmount,onMounted,ref} = await importShared('vue');

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
    const { draft, changedCount, changedKeys, buildSavePayload } = useConfigDraft(props.initialConfig);
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
    const yamlField = computed(() => localizedFields.value.find(
      (field) => field.key === "recognition_guard_custom_config"
    ));
    const changedItems = computed(() => changedKeys.value.slice(0, 3).map((key) => localizedFields.value.find((field) => field.key === key)).filter((field) => Boolean(field)));
    const hiddenChangedCount = computed(() => Math.max(0, changedKeys.value.length - changedItems.value.length));
    const activeGroup = ref("global");
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
    let fieldScrollRoot = null;
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
    const activeGroupMeta = computed(
      () => localizedGroups.value.find((group) => group.key === activeGroup.value) ?? localizedGroups.value[0]
    );
    const activeSections = computed(
      () => sectionDefinitions[activeGroup.value].map((section) => ({
        ...section,
        title: t(locale.value, section.titleKey),
        fields: section.keys.map((key) => fieldsByKey.value.get(key)).filter((field) => Boolean(field) && field?.kind !== "textarea")
      })).filter((section) => section.fields.length > 0)
    );
    const cadenceSummary = computed(() => [
      {
        icon: "mdi-radar",
        title: t(locale.value, "config.generalInspection"),
        value: t(locale.value, "config.everyMinutes", { value: draft.auto_check_interval_minutes })
      },
      {
        icon: "mdi-download-network-outline",
        title: t(locale.value, "config.downloadInspection"),
        value: t(locale.value, "config.everyMinutes", { value: draft.download_check_interval_minutes })
      },
      {
        icon: "mdi-database-search-outline",
        title: t(locale.value, "config.metadataInspection"),
        value: t(locale.value, "config.everyHours", { value: draft.meta_check_interval_hours })
      },
      {
        icon: "mdi-auto-fix",
        title: t(locale.value, "config.bestVersionInspection"),
        value: draft.best_version_cron || t(locale.value, "config.notScheduled")
      }
    ]);
    const activeDomainCount = computed(() => {
      const values = Object.values(runtimeSummary.value?.domains ?? {});
      return {
        active: values.filter((value) => value === true || typeof value === "string" && !["off", "no"].includes(value)).length,
        total: values.length
      };
    });
    function handleConfigScroll(event) {
      const scrollRoot = event.currentTarget;
      if (!scrollRoot) return;
      scrollRoot.classList.add("sae-config-scroll-root--active");
      window.clearTimeout(scrollIdleTimer);
      scrollIdleTimer = window.setTimeout(() => {
        scrollRoot.classList.remove("sae-config-scroll-root--active");
      }, 600);
    }
    onMounted(() => {
      void loadSummary(props.api).then((payload) => {
        runtimeSummary.value = payload;
        summaryState.value = payload ? "available" : "unavailable";
      });
      const scrollRoot = configHeaderSentinel.value?.closest(".v-card-text") ?? null;
      configScrollRoot = scrollRoot;
      fieldScrollRoot = fieldSurfaceHeading.value?.closest(".sae-field-surface") ?? null;
      scrollRoot?.classList.add("sae-config-scroll-root");
      fieldScrollRoot?.classList.add("sae-config-scroll-root");
      scrollRoot?.addEventListener("scroll", handleConfigScroll, { passive: true });
      fieldScrollRoot?.addEventListener("scroll", handleConfigScroll, { passive: true });
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
      fieldScrollRoot?.removeEventListener("scroll", handleConfigScroll);
      configScrollRoot?.classList.remove("sae-config-scroll-root", "sae-config-scroll-root--active");
      fieldScrollRoot?.classList.remove("sae-config-scroll-root", "sae-config-scroll-root--active");
    });
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
      return numberFieldUnit(field.key, locale.value);
    }
    function selectionOverflowCount(key) {
      const value = draft[key];
      return Array.isArray(value) ? Math.max(0, value.length - 1) : 0;
    }
    function selectMobileGroup(group) {
      activeGroup.value = group;
      mobileGroupSheet.value = false;
    }
    function saveConfig() {
      emit("save", buildSavePayload());
    }
    return (_ctx, _cache) => {
      const _component_VIcon = _resolveComponent("VIcon");
      const _component_VChip = _resolveComponent("VChip");
      const _component_VBtn = _resolveComponent("VBtn");
      const _component_VListItem = _resolveComponent("VListItem");
      const _component_VList = _resolveComponent("VList");
      const _component_VTooltip = _resolveComponent("VTooltip");
      const _component_VSwitch = _resolveComponent("VSwitch");
      const _component_VSelect = _resolveComponent("VSelect");
      const _component_VTextField = _resolveComponent("VTextField");
      const _component_VCronField = _resolveComponent("VCronField");
      const _component_VProgressCircular = _resolveComponent("VProgressCircular");
      const _component_VSpacer = _resolveComponent("VSpacer");
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
                  color: "warning",
                  icon: "mdi-circle",
                  size: "8"
                }),
                _createTextVNode(" " + _toDisplayString(_unref(t)(locale.value, "config.changedCount", { count: _unref(changedCount) })), 1)
              ])) : _createCommentVNode("", true),
              _createVNode(_component_VBtn, {
                class: "sae-config-header__save",
                color: "primary",
                disabled: _unref(changedCount) === 0,
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
              }, 8, ["disabled"]),
              _createVNode(_component_VBtn, {
                "aria-label": _unref(t)(locale.value, "config.close"),
                class: "sae-config-header__close",
                icon: "",
                size: "small",
                variant: "text",
                onClick: _cache[0] || (_cache[0] = ($event) => emit("close"))
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_VIcon, { icon: "mdi-close" })
                ]),
                _: 1
              }, 8, ["aria-label"])
            ])
          ], 2),
          _createElementVNode("div", _hoisted_10, [
            _createElementVNode("div", _hoisted_11, [
              _createElementVNode("nav", {
                class: "sae-group-nav",
                "aria-label": _unref(t)(locale.value, "config.selectGroup")
              }, [
                _createElementVNode("div", _hoisted_13, _toDisplayString(_unref(t)(locale.value, "config.settings")), 1),
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
              ], 8, _hoisted_12),
              _createElementVNode("main", _hoisted_14, [
                _createElementVNode("div", {
                  ref_key: "fieldSurfaceHeading",
                  ref: fieldSurfaceHeading,
                  class: "sae-field-surface__heading"
                }, [
                  _createElementVNode("div", _hoisted_15, [
                    _createVNode(_component_VIcon, {
                      icon: activeGroupMeta.value.icon,
                      color: "primary",
                      size: "22"
                    }, null, 8, ["icon"]),
                    _createElementVNode("div", null, [
                      _createElementVNode("h2", null, _toDisplayString(activeGroupMeta.value.title), 1),
                      _createElementVNode("p", null, _toDisplayString(activeGroupMeta.value.summary), 1)
                    ])
                  ]),
                  _createElementVNode("div", _hoisted_16, [
                    _createVNode(_component_VBtn, {
                      "aria-expanded": mobileGroupSheet.value,
                      "aria-label": _unref(t)(locale.value, "config.selectGroup"),
                      "aria-haspopup": "dialog",
                      class: "sae-mobile-group-action",
                      icon: "",
                      size: "small",
                      type: "button",
                      variant: "tonal",
                      onClick: _cache[1] || (_cache[1] = ($event) => mobileGroupSheet.value = true)
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VIcon, {
                          icon: "mdi-view-list-outline",
                          size: "18"
                        }),
                        _createVNode(_component_VTooltip, {
                          activator: "parent",
                          text: _unref(t)(locale.value, "config.selectGroup")
                        }, null, 8, ["text"])
                      ]),
                      _: 1
                    }, 8, ["aria-expanded", "aria-label"]),
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
                  ])
                ], 512),
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
                            _createElementVNode("div", _hoisted_19, _toDisplayString(_unref(displayFieldLabel)(field)), 1),
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
                                  index === 0 ? (_openBlock(), _createElementBlock("span", _hoisted_22, _toDisplayString(item.title), 1)) : index === 1 ? (_openBlock(), _createElementBlock("span", _hoisted_23, " +" + _toDisplayString(selectionOverflowCount(field.key)), 1)) : _createCommentVNode("", true)
                                ]),
                                key: "0"
                              } : void 0
                            ]), 1032, ["modelValue", "onUpdate:modelValue", "aria-label", "items", "multiple"])) : field.kind === "number" ? (_openBlock(), _createElementBlock("div", _hoisted_24, [
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
                              fieldUnit(field) ? (_openBlock(), _createElementBlock("span", _hoisted_25, _toDisplayString(fieldUnit(field)), 1)) : _createCommentVNode("", true)
                            ])) : field.kind === "cron" ? (_openBlock(), _createBlock(_component_VCronField, {
                              key: 3,
                              modelValue: _unref(draft)[field.key],
                              "onUpdate:modelValue": ($event) => _unref(draft)[field.key] = $event,
                              "aria-label": field.label,
                              class: "sae-text-control",
                              clearable: false,
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
                              class: "sae-text-control",
                              density: "compact",
                              "hide-details": "",
                              variant: "outlined"
                            }, null, 8, ["id", "modelValue", "onUpdate:modelValue", "aria-label"])) : _createCommentVNode("", true)
                          ])
                        ], 2);
                      }), 128))
                    ])
                  ]);
                }), 128)),
                activeGroup.value === "cleanup" ? (_openBlock(), _createElementBlock("section", _hoisted_26, [
                  _createElementVNode("div", _hoisted_27, [
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
                    onClick: _cache[2] || (_cache[2] = ($event) => trackerDialogOpen.value = true)
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.edit")), 1)
                    ]),
                    _: 1
                  }, 8, ["aria-label"])
                ])) : _createCommentVNode("", true),
                activeGroup.value === "recognition" ? (_openBlock(), _createElementBlock("section", _hoisted_28, [
                  _createElementVNode("div", _hoisted_29, [
                    _createVNode(_component_VIcon, {
                      color: "primary",
                      icon: "mdi-code-braces",
                      size: "22"
                    }),
                    _createElementVNode("div", null, [
                      _createElementVNode("strong", null, _toDisplayString(yamlField.value.label), 1),
                      _createElementVNode("p", null, _toDisplayString(yamlField.value.hint), 1)
                    ])
                  ]),
                  _createVNode(_component_VBtn, {
                    "aria-label": _unref(t)(locale.value, "config.editLabel", { label: yamlField.value.label }),
                    color: "primary",
                    "prepend-icon": "mdi-pencil-outline",
                    type: "button",
                    variant: "tonal",
                    onClick: _cache[3] || (_cache[3] = ($event) => yamlDialogOpen.value = true)
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(_unref(t)(locale.value, "config.edit")), 1)
                    ]),
                    _: 1
                  }, 8, ["aria-label"])
                ])) : _createCommentVNode("", true)
              ]),
              _createElementVNode("aside", _hoisted_30, [
                _createElementVNode("div", _hoisted_31, [
                  _createVNode(_component_VIcon, {
                    color: "primary",
                    icon: "mdi-clock-outline",
                    size: "20"
                  }),
                  _createElementVNode("h2", null, _toDisplayString(_unref(t)(locale.value, "config.cadence")), 1)
                ]),
                _createElementVNode("ul", _hoisted_32, [
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(cadenceSummary.value, (item) => {
                    return _openBlock(), _createElementBlock("li", {
                      key: item.title,
                      class: "sae-impact-preview__item"
                    }, [
                      _createVNode(_component_VIcon, {
                        icon: item.icon,
                        size: "18"
                      }, null, 8, ["icon"]),
                      _createElementVNode("span", null, _toDisplayString(item.title), 1),
                      _createElementVNode("strong", null, _toDisplayString(item.value), 1)
                    ]);
                  }), 128))
                ]),
                changedItems.value.length ? (_openBlock(), _createElementBlock("section", _hoisted_33, [
                  _createElementVNode("div", _hoisted_34, [
                    _createVNode(_component_VIcon, {
                      color: "warning",
                      icon: "mdi-format-list-checks",
                      size: "19"
                    }),
                    _createElementVNode("h3", null, _toDisplayString(_unref(t)(locale.value, "config.changes")), 1)
                  ]),
                  _createElementVNode("ul", null, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(changedItems.value, (item) => {
                      return _openBlock(), _createElementBlock("li", {
                        key: item.key
                      }, [
                        _createVNode(_component_VIcon, {
                          color: "warning",
                          icon: "mdi-circle",
                          size: "6"
                        }),
                        _createElementVNode("span", null, _toDisplayString(_unref(displayFieldLabel)(item)), 1)
                      ]);
                    }), 128))
                  ]),
                  hiddenChangedCount.value > 0 ? (_openBlock(), _createElementBlock("p", _hoisted_35, _toDisplayString(_unref(t)(locale.value, "config.moreChanges", { count: hiddenChangedCount.value })), 1)) : _createCommentVNode("", true)
                ])) : _createCommentVNode("", true),
                _createElementVNode("section", {
                  "aria-label": _unref(t)(locale.value, "config.runtime"),
                  class: "sae-runtime-summary"
                }, [
                  _createElementVNode("div", _hoisted_37, [
                    _createVNode(_component_VIcon, {
                      color: "primary",
                      icon: "mdi-chart-box-outline",
                      size: "19"
                    }),
                    _createElementVNode("h3", null, _toDisplayString(_unref(t)(locale.value, "config.runtime")), 1)
                  ]),
                  summaryState.value === "loading" ? (_openBlock(), _createElementBlock("div", _hoisted_38, [
                    _createVNode(_component_VProgressCircular, {
                      color: "primary",
                      indeterminate: "",
                      size: "18",
                      width: "2"
                    }),
                    _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.runtimeLoading")), 1)
                  ])) : summaryState.value === "available" && runtimeSummary.value ? (_openBlock(), _createElementBlock("div", _hoisted_39, [
                    _createElementVNode("div", _hoisted_40, [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-timer-sand",
                        size: "18"
                      }),
                      _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.pendingCount")), 1),
                      _createElementVNode("strong", null, _toDisplayString(runtimeSummary.value.pending_count), 1)
                    ]),
                    _createElementVNode("div", _hoisted_41, [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-download-network-outline",
                        size: "18"
                      }),
                      _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.monitoredCount")), 1),
                      _createElementVNode("strong", null, _toDisplayString(runtimeSummary.value.monitored_torrents), 1)
                    ]),
                    _createElementVNode("div", _hoisted_42, [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-toggle-switch-outline",
                        size: "18"
                      }),
                      _createElementVNode("span", null, _toDisplayString(_unref(t)(locale.value, "config.activeDomains")), 1),
                      _createElementVNode("strong", null, _toDisplayString(activeDomainCount.value.active) + " / " + _toDisplayString(activeDomainCount.value.total), 1)
                    ])
                  ])) : (_openBlock(), _createElementBlock("p", _hoisted_43, _toDisplayString(_unref(t)(locale.value, "config.runtimeUnavailable")), 1))
                ], 8, _hoisted_36)
              ])
            ])
          ]),
          _unref(changedCount) > 0 ? (_openBlock(), _createElementBlock("div", _hoisted_44, [
            _createElementVNode("span", _hoisted_45, [
              _createVNode(_component_VIcon, {
                color: "warning",
                icon: "mdi-circle",
                size: "8"
              }),
              _createTextVNode(" " + _toDisplayString(_unref(t)(locale.value, "config.changedCount", { count: _unref(changedCount) })), 1)
            ]),
            _createVNode(_component_VSpacer),
            _createVNode(_component_VBtn, {
              class: "sae-mobile-save-dock__save",
              color: "primary",
              disabled: _unref(changedCount) === 0,
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
            }, 8, ["disabled"])
          ])) : _createCommentVNode("", true)
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

const Config = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-4690db6a"]]);

export { Config as default };
