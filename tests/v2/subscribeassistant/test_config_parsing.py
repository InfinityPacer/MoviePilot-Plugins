"""
SubscribeAssistant P2 配置解析与杂项纯函数单测。

用例只覆盖静态解析、关键字归一化、版本比较和默认 Tracker 文案，不初始化插件。
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from subscribeassistant import SubscribeAssistant


class ConfigParsingTest:
    """配置解析工具：数值、布尔、枚举和关键字配置。"""

    def test_get_float_config_reads_numeric_string(self):
        assert SubscribeAssistant._SubscribeAssistant__get_float_config({"k": "1.5"}, "k", 2.0) == 1.5

    def test_get_float_config_returns_default_when_key_missing(self):
        assert SubscribeAssistant._SubscribeAssistant__get_float_config({}, "k", 2.0) == 2.0

    def test_get_float_config_returns_default_for_invalid_value(self):
        assert SubscribeAssistant._SubscribeAssistant__get_float_config({"k": "bad"}, "k", 2.0) == 2.0

    def test_get_int_config_accepts_float_string_and_truncates(self):
        assert SubscribeAssistant._SubscribeAssistant__get_int_config({"k": "3.9"}, "k", 1) == 3

    def test_get_int_config_returns_default_for_none(self):
        assert SubscribeAssistant._SubscribeAssistant__get_int_config({"k": None}, "k", 7) == 7

    def test_get_bool_config_preserves_boolean(self):
        assert SubscribeAssistant._SubscribeAssistant__get_bool_config({"k": True}, "k", False)

    def test_get_bool_config_recognizes_truthy_strings(self):
        for value in ["true", "1", "yes", "on", "guard", "TRUE"]:
            assert SubscribeAssistant._SubscribeAssistant__get_bool_config({"k": value}, "k", False), \
                f"Expected True for value={value!r}"

    def test_get_bool_config_treats_other_strings_as_false(self):
        assert not SubscribeAssistant._SubscribeAssistant__get_bool_config({"k": "false"}, "k", True)

    def test_get_bool_config_uses_python_truthiness_for_non_string(self):
        assert not SubscribeAssistant._SubscribeAssistant__get_bool_config({"k": 0}, "k", True)
        assert SubscribeAssistant._SubscribeAssistant__get_bool_config({"k": 2}, "k", False)

    def test_normalize_keyword_patterns_splits_lines(self):
        result = SubscribeAssistant._SubscribeAssistant__normalize_keyword_patterns(" 动画 \n\n 电影 ")
        assert result == ["动画", "电影"]

    def test_normalize_keyword_patterns_accepts_list_and_strips(self):
        result = SubscribeAssistant._SubscribeAssistant__normalize_keyword_patterns([" 动画 ", 123, ""])
        assert result == ["动画", "123"]

    def test_normalize_keyword_patterns_rejects_unsupported_type(self):
        with patch("subscribeassistant.logger.warning") as warning:
            result = SubscribeAssistant._SubscribeAssistant__normalize_keyword_patterns({"bad": "value"})
        assert result == []
        warning.assert_called_once()

    def test_split_custom_words_uses_lines_and_strips(self):
        assert SubscribeAssistant._SubscribeAssistant__split_custom_words(
            "  别名1\n\n别名2  ") == ["别名1", "别名2"]

    def test_normalize_choice_returns_default_for_unknown(self):
        assert SubscribeAssistant._SubscribeAssistant__normalize_choice(
            "bad", {"off", "strict"}, "off") == "off"

    def test_normalize_recognition_guard_notify_rejects_unknown(self):
        assert SubscribeAssistant._SubscribeAssistant__normalize_recognition_guard_notify("verbose") == "off"

    def test_default_keyword_config_contains_required_groups(self):
        text = SubscribeAssistant._SubscribeAssistant__get_default_recognition_guard_keyword_config()
        for key in ["live_action:", "animation:", "movie:", "tv:", "allow:", "block:"]:
            assert key in text

    def test_default_tracker_response_contains_known_errors(self):
        text = SubscribeAssistant._SubscribeAssistant__get_default_tracker_response()
        assert "torrent not registered" in text
        assert "torrent banned" in text

    def test_compare_versions_returns_one_when_second_is_newer(self):
        assert SubscribeAssistant._SubscribeAssistant__compare_versions("2.1", "2.2") == 1

    def test_compare_versions_returns_zero_when_equal_or_invalid(self):
        assert SubscribeAssistant._SubscribeAssistant__compare_versions("2.2", "2.2") == 0
        assert SubscribeAssistant._SubscribeAssistant__compare_versions("bad", "2.2") == 0

    def test_compare_versions_returns_minus_one_when_second_is_older(self):
        assert SubscribeAssistant._SubscribeAssistant__compare_versions("2.3", "2.2") == -1

    def test_package_requires_main_subscribe_fact_contract(self):
        package = json.loads(Path("package.v2.json").read_text(encoding="utf-8"))
        specifier = SpecifierSet(package["SubscribeAssistant"]["system_version"])
        assert Version("2.13.16") not in specifier
        assert Version("2.13.17") in specifier


class InitPluginConfigTest:
    """插件初始化配置装载、任务注册和持久化回写。"""

    def test_init_plugin_without_config_only_initializes_runtime_dependencies(self):
        plugin = object.__new__(SubscribeAssistant)
        with patch("subscribeassistant.TmdbChain") as tmdb_chain, \
                patch("subscribeassistant.DownloaderHelper") as downloader_helper, \
                patch("subscribeassistant.DownloadHistoryOper") as downloadhistory_oper, \
                patch("subscribeassistant.TransferHistoryOper") as transferhistory_oper, \
                patch("subscribeassistant.SubscribeOper") as subscribe_oper:
            plugin.init_plugin(None)

        tmdb_chain.assert_called_once()
        downloader_helper.assert_called_once()
        downloadhistory_oper.assert_called_once()
        transferhistory_oper.assert_called_once()
        subscribe_oper.assert_called_once()
        assert plugin._recognition_guard_notify_cache == {}

    def test_init_plugin_loads_config_registers_one_shot_jobs_and_persists_normalized_values(self):
        plugin = object.__new__(SubscribeAssistant)
        scheduler = MagicMock()
        config = {
            "enabled": True,
            "notify": True,
            "onlyonce": True,
            "auto_download_delete": False,
            "manual_delete_listen": False,
            "tracker_response_listen": True,
            "tracker_response": " failure \n\n banned ",
            "auto_search_when_delete": False,
            "delete_exclude_tags": "H&R,PT",
            "auto_tv_pending": False,
            "auto_pause": True,
            "meta_check_interval": 8,
            "auto_download_pending": False,
            "skip_deletion": False,
            "reset_task": True,
            "auto_best_type": "all",
            "auto_best_clear_history_type": "movie",
            "auto_best_cron": "0 3 * * *",
            "auto_best_episode_to_full": "true",
            "auto_best_backfill_priority": "yes",
            "backfill_best_version_now": "on",
            "download_check_interval": "7.5",
            "download_timeout": "4",
            "download_timeout_progress_threshold": "9",
            "download_timeout_retry_limit": "5",
            "recognition_guard_mode": "strict",
            "recognition_guard_target_mode": "animation",
            "recognition_guard_notify": "all",
            "recognition_guard_same_name_mode": "false",
            "recognition_guard_movie_year_mode": "strict",
            "recognition_guard_tv_year_mode": "season_strict",
            "recognition_guard_no_year_action": "filter",
            "recognition_guard_tmdb_recheck_mode": "all",
            "recognition_guard_cache_maxsize": "32",
            "recognition_guard_keyword_config": "allow:\n  - PROPER",
            "timeout_history_cleanup": "24",
            "auto_tv_pending_days": "3",
            "auto_tv_pending_episodes": "2",
            "auto_update_tv_pending_episodes": "12",
            "auto_best_remaining_days": "60",
            "auto_pause_user": "alice,bob",
            "auto_pause_movie_air_days": "10",
            "auto_pause_tv_air_days": "4",
            "auto_pause_tv_latest_days": "2",
            "auto_pause_no_download_actions": ["pause"],
            "auto_pause_movie_no_download_days": "30",
            "auto_pause_tv_no_download_days": "14",
        }

        with patch("subscribeassistant.TmdbChain"), \
                patch("subscribeassistant.DownloaderHelper"), \
                patch("subscribeassistant.DownloadHistoryOper"), \
                patch("subscribeassistant.TransferHistoryOper"), \
                patch("subscribeassistant.SubscribeOper"), \
                patch("subscribeassistant.BackgroundScheduler", return_value=scheduler), \
                patch.object(plugin, "stop_service") as stop_service, \
                patch.object(plugin, "update_config") as update_config:
            plugin.init_plugin(config)

        stop_service.assert_called_once()
        scheduler.start.assert_called_once()
        assert scheduler.add_job.call_count == 3
        assert plugin._tracker_responses == ["failure", "banned"]
        assert plugin._auto_best_types
        assert plugin._auto_best_clear_history_types
        assert plugin._download_check_interval == 7.5
        assert plugin._download_timeout_retry_limit == 5
        assert plugin._recognition_guard_notify == "all"
        assert plugin._recognition_guard_same_name_protection is False
        assert plugin._recognition_guard_cache_maxsize == 32
        assert plugin._auto_pause_users == {"alice", "bob"}
        assert plugin._onlyonce is False
        assert plugin._reset_task is False
        assert plugin._backfill_best_version_now is False
        persisted = update_config.call_args.kwargs["config"]
        assert persisted["onlyonce"] is False
        assert persisted["reset_task"] is False
        assert persisted["backfill_best_version_now"] is False
        assert persisted["recognition_guard_keyword_config"] == "allow:\n  - PROPER"
