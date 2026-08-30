"""WebhookNotify V3 的路由、鉴权与通知转发合同测试。"""

from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.adapters.web.security import access as web_security
from app.plugins.webhooknotify import WebhookNotify, WebhookNotifyPayload
from app.runtime.extensions.plugin.contracts import supports_plugin_hook
from app.schemas.message import Message
from app.schemas.response import Response
from app.schemas.token import TokenPayload
from app.schemas.types import MessageType
from app.sdk.config import settings
from app.sdk.security import (
    set_superuser_token_payload_provider,
    verify_apikey,
)


_TEST_API_TOKEN = "moviepilot-test-token"
_TEST_PLUGIN_API_KEY = "webhook-plugin-test-key"


@pytest.fixture(autouse=True)
def configure_host_api_credential():
    """为最小测试应用装配 V3 宿主 API 凭据对应的管理员身份端口。"""
    set_superuser_token_payload_provider(
        lambda: TokenPayload(
            sub=7,
            username="tester",
            super_user=True,
            level=1,
            purpose="authentication",
        ),
    )
    yield
    web_security.reset_superuser_token_payload_provider()


def _build_test_app(plugin: WebhookNotify) -> FastAPI:
    """按 V3 插件 API 元数据注册最小 FastAPI 应用。"""
    test_app = FastAPI()
    for source_api in plugin.get_api():
        api = source_api.copy()
        path = api.pop("path")
        auth = api.pop("auth")
        allow_anonymous = api.pop("allow_anonymous")
        dependencies = list(api.get("dependencies") or ())
        if not allow_anonymous:
            assert auth == "apikey"
            dependencies.append(Depends(verify_apikey))
        api["dependencies"] = dependencies
        test_app.add_api_route(path, **api)
    return test_app


def _mock_notification_chain(plugin: WebhookNotify) -> MagicMock:
    """替换通知链提交方法，便于检查最终 Message 合同。"""
    post_message = MagicMock()
    plugin.chain.post_message = post_message
    return post_message


def _assert_notification(
    post_message: MagicMock,
    *,
    mtype: MessageType,
    title: str | None = None,
    text: str | None = None,
) -> None:
    """确认通知只包含 Webhook 提供的消息字段。"""
    post_message.assert_called_once()
    notification = post_message.call_args.args[0]
    assert isinstance(notification, Message)
    assert notification.mtype == mtype
    assert notification.title == title
    assert notification.text == text
    assert notification.source is None
    assert notification.link is None


def test_payload_accepts_either_field_and_rejects_empty_message():
    assert WebhookNotifyPayload(title="告警").body is None
    assert WebhookNotifyPayload(body="故障").title is None
    assert WebhookNotifyPayload(title="告警", body="故障").body == "故障"

    with pytest.raises(ValidationError, match="title 和 body 至少提供一项"):
        WebhookNotifyPayload()
    with pytest.raises(ValidationError, match="title 和 body 至少提供一项"):
        WebhookNotifyPayload(title=" ", body="\n")


def test_api_uses_host_api_key_auth_without_plugin_key():
    plugin = WebhookNotify()
    plugin.init_plugin({"api_key": "   "})

    api_definitions = plugin.get_api()

    assert len(api_definitions) == 2
    assert {tuple(api["methods"]) for api in api_definitions} == {
        ("GET",),
        ("POST",),
    }
    assert all(api["path"] == "/webhook" for api in api_definitions)
    assert all(api["auth"] == "apikey" for api in api_definitions)
    assert all(api["allow_anonymous"] is False for api in api_definitions)
    assert all(api["dependencies"] == [] for api in api_definitions)
    assert all(api["response_model"] is Response for api in api_definitions)


def test_api_uses_plugin_key_dependency_when_configured():
    plugin = WebhookNotify()
    plugin.init_plugin({"api_key": _TEST_PLUGIN_API_KEY})

    api_definitions = plugin.get_api()

    assert all(api["auth"] == "apikey" for api in api_definitions)
    assert all(api["allow_anonymous"] is True for api in api_definitions)
    assert all(len(api["dependencies"]) == 1 for api in api_definitions)


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"headers": {"X-API-KEY": _TEST_API_TOKEN}},
        {"params": {"apikey": _TEST_API_TOKEN}},
    ],
)
def test_host_api_key_auth_accepts_public_api_token(monkeypatch, request_kwargs):
    plugin = WebhookNotify()
    plugin.init_plugin({"enabled": True})
    post_message = _mock_notification_chain(plugin)
    monkeypatch.setattr(settings, "API_TOKEN", _TEST_API_TOKEN)
    client = TestClient(_build_test_app(plugin))

    unauthorized = client.post("/webhook", json={"title": "未认证"})
    authorized = client.post(
        "/webhook",
        json={"title": "路由故障", "body": "主线路不可达"},
        **request_kwargs,
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json() == {
        "success": True,
        "message": "通知已提交",
        "data": {},
    }
    _assert_notification(
        post_message,
        mtype=MessageType.Plugin,
        title="路由故障",
        text="主线路不可达",
    )


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"headers": {"X-API-KEY": _TEST_PLUGIN_API_KEY}},
        {"params": {"apikey": _TEST_PLUGIN_API_KEY}},
    ],
)
def test_plugin_api_key_replaces_public_api_token(monkeypatch, request_kwargs):
    plugin = WebhookNotify()
    plugin.init_plugin({"enabled": True, "api_key": _TEST_PLUGIN_API_KEY})
    post_message = _mock_notification_chain(plugin)
    monkeypatch.setattr(settings, "API_TOKEN", _TEST_API_TOKEN)
    client = TestClient(_build_test_app(plugin))

    missing = client.post("/webhook", json={"title": "独立认证"})
    public_token = client.post(
        "/webhook",
        json={"title": "公共令牌"},
        headers={"X-API-KEY": _TEST_API_TOKEN},
    )
    wrong_header_overrides_query = client.post(
        f"/webhook?apikey={_TEST_PLUGIN_API_KEY}",
        json={"title": "错误头"},
        headers={"X-API-KEY": "wrong-key"},
    )
    authorized = client.post(
        "/webhook",
        json={"title": "独立认证"},
        **request_kwargs,
    )

    assert missing.status_code == 401
    assert public_token.status_code == 401
    assert wrong_header_overrides_query.status_code == 401
    assert authorized.status_code == 200
    _assert_notification(post_message, mtype=MessageType.Plugin, title="独立认证")


@pytest.mark.parametrize(
    ("payload", "expected_title", "expected_text"),
    [
        ({"title": "只有标题"}, "只有标题", None),
        ({"body": "只有正文"}, None, "只有正文"),
    ],
)
def test_post_accepts_title_or_body(
    monkeypatch,
    payload: dict[str, str],
    expected_title: str | None,
    expected_text: str | None,
):
    plugin = WebhookNotify()
    plugin.init_plugin({"enabled": True})
    post_message = _mock_notification_chain(plugin)
    monkeypatch.setattr(settings, "API_TOKEN", _TEST_API_TOKEN)
    client = TestClient(_build_test_app(plugin))

    response = client.post(
        f"/webhook?apikey={_TEST_API_TOKEN}",
        json=payload,
    )

    assert response.status_code == 200
    _assert_notification(
        post_message,
        mtype=MessageType.Plugin,
        title=expected_title,
        text=expected_text,
    )


@pytest.mark.parametrize(
    ("params", "expected_title", "expected_text"),
    [
        ({"title": "只有标题"}, "只有标题", None),
        ({"body": "只有正文"}, None, "只有正文"),
    ],
)
def test_get_accepts_title_or_body(
    monkeypatch,
    params: dict[str, str],
    expected_title: str | None,
    expected_text: str | None,
):
    plugin = WebhookNotify()
    plugin.init_plugin({"enabled": True})
    post_message = _mock_notification_chain(plugin)
    monkeypatch.setattr(settings, "API_TOKEN", _TEST_API_TOKEN)
    client = TestClient(_build_test_app(plugin))
    params["apikey"] = _TEST_API_TOKEN

    response = client.get("/webhook", params=params)

    assert response.status_code == 200
    _assert_notification(
        post_message,
        mtype=MessageType.Plugin,
        title=expected_title,
        text=expected_text,
    )


def test_get_and_post_reject_missing_content(monkeypatch):
    plugin = WebhookNotify()
    plugin.init_plugin({"enabled": True})
    post_message = _mock_notification_chain(plugin)
    monkeypatch.setattr(settings, "API_TOKEN", _TEST_API_TOKEN)
    client = TestClient(_build_test_app(plugin))

    post_response = client.post(f"/webhook?apikey={_TEST_API_TOKEN}", json={})
    get_response = client.get(f"/webhook?apikey={_TEST_API_TOKEN}")

    assert post_response.status_code == 422
    assert get_response.status_code == 422
    post_message.assert_not_called()


def test_disabled_plugin_returns_service_unavailable(monkeypatch):
    plugin = WebhookNotify()
    post_message = _mock_notification_chain(plugin)
    monkeypatch.setattr(settings, "API_TOKEN", _TEST_API_TOKEN)
    client = TestClient(_build_test_app(plugin))

    response = client.post(
        f"/webhook?apikey={_TEST_API_TOKEN}",
        json={"title": "标题"},
    )

    assert plugin.get_state() is False
    assert response.status_code == 503
    post_message.assert_not_called()


def test_configured_message_type_is_forwarded_or_defaults_to_plugin():
    plugin = WebhookNotify()
    plugin.init_plugin({"enabled": True, "notify_type": "Manual"})
    post_message = _mock_notification_chain(plugin)

    response = plugin.receive_webhook(WebhookNotifyPayload(title="标题"))

    assert response.success is True
    _assert_notification(post_message, mtype=MessageType.Manual, title="标题")

    plugin.init_plugin({"enabled": True, "notify_type": "invalid"})
    post_message.reset_mock()
    response = plugin.receive_webhook(WebhookNotifyPayload(title="标题"))

    assert response.success is True
    _assert_notification(post_message, mtype=MessageType.Plugin, title="标题")


def test_form_and_lifecycle_defaults():
    plugin = WebhookNotify()

    assert plugin.get_state() is False
    assert plugin.get_command() == []
    assert plugin.get_page() is None
    assert supports_plugin_hook(plugin, "get_page") is False
    _, defaults = plugin.get_form()
    assert defaults == {
        "enabled": False,
        "notify_type": MessageType.Plugin.name,
        "api_key": "",
    }


def test_logging_does_not_include_message_or_key(monkeypatch):
    plugin = WebhookNotify()
    plugin.init_plugin({"enabled": True, "api_key": _TEST_PLUGIN_API_KEY})
    _mock_notification_chain(plugin)
    log_info = MagicMock()
    monkeypatch.setattr("app.plugins.webhooknotify.logger.info", log_info)

    response = plugin.receive_webhook(
        WebhookNotifyPayload(title="敏感标题", body="敏感正文")
    )

    assert response.success is True
    logged_values = " ".join(
        str(value)
        for call in log_info.call_args_list
        for value in (*call.args, *call.kwargs.values())
    )
    assert "敏感标题" not in logged_values
    assert "敏感正文" not in logged_values
    assert _TEST_PLUGIN_API_KEY not in logged_values
