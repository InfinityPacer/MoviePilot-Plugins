"""通过 Webhook 接收外部消息并提交到 MoviePilot 通知链。"""

from __future__ import annotations

from secrets import compare_digest
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Security, status
from pydantic import BaseModel, Field, model_validator

from app.plugins import _PluginBase
from app.schemas.message import Message
from app.schemas.response import Response
from app.schemas.types import MessageType
from app.sdk.logging import logger
from app.sdk.security import api_key_header, api_key_query


class WebhookNotifyPayload(BaseModel):
    """外部 Webhook 通知的消息载荷。"""

    # 标题和正文均可单独发送，避免调用方为缺失字段构造无意义占位文本。
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=10000)

    @model_validator(mode="after")
    def validate_message(self) -> "WebhookNotifyPayload":
        """把纯空白字段视为缺失，并保证通知至少包含一项可见内容。"""
        if self.title is not None and not self.title.strip():
            self.title = None
        if self.body is not None and not self.body.strip():
            self.body = None
        if self.title is None and self.body is None:
            raise ValueError("title 和 body 至少提供一项")
        return self


class WebhookNotify(_PluginBase):
    """接收入站 Webhook，并转发到 MoviePilot 已配置的通知渠道。"""

    plugin_name = "Webhook消息推送"
    plugin_desc = "接收 Webhook 消息并推送到通知客户端。"
    plugin_icon = (
        "https://raw.githubusercontent.com/InfinityPacer/"
        "MoviePilot-Plugins/main/icons/webhooknotify.png"
    )
    plugin_version = "2.0.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "webhooknotify_"
    plugin_order = 999
    auth_level = 1

    _enabled = False
    # MoviePilot 通知渠道按消息类型过滤，默认使用专用的插件分类。
    _notify_type = MessageType.Plugin
    _api_key = ""

    def init_plugin(self, config: dict | None = None) -> None:
        """加载插件开关、消息类型和可选的独立 API Key。"""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        notify_type = config.get("notify_type", MessageType.Plugin.name)
        self._notify_type = (
            MessageType.__members__.get(notify_type, MessageType.Plugin)
            if isinstance(notify_type, str)
            else MessageType.Plugin
        )
        api_key = config.get("api_key")
        self._api_key = api_key.strip() if isinstance(api_key, str) else ""

    def get_state(self) -> bool:
        """返回 Webhook 接收能力是否启用。"""
        return self._enabled

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        """Webhook 通知没有需要注册到聊天客户端的命令。"""
        return []

    def get_api(self) -> list[dict[str, Any]]:
        """按独立 Key 配置状态注册对应的入站认证方式。"""
        use_plugin_key = bool(self._api_key)
        dependencies = [Depends(self._verify_api_key)] if use_plugin_key else []
        return [
            {
                "path": "/webhook",
                "endpoint": self.receive_webhook,
                "methods": ["POST"],
                "auth": "apikey",
                "allow_anonymous": use_plugin_key,
                "dependencies": dependencies.copy(),
                "response_model": Response,
                "summary": "接收 Webhook JSON 通知",
                "description": "使用 API Key 接收 JSON；title 和 body 至少提供一项。",
            },
            {
                "path": "/webhook",
                "endpoint": self.receive_webhook_get,
                "methods": ["GET"],
                "auth": "apikey",
                "allow_anonymous": use_plugin_key,
                "dependencies": dependencies.copy(),
                "response_model": Response,
                "summary": "接收 Webhook 查询通知",
                "description": "使用 API Key 接收查询参数；title 和 body 至少提供一项。",
            },
        ]

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        """展示启用开关、消息类型和入站请求约定。"""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "notify_type",
                                            "label": "消息类型",
                                            "items": [
                                                {"title": item.value, "value": item.name}
                                                for item in MessageType
                                            ],
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "api_key",
                                            "label": "APIKEY",
                                            "type": "password",
                                            "placeholder": "留空则使用主程序 API Token",
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": (
                                                "GET/POST /api/v1/plugin/"
                                                "WebhookNotify/webhook，使用 X-API-KEY "
                                                "或 apikey 认证，title 和 body 至少提供一项。"
                                            ),
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "notify_type": MessageType.Plugin.name,
            "api_key": "",
        }

    def get_page(self) -> None:
        """保持空钩子，使宿主不声明详情页能力。"""
        pass

    def stop_service(self) -> None:
        """Webhook消息推送没有后台服务需要停止。"""

    def receive_webhook(self, payload: WebhookNotifyPayload) -> Response:
        """接收 POST JSON，并把外部消息交给 MoviePilot 通知链。"""
        return self._post_notification(payload, request_method="POST")

    def receive_webhook_get(
        self,
        title: Annotated[str | None, Query(max_length=200)] = None,
        body: Annotated[str | None, Query(max_length=10000)] = None,
    ) -> Response:
        """接收 GET 查询参数，并把外部消息交给 MoviePilot 通知链。"""
        if not ((title and title.strip()) or (body and body.strip())):
            raise HTTPException(
                status_code=422,
                detail="title 和 body 至少提供一项",
            )
        return self._post_notification(
            WebhookNotifyPayload(title=title, body=body),
            request_method="GET",
        )

    def _verify_api_key(
        self,
        key_query: Annotated[str | None, Security(api_key_query)] = None,
        key_header: Annotated[str | None, Security(api_key_header)] = None,
    ) -> str:
        """校验插件独立 Key。"""
        supplied_key = key_header or key_query
        if (
            not supplied_key
            or not self._api_key
            or not compare_digest(supplied_key, self._api_key)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key 校验不通过",
            )
        return supplied_key

    def _post_notification(
        self,
        payload: WebhookNotifyPayload,
        request_method: str,
    ) -> Response:
        """执行统一的启用状态检查和通知提交。"""
        if not self._enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook消息推送插件未启用",
            )

        logger.info(
            "接收 %s Webhook 消息，消息类型：%s，包含标题：%s，包含正文：%s",
            request_method,
            self._notify_type.value,
            bool(payload.title),
            bool(payload.body),
        )
        self.chain.post_message(
            Message(
                mtype=self._notify_type,
                title=payload.title,
                text=payload.body,
            )
        )
        logger.info("%s Webhook 消息已提交到 MoviePilot 通知链", request_method)
        return Response(success=True, message="通知已提交", data={})
