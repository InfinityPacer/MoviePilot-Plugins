"""shared/config.py PluginConfig 单测。"""
from subscribeassistantenhanced.shared.config import PluginConfig


class PluginConfigDefaultsTest:
    """所有配置属性的默认值验证。"""

    def setup_method(self):
        self.cfg = PluginConfig({})

    # --- domain switches ---

    def test_completion_guard_mode_default_balanced(self):
        assert self.cfg.completion_guard_mode == "balanced"

    def test_pending_enhanced_enabled_default_true(self):
        assert self.cfg.pending_enhanced_enabled is True

    def test_pause_enhanced_enabled_default_false(self):
        assert self.cfg.pause_enhanced_enabled is False

    def test_download_monitor_enabled_default_true(self):
        assert self.cfg.download_monitor_enabled is True

    def test_verify_enabled_default_false(self):
        assert self.cfg.verify_enabled is False

    def test_site_signal_defaults(self):
        """站点完结信号默认参与守卫佐证，扩集仍需用户显式开启。"""
        assert self.cfg.site_total_probe_enabled is False
        assert self.cfg.site_completion_evidence_enabled is True

    def test_completion_observation_declares_single_days_key(self):
        keys = set(self.cfg.declared_keys())
        assert {key for key in keys if key.startswith("timeout_release")} == {"timeout_release_days"}
        assert {key for key in PluginConfig.defaults() if key.startswith("timeout_release")} == {"timeout_release_days"}

    # --- signal engine ---

    def test_volatility_enabled_default_true(self):
        assert self.cfg.volatility_enabled is True

    def test_volatility_window_days_default(self):
        assert self.cfg.volatility_window_days == 3

    def test_cadence_enabled_default_true(self):
        assert self.cfg.cadence_enabled is True

    def test_cadence_multiplier_default(self):
        assert self.cfg.cadence_multiplier == 2.5

    def test_cadence_min_window_days_default(self):
        assert self.cfg.cadence_min_window_days == 7

    def test_cadence_min_episodes_default(self):
        assert self.cfg.cadence_min_episodes == 3

    def test_season_cooldown_days_default(self):
        assert self.cfg.season_cooldown_days == 14

    # --- postcheck ---

    def test_verify_interval_hours_default(self):
        assert self.cfg.verify_interval_hours == 12

    def test_verify_retention_days_default(self):
        assert self.cfg.verify_retention_days == 180

    def test_timeout_release_days_default(self):
        assert self.cfg.timeout_release_days == 7

    def test_timeout_cadence_acceleration_default(self):
        assert self.cfg.timeout_cadence_acceleration is True

    # --- download ---

    def test_auto_check_interval_minutes_default(self):
        assert self.cfg.auto_check_interval_minutes == 30

    def test_download_check_interval_minutes_default(self):
        assert self.cfg.download_check_interval_minutes == 10

    def test_best_version_cron_default(self):
        assert self.cfg.best_version_cron == "0 15 * * *"

    def test_open_tracker_dialog_default_false(self):
        assert self.cfg.open_tracker_dialog is False

    def test_download_timeout_minutes_default(self):
        assert self.cfg.download_timeout_minutes == 120

    def test_download_progress_threshold_default(self):
        assert self.cfg.download_progress_threshold == 10

    def test_download_retry_limit_default(self):
        assert self.cfg.download_retry_limit == 3

    def test_delete_record_retention_hours_default_24h(self):
        """删除指纹默认保留 24 小时，避免长期屏蔽同源资源。"""
        assert self.cfg.delete_record_retention_hours == 24

    def test_delete_exclude_tags_default_protection(self):
        assert self.cfg.delete_exclude_tags == "H&R"

    def test_default_tracker_response_default_keywords(self):
        assert "torrent not registered" in self.cfg.default_tracker_response
        assert "torrent banned" in self.cfg.default_tracker_response

    def test_empty_tracker_defaults_fall_back_to_builtin_values(self):
        cfg = PluginConfig({
            "delete_exclude_tags": "",
            "default_tracker_response": "",
        })

        assert cfg.delete_exclude_tags == "H&R"
        assert "torrent not registered" in cfg.default_tracker_response

    # --- pause ---

    def test_airing_pause_days_default(self):
        assert self.cfg.airing_pause_days == 30

    def test_pre_air_pause_days_default(self):
        assert self.cfg.movie_air_pause_days == 7
        assert self.cfg.tv_air_pause_days == 14

    def test_no_download_days_default(self):
        assert self.cfg.movie_no_download_days == 365
        assert self.cfg.tv_no_download_days == 180

    def test_paused_probe_defaults(self):
        """暂停订阅补搜默认只开启无下载场景，并保留保守的时间门槛。"""
        assert self.cfg.paused_probe_reasons == ["no_download"]
        assert self.cfg.paused_probe_min_pause_days == 14
        assert self.cfg.paused_probe_interval_hours == 72

    def test_progress_diagnostic_defaults(self):
        """无进展诊断默认关闭，轮数与冷却保持保守阈值。"""
        assert self.cfg.progress_diagnostic_mode == "off"
        assert self.cfg.progress_diagnostic_stalled_rounds == 3
        assert self.cfg.progress_diagnostic_cooldown_hours == 24

    def test_progress_diagnostic_mode_accepts_only_current_modes(self):
        """无进展诊断按模式扩展，非法值回退关闭。"""
        assert PluginConfig({"progress_diagnostic_mode": "notify"}).progress_diagnostic_mode == "notify"
        assert PluginConfig({"progress_diagnostic_mode": "auto"}).progress_diagnostic_mode == "off"

    def test_progress_diagnostic_keys_are_declared(self):
        """配置契约只暴露当前无进展诊断 key。"""
        keys = set(self.cfg.declared_keys())
        assert {key for key in keys if key.startswith("progress_diagnostic_")} == {
            "progress_diagnostic_mode",
            "progress_diagnostic_stalled_rounds",
            "progress_diagnostic_cooldown_hours",
        }

    # --- pending ---

    def test_auto_tv_pending_days_default_disabled(self):
        assert self.cfg.auto_tv_pending_days == 0

    def test_auto_tv_pending_episodes_default(self):
        assert self.cfg.auto_tv_pending_episodes == 1

    def test_pending_use_volatility_default(self):
        assert self.cfg.pending_use_volatility is False

    def test_internal_pending_default_total_is_not_declared(self):
        """待定缺总集数时不再暴露虚拟总集数配置。"""
        keys = set(self.cfg.declared_keys())
        assert "pending_default_total_episodes" not in keys

    def test_download_pause_expiry_keys_are_not_declared(self):
        """下载超时删种后走删除指纹与补搜，不再提供下载暂停超期配置。"""
        keys = set(self.cfg.declared_keys())
        assert "download_pause_max_days" not in keys
        assert "download_pause_expire_action" not in keys

    def test_best_version_backfill_default_disabled(self):
        assert self.cfg.best_version_backfill_enabled is False

    def test_subscription_cleanup_defaults(self):
        """订阅清理默认关闭，且默认不选任何触发场景。"""
        assert self.cfg.subscription_cleanup_history_type == "no"
        assert self.cfg.subscription_cleanup_history_scenes == []

    def test_removed_best_version_boolean_keys_are_not_declared(self):
        """洗版开关语义由枚举字段承载，旧布尔键不再进入默认 model。"""
        keys = set(self.cfg.declared_keys())
        assert "best_version_enabled" not in keys
        assert "auto_best_version_on_complete" not in keys
        assert "best_version_clear_history_enabled" not in keys

    def test_old_best_version_clear_history_key_is_not_declared(self):
        """清理配置归入订阅清理页签，旧洗版清理字段不再作为配置契约。"""
        keys = set(self.cfg.declared_keys())
        assert "best_version_clear_history_type" not in keys


class PluginConfigCoercionTest:
    """类型强转与兜底。"""

    def test_int_from_string(self):
        cfg = PluginConfig({"volatility_window_days": "7"})
        assert cfg.volatility_window_days == 7
        assert isinstance(cfg.volatility_window_days, int)

    def test_verify_retention_days_uses_user_value(self):
        """H 快照实际保留期必须服从用户配置。"""
        cfg = PluginConfig({"verify_retention_days": "30"})
        assert cfg.verify_retention_days == 30

    def test_float_from_string(self):
        cfg = PluginConfig({"cadence_multiplier": "3.0"})
        assert cfg.cadence_multiplier == 3.0
        assert isinstance(cfg.cadence_multiplier, float)

    def test_bool_from_truthy_string(self):
        cfg = PluginConfig({"volatility_enabled": "true"})
        assert cfg.volatility_enabled is True

    def test_bool_from_falsy_string(self):
        cfg = PluginConfig({"volatility_enabled": "false"})
        assert cfg.volatility_enabled is False

    def test_invalid_int_falls_back_to_default(self):
        cfg = PluginConfig({"volatility_window_days": "bad"})
        assert cfg.volatility_window_days == 3

    def test_invalid_float_falls_back_to_default(self):
        cfg = PluginConfig({"cadence_multiplier": "bad"})
        assert cfg.cadence_multiplier == 2.5

    def test_missing_key_uses_default(self):
        cfg = PluginConfig({"unrelated_key": 999})
        assert cfg.cadence_min_episodes == 3

    def test_completion_guard_mode_accepts_declared_values(self):
        for mode in ("off", "strict", "balanced", "loose"):
            assert PluginConfig({"completion_guard_mode": mode}).completion_guard_mode == mode

    def test_invalid_completion_guard_mode_falls_back_to_balanced(self):
        assert PluginConfig({"completion_guard_mode": "bad"}).completion_guard_mode == "balanced"

    def test_subscription_cleanup_type_accepts_declared_values(self):
        for value in ("no", "all", "movie", "tv"):
            cfg = PluginConfig({"subscription_cleanup_history_type": value})
            assert cfg.subscription_cleanup_history_type == value

    def test_subscription_cleanup_type_rejects_unknown_value(self):
        assert PluginConfig({"subscription_cleanup_history_type": "bad"}).subscription_cleanup_history_type == "no"

    def test_subscription_cleanup_scenes_parse_list_or_csv(self):
        cfg = PluginConfig({
            "subscription_cleanup_history_scenes": ["normal", "best_version"]
        })
        assert cfg.subscription_cleanup_history_scenes == ["normal", "best_version"]

        cfg = PluginConfig({
            "subscription_cleanup_history_scenes": "normal,best_version_episode,bad"
        })
        assert cfg.subscription_cleanup_history_scenes == ["normal", "best_version_episode"]

    def test_subscription_cleanup_scenes_reject_removed_full_value(self):
        cfg = PluginConfig({
            "subscription_cleanup_history_scenes": ["best_version_episode", "best_version_full"]
        })
        assert cfg.subscription_cleanup_history_scenes == ["best_version_episode"]

    def test_int_from_float_string_truncates(self):
        cfg = PluginConfig({"download_retry_limit": "3.9"})
        assert cfg.download_retry_limit == 3

    def test_bool_recognizes_on_guard_yes(self):
        for val in ["on", "guard", "yes", "1", "TRUE"]:
            cfg = PluginConfig({"pending_use_volatility": val})
            assert cfg.pending_use_volatility is True, f"Expected True for {val!r}"

    def test_paused_probe_reasons_parse_list_or_csv(self):
        """补搜场景按多选值解析，不受自动暂停总开关直接裁剪。"""
        assert PluginConfig({"paused_probe_reasons": []}).paused_probe_reasons == []
        assert PluginConfig({"paused_probe_reasons": ["no_download", " external "]}).paused_probe_reasons == [
            "no_download",
            "external",
        ]
        assert PluginConfig({"paused_probe_reasons": "pre_air,airing_gap"}).paused_probe_reasons == [
            "pre_air",
            "airing_gap",
        ]

    def test_paused_probe_interval_has_24h_runtime_floor(self):
        """同一订阅主动补搜间隔最低 24 小时，避免配置误填造成高频搜索。"""
        assert PluginConfig({"paused_probe_interval_hours": 1}).paused_probe_interval_hours == 24
