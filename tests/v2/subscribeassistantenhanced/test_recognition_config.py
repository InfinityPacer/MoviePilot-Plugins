"""识别增强配置契约测试。"""
from unittest.mock import MagicMock

from subscribeassistantenhanced import SubscribeAssistantEnhanced
from subscribeassistantenhanced.form import build_form
from subscribeassistantenhanced.shared.config import PluginConfig


def test_recognition_guard_defaults_are_upgrade_safe():
    cfg = PluginConfig({})

    assert cfg.recognition_guard_mode == "off"


def test_recognition_guard_invalid_mode_falls_back_to_safe_value():
    cfg = PluginConfig({"recognition_guard_mode": "bad"})

    assert cfg.recognition_guard_mode == "off"
    assert cfg.recognition_guard_config_warnings == {"invalid_mode"}


def test_recognition_guard_audit_mode_is_valid_zero_side_effect_mode():
    cfg = PluginConfig({"recognition_guard_mode": "audit"})

    assert cfg.recognition_guard_mode == "audit"


def test_recognition_guard_mode_is_the_only_declared_recognition_key():
    defaults = PluginConfig.defaults()
    recognition_keys = {key for key in defaults if key.startswith("recognition_guard")}

    assert recognition_keys == {"recognition_guard_mode"}


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
    for key in (
        "recognition_guard_active",
        "recognition_guard_enabled",
        "recognition_guard_notify",
        "recognition_guard_notify_interval",
        "recognition_guard_tmdb_recheck_mode",
        "recognition_guard_missing_year_policy",
        "recognition_guard_keyword_config",
        "recognition_guard_target_mode",
        "recognition_guard_cache_maxsize",
    ):
        assert key not in persisted
