"""插件配置解析器，统一类型转换和默认值。"""


# Tracker 默认关键字覆盖常见无效种子响应，避免空配置时监听开关没有实际匹配能力。
DEFAULT_TRACKER_RESPONSE = """torrent not registered with this tracker
torrent banned"""

# 自动删种默认跳过 H&R 标签，避免误删需要长期做种的任务。
DEFAULT_DELETE_EXCLUDE_TAGS = "H&R"

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
        """通用巡检周期（分钟）：待定释放、无下载处理和删除记录清理共用。"""
        return self.get_int("auto_check_interval_minutes", 60)

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
        return self.get_int("download_timeout_minutes", 120)

    @property
    def download_progress_threshold(self) -> int:
        return self.get_int("download_progress_threshold", 10)

    @property
    def download_retry_limit(self) -> int:
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
        """订阅清理整理记录场景：normal/best_version_episode/best_version_full。"""
        scenes = self.get_list("subscription_cleanup_history_scenes")
        allowed = {"normal", "best_version_episode", "best_version_full"}
        return [scene for scene in scenes if scene in allowed]

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
    def recognition_guard_config_warnings(self) -> set[str]:
        """识别增强配置解析告警码快照，供日志和测试读取，不作为可保存配置。"""
        return set(self._recognition_guard_config_warnings)

    # ---- 订阅待定 ----

    @property
    def pending_enhanced_enabled(self) -> bool:
        return self.get_bool("pending_enhanced_enabled", True)

    @property
    def pending_download_enabled(self) -> bool:
        """自动待定下载中订阅：存在进行中下载时否决完成（守门已实现，此开关控制是否启用）。"""
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
        return self.get_bool("pending_use_volatility", False)

    # ---- 订阅暂停 ----

    @property
    def pause_enhanced_enabled(self) -> bool:
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

    # ---- 订阅洗版 ----

    @property
    def best_version_type(self) -> str:
        """洗版类型：no=关闭自动洗版；all/movie/tv/tv_episode=按范围自动创建并巡检洗版订阅。"""
        val = self.get_str("best_version_type", "no")
        return val if val in ("no", "all", "movie", "tv", "tv_episode") else "no"

    @property
    def best_version_remaining_days(self) -> int:
        """洗版时限（天）：达到天数后自动终止洗版，有下载则按最新时间计；0=不限。"""
        return self.get_int("best_version_remaining_days", 0)

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
    def volatility_enabled(self) -> bool:
        return self.get_bool("volatility_enabled", True)

    @property
    def volatility_window_days(self) -> int:
        return self.get_int("volatility_window_days", 7)

    @property
    def cadence_enabled(self) -> bool:
        return self.get_bool("cadence_enabled", True)

    @property
    def cadence_multiplier(self) -> float:
        return self.get_float("cadence_multiplier", 2.5)

    @property
    def cadence_min_window_days(self) -> int:
        return self.get_int("cadence_min_window_days", 7)

    @property
    def cadence_min_episodes(self) -> int:
        return self.get_int("cadence_min_episodes", 3)

    @property
    def season_cooldown_days(self) -> int:
        return self.get_int("season_cooldown_days", 14)

    @property
    def verify_enabled(self) -> bool:
        return self.get_bool("verify_enabled", False)

    @property
    def verify_interval_hours(self) -> int:
        return self.get_int("verify_interval_hours", 12)

    @property
    def verify_retention_days(self) -> int:
        """完成快照保留天数；用户配置覆盖默认的 180 天。"""
        return self.get_int("verify_retention_days", 180)

    @property
    def timeout_release_days(self) -> int:
        return self.get_int("timeout_release_days", 7)

    @property
    def timeout_cadence_acceleration(self) -> bool:
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
