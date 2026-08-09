from typing import Annotated, Any, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from app import schemas
from app.core.security import verify_apitoken
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType


class WebhookNotifyPayload(BaseModel):
    """外部 Webhook 通知的消息载荷。"""

    # 标题和正文均可单独发送，避免调用方为缺失字段构造无意义占位文本。
    title: Optional[str] = Field(default=None, max_length=200)
    body: Optional[str] = Field(default=None, max_length=10000)

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
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/webhooknotify.png"
    plugin_version = "1.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "webhooknotify_"
    plugin_order = 999
    auth_level = 1

    _enabled = False
    # MoviePilot 通知渠道按消息类型过滤，默认使用专用的插件分类。
    _notify_type = NotificationType.Plugin

    def init_plugin(self, config: dict = None):
        """加载插件开关和消息类型；公共 API_TOKEN 不在插件配置中重复保存。"""
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        notify_type = config.get("notify_type", NotificationType.Plugin.name)
        self._notify_type = (
            NotificationType.__members__.get(notify_type, NotificationType.Plugin)
            if isinstance(notify_type, str)
            else NotificationType.Plugin
        )

    def get_state(self) -> bool:
        """返回 Webhook 接收能力是否启用。"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """Webhook 通知没有需要注册到聊天客户端的命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """注册使用公共 API_TOKEN 认证的入站 Webhook。"""
        return [
            {
                "path": "/webhook",
                "endpoint": self.receive_webhook,
                "methods": ["POST"],
                # 插件注册器的默认 apikey 只读取 X-API-KEY/apikey；认证依赖由
                # receive_webhook 的参数显式声明，以保持 MoviePilot 原生 ?token= 约定。
                "allow_anonymous": True,
                "response_model": schemas.Response,
                "summary": "接收 Webhook JSON 通知",
                "description": "使用 MoviePilot 公共 API_TOKEN 接收 JSON；title 和 body 至少提供一项。",
            },
            {
                "path": "/webhook",
                "endpoint": self.receive_webhook_get,
                "methods": ["GET"],
                "allow_anonymous": True,
                "response_model": schemas.Response,
                "summary": "接收 Webhook 查询通知",
                "description": "使用 MoviePilot 公共 API_TOKEN 接收查询参数；title 和 body 至少提供一项。",
            },
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
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
                                                for item in NotificationType
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
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "GET/POST /api/v1/plugin/WebhookNotify/webhook?token=API_TOKEN，title 和 body 至少提供一项。",
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
            "notify_type": NotificationType.Plugin.name,
        }

    def get_page(self) -> Optional[List[dict]]:
        """不提供插件数据页。"""
        pass

    def stop_service(self):
        """Webhook消息推送没有后台服务需要停止。"""
        pass

    def receive_webhook(
        self,
        payload: WebhookNotifyPayload,
        _: Annotated[str, Depends(verify_apitoken)],
    ) -> schemas.Response:
        """接收 POST JSON，并把外部消息交给 MoviePilot 通知链。"""
        return self._post_notification(payload, request_method="POST")

    def receive_webhook_get(
        self,
        _: Annotated[str, Depends(verify_apitoken)],
        title: Annotated[Optional[str], Query(max_length=200)] = None,
        body: Annotated[Optional[str], Query(max_length=10000)] = None,
    ) -> schemas.Response:
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

    def _post_notification(
        self,
        payload: WebhookNotifyPayload,
        request_method: str,
    ) -> schemas.Response:
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
            schemas.Notification(
                mtype=self._notify_type,
                title=payload.title,
                text=payload.body,
            )
        )
        logger.info("%s Webhook 消息已提交到 MoviePilot 通知链", request_method)
        return schemas.Response(success=True, message="通知已提交")
