"""AuxiliaryAuth V3 的认证事件、服务筛选和生命周期合同测试。"""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.plugins import auxiliaryauth
from app.plugins.auxiliaryauth import AuxiliaryAuth
from app.runtime.extensions.plugin.contracts import supports_plugin_hook
from app.schemas.event import AuthInterceptCredentials
from app.schemas.types import ChainEventType
from app.sdk.events import Event


def _plugin(*, enabled: bool = True, mediaservers: list[str] | None = None) -> AuxiliaryAuth:
    """构造不依赖完整插件 Runtime 的纯逻辑实例。"""
    plugin = object.__new__(AuxiliaryAuth)
    plugin.mediaserver_helper = MagicMock()
    plugin._enabled = enabled
    plugin._mediaservers = ["Plex A"] if mediaservers is None else mediaservers
    plugin._allow_anonymous = False
    return plugin


def _service(name: str, *, inactive: bool = False, instance: bool = True) -> SimpleNamespace:
    """构造媒体服务信息及可控的连接状态。"""
    service_instance = (
        SimpleNamespace(is_inactive=MagicMock(return_value=inactive))
        if instance
        else None
    )
    return SimpleNamespace(name=name, instance=service_instance, type="plex")


def _event(*, channel: str = "Plex", service: str = "Plex A", cancel: bool = False) -> Event:
    """构造经过认证事件 schema 校验的链式事件。"""
    payload = AuthInterceptCredentials(
        username="alice",
        channel=channel,
        service=service,
        status="completed",
        token="test-token",
        cancel=cancel,
    )
    return Event(ChainEventType.AuthIntercept, payload)


def test_v3_source_uses_sdk_boundaries_and_public_auth_schema() -> None:
    """V3 实现通过公开 SDK 访问事件、日志和媒体服务，认证载荷使用公开 schema。"""
    source_path = Path(__file__).parents[3] / "plugins.v3" / "auxiliaryauth" / "__init__.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert AuxiliaryAuth.plugin_version == "2.0.0"
    assert "app.sdk.events" in imported_modules
    assert "app.sdk.logging" in imported_modules
    assert "app.sdk.services" in imported_modules
    assert "app.schemas.event" in imported_modules
    assert not any(
        module.startswith(
            ("app.compat", "app.core", "app.helper", "app.log", "app.utils", "app.db")
        )
        for module in imported_modules
    )


def test_init_plugin_resets_state_and_parses_selection(monkeypatch) -> None:
    """重载配置时应重置开关、媒体服务选择和历史匿名认证状态。"""
    helper = MagicMock()
    monkeypatch.setattr(auxiliaryauth, "MediaServerHelper", lambda: helper)
    plugin = object.__new__(AuxiliaryAuth)
    plugin._enabled = True
    plugin._mediaservers = ["old"]
    plugin._allow_anonymous = True

    plugin.init_plugin({"enabled": False, "mediaservers": ("Plex A",), "allow_anonymous": False})

    assert plugin.mediaserver_helper is helper
    assert plugin.get_state() is False
    assert plugin._mediaservers == ["Plex A"]
    assert plugin._allow_anonymous is False

    plugin.init_plugin()
    assert plugin.get_state() is False
    assert plugin._mediaservers == []
    assert plugin._allow_anonymous is False


def test_service_infos_returns_only_connected_selected_services() -> None:
    """服务目录只保留配置选中的可用实例，并安全处理空实例。"""
    plugin = _plugin(mediaservers=["Plex A", "Plex B", "Plex C"])
    active = _service("Plex A")
    inactive = _service("Plex B", inactive=True)
    missing = _service("Plex C", instance=False)
    plugin.mediaserver_helper.get_services.return_value = {
        "Plex A": active,
        "Plex B": inactive,
        "Plex C": missing,
    }

    assert plugin.service_infos == {"Plex A": active}
    plugin.mediaserver_helper.get_services.assert_called_once_with(
        name_filters=["Plex A", "Plex B", "Plex C"]
    )


def test_service_infos_returns_none_without_selection_or_available_service() -> None:
    """没有选中服务或没有可用实例时返回空结果。"""
    plugin = _plugin(mediaservers=[])
    assert plugin.service_infos is None
    plugin.mediaserver_helper.get_services.assert_not_called()

    plugin._mediaservers = ["Plex A"]
    plugin.mediaserver_helper.get_services.return_value = {}
    assert plugin.service_infos is None


def test_disabled_plugin_does_not_touch_auth_event() -> None:
    """停用插件必须保持认证事件不变，也不能查询媒体服务。"""
    plugin = _plugin(enabled=False)
    event = _event()

    plugin.handle_auth_intercept(event)

    assert event.event_data.cancel is False
    assert event.event_data.source == "未知拦截源"
    plugin.mediaserver_helper.get_services.assert_not_called()


def test_already_cancelled_event_is_not_modified() -> None:
    """已被其他处理器拦截的事件必须保持原状态。"""
    plugin = _plugin()
    event = _event(cancel=True)

    plugin.handle_auth_intercept(event)

    assert event.event_data.cancel is True
    assert event.event_data.source == "未知拦截源"
    plugin.mediaserver_helper.get_services.assert_not_called()


@pytest.mark.parametrize("channel", ["Emby", "Jellyfin", "Plex"])
def test_selected_connected_supported_channel_is_allowed(channel: str) -> None:
    """三个受支持渠道在已选且连接的服务上允许认证通过。"""
    plugin = _plugin()
    service = _service("Plex A")
    plugin.mediaserver_helper.get_services.return_value = {"Plex A": service}
    event = _event(channel=channel)

    plugin.handle_auth_intercept(event)

    assert event.event_data.cancel is False
    assert event.event_data.source == "未知拦截源"


def test_supported_channel_is_intercepted_when_service_is_unavailable() -> None:
    """受支持渠道找不到已连接服务时必须取消认证并标记来源。"""
    plugin = _plugin()
    plugin.mediaserver_helper.get_services.return_value = {
        "Plex A": _service("Plex A", inactive=True)
    }
    event = _event(channel="Plex", service="Plex A")

    plugin.handle_auth_intercept(event)

    assert event.event_data.cancel is True
    assert event.event_data.source == plugin.plugin_name


def test_unsupported_channel_is_passed_through_without_service_lookup() -> None:
    """未支持渠道不由插件判断，保持事件原状态并放行后续处理器。"""
    plugin = _plugin()
    event = _event(channel="Navidrome")

    plugin.handle_auth_intercept(event)

    assert event.event_data.cancel is False
    assert event.event_data.source == "未知拦截源"
    plugin.mediaserver_helper.get_services.assert_not_called()


def test_lifecycle_and_empty_capabilities_are_explicit() -> None:
    """插件无命令、API、后台服务和详情页时显式返回空能力。"""
    plugin = _plugin(enabled=False)

    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() is None
    assert supports_plugin_hook(plugin, "get_page") is False
    assert plugin.get_service() == []
    plugin.stop_service()


def test_form_exposes_configured_media_server_names() -> None:
    """配置表单应从公开媒体服务助手读取服务名称，并提供空选择默认值。"""
    plugin = _plugin(enabled=False)
    plugin.mediaserver_helper.get_configs.return_value = {
        "Plex A": SimpleNamespace(name="Plex A", type="plex"),
        "Emby A": SimpleNamespace(name="Emby A", type="emby"),
    }

    form, defaults = plugin.get_form()
    select = form[0]["content"][1]["content"][0]["content"][0]

    assert select["component"] == "VSelect"
    assert select["props"]["items"] == [
        {"title": "Plex A", "value": "Plex A"},
        {"title": "Emby A", "value": "Emby A"},
    ]
    assert defaults == {
        "enabled": False,
        "mediaservers": [],
        "allow_anonymous": False,
    }
