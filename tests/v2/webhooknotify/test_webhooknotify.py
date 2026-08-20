from typing import Optional
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.security import verify_apikey
from app.schemas.types import NotificationType
from app.utils.object import ObjectUtils

import app.plugins.webhooknotify as webhooknotify
from app.plugins.webhooknotify import WebhookNotify, WebhookNotifyPayload


def _build_test_app(plugin: WebhookNotify) -> FastAPI:
    """按插件 API 元数据注册最小 FastAPI 应用，覆盖真实依赖注入契约。"""
    test_app = FastAPI()
    for api_definition in plugin.get_api():
        api = api_definition.copy()
        path = api.pop("path")
        allow_anonymous = api.pop("allow_anonymous")
        dependencies = api.setdefault("dependencies", [])
        if not allow_anonymous:
            dependencies.append(Depends(verify_apikey))
        test_app.add_api_route(path, **api)
    return test_app


def _mock_notification_chain(plugin: WebhookNotify) -> MagicMock:
    """替换通知链提交方法，便于检查最终 Notification 契约。"""
    post_message = MagicMock()
    plugin.chain.post_message = post_message
    return post_message


def _assert_notification(
    post_message: MagicMock,
    *,
    mtype: NotificationType,
    title: Optional[str] = None,
    text: Optional[str] = None,
) -> None:
    """确认消息不绑定渠道配置，也不附加默认插件详情链接。"""
    post_message.assert_called_once()
    notification = post_message.call_args.args[0]
    assert notification.mtype == mtype
    assert notification.title == title
    assert notification.text == text
    assert notification.source is None
    assert notification.link is None


class TestWebhookNotify:
    """Webhook 请求校验、双模式 API Key 认证和通知转发契约。"""

    def test_payload_accepts_either_field_and_rejects_empty_message(self):
        assert WebhookNotifyPayload(title="告警").body is None
        assert WebhookNotifyPayload(body="故障").title is None
        assert WebhookNotifyPayload(title="告警", body="故障").body == "故障"

        with pytest.raises(ValidationError, match="title 和 body 至少提供一项"):
            WebhookNotifyPayload()
        with pytest.raises(ValidationError, match="title 和 body 至少提供一项"):
            WebhookNotifyPayload(title=" ", body="\n")

    def test_api_uses_default_auth_without_plugin_key(self):
        plugin = WebhookNotify()
        plugin.init_plugin({"api_key": "   "})
        api_definitions = plugin.get_api()

        assert len(api_definitions) == 2
        assert {tuple(api["methods"]) for api in api_definitions} == {("GET",), ("POST",)}
        assert all(api["path"] == "/webhook" for api in api_definitions)
        assert all(api["allow_anonymous"] is False for api in api_definitions)
        assert all(api.get("dependencies") == [] for api in api_definitions)
        assert all(api["response_model"] for api in api_definitions)

    def test_api_uses_plugin_auth_when_plugin_key_is_configured(self):
        plugin = WebhookNotify()
        plugin.init_plugin({"api_key": "plugin-key"})

        api_definitions = plugin.get_api()

        assert all(api["allow_anonymous"] is True for api in api_definitions)
        assert all(len(api["dependencies"]) == 1 for api in api_definitions)

    def test_data_page_is_not_exposed(self):
        assert WebhookNotify().get_page() is None
        assert ObjectUtils.check_method(WebhookNotify.get_page) is False

    def test_form_defaults_to_disabled_and_exposes_all_notification_types(self):
        plugin = WebhookNotify()
        form, defaults = plugin.get_form()
        enabled_row = form[0]["content"][0]
        notify_type_row = form[0]["content"][1]
        api_key_row = form[0]["content"][2]
        enabled_field = enabled_row["content"][0]["content"][0]
        notify_type_field = notify_type_row["content"][0]["content"][0]
        api_key_field = api_key_row["content"][0]["content"][0]

        assert defaults == {
            "enabled": False,
            "notify_type": NotificationType.Plugin.name,
            "api_key": "",
        }
        assert enabled_row["component"] == "VRow"
        assert notify_type_row["component"] == "VRow"
        assert notify_type_row["content"][0]["props"] == {"cols": 12, "md": 6}
        assert "hint" not in enabled_field["props"]
        assert "persistent-hint" not in enabled_field["props"]
        assert notify_type_field["props"]["label"] == "消息类型"
        assert "hint" not in notify_type_field["props"]
        assert "persistent-hint" not in notify_type_field["props"]
        assert notify_type_field["props"]["items"] == [
            {"title": item.value, "value": item.name}
            for item in NotificationType
        ]
        assert api_key_row["component"] == "VRow"
        assert api_key_row["content"][0]["props"] == {"cols": 12, "md": 6}
        assert api_key_field["component"] == "VTextField"
        assert api_key_field["props"]["model"] == "api_key"
        assert api_key_field["props"]["label"] == "APIKEY"
        assert api_key_field["props"]["type"] == "password"
        info_row = form[0]["content"][3]
        assert info_row["component"] == "VRow"
        assert info_row["content"][0]["component"] == "VCol"
        assert info_row["content"][0]["props"] == {"cols": 12}
        assert info_row["content"][0]["content"][0]["component"] == "VAlert"

    @pytest.mark.parametrize(
        ("request_kwargs",),
        [
            ({"headers": {"X-API-KEY": "moviepilot-key"}},),
            ({"params": {"apikey": "moviepilot-key"}},),
        ],
    )
    def test_default_auth_accepts_public_api_token(
        self,
        monkeypatch,
        request_kwargs,
    ):
        plugin = WebhookNotify()
        plugin.init_plugin({"enabled": True})
        post_message = _mock_notification_chain(plugin)
        monkeypatch.setattr(settings, "API_TOKEN", "moviepilot-key")
        client = TestClient(_build_test_app(plugin))
        payload = {"title": "路由故障", "body": "主线路不可达"}

        unauthorized = client.post("/webhook", json=payload)
        authorized = client.post("/webhook", json=payload, **request_kwargs)

        assert unauthorized.status_code == 401
        assert authorized.status_code == 200
        assert authorized.json()["success"] is True
        _assert_notification(
            post_message,
            mtype=NotificationType.Plugin,
            title="路由故障",
            text="主线路不可达",
        )

    @pytest.mark.parametrize(
        ("request_kwargs",),
        [
            ({"headers": {"X-API-KEY": "plugin-key"}},),
            ({"params": {"apikey": "plugin-key"}},),
        ],
    )
    def test_plugin_key_replaces_public_api_token(
        self,
        monkeypatch,
        request_kwargs,
    ):
        plugin = WebhookNotify()
        plugin.init_plugin({"enabled": True, "api_key": "plugin-key"})
        post_message = _mock_notification_chain(plugin)
        monkeypatch.setattr(settings, "API_TOKEN", "moviepilot-key")
        client = TestClient(_build_test_app(plugin))
        payload = {"title": "独立认证"}

        missing = client.post("/webhook", json=payload)
        public_token = client.post(
            "/webhook",
            json=payload,
            headers={"X-API-KEY": "moviepilot-key"},
        )
        wrong_header_overrides_query = client.post(
            "/webhook?apikey=plugin-key",
            json=payload,
            headers={"X-API-KEY": "wrong-key"},
        )
        authorized = client.post("/webhook", json=payload, **request_kwargs)

        assert missing.status_code == 401
        assert public_token.status_code == 401
        assert wrong_header_overrides_query.status_code == 401
        assert authorized.status_code == 200
        _assert_notification(
            post_message,
            mtype=NotificationType.Plugin,
            title="独立认证",
        )

    @pytest.mark.parametrize(
        ("payload", "expected_title", "expected_text"),
        [
            ({"title": "只有标题"}, "只有标题", None),
            ({"body": "只有正文"}, None, "只有正文"),
        ],
    )
    def test_post_accepts_title_or_body(self, monkeypatch, payload, expected_title, expected_text):
        plugin = WebhookNotify()
        plugin.init_plugin({"enabled": True})
        post_message = _mock_notification_chain(plugin)
        monkeypatch.setattr(settings, "API_TOKEN", "unit-test-token")
        client = TestClient(_build_test_app(plugin))

        response = client.post("/webhook?apikey=unit-test-token", json=payload)

        assert response.status_code == 200
        _assert_notification(
            post_message,
            mtype=NotificationType.Plugin,
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
    def test_get_accepts_title_or_body(self, monkeypatch, params, expected_title, expected_text):
        plugin = WebhookNotify()
        plugin.init_plugin({"enabled": True})
        post_message = _mock_notification_chain(plugin)
        monkeypatch.setattr(settings, "API_TOKEN", "unit-test-token")
        client = TestClient(_build_test_app(plugin))
        params["apikey"] = "unit-test-token"

        response = client.get("/webhook", params=params)

        assert response.status_code == 200
        _assert_notification(
            post_message,
            mtype=NotificationType.Plugin,
            title=expected_title,
            text=expected_text,
        )

    def test_submission_logs_metadata_without_message_content(self, monkeypatch):
        plugin = WebhookNotify()
        plugin.init_plugin({"enabled": True, "api_key": "unit-test-token"})
        _mock_notification_chain(plugin)
        log_info = MagicMock()
        monkeypatch.setattr(webhooknotify.logger, "info", log_info)
        client = TestClient(_build_test_app(plugin))

        response = client.post(
            "/webhook",
            headers={"X-API-KEY": "unit-test-token"},
            json={"title": "敏感标题", "body": "敏感正文"},
        )

        assert response.status_code == 200
        assert log_info.call_count == 2
        logged_values = " ".join(
            str(value)
            for call in log_info.call_args_list
            for value in (*call.args, *call.kwargs.values())
        )
        assert "POST" in logged_values
        assert "敏感标题" not in logged_values
        assert "敏感正文" not in logged_values
        assert "unit-test-token" not in logged_values

    def test_get_and_post_reject_missing_content(self, monkeypatch):
        plugin = WebhookNotify()
        plugin.init_plugin({"enabled": True})
        post_message = _mock_notification_chain(plugin)
        monkeypatch.setattr(settings, "API_TOKEN", "unit-test-token")
        client = TestClient(_build_test_app(plugin))

        post_response = client.post("/webhook?apikey=unit-test-token", json={})
        get_response = client.get("/webhook?apikey=unit-test-token")

        assert post_response.status_code == 422
        assert get_response.status_code == 422
        post_message.assert_not_called()

    def test_plugin_defaults_to_disabled_and_returns_service_unavailable(self):
        plugin = WebhookNotify()
        post_message = _mock_notification_chain(plugin)

        assert plugin.get_state() is False

        with pytest.raises(HTTPException) as exc_info:
            plugin.receive_webhook(WebhookNotifyPayload(title="标题"))

        assert exc_info.value.status_code == 503
        post_message.assert_not_called()

    def test_missing_enabled_config_keeps_plugin_disabled(self):
        plugin = WebhookNotify()

        plugin.init_plugin({"notify_type": NotificationType.Manual.name})

        assert plugin.get_state() is False

    @pytest.mark.parametrize(
        ("notify_type", "expected_type"),
        [
            ("Manual", NotificationType.Manual),
            ("invalid", NotificationType.Plugin),
            (None, NotificationType.Plugin),
        ],
    )
    def test_configured_notification_type_is_forwarded_or_defaults_to_plugin(
        self,
        notify_type,
        expected_type,
    ):
        plugin = WebhookNotify()
        plugin.init_plugin({"enabled": True, "notify_type": notify_type})
        post_message = _mock_notification_chain(plugin)

        response = plugin.receive_webhook(
            WebhookNotifyPayload(title="标题"),
        )

        assert response.success is True
        _assert_notification(
            post_message,
            mtype=expected_type,
            title="标题",
            text=None,
        )
