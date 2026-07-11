"""识别增强配置契约测试。"""
from pathlib import Path
from unittest.mock import MagicMock

import subscribeassistantenhanced as plugin_module
from subscribeassistantenhanced import SubscribeAssistantEnhanced
from subscribeassistantenhanced.form import build_form
from subscribeassistantenhanced.shared.config import PluginConfig


README_PATH = Path(__file__).resolve().parents[3] / "plugins.v2" / "subscribeassistantenhanced" / "README.md"


def test_recognition_guard_defaults_are_upgrade_safe():
    cfg = PluginConfig({})

    assert cfg.recognition_guard_mode == "off"
    assert cfg.recognition_guard_notify == "off"
    assert cfg.recognition_guard_notify_interval == 3600
    assert cfg.recognition_guard_tmdb_recheck_mode == "balanced_strict"
    assert cfg.recognition_guard_cache_maxsize == 100000
    assert "配置说明 BEGIN" in cfg.recognition_guard_custom_config


def test_recognition_guard_invalid_mode_falls_back_to_safe_value():
    cfg = PluginConfig({
        "recognition_guard_mode": "bad",
        "recognition_guard_notify": "bad",
        "recognition_guard_notify_interval": "59",
        "recognition_guard_tmdb_recheck_mode": "bad",
        "recognition_guard_cache_maxsize": "99",
    })

    assert cfg.recognition_guard_mode == "off"
    assert cfg.recognition_guard_notify == "off"
    assert cfg.recognition_guard_notify_interval == 3600
    assert cfg.recognition_guard_tmdb_recheck_mode == "balanced_strict"
    assert cfg.recognition_guard_cache_maxsize == 100000
    assert cfg.recognition_guard_config_warnings == {
        "invalid_mode",
        "invalid_recognition_notify",
        "invalid_notify_interval",
        "invalid_tmdb_recheck_mode",
        "invalid_cache_maxsize",
    }


def test_recognition_guard_audit_mode_is_valid_zero_side_effect_mode():
    cfg = PluginConfig({"recognition_guard_mode": "audit"})

    assert cfg.recognition_guard_mode == "audit"


def test_recognition_guard_public_keys_match_final_contract():
    defaults = PluginConfig.defaults()
    recognition_keys = {key for key in defaults if key.startswith("recognition_guard")}

    assert recognition_keys == {
        "recognition_guard_mode",
        "recognition_guard_notify",
        "recognition_guard_notify_interval",
        "recognition_guard_tmdb_recheck_mode",
        "recognition_guard_cache_maxsize",
        "recognition_guard_custom_config",
    }
    assert "recognition_guard_enabled" not in defaults
    assert "recognition_guard_active" not in defaults
    assert "recognition_guard_keyword_config" not in defaults
    assert "recognition_guard_target_mode" not in defaults
    assert "recognition_guard_missing_year_policy" not in defaults


def test_recognition_guard_warning_snapshot_is_not_persisted_form_key():
    assert "recognition_guard_config_warnings" not in PluginConfig({}).declared_keys()

    _conf, model = build_form()
    assert "recognition_guard_config_warnings" not in model


def test_recognition_guard_missing_fields_are_persisted_off_on_init():
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()

    plugin.init_plugin({})

    persisted = plugin.update_config.call_args.args[0]
    assert persisted["recognition_guard_mode"] == "off"
    assert persisted["recognition_guard_notify"] == "off"
    assert persisted["recognition_guard_notify_interval"] == 3600
    assert persisted["recognition_guard_tmdb_recheck_mode"] == "balanced_strict"
    assert persisted["recognition_guard_cache_maxsize"] == 100000
    assert "配置说明 BEGIN" in persisted["recognition_guard_custom_config"]
    for key in (
        "recognition_guard_active",
        "recognition_guard_enabled",
        "recognition_guard_missing_year_policy",
        "recognition_guard_keyword_config",
        "recognition_guard_target_mode",
    ):
        assert key not in persisted


def test_upgrade_persistence_drops_retired_config_keys():
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()

    plugin.init_plugin({
        "recognition_guard_mode": "balanced",
        "recognition_guard_enabled": True,
        "recognition_guard_active": True,
        "recognition_guard_keyword_config": "hard_block:\n  - legacy\n",
        "recognition_guard_target_mode": "animation",
        "recognition_guard_missing_year_policy": "block",
        "open_tracker_dialog": True,
        "progress_diagnostic_mode": "notify",
        "progress_diagnostic_stalled_rounds": 3,
        "progress_diagnostic_cooldown_hours": 24,
    })

    persisted = plugin.update_config.call_args.args[0]
    for key in (
        "recognition_guard_enabled",
        "recognition_guard_active",
        "recognition_guard_keyword_config",
        "recognition_guard_target_mode",
        "recognition_guard_missing_year_policy",
        "open_tracker_dialog",
        "progress_diagnostic_mode",
        "progress_diagnostic_stalled_rounds",
        "progress_diagnostic_cooldown_hours",
    ):
        assert key not in persisted


def test_recognition_guard_invalid_existing_values_are_not_persisted_as_fallbacks():
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    raw = {
        "recognition_guard_mode": "bad",
        "recognition_guard_notify": "bad",
        "recognition_guard_notify_interval": "0",
        "recognition_guard_tmdb_recheck_mode": "bad",
        "recognition_guard_cache_maxsize": "-1",
        "recognition_guard_custom_config": "",
    }

    plugin.init_plugin(raw)

    plugin.update_config.assert_not_called()
    assert plugin._config.recognition_guard_mode == "off"
    assert plugin._config.recognition_guard_notify == "off"
    assert plugin._config.recognition_guard_notify_interval == 3600
    assert plugin._config.recognition_guard_tmdb_recheck_mode == "balanced_strict"
    assert plugin._config.recognition_guard_cache_maxsize == 100000
    assert {
        "invalid_mode",
        "invalid_recognition_notify",
        "invalid_notify_interval",
        "invalid_tmdb_recheck_mode",
        "invalid_cache_maxsize",
    }.issubset(plugin._config.recognition_guard_config_warnings)


def test_recognition_guard_startup_summary_keeps_interval_warning_after_upgrade(monkeypatch):
    messages = []
    monkeypatch.setattr(plugin_module.logger, "info", messages.append)
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()

    plugin.init_plugin({
        "recognition_guard_mode": "balanced",
        "recognition_guard_notify_interval": "0",
    })

    assert plugin.update_config.called
    joined = "\n".join(messages)
    assert "识别增强告警=invalid_notify_interval" in joined


def test_recognition_guard_readme_documents_public_contract_only():
    readme = README_PATH.read_text(encoding="utf-8")

    expected_rows = {
        "| 识别增强模式 | `recognition_guard_mode` | enum | `off` |",
        "| 识别增强通知 | `recognition_guard_notify` | enum | `off` |",
        "| 识别增强通知限频（秒） | `recognition_guard_notify_interval` | int | `3600` |",
        "| 识别增强二次识别 | `recognition_guard_tmdb_recheck_mode` | enum | `balanced_strict` |",
        "| 识别增强缓存大小 | `recognition_guard_cache_maxsize` | int | `100000` |",
        "| 自定义识别规则 | `recognition_guard_custom_config` | YAML | 内置说明模板 |",
    }
    for row in expected_rows:
        assert row in readme

    for option in (
        "`off` / `audit` / `loose` / `balanced` / `strict`",
        "`off` / `summary` / `detail` / `all`",
        "`off` / `all` / `strict` / `balanced_strict`",
        "`inherit` / `observe` / `soft_block` / `block`",
        "`recover_soft_block` / `never_recover`",
    ):
        assert option in readme

    for forbidden_key in (
        "recognition_guard_enabled",
        "recognition_guard_active",
        "recognition_guard_keyword_config",
        "recognition_guard_target_mode",
        "recognition_guard_missing_year_policy",
    ):
        assert forbidden_key not in readme
