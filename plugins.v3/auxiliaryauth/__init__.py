"""按已连接的媒体服务限制外部媒体服务器认证。"""

from __future__ import annotations

from typing import Any, ClassVar

from app.plugins import _PluginBase
from app.schemas.event import AuthInterceptCredentials
from app.schemas.system import ServiceInfo
from app.schemas.types import ChainEventType
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.sdk.services import MediaServerHelper


class AuxiliaryAuth(_PluginBase):
    """只允许配置且已连接的媒体服务通过认证拦截事件。"""

    plugin_name = "辅助认证"
    plugin_desc = "支持使用第三方系统进行辅助认证。"
    plugin_icon = (
        "https://raw.githubusercontent.com/InfinityPacer/"
        "MoviePilot-Plugins/main/icons/auxiliaryauth.png"
    )
    plugin_version = "2.0.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "auxiliaryauth_"
    plugin_order = 41
    auth_level = 1

    _SUPPORTED_CHANNELS: ClassVar[frozenset[str]] = frozenset(
        ("Emby", "Jellyfin", "Plex")
    )
    mediaserver_helper: MediaServerHelper | None = None
    _enabled = False
    _mediaservers: ClassVar[list[str]] = []
    _allow_anonymous = False

    def init_plugin(self, config: dict | None = None) -> None:
        """加载开关和媒体服务选择，并在重载时清理旧配置状态。"""
        self.mediaserver_helper = MediaServerHelper()
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        mediaservers = config.get("mediaservers") or []
        self._mediaservers = (
            list(mediaservers)
            if isinstance(mediaservers, (list, tuple, set))
            else []
        )
        self._allow_anonymous = bool(config.get("allow_anonymous", False))

    @property
    def service_infos(self) -> dict[str, ServiceInfo] | None:
        """返回配置选中且当前有可用实例的媒体服务。"""
        if not self._mediaservers:
            logger.warning("尚未配置媒体服务器，请检查配置")
            return None

        if not self.mediaserver_helper:
            self.mediaserver_helper = MediaServerHelper()
        services = self.mediaserver_helper.get_services(name_filters=self._mediaservers)
        if not services:
            logger.warning("获取媒体服务器实例失败，请检查配置")
            return None

        active_services: dict[str, ServiceInfo] = {}
        for service_name, service_info in services.items():
            if not service_info.instance or service_info.instance.is_inactive():
                logger.warning(f"媒体服务器 {service_name} 未连接，请检查配置")
            else:
                active_services[service_name] = service_info

        if not active_services:
            logger.warning("没有已连接的媒体服务器，请检查配置")
            return None
        return active_services

    def get_state(self) -> bool:
        """返回插件是否启用。"""
        return self._enabled

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        """本插件不注册远程控制命令。"""
        return []

    def get_api(self) -> list[dict[str, Any]]:
        """本插件不暴露自有 HTTP API。"""
        return []

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        """拼装插件配置页面和默认配置。"""
        if not self.mediaserver_helper:
            self.mediaserver_helper = MediaServerHelper()
        media_server_items = [
            {"title": config.name, "value": config.name}
            for config in self.mediaserver_helper.get_configs().values()
            if config.name
        ]
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                            "hint": "开启后插件将处于激活状态",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            }
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
                                        "component": "VSelect",
                                        "props": {
                                            "multiple": True,
                                            "chips": True,
                                            "clearable": True,
                                            "model": "mediaservers",
                                            "label": "启用辅助认证的媒体服务器",
                                            "hint": "选择启用辅助认证的媒体服务器",
                                            "persistent-hint": True,
                                            "items": media_server_items,
                                        },
                                    }
                                ],
                            }
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
                                                "注意：启用辅助认证需要在 app.env 文件或环境变量中设置 "
                                                "AUXILIARY_AUTH_ENABLE 参数为开启状态"
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
            "mediaservers": [],
            "allow_anonymous": False,
        }

    def get_page(self) -> None:
        """本插件没有详情页。"""
        pass  # noqa: PIE790  # pylint: disable=unnecessary-pass

    def get_service(self) -> list[dict[str, Any]]:
        """本插件不注册后台服务。"""
        return []

    def stop_service(self) -> None:
        """本插件没有需要停止的后台服务。"""

    @eventmanager.register(ChainEventType.AuthIntercept)
    def handle_auth_intercept(self, event: Event) -> None:
        """阻止未配置或不可用媒体服务的认证继续执行。"""
        if not self._enabled or not event or not event.event_data:
            return

        event_data: AuthInterceptCredentials = event.event_data
        logger.info(
            f"处理认证通过拦截事件 - 用户名: {event_data.username}, "
            f"渠道: {event_data.channel}, 服务: {event_data.service}"
        )

        if event_data.cancel:
            logger.debug("该事件已被其他事件处理器处理，跳过后续操作")
            return

        if event_data.channel not in self._SUPPORTED_CHANNELS:
            logger.info(f"尚未支持处理渠道: {event_data.channel}，跳过拦截")
            return

        services = self.service_infos
        if not services or event_data.service not in services:
            event_data.cancel = True
            event_data.source = self.plugin_name
            logger.warning(
                f"认证被拦截，用户：{event_data.username}，渠道：{event_data.channel}，"
                f"服务：{event_data.service}，拦截源：{event_data.source}"
            )
            return

        event_data.cancel = False
        logger.info(
            f"用户：{event_data.username}，渠道: {event_data.channel}，"
            f"服务 {event_data.service} 允许认证通过"
        )
