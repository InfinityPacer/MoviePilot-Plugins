"""Commands 的配置、事件和生命周期合同测试。"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from app.plugins.commands import Commands
from app.runtime.extensions.plugin.contracts import supports_plugin_hook
from app.schemas.event import CommandRegisterEventData
from app.schemas.types import ChainEventType
from app.sdk.events import Event


def _plugin(
    *,
    notify_clients=None,
    custom_commands=None,
    services=None,
    notify_helper=None,
) -> Commands:
    """构造不依赖完整插件 Runtime 的纯逻辑实例。"""
    plugin = object.__new__(Commands)
    plugin.notify_helper = notify_helper or MagicMock()
    plugin._enabled = True
    plugin._notify_clients = list(notify_clients or [])
    plugin._custom_commands = custom_commands or {}
    plugin.notify_helper.get_services.return_value = services or {}
    return plugin


def _event(*, origin="WeChat", service="Telegram", commands=None, cancel=False):
    """构造经过宿主事件合同校验的命令注册事件。"""
    payload = CommandRegisterEventData(
        commands=commands or {},
        origin=origin,
        service=service,
        cancel=cancel,
    )
    return Event(ChainEventType.CommandRegister, payload)


def test_v3_source_uses_sdk_boundaries_and_public_command_schema():
    """Commands V3 实现仅从 SDK 获取事件、通知服务和日志入口。"""
    source = (
        Path(__file__).parents[3] / "plugins.v3" / "commands" / "__init__.py"
    ).read_text(encoding="utf-8")

    assert "from app.sdk.events import Event, eventmanager" in source
    assert "from app.sdk.logging import logger" in source
    assert "from app.sdk.services import NotificationHelper" in source
    assert "from app.schemas.event import CommandRegisterEventData" in source
    assert "from app.schemas.types import ChainEventType" in source
    for legacy_prefix in (
        "from app.compat",
        "from app.core",
        "from app.helper",
        "from app.log",
        "from app.db",
    ):
        assert legacy_prefix not in source


def test_init_plugin_parses_json_and_resets_state(monkeypatch):
    """重载时应解析 JSON 菜单并清理上一次实例遗留的选择。"""
    helper = MagicMock()
    monkeypatch.setattr("app.plugins.commands.NotificationHelper", lambda: helper)
    plugin = object.__new__(Commands)

    plugin.init_plugin(
        {
            "enabled": 1,
            "notify_clients": ("Telegram", "WeChat"),
            "custom_commands": json.dumps(
                {"Telegram": {"/sites": {"category": "站点"}}}
            ),
        }
    )

    assert plugin.get_state() is True
    assert plugin._notify_clients == ["Telegram", "WeChat"]
    assert plugin._custom_commands == {
        "Telegram": {"/sites": {"category": "站点"}}
    }

    plugin.init_plugin({"enabled": False, "custom_commands": "{"})

    assert plugin.get_state() is False
    assert plugin._notify_clients == []
    assert plugin._custom_commands == {}
    assert helper is plugin.notify_helper


def test_service_infos_filters_selected_notification_clients():
    """通知服务查询必须把用户选择的客户端名称传给 SDK。"""
    helper = MagicMock()
    services = {"Telegram": object()}
    plugin = _plugin(
        notify_clients=["Telegram", "WeChat"],
        services=services,
        notify_helper=helper,
    )

    assert plugin.service_infos == services
    helper.get_services.assert_called_once_with(
        name_filters=["Telegram", "WeChat"]
    )


def test_command_chain_origin_persists_preset_commands_without_intercepting():
    """CommandChain 来源只更新预置命令快照，不拦截事件。"""
    plugin = _plugin(notify_clients=[])
    plugin.get_config = MagicMock(return_value={"enabled": True})
    plugin.update_config = MagicMock()
    commands = {"/sites": {"category": "站点", "description": "查询站点"}}
    event = _event(origin="CommandChain", commands=commands)

    plugin.handle_command_register(event)

    plugin.get_config.assert_called_once_with()
    plugin.update_config.assert_called_once_with(
        config={
            "enabled": True,
            "preset_commands": json.dumps(commands, indent=4, ensure_ascii=False),
        }
    )
    assert event.event_data.cancel is False


def test_unsupported_origin_is_passed_through():
    """非微信和 Telegram 来源保持原始事件，不触发客户端筛选。"""
    helper = MagicMock()
    plugin = _plugin(
        notify_clients=["Telegram"],
        notify_helper=helper,
        services={"Telegram": object()},
    )
    event = _event(origin="Slack", commands={"/sites": {"category": "站点"}})

    plugin.handle_command_register(event)

    assert event.event_data.cancel is False
    assert event.event_data.source == "未知拦截源"
    helper.get_services.assert_not_called()


def test_unselected_notification_client_is_intercepted():
    """未选中的通知客户端必须取消命令注册，避免泄漏完整菜单。"""
    plugin = _plugin(notify_clients=["Telegram"], services={})
    event = _event(origin="WeChat", service="WeChat")

    plugin.handle_command_register(event)

    assert event.event_data.cancel is True
    assert event.event_data.source == plugin.plugin_name


def test_selected_client_is_allowed_and_commands_are_pruned_and_overridden():
    """选中客户端仅保留自定义命令，并覆盖允许声明的菜单字段。"""
    plugin = _plugin(
        notify_clients=["Telegram"],
        services={"Telegram": object()},
        custom_commands={
            "Telegram": {
                "/sites": {"category": "自定义站点"},
            }
        },
    )
    commands = {
        "/sites": {
            "category": "站点",
            "description": "查询站点",
            "event": "sites",
        },
        "/version": {
            "category": "管理",
            "description": "当前版本",
            "event": "version",
        },
    }
    event = _event(origin="Telegram", service="Telegram", commands=commands)

    plugin.handle_command_register(event)

    assert event.event_data.cancel is False
    assert event.event_data.source == plugin.plugin_name
    assert event.event_data.commands == {
        "/sites": {
            "category": "自定义站点",
            "description": "查询站点",
            "event": "sites",
        }
    }


def test_selected_client_without_custom_commands_is_allowed_unchanged():
    """客户端已选中但没有自定义菜单时，保留宿主预置命令。"""
    plugin = _plugin(
        notify_clients=["Telegram"],
        services={"Telegram": object()},
    )
    commands = {"/sites": {"category": "站点", "description": "查询站点"}}
    event = _event(origin="Telegram", service="Telegram", commands=commands)

    plugin.handle_command_register(event)

    assert event.event_data.cancel is False
    assert event.event_data.commands == commands


def test_already_cancelled_event_is_not_modified():
    """已被其他处理器取消的事件必须保持原状态并跳过客户端查询。"""
    helper = MagicMock()
    plugin = _plugin(
        notify_clients=["Telegram"],
        notify_helper=helper,
        services={"Telegram": object()},
    )
    event = _event(origin="Telegram", service="Telegram", cancel=True)

    plugin.handle_command_register(event)

    assert event.event_data.cancel is True
    assert event.event_data.source == "未知拦截源"
    helper.get_services.assert_not_called()


def test_lifecycle_and_empty_capabilities_contract(monkeypatch):
    """插件生命周期与无自有命令、API、页面和服务的声明保持稳定。"""
    helper = MagicMock()
    monkeypatch.setattr("app.plugins.commands.NotificationHelper", lambda: helper)
    plugin = object.__new__(Commands)

    plugin.init_plugin()

    assert plugin.get_state() is False
    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() is None
    assert supports_plugin_hook(plugin, "get_page") is False
    assert plugin.get_service() == []
    plugin.stop_service()


def test_default_form_commands_are_valid_json():
    """配置表单提供的预置示例必须可直接解析。"""
    plugin = _plugin()
    _form, defaults = plugin.get_form()

    assert defaults["enabled"] is False
    assert json.loads(defaults["custom_commands"])["通知渠道1"]["/sites"]
