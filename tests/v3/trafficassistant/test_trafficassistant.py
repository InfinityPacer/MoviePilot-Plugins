"""TrafficAssistant V3 公开宿主边界与刷流联动合同测试。"""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.plugins.trafficassistant import TrafficAssistant
from app.plugins.trafficassistant.trafficconfig import TrafficConfig


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_SOURCE = REPO_ROOT / "plugins.v3/trafficassistant/__init__.py"
CONFIG_SOURCE = REPO_ROOT / "plugins.v3/trafficassistant/trafficconfig.py"


def _update_brush_site(plugin_config: dict, site_id: int, enable: bool):
    """调用刷流联动入口并返回保存配置的 mock。"""
    plugin = object.__new__(TrafficAssistant)
    with (
        patch.object(TrafficAssistant, "get_config", return_value=plugin_config),
        patch.object(TrafficAssistant, "update_config") as update_config,
    ):
        result = plugin._TrafficAssistant__update_brush_sites(
            site_id=site_id,
            enable=enable,
            plugin_id="BrushFlow",
        )
    return result, update_config


def test_v3_source_uses_public_sdk_and_oper_boundaries():
    """V3 源码使用公开 SDK 与 Oper，不引入旧路径兼容层。"""
    for source_path in (PLUGIN_SOURCE, CONFIG_SOURCE):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }

        assert not any(
            module.startswith(("app.compat", "app.core", "app.helper", "app.log", "app.utils"))
            for module in imported_modules
        )
        assert "app.sdk._legacy" not in imported_modules

    source_tree = ast.parse(PLUGIN_SOURCE.read_text(encoding="utf-8"), filename=str(PLUGIN_SOURCE))
    imported_modules = {
        node.module
        for node in ast.walk(source_tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert {
        "app.db.oper.site",
        "app.db.oper.systemconfig",
        "app.sdk.config",
        "app.sdk.events",
        "app.sdk.logging",
        "app.sdk.network",
        "app.sdk.plugins",
        "app.sdk.scheduler",
    } <= imported_modules
    assert "app.scheduler" not in imported_modules
    assert "from .trafficconfig import" in PLUGIN_SOURCE.read_text(encoding="utf-8")


def test_v3_metadata_and_version_contract_are_consistent():
    """V3 索引、类版本和旧代回退阻断标志保持一致。"""
    package_v3 = json.loads((REPO_ROOT / "package.v3.json").read_text(encoding="utf-8"))
    package_v2 = json.loads((REPO_ROOT / "package.v2.json").read_text(encoding="utf-8"))
    metadata = package_v3["TrafficAssistant"]

    assert TrafficAssistant.plugin_version == "2.0.0"
    assert metadata["version"] == TrafficAssistant.plugin_version
    assert metadata["system_version"] == ">=3.0.0"
    assert list(metadata["history"]) == ["v2.0.0"]
    assert metadata["history"]["v2.0.0"]
    assert package_v2["TrafficAssistant"]["v3"] is False


def test_v3_empty_capabilities_and_state_are_explicit():
    """未配置时返回稳定的布尔状态和空能力列表。"""
    plugin = object.__new__(TrafficAssistant)

    assert plugin.get_state() is False
    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() is None
    assert plugin.get_service() == []


def test_v4_enables_plugin_and_adds_site():
    config = {"enabled": False, "brushsites": [2]}

    (changed, _), update_config = _update_brush_site(config, site_id=1, enable=True)

    assert changed is True
    assert config == {"enabled": True, "brushsites": [2, 1]}
    update_config.assert_called_once_with(config=config, plugin_id="BrushFlow")


def test_v4_disables_only_matching_site():
    config = {"enabled": True, "brushsites": [1, 2]}

    (changed, _), update_config = _update_brush_site(config, site_id=1, enable=False)

    assert changed is True
    assert config == {"enabled": True, "brushsites": [2]}
    update_config.assert_called_once_with(config=config, plugin_id="BrushFlow")


def test_v5_enables_all_matching_tasks_and_global_switch():
    config = {
        "enabled": False,
        "tasks": [
            {"id": "site-1-a", "site_id": 1, "enabled": False},
            {"id": "site-2", "site_id": 2, "enabled": False},
            {"id": "site-1-b", "site_id": 1, "enabled": True},
        ],
    }

    (changed, _), update_config = _update_brush_site(config, site_id=1, enable=True)

    assert changed is True
    assert config["enabled"] is True
    assert [task["enabled"] for task in config["tasks"]] == [True, False, True]
    update_config.assert_called_once_with(config=config, plugin_id="BrushFlow")


def test_v5_disables_all_matching_tasks_without_disabling_plugin():
    config = {
        "enabled": True,
        "tasks": [
            {"id": "site-1-a", "site_id": 1, "enabled": True},
            {"id": "site-2", "site_id": 2, "enabled": True},
            {"id": "site-1-b", "site_id": 1, "enabled": False},
        ],
    }

    (changed, _), update_config = _update_brush_site(config, site_id=1, enable=False)

    assert changed is True
    assert config["enabled"] is True
    assert [task["enabled"] for task in config["tasks"]] == [False, True, False]
    update_config.assert_called_once_with(config=config, plugin_id="BrushFlow")


def test_v5_missing_site_does_not_enable_global_switch():
    config = {
        "enabled": False,
        "tasks": [{"id": "site-2", "site_id": 2, "enabled": False}],
    }

    (changed, message), update_config = _update_brush_site(config, site_id=1, enable=True)

    assert changed is False
    assert config["enabled"] is False
    assert "未找到" in message
    update_config.assert_not_called()


def _traffic_config(site_ids: list[int]) -> TrafficConfig:
    """构造启用低分享率刷流动作的多站点配置。"""
    return TrafficConfig(
        ratio_lower_limit=1,
        ratio_upper_limit=5,
        enable_auto_brush_if_below=True,
        brush_plugin="BrushFlow",
        site_infos={
            site_id: SimpleNamespace(name=f"站点{site_id}")
            for site_id in site_ids
        },
    )


def _site_statistics(site_ids: list[int]) -> dict:
    """构造触发低分享率动作的站点统计。"""
    return {
        f"站点{site_id}": {
            "success": True,
            "ratio": 0.5,
            "statistic_time": "2026-07-28",
        }
        for site_id in site_ids
    }


def test_v5_batch_saves_each_changed_site_before_single_reload():
    traffic_config = _traffic_config([1, 2])
    brush_config = {
        "enabled": True,
        "tasks": [
            {"id": "site-1", "site_id": 1, "enabled": False},
            {"id": "site-2", "site_id": 2, "enabled": False},
        ],
    }
    operations = []
    plugin = object.__new__(TrafficAssistant)
    plugin._traffic_config = traffic_config

    with (
        patch.object(TrafficAssistant, "get_config", return_value=brush_config),
        patch.object(
            TrafficAssistant,
            "update_config",
            side_effect=lambda **_kwargs: operations.append("save"),
        ),
        patch.object(
            TrafficAssistant,
            "_TrafficAssistant__reload_plugin",
            side_effect=lambda **_kwargs: operations.append("reload"),
        ),
    ):
        plugin._TrafficAssistant__auto_traffic(
            traffic_config=traffic_config,
            site_statistics=_site_statistics([1, 2]),
        )

    assert operations == ["save", "save", "reload"]
    assert [task["enabled"] for task in brush_config["tasks"]] == [True, True]


def test_v5_batch_does_not_reload_without_matching_task():
    traffic_config = _traffic_config([3])
    brush_config = {
        "enabled": False,
        "tasks": [{"id": "site-1", "site_id": 1, "enabled": False}],
    }
    plugin = object.__new__(TrafficAssistant)
    plugin._traffic_config = traffic_config

    with (
        patch.object(TrafficAssistant, "get_config", return_value=brush_config),
        patch.object(TrafficAssistant, "update_config") as update_config,
        patch.object(TrafficAssistant, "_TrafficAssistant__reload_plugin") as reload_plugin,
    ):
        plugin._TrafficAssistant__auto_traffic(
            traffic_config=traffic_config,
            site_statistics=_site_statistics([3]),
        )

    assert brush_config["enabled"] is False
    update_config.assert_not_called()
    reload_plugin.assert_not_called()


def test_site_config_overrides_global_thresholds():
    config = TrafficConfig(
        ratio_lower_limit=1,
        ratio_upper_limit=5,
        enable_site_config=True,
        site_config_str="- site_name: site-a\n  ratio_lower_limit: 2\n  ratio_upper_limit: 8\n",
    )

    site_config = config.get_site_config("site-a")

    assert site_config.ratio_lower_limit == 2.0
    assert site_config.ratio_upper_limit == 8.0
    assert config.get_site_config("unknown").ratio_lower_limit == 1.0
