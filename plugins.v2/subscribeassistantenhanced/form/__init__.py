"""配置表单（vuetify 模式）：顶部开关行 + 周期行 + 7 个 Tab 分页 + 底部提示。

设计：表单字段名 == PluginConfig 配置键，model 默认值由 PluginConfig.defaults() 派生，避免保存配置与运行时键漂移。
conf 结构：[switch_row, period_row, VTabs, VWindow, *footer]，VTabs/VWindow 共用 model "_tab" 联动当前页；
每个字段挂常驻 hint（LABELS/HINTS 双表维护），Tab 内按行列布局排列，底部三条 VAlert 给出指引与风险提示。
"""
from ..shared.config import PluginConfig
from .components import (ace_editor_field, alert_row, cron_field, field_for, multi_select_field,
                         select_field, switch_col, tabs, textarea_field)

# 各配置键的中文显示名（与 README 配置项名保持一致）
LABELS = {
    # 全局开关与运行
    "enabled": "启用插件",
    "notify": "发送通知",
    "reset_task": "重置数据",
    "onlyonce": "立即运行一次",
    # 周期
    "download_check_interval_minutes": "下载检查周期（分钟）",
    "meta_check_interval_hours": "元数据检查周期（小时）",
    "best_version_cron": "洗版检查周期",
    # 订阅清理
    "download_monitor_enabled": "下载超时自动删除",
    "manual_delete_listen": "监听手动删除种子",
    "tracker_response_listen": "监听Tracker响应关键字",
    "auto_search_when_delete": "删除后触发搜索补全",
    "skip_deletion": "跳过近期删除资源",
    "download_timeout_minutes": "下载超时时间（分钟）",
    "download_progress_threshold": "下载超时进度阈值",
    "download_retry_limit": "下载连续超时重试次数",
    "delete_record_retention_hours": "删除记录保留（小时）",
    "delete_exclude_tags": "排除标签",
    "default_tracker_response": "Tracker响应关键字",
    "open_tracker_dialog": "打开Tracker配置窗口",
    "auto_check_interval_minutes": "通用巡检周期（分钟）",
    "subscription_cleanup_history_type": "清理整理记录范围",
    "subscription_cleanup_history_scenes": "清理整理记录场景",
    # 识别增强
    "recognition_guard_mode": "识别增强模式",
    "recognition_guard_notify": "识别增强通知",
    "recognition_guard_notify_interval": "识别增强通知限频（秒）",
    "recognition_guard_tmdb_recheck_mode": "识别增强二次识别",
    "recognition_guard_cache_maxsize": "识别增强缓存大小",
    "recognition_guard_custom_config": "识别增强自定义策略",
    # 订阅待定
    "pending_enhanced_enabled": "自动待定剧集订阅",
    "pending_download_enabled": "自动待定下载中订阅",
    "auto_tv_pending_days": "剧集待定天数",
    "auto_tv_pending_episodes": "剧集待定集数",
    "pending_use_volatility": "待定参考变更速率",
    # 订阅暂停
    "pause_enhanced_enabled": "自动暂停订阅",
    "auto_pause_users": "自动暂停新增订阅的用户（逗号分隔）",
    "airing_pause_days": "即将播出暂停天数",
    "tv_air_pause_days": "剧集上映暂停天数",
    "movie_air_pause_days": "电影上映暂停天数",
    "tv_no_download_days": "剧集无下载处理天数",
    "movie_no_download_days": "电影无下载处理天数",
    "no_download_actions": "无下载处理策略",
    # 订阅补全
    "paused_probe_reasons": "暂停订阅补搜场景",
    "paused_probe_min_pause_days": "暂停满N天后补搜",
    "paused_probe_interval_hours": "补搜间隔（小时）",
    "site_total_probe_enabled": "站点集数探测",
    "progress_diagnostic_mode": "无进展诊断模式",
    "progress_diagnostic_stalled_rounds": "连续无进展轮数",
    "progress_diagnostic_cooldown_hours": "诊断冷却（小时）",
    # 订阅洗版
    "best_version_type": "洗版类型",
    "best_version_episode_to_full": "分集转全集",
    "best_version_backfill_enabled": "回填已存在集",
    "backfill_best_version_now": "立即扫描存量并回填",
    "best_version_movie_remaining_days": "电影洗版时限（天）",
    "best_version_tv_remaining_days": "剧集洗版时限（天）",
    # 完结信号
    "completion_guard_mode": "完结守卫模式",
    "site_completion_evidence_enabled": "站点完结信号",
    "volatility_enabled": "变更速率信号",
    "volatility_window_days": "变更速率窗口（天）",
    "cadence_enabled": "播出节奏信号",
    "cadence_multiplier": "节奏窗口系数",
    "cadence_min_window_days": "节奏窗口下限（天）",
    "cadence_min_episodes": "节奏参与最少集数",
    "season_cooldown_days": "季冷却期（天）",
    "verify_enabled": "自动纠错",
    "verify_interval_hours": "自动纠错间隔（小时）",
    "verify_retention_days": "快照保留（天）",
    "timeout_release_days": "完成前观察天数",
    "timeout_cadence_acceleration": "按节奏加速释放",
}

# 各配置键的常驻说明，缺省键不显示说明行。
HINTS = {
    # 全局开关与运行
    "enabled": "开启后插件将处于激活状态",
    "notify": "是否在特定事件发生时发送通知",
    "reset_task": "将重置所有待定/暂停/监控等任务数据，执行后自动复位",
    "onlyonce": "保存后立即运行一次全量巡检，执行后自动复位",
    # 周期
    "auto_check_interval_minutes": "站点采样、待定释放、无下载处理和清理周期",
    "download_check_interval_minutes": "下载检查的周期，定时检查下载任务状态",
    "meta_check_interval_hours": "元数据检查的周期，定时复核订阅元数据状态",
    "best_version_cron": "洗版检查的周期，如 0 15 * * *",
    # 订阅清理
    "download_monitor_enabled": "订阅下载超时将自动删除种子",
    "manual_delete_listen": "监听用户手动删除的种子记录",
    "tracker_response_listen": "命中Tracker响应关键字时将自动删除种子",
    "auto_search_when_delete": "删种后将自动触发搜索补全",
    "skip_deletion": "跳过最近删除的种子，避免再次下载",
    "download_timeout_minutes": "作为下载进度观察窗口，窗口内进度增长低于阈值时视为超时",
    "download_progress_threshold": "超时窗口内下载进度增长低于N%时才删除",
    "download_retry_limit": "连续低进度超时N次后保留种子并通知",
    "delete_record_retention_hours": "定时清理N小时前的删除记录",
    "delete_exclude_tags": "需要排除的标签，多个标签用逗号分隔",
    "default_tracker_response": "每一行一个关键字，忽略大小写，支持正则表达式匹配",
    "open_tracker_dialog": "自定义Tracker配置以实现更精准的种子匹配",
    "subscription_cleanup_history_type": "订阅下载前清理旧整理记录、源文件和入库前目标文件的媒体类型范围（破坏性）",
    "subscription_cleanup_history_scenes": "选择普通订阅、洗版订阅或分集洗版下载时触发订阅清理",
    # 识别增强
    "recognition_guard_mode": "在自动下载前复核订阅候选是否像当前订阅目标",
    "recognition_guard_notify": "控制识别增强消息推送，不影响审计日志",
    "recognition_guard_notify_interval": "同订阅同动作同原因的通知限频秒数",
    "recognition_guard_tmdb_recheck_mode": "控制二次识别触发范围",
    "recognition_guard_cache_maxsize": "缓存二次识别结果，避免重复识别",
    "recognition_guard_custom_config": "YAML 策略覆盖；清空表示无自定义覆盖",
    # 订阅待定
    "pending_enhanced_enabled": "自动标记订阅剧集为待定状态，避免提前完成订阅",
    "pending_download_enabled": "存在进行中下载时自动标记待定，避免提前完成订阅",
    "auto_tv_pending_days": "当前日期小于上映日期加N天，则视为待定，为0时不处理",
    "auto_tv_pending_episodes": "剧集数小于等于设置的集数，则视为待定，为0时不处理",
    "pending_use_volatility": "接近完结且总集数变化时提前待定",
    # 订阅暂停
    "pause_enhanced_enabled": "自动标记订阅为暂停状态，避免无意义的请求",
    "auto_pause_users": "名单内用户新增订阅时将自动暂停，多个用户用逗号分隔，为空时不启用",
    "airing_pause_days": "已存在最新播出集，且下集距当前日期大于N天，则视为暂停，为0时不处理",
    "tv_air_pause_days": "当前日期小于开播日期减N天，则视为暂停，为0时不处理",
    "movie_air_pause_days": "当前日期小于上映日期减N天，则视为暂停，为0时不处理",
    "tv_no_download_days": "剧集上映后N天内无新的订阅下载，则按策略处理，为0时不处理",
    "movie_no_download_days": "电影上映后N天内无新的订阅下载，则按策略处理，为0时不处理",
    "no_download_actions": "选择无下载时的处理策略",
    # 订阅补全
    "paused_probe_reasons": "选择允许低频补搜的暂停原因",
    "paused_probe_min_pause_days": "暂停达到天数后开始补搜，0 表示不处理",
    "paused_probe_interval_hours": "同一订阅两次补搜的最小间隔",
    "site_total_probe_enabled": "用站点缓存资源辅助发现目标集数不足",
    "progress_diagnostic_mode": "订阅长期无进展时的诊断处理方式",
    "progress_diagnostic_stalled_rounds": "连续无进展多少轮后处理，0 表示不处理",
    "progress_diagnostic_cooldown_hours": "同一订阅诊断提醒的最小间隔",
    # 订阅洗版
    "best_version_type": "选择需要自动洗版的类型，关闭时不自动创建和巡检洗版订阅",
    "best_version_episode_to_full": "订阅目标集数满足时，从分集洗版切换为全集洗版",
    "best_version_backfill_enabled": "新建或转分集洗版时回填媒体库已有集，避免重复下载",
    "backfill_best_version_now": "保存后对存量分集洗版订阅执行一次回填，执行后自动复位",
    "best_version_movie_remaining_days": "电影洗版订阅达到指定天数后自动终止，有下载则按最新时间计算，为0时不限",
    "best_version_tv_remaining_days": "剧集洗版订阅达到指定天数后自动终止，有下载则按最新时间计算，为0时不限",
    # 完结信号
    "completion_guard_mode": "选择完成前复核强度，默认使用平衡策略",
    "site_completion_evidence_enabled": "使用站点资源标题佐证完结信号",
    "volatility_enabled": "总集数近期变化时视为不稳定",
    "volatility_window_days": "统计总集数变化的天数，越长越保守",
    "cadence_enabled": "按已播间隔判断等待期，不会直接判定完结",
    "cadence_multiplier": "放大预计等待时间，数值越大等待越久",
    "cadence_min_window_days": "预计等待时间不得少于设置天数",
    "cadence_min_episodes": "已播集数达到设置值后才计算播出间隔",
    "season_cooldown_days": "最后一集播出后继续观察的天数",
    "verify_enabled": "完成后检查集数，增加时自动重建订阅",
    "verify_interval_hours": "完成后重新检查集数的间隔",
    "verify_retention_days": "完成快照按设置天数保留并自动清理，默认180天",
    "timeout_release_days": "完成前观察允许保留的最长天数",
    "timeout_cadence_acceleration": "等待期结束时缩短观察期限",
}

TOP_SWITCHES = ["enabled", "notify", "reset_task", "onlyonce"]

PERIODS = [
    "auto_check_interval_minutes",
    "download_check_interval_minutes",
    "meta_check_interval_hours",
    "best_version_cron",
]

# 各 Tab 的字段布局：标题 → 行列表，每行从左到右为该行字段键；
# 默认每列 md=4（一行三列），需特殊列宽时写成 (字段键, md)。
TABS = [
    ("订阅清理", [
        ["download_monitor_enabled", "manual_delete_listen", "tracker_response_listen"],
        ["open_tracker_dialog", "auto_search_when_delete", "skip_deletion"],
        [("subscription_cleanup_history_type", 4), ("subscription_cleanup_history_scenes", 8)],
        ["download_timeout_minutes", "download_progress_threshold", "download_retry_limit"],
        ["delete_record_retention_hours", "delete_exclude_tags"],
    ]),
    ("订阅待定", [
        [("pending_download_enabled", 4), ("pending_enhanced_enabled", 4), ("pending_use_volatility", 4)],
        [("auto_tv_pending_days", 6), ("auto_tv_pending_episodes", 6)],
    ]),
    ("订阅暂停", [
        [("pause_enhanced_enabled", 4), ("auto_pause_users", 8)],
        ["movie_air_pause_days", "tv_air_pause_days", "airing_pause_days"],
        ["movie_no_download_days", "tv_no_download_days", "no_download_actions"],
    ]),
    ("订阅补全", [
        [("site_total_probe_enabled", 12)],
        ["progress_diagnostic_mode", "progress_diagnostic_stalled_rounds", "progress_diagnostic_cooldown_hours"],
        ["paused_probe_reasons", "paused_probe_min_pause_days", "paused_probe_interval_hours"],
    ]),
    ("订阅洗版", [
        ["best_version_type", "best_version_movie_remaining_days", "best_version_tv_remaining_days"],
        ["best_version_episode_to_full", "best_version_backfill_enabled", "backfill_best_version_now"],
    ]),
    ("完结信号", [
        ["verify_enabled", "site_completion_evidence_enabled", "volatility_enabled"],
        ["cadence_enabled", "timeout_cadence_acceleration", "completion_guard_mode"],
        ["volatility_window_days", "cadence_multiplier", "cadence_min_window_days"],
        ["cadence_min_episodes", "season_cooldown_days", "verify_interval_hours"],
        ["verify_retention_days", "timeout_release_days"],
    ]),
    ("识别增强", [
        ["recognition_guard_mode", "recognition_guard_notify", "recognition_guard_notify_interval"],
        ["recognition_guard_tmdb_recheck_mode", "recognition_guard_cache_maxsize"],
        [("recognition_guard_custom_config", 12)],
    ]),
]

# 下载检查需要分钟级响应，保留 5 分钟起步的高频选项。
_MINUTE_INTERVAL_ITEMS = [
    {"title": "5分钟", "value": 5},
    {"title": "10分钟", "value": 10},
    {"title": "15分钟", "value": 15},
    {"title": "30分钟", "value": 30},
    {"title": "60分钟", "value": 60},
    {"title": "120分钟", "value": 120},
]

# 通用巡检承载站点证据采样与本地生命周期巡检，保留高频选项给追更敏感场景按需调整。
_COMMON_INTERVAL_ITEMS = [
    {"title": "10分钟", "value": 10},
    {"title": "20分钟", "value": 20},
    {"title": "30分钟", "value": 30},
    {"title": "60分钟", "value": 60},
    {"title": "120分钟", "value": 120},
    {"title": "240分钟", "value": 240},
]

# 固定枚举选择项（非布尔/字符串/数值，需限定候选集的字段）
SELECT_ITEMS = {
    "completion_guard_mode": [
        {"title": "关闭", "value": "off"},
        {"title": "严格", "value": "strict"},
        {"title": "平衡", "value": "balanced"},
        {"title": "宽松", "value": "loose"},
    ],
    "download_check_interval_minutes": _MINUTE_INTERVAL_ITEMS,
    "auto_check_interval_minutes": _COMMON_INTERVAL_ITEMS,
    "meta_check_interval_hours": [
        {"title": "1小时", "value": 1},
        {"title": "3小时", "value": 3},
        {"title": "6小时", "value": 6},
        {"title": "12小时", "value": 12},
        {"title": "24小时", "value": 24},
    ],
    "paused_probe_interval_hours": [
        {"title": "24", "value": 24},
        {"title": "48", "value": 48},
        {"title": "72", "value": 72},
        {"title": "96", "value": 96},
        {"title": "120", "value": 120},
        {"title": "144", "value": 144},
    ],
    "progress_diagnostic_mode": [
        {"title": "关闭", "value": "off"},
        {"title": "仅通知", "value": "notify"},
    ],
    "best_version_type": [
        {"title": "关闭", "value": "no"},
        {"title": "全部", "value": "all"},
        {"title": "电影", "value": "movie"},
        {"title": "剧集", "value": "tv"},
        {"title": "剧集（分集下载）", "value": "tv_episode"},
    ],
    "subscription_cleanup_history_type": [
        {"title": "关闭", "value": "no"},
        {"title": "全部", "value": "all"},
        {"title": "电影", "value": "movie"},
        {"title": "剧集", "value": "tv"},
    ],
    "recognition_guard_mode": [
        {"title": "关闭", "value": "off"},
        {"title": "审计", "value": "audit"},
        {"title": "宽松", "value": "loose"},
        {"title": "平衡", "value": "balanced"},
        {"title": "严格", "value": "strict"},
    ],
    "recognition_guard_notify": [
        {"title": "关闭", "value": "off"},
        {"title": "摘要", "value": "summary"},
        {"title": "明细", "value": "detail"},
        {"title": "全部", "value": "all"},
    ],
    "recognition_guard_tmdb_recheck_mode": [
        {"title": "关闭", "value": "off"},
        {"title": "全部", "value": "all"},
        {"title": "严格", "value": "strict"},
        {"title": "平衡和严格", "value": "balanced_strict"},
    ],
}

# 多选枚举字段（chips 展示）
MULTI_ITEMS = {
    "subscription_cleanup_history_scenes": [
        {"title": "普通订阅", "value": "normal"},
        {"title": "洗版订阅", "value": "best_version"},
        {"title": "分集洗版", "value": "best_version_episode"},
    ],
    "no_download_actions": [
        {"title": "暂停电影订阅", "value": "pause_movie"},
        {"title": "暂停剧集订阅", "value": "pause_tv"},
        {"title": "完成电影订阅", "value": "complete_movie"},
        {"title": "完成剧集订阅", "value": "complete_tv"},
        {"title": "删除电影订阅", "value": "delete_movie"},
        {"title": "删除剧集订阅", "value": "delete_tv"},
    ],
    "paused_probe_reasons": [
        {"title": "无下载", "value": "no_download"},
        {"title": "上映/开播", "value": "pre_air"},
        {"title": "播出间隔", "value": "airing_gap"},
        {"title": "用户名", "value": "auto_user"},
        {"title": "外部暂停", "value": "external"},
        {"title": "全部", "value": "all"},
    ],
}


# 插件 README（底部「详细说明」指引指向插件市场仓库内的独立文档）
README_URL = ("https://github.com/InfinityPacer/MoviePilot-Plugins/"
              "blob/main/plugins.v2/subscribeassistantenhanced/README.md")
# Tab 内字段默认列宽：md=4 即一行三列
FIELD_MD = 4

# 按 cron 表达式调度的字段，表单用 VCronField 而非数值框
CRON_FIELDS = {"best_version_cron"}


def _field(key: str, defaults: dict, md: int = FIELD_MD) -> dict:
    """按字段类型选择控件：cron 字段走 cron_field，多选枚举走 multi_select_field，固定枚举走 select_field，其余交 field_for 按默认值类型分发。

    field_for 按默认值类型出控件（bool→开关、str→文本、数值→数值框），故同一行可混排开关与输入；md 为该列宽度。
    """
    label = LABELS.get(key, key)
    hint = HINTS.get(key, "")
    if key in CRON_FIELDS:
        return cron_field(key, label, hint, md)
    if key in MULTI_ITEMS:
        return multi_select_field(key, label, MULTI_ITEMS[key], hint, md)
    if key in SELECT_ITEMS:
        return select_field(key, label, SELECT_ITEMS[key], hint, md)
    if key == "recognition_guard_custom_config":
        return ace_editor_field(key, label, hint, md)
    return field_for(key, label, defaults.get(key), hint, md)


def _row(cols: list) -> dict:
    """把若干字段列包成一个 VRow。"""
    return {"component": "VRow", "content": cols}


def _tracker_dialog() -> dict:
    """「打开Tracker配置窗口」开关弹出的 Tracker 配置弹窗，内含多行关键字文本框（每行一个，支持正则）。

    Tracker 关键字不内联在表单，而是放进 open_tracker_dialog 控制的弹窗里。
    """
    key = "default_tracker_response"
    return {
        "component": "VDialog",
        "props": {
            "model": "open_tracker_dialog",
            "max-width": "65rem",
            "overlay-class": "v-dialog--scrollable v-overlay--scroll-blocked",
            "content-class": "v-card v-card--density-default v-card--variant-elevated rounded-t",
        },
        "content": [{
            "component": "VCard",
            "props": {"title": "自定义Tracker配置"},
            "content": [
                {"component": "VDialogCloseBtn", "props": {"model": "open_tracker_dialog"}},
                {"component": "VCardText", "content": [
                    {"component": "VRow", "content": [
                        textarea_field(key, LABELS.get(key, key), HINTS.get(key, ""), md=12, rows=10),
                    ]},
                ]},
            ],
        }],
    }


def _tab_windows(defaults: dict) -> list:
    """按 TABS 的行布局构建各 Tab 页：每个 Tab 是若干 VRow，行内列顺序即字段顺序。

    行内每项为字段键，或 (字段键, md) 指定该列宽度，缺省 md 为 FIELD_MD；
    「订阅清理」页额外挂一个由 open_tracker_dialog 控制的 Tracker 关键字弹窗。
    """
    windows = []
    for title, rows in TABS:
        win_rows = []
        for row in rows:
            cols = []
            for item in row:
                key, md = item if isinstance(item, tuple) else (item, FIELD_MD)
                cols.append(_field(key, defaults, md))
            win_rows.append(_row(cols))
        if title == "订阅清理":
            win_rows.append(_tracker_dialog())
        windows.append(win_rows)
    return windows


def _footer() -> list:
    """底部提示区：README 指引、数据源说明与破坏性风险警告。"""
    return [
        alert_row("success", text="注意：详细使用说明与配置释义请参考：", content=[
            {"component": "a",
             "props": {"href": README_URL, "target": "_blank"},
             "content": [{"component": "u", "text": "README"}]},
        ], margin_top="12px"),
        alert_row("info", text="注意：本插件仅支持 TMDB 数据源，订阅状态相关说明请查阅 ", content=[
            {"component": "a",
             "props": {"href": "https://github.com/jxxghp/MoviePilot/pull/3330", "target": "_blank"},
             "content": [{"component": "u", "text": "#3330"}]},
            {"component": "span", "text": "、"},
            {"component": "a",
             "props": {"href": "https://github.com/jxxghp/MoviePilot-Frontend/pull/477", "target": "_blank"},
             "content": [{"component": "u", "text": "#477"}]},
            {"component": "span", "text": "、"},
            {"component": "a",
             "props": {"href": "https://github.com/jxxghp/MoviePilot/pull/6015", "target": "_blank"},
             "content": [{"component": "u", "text": "#6015"}]},
        ]),
        alert_row("error", text="注意：本插件可能导致订阅数据异常、媒体文件丢失，相关风险请自行评估与承担"),
    ]


def build_form():
    """聚合表单：顶部开关行 + 周期行 + 7 个 Tab + 底部提示；model 为全部配置键默认值。"""
    defaults = PluginConfig.defaults()
    beta_alert = alert_row(
        "warning",
        text="BETA 版本提示：本插件仍处于测试阶段，可能调整订阅状态、洗版记录、下载任务和媒体文件。"
    )
    # 顶部一行：4 个全局开关（一行铺满 4 列）
    switch_row = _row([switch_col(k, LABELS.get(k, k), HINTS.get(k, ""), md=3)
                       for k in TOP_SWITCHES])
    # 第二行：4 个公共周期配置（下载/元数据/通用巡检用下拉，洗版用 cron）
    period_row = _row([_field(k, defaults, md=3) for k in PERIODS])
    titles = [t for t, _ in TABS]
    windows = _tab_windows(defaults)
    conf = [beta_alert, switch_row, period_row, *tabs(titles, windows), *_footer()]
    return conf, dict(defaults)
