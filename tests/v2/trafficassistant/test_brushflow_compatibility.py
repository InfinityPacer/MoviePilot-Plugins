"""站点流量管理对不同版本站点刷流配置契约的兼容性测试。"""

from types import SimpleNamespace
from unittest.mock import patch

from app.plugins.trafficassistant import TrafficAssistant
from app.plugins.trafficassistant.trafficconfig import TrafficConfig


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
