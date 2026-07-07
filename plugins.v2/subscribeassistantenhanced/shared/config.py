"""插件配置解析器，统一类型转换和默认值。"""


# Tracker 默认关键字覆盖常见无效种子响应，避免空配置时监听开关没有实际匹配能力。
DEFAULT_TRACKER_RESPONSE = """torrent not registered with this tracker
torrent banned"""

# 自动删种默认跳过 H&R 标签，避免误删需要长期做种的任务。
DEFAULT_DELETE_EXCLUDE_TAGS = "H&R"

DEFAULT_VOLATILITY_WINDOW_DAYS = 3

DEFAULT_RECOGNITION_GUARD_CUSTOM_CONFIG = """####### 配置说明 BEGIN #######
# 1. 本配置只控制识别增强的策略覆盖和关键词，不控制通知、二次识别触发或缓存大小。
# 2. 未配置或保持注释的项目均继承 recognition_guard_mode 当前模板。
# 3. actions 的值可选：inherit / observe / soft_block / block：
#    - inherit：继承当前 recognition_guard_mode 模板，不单独覆盖。
#    - observe：只记录审计和可选通知，不移除候选，下载选择不受影响。
#    - soft_block：先从候选池移除；如果整轮候选被清空，且 empty_pool 策略允许，该候选可降级为 observe 恢复。
#    - block：从候选池移除，集合级保护也不得恢复；用于用户明确不想下载的风险。
# 4. allow 只能抵消非 hard veto 风险；不能覆盖显式 ID 错配、明确类型/形态互串、目标范围完全不覆盖等 hard veto。
# 5. block 是普通黑名单风险，动作由 mode 或 actions.user_block 决定；hard_block 才是一律强拦截。
# 6. 正则使用 Python re 语法；非法正则会跳过对应条目并记录配置告警，不影响其他规则。
# 7. keywords 下的内置证据词分组如果取消注释配置，表示替换该分组；未配置的分组继续使用内置默认。
####### 配置说明 END #######

actions:
  # 候选缺少年份。多站点用户可改为 block，少站点用户建议 inherit 或 observe。
  # missing_year: block

  # 候选全集范围明显大于目标窗口，例如目标缺 E08-E19，候选是全 60 集。
  # target_range_oversized: block

  # 命中 keywords.block 时的动作。
  # user_block: soft_block

  # 二次识别结果与订阅目标不一致。
  # secondary_identity_conflict: block

empty_pool:
  # 整轮候选被识别增强清空时的恢复策略：recover_soft_block / never_recover。
  # policy: recover_soft_block

  # 即使动作是 soft_block，也不允许因整轮候选清空而恢复的原因码。
  # non_recoverable_codes:
  #   - target_range_oversized
  #   - missing_year

keywords:
  # 白名单：只抵消非 hard veto 风险。
  # allow:
  #   - 官方合集

  # 普通黑名单：动作由 mode 或 actions.user_block 决定。
  # block:
  #   - 低可信风险词

  # 强黑名单：所有启用模式下 hard veto；audit 只记录 would block。
  # hard_block:
  #   - 强制错误词

  # 以下是内置证据词分组；如需覆盖某一组，取消注释并完整写出该组。
  # live_action:
  #   - 真人版
  #   - 电视剧版
  #   - 实拍版
  #   - 真人剧
  # animation:
  #   - 动画
  #   - 动漫
  #   - 国漫
  #   - 番剧
  # movie:
  #   - 电影版
  #   - 剧场版
  #   - 劇場版
  #   - '\\bMovie\\b'
  # tv:
  #   - '\\bS\\d{1,3}(?:E\\d{1,4})?\\b'
  #   - '第\\s*\\d+\\s*[集季]'
  #   - '全\\s*\\d+\\s*集'
"""


class PluginConfig:
    """所有配置项属性化访问，类型安全，缺失 key 走默认值。"""

    def __init__(self, raw: dict):
        self._raw = raw or {}
        self._recognition_guard_config_warnings: set[str] = set()

    def get_bool(self, key: str, default: bool = False) -> bool:
        """布尔值解析：支持 bool / 字符串 true/false/on/off/yes/no/1/0。"""
        val = self._raw.get(key)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() in ("true", "on", "yes", "1", "guard")
        return bool(val)

    def get_int(self, key: str, default: int = 0) -> int:
        val = self._raw.get(key)
        if val is None:
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        val = self._raw.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def get_str(self, key: str, default: str = "") -> str:
        val = self._raw.get(key)
        if val is None:
            return default
        return str(val)

    def get_non_empty_str(self, key: str, default: str = "") -> str:
        """文本配置解析：缺失或空白都回退默认值，适用于必须有安全基线的字段。"""
        val = self._raw.get(key)
        if val is None:
            return default
        text = str(val)
        return text if text.strip() else default

    def get_list(self, key: str, default=None) -> list:
        """列表型配置：原生 list 直返；逗号分隔字符串拆分去空；其余返回默认。"""
        val = self._raw.get(key)
        if isinstance(val, list):
            return [str(v).strip() for v in val if str(v).strip()]
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return list(default or [])

    def _get_recognition_enum(self, key: str, default: str, allowed: set[str], warning_code: str) -> str:
        """识别增强枚举配置解析；非法值回退安全默认并保留稳定告警码。"""
        value = self.get_str(key, default).strip().lower()
        if value in allowed:
            return value
        self._recognition_guard_config_warnings.add(warning_code)
        return default

    def _get_recognition_min_int(self, key: str, default: int, minimum: int, warning_code: str) -> int:
        """识别增强正整数解析；非法、浮点或低于下限时使用运行时默认值并记录告警。"""
        val = self._raw.get(key)
        if val is None:
            return default
        if isinstance(val, bool):
            self._recognition_guard_config_warnings.add(warning_code)
            return default
        try:
            text = str(val).strip()
            if not text or any(char in text for char in (".", "e", "E")):
                raise ValueError
            parsed = int(text)
        except (ValueError, TypeError):
            self._recognition_guard_config_warnings.add(warning_code)
            return default
        if parsed < minimum:
            self._recognition_guard_config_warnings.add(warning_code)
            return default
        return parsed

    # ---- 全局开关与运行 ----

    @property
    def enabled(self) -> bool:
        """插件总开关：关闭后所有域与定时任务不生效。"""
        return self.get_bool("enabled", False)

    @property
    def notify(self) -> bool:
        """是否在关键事件（删种/暂停/重建等）发送通知。"""
        return self.get_bool("notify", True)

    @property
    def onlyonce(self) -> bool:
        """立即运行一次：保存后触发一轮全量巡检，执行后自动复位。"""
        return self.get_bool("onlyonce", False)

    @property
    def reset_task(self) -> bool:
        """重置数据：清空待定/暂停/监控等插件任务数据，执行后自动复位。"""
        return self.get_bool("reset_task", False)

    # ---- 公共周期 ----

    @property
    def auto_check_interval_minutes(self) -> int:
        """通用巡检周期（分钟）：站点证据采样、待定释放、无下载处理和本地清理共用。"""
        return self.get_int("auto_check_interval_minutes", 30)

    @property
    def download_check_interval_minutes(self) -> int:
        """下载检查周期（分钟）：定时读取下载器状态并处理超时/Tracker/手动删种。"""
        return self.get_int("download_check_interval_minutes", 10)

    @property
    def meta_check_interval_hours(self) -> int:
        """元数据检查周期（小时）：定时复核订阅元数据并重评信号/待定。"""
        return self.get_int("meta_check_interval_hours", 3)

    @property
    def best_version_cron(self) -> str:
        """洗版检查周期：cron 表达式，由 CronTrigger 调度定时推进洗版订阅。"""
        return self.get_str("best_version_cron", "0 15 * * *")

    # ---- 订阅清理 ----

    @property
    def download_monitor_enabled(self) -> bool:
        """下载超时自动删除：控制超时、Tracker 关键字和手动删种善后等破坏性下载管理。"""
        return self.get_bool("download_monitor_enabled", True)

    @property
    def manual_delete_listen(self) -> bool:
        """监听用户手动删除的种子；关闭后下载器侧消失不触发删除处理。"""
        return self.get_bool("manual_delete_listen", True)

    @property
    def tracker_response_listen(self) -> bool:
        """Tracker 返回内容包含关键字时自动删种；关闭后不按 Tracker 返回内容删种。"""
        return self.get_bool("tracker_response_listen", True)

    @property
    def auto_search_when_delete(self) -> bool:
        """删种后自动触发该订阅补全搜索。"""
        return self.get_bool("auto_search_when_delete", True)

    @property
    def skip_deletion(self) -> bool:
        """资源选择阶段跳过删除指纹命中的近期删除资源，避免再次下载刚删的种子。"""
        return self.get_bool("skip_deletion", True)

    @property
    def download_timeout_minutes(self) -> int:
        """下载超时时间：同一下载任务观察窗口内进度不足时才进入超时判断。"""
        return self.get_int("download_timeout_minutes", 120)

    @property
    def download_progress_threshold(self) -> int:
        """下载进度阈值：超时窗口内进度增长低于该百分比才视为停滞。"""
        return self.get_int("download_progress_threshold", 10)

    @property
    def download_retry_limit(self) -> int:
        """下载连续超时重试次数：达到上限后保留任务并停止自动删种重试。"""
        return self.get_int("download_retry_limit", 3)

    @property
    def delete_exclude_tags(self) -> str:
        """自动删种排除标签：带有任一标签的种子不参与超时或 Tracker 关键字删除。"""
        return self.get_non_empty_str("delete_exclude_tags", DEFAULT_DELETE_EXCLUDE_TAGS)

    @property
    def default_tracker_response(self) -> str:
        """Tracker 响应关键字：每行一个匹配项，空配置使用内置关键字。"""
        return self.get_non_empty_str("default_tracker_response", DEFAULT_TRACKER_RESPONSE)

    @property
    def open_tracker_dialog(self) -> bool:
        """打开 Tracker 配置弹窗：仅控制表单弹窗开合的 UI 状态，不参与业务逻辑。"""
        return self.get_bool("open_tracker_dialog", False)

    @property
    def delete_record_retention_hours(self) -> int:
        """删除指纹保留期（小时）：超过则定时清理，避免长期屏蔽同源资源。"""
        return self.get_int("delete_record_retention_hours", 24)

    @property
    def subscription_cleanup_history_type(self) -> str:
        """订阅清理整理记录范围：no/all/movie/tv，命中后才允许执行破坏性清理事务。"""
        val = self.get_str("subscription_cleanup_history_type", "no")
        return val if val in ("no", "all", "movie", "tv") else "no"

    @property
    def subscription_cleanup_history_scenes(self) -> list:
        """订阅清理整理记录场景：normal/best_version/best_version_episode。"""
        scenes = self.get_list("subscription_cleanup_history_scenes")
        allowed = {"normal", "best_version", "best_version_episode"}
        return [scene for scene in (str(scene or "") for scene in scenes) if scene in allowed]

    # ---- 识别增强 ----

    @property
    def recognition_guard_mode(self) -> str:
        """识别增强模式：候选准入的风险偏好，历史配置缺字段时保持关闭。"""
        return self._get_recognition_enum(
            "recognition_guard_mode",
            "off",
            {"off", "audit", "loose", "balanced", "strict"},
            "invalid_mode",
        )

    @property
    def recognition_guard_notify(self) -> str:
        """识别增强通知模式：只影响消息推送，不影响本地审计日志。"""
        return self._get_recognition_enum(
            "recognition_guard_notify",
            "off",
            {"off", "summary", "detail", "all"},
            "invalid_recognition_notify",
        )

    @property
    def recognition_guard_notify_interval(self) -> int:
        """识别增强通知限频秒数，同订阅同动作同原因命中时只抑制通知。"""
        return self._get_recognition_min_int(
            "recognition_guard_notify_interval",
            3600,
            60,
            "invalid_notify_interval",
        )

    @property
    def recognition_guard_tmdb_recheck_mode(self) -> str:
        """二次识别触发范围：audit 按 balanced 口径计算。"""
        return self._get_recognition_enum(
            "recognition_guard_tmdb_recheck_mode",
            "balanced_strict",
            {"off", "all", "strict", "balanced_strict"},
            "invalid_tmdb_recheck_mode",
        )

    @property
    def recognition_guard_cache_maxsize(self) -> int:
        """二次识别缓存上限，避免同一候选重复识别。"""
        return self._get_recognition_min_int(
            "recognition_guard_cache_maxsize",
            100000,
            100,
            "invalid_cache_maxsize",
        )

    @property
    def recognition_guard_custom_config(self) -> str:
        """识别增强 YAML 自定义策略；空文本表示无自定义覆盖。"""
        return self.get_str("recognition_guard_custom_config", DEFAULT_RECOGNITION_GUARD_CUSTOM_CONFIG)

    @property
    def recognition_guard_config_warnings(self) -> set[str]:
        """识别增强配置解析告警码快照，供日志和测试读取，不作为可保存配置。"""
        return set(self._recognition_guard_config_warnings)

    # ---- 订阅待定 ----

    @property
    def pending_enhanced_enabled(self) -> bool:
        """自动待定剧集订阅：按开播时间、已播集数和可选变化信号标记待定。"""
        return self.get_bool("pending_enhanced_enabled", True)

    @property
    def pending_download_enabled(self) -> bool:
        """自动待定下载中订阅：存在进行中下载时否决完成，避免入库前完成订阅。"""
        return self.get_bool("pending_download_enabled", True)

    @property
    def auto_tv_pending_days(self) -> int:
        """剧集待定天数：开播后 N 天内保持待定；0 表示不按天数进入待定。"""
        return self.get_int("auto_tv_pending_days", 0)

    @property
    def auto_tv_pending_episodes(self) -> int:
        """剧集待定集数：已播出集数小于等于 N 时保持待定；0 表示不按集数进入待定。"""
        return self.get_int("auto_tv_pending_episodes", 1)

    @property
    def pending_use_volatility(self) -> bool:
        """待定参考变更速率：接近完结且总集数近期变化时参与待定判断。"""
        return self.get_bool("pending_use_volatility", False)

    # ---- 订阅暂停 ----

    @property
    def pause_enhanced_enabled(self) -> bool:
        """自动暂停订阅：按播出距离、上映距离和用户名单暂停订阅。"""
        return self.get_bool("pause_enhanced_enabled", False)

    @property
    def auto_pause_users(self) -> str:
        """用户名自动暂停名单，逗号分隔；新增订阅用户在名单内时自动暂停，空串表示不启用。"""
        return self.get_str("auto_pause_users", "")

    @property
    def airing_pause_days(self) -> int:
        """即将播出暂停天数：下一集距离超过 N 天时暂停；0=不处理。"""
        return self.get_int("airing_pause_days", 30)

    @property
    def movie_air_pause_days(self) -> int:
        """电影上映暂停天数：当前日期早于上映日期减 N 天则暂停；0=不处理。"""
        return self.get_int("movie_air_pause_days", 7)

    @property
    def tv_air_pause_days(self) -> int:
        """剧集上映暂停天数：当前日期早于开播日期减 N 天则暂停；0=不处理。"""
        return self.get_int("tv_air_pause_days", 14)

    @property
    def movie_no_download_days(self) -> int:
        """电影无下载处理天数：上映后 N 天内无下载则按无下载策略处理；0=不处理。"""
        return self.get_int("movie_no_download_days", 365)

    @property
    def tv_no_download_days(self) -> int:
        """剧集无下载处理天数：上映后 N 天内无下载则按无下载策略处理；0=不处理。"""
        return self.get_int("tv_no_download_days", 180)

    @property
    def no_download_actions(self) -> list:
        """无下载处理策略（多选）：pause/complete/delete × movie/tv 的组合。"""
        return self.get_list("no_download_actions")

    # ---- 订阅补全 ----

    @property
    def site_total_probe_enabled(self) -> bool:
        """站点集数探测：使用站点缓存资源辅助发现目标集数不足。"""
        return self.get_bool("site_total_probe_enabled", False)

    @property
    def paused_probe_reasons(self) -> list:
        """暂停订阅低频补搜场景；缺省只对无下载暂停进行主动搜索。"""
        return self.get_list("paused_probe_reasons", ["no_download"])

    @property
    def paused_probe_min_pause_days(self) -> int:
        """暂停订阅达到天数后才允许主动补搜；0=不处理。"""
        return self.get_int("paused_probe_min_pause_days", 14)

    @property
    def paused_probe_interval_hours(self) -> int:
        """同一订阅主动补搜的最小间隔，运行时不低于 24 小时。"""
        return max(self.get_int("paused_probe_interval_hours", 72), 24)

    # ---- 无进展诊断 ----

    @property
    def progress_diagnostic_mode(self) -> str:
        """无进展诊断模式：off=关闭，notify=仅发送诊断通知。"""
        val = self.get_str("progress_diagnostic_mode", "off").strip().lower()
        return val if val in ("off", "notify") else "off"

    @property
    def progress_diagnostic_stalled_rounds(self) -> int:
        """连续无进展轮数阈值：缺失集数连续 N 轮巡检未减少后发出诊断通知；0=不处理。"""
        return self.get_int("progress_diagnostic_stalled_rounds", 3)

    @property
    def progress_diagnostic_cooldown_hours(self) -> int:
        """同一订阅两次诊断通知的最小间隔小时数，避免反复打扰。"""
        return self.get_int("progress_diagnostic_cooldown_hours", 24)

    # ---- 订阅洗版 ----

    @property
    def best_version_type(self) -> str:
        """洗版类型：no=关闭自动洗版；all/movie/tv/tv_episode=按范围自动创建并巡检洗版订阅。"""
        val = self.get_str("best_version_type", "no")
        return val if val in ("no", "all", "movie", "tv", "tv_episode") else "no"

    @property
    def best_version_movie_remaining_days(self) -> int:
        """电影洗版时限：达到天数后自动终止，有下载则按最新时间计；0=不限。"""
        return self.get_int("best_version_movie_remaining_days", 0)

    @property
    def best_version_tv_remaining_days(self) -> int:
        """剧集全集洗版时限：达到天数后自动终止，有下载则按最新时间计；0=不限。"""
        return self.get_int("best_version_tv_remaining_days", 0)

    @property
    def best_version_episode_to_full(self) -> bool:
        """分集转全集：分集洗版订阅目标集满足时切换为整季洗版。"""
        return self.get_bool("best_version_episode_to_full", False)

    @property
    def best_version_backfill_enabled(self) -> bool:
        """回填已存在集：新建或转分集洗版时把媒体库已有集标为顶档。"""
        return self.get_bool("best_version_backfill_enabled", False)

    @property
    def backfill_best_version_now(self) -> bool:
        """立即扫描存量并回填：对现有分集洗版订阅执行一次回填。"""
        return self.get_bool("backfill_best_version_now", False)

    # ---- 完结信号与验证 ----

    @property
    def completion_guard_mode(self) -> str:
        """完结守卫模式：关闭、严格、平衡或宽松。"""
        value = self.get_str("completion_guard_mode", "balanced").strip().lower()
        return value if value in {"off", "strict", "balanced", "loose"} else "balanced"

    @property
    def site_completion_evidence_enabled(self) -> bool:
        """站点完结信号：使用站点资源标题佐证当前目标完成。"""
        return self.get_bool("site_completion_evidence_enabled", True)

    @property
    def volatility_enabled(self) -> bool:
        """变更速率信号：总集数在观察窗口内变化时阻止直接完成。"""
        return self.get_bool("volatility_enabled", True)

    @property
    def volatility_window_days(self) -> int:
        """变更速率窗口：统计总集数变化的天数，值越大越保守。"""
        return self.get_int("volatility_window_days", DEFAULT_VOLATILITY_WINDOW_DAYS)

    @property
    def cadence_enabled(self) -> bool:
        """播出节奏信号：按已播间隔估算继续等待期，不单独判定完结。"""
        return self.get_bool("cadence_enabled", True)

    @property
    def cadence_multiplier(self) -> float:
        """节奏窗口系数：放大已播间隔得到最低等待窗口。"""
        return self.get_float("cadence_multiplier", 2.5)

    @property
    def cadence_min_window_days(self) -> int:
        """节奏窗口下限：节奏估算的等待窗口不得低于该天数。"""
        return self.get_int("cadence_min_window_days", 7)

    @property
    def cadence_min_episodes(self) -> int:
        """节奏参与最少集数：已播集数达到该值后才计算播出节奏。"""
        return self.get_int("cadence_min_episodes", 3)

    @property
    def season_cooldown_days(self) -> int:
        """季冷却期：末集播出后继续观察的天数。"""
        return self.get_int("season_cooldown_days", 14)

    @property
    def verify_enabled(self) -> bool:
        """自动纠错：完成后定时复核集数，发现增加时重建订阅。"""
        return self.get_bool("verify_enabled", False)

    @property
    def verify_interval_hours(self) -> int:
        """自动纠错间隔：完成快照复核的定时周期。"""
        return self.get_int("verify_interval_hours", 12)

    @property
    def verify_retention_days(self) -> int:
        """完成快照保留天数；用户配置覆盖默认的 180 天。"""
        return self.get_int("verify_retention_days", 180)

    @property
    def timeout_release_days(self) -> int:
        """完成前观察天数：低置信或不稳定完成否决可保留的最长观察窗口。"""
        return self.get_int("timeout_release_days", 7)

    @property
    def timeout_cadence_acceleration(self) -> bool:
        """按节奏加速释放：播出节奏等待期结束后缩短完成前观察窗口。"""
        return self.get_bool("timeout_cadence_acceleration", True)

    def declared_keys(self) -> list:
        """返回所有配置键（与各 @property 同名）。供表单 model 覆盖校验，避免表单与配置漂移。"""
        excluded = {"recognition_guard_config_warnings"}
        return [name for name, value in vars(type(self)).items()
                if isinstance(value, property) and name not in excluded]

    @classmethod
    def defaults(cls) -> dict:
        """返回所有配置键的默认值（构造空配置读取各 property），供表单 model 默认数据。"""
        blank = cls({})
        return {key: getattr(blank, key) for key in blank.declared_keys()}
