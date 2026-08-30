"""按通知客户端配置管理 MoviePilot 远程命令菜单。"""

import json
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple

from app.plugins import _PluginBase
from app.schemas.event import CommandRegisterEventData
from app.schemas.system import ServiceInfo
from app.schemas.types import ChainEventType
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.sdk.services import NotificationHelper


class Commands(_PluginBase):
    """按通知客户端配置筛选并调整远程命令菜单。"""

    plugin_name = "命令管理"
    plugin_desc = "实现微信、Telegram等客户端的命令管理。"
    plugin_icon = (
        "https://raw.githubusercontent.com/InfinityPacer/"
        "MoviePilot-Plugins/main/icons/commands.png"
    )
    plugin_version = "2.0.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "commands_"
    plugin_order = 42
    auth_level = 1

    # 通知服务目录由宿主 SDK 在插件初始化时绑定，避免导入期抓取运行时模块。
    notify_helper: Optional[NotificationHelper] = None
    _enabled = False
    _notify_clients: List[str] = []
    _custom_commands: Dict[str, Dict[str, dict]] = {}

    def init_plugin(self, config: Optional[dict] = None):
        """读取命令菜单配置，并在每次重载时重置旧实例状态。"""
        self.notify_helper = NotificationHelper()
        self._enabled = False
        self._notify_clients = []
        self._custom_commands = {}
        if not config:
            return

        self._enabled = bool(config.get("enabled", False))
        notify_clients = config.get("notify_clients")
        if isinstance(notify_clients, (list, tuple, set)):
            self._notify_clients = [str(name) for name in notify_clients if name]
        elif notify_clients:
            self._notify_clients = [str(notify_clients)]
        self._custom_commands = self.__parse_custom_commands(
            config.get("custom_commands")
        )

    @staticmethod
    def __parse_custom_commands(value: Any) -> Dict[str, Dict[str, dict]]:
        """解析表单中的 JSON 菜单配置，非法输入按空配置处理。"""
        try:
            if isinstance(value, Mapping):
                parsed = dict(value)
            elif value in (None, ""):
                return {}
            else:
                parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError("自定义命令必须是 JSON 对象")
            return parsed
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            logger.error(f"自定义命令格式错误，请检查，{error}")
            return {}

    def __get_notify_helper(self) -> NotificationHelper:
        """返回已绑定的通知服务目录，兼容宿主调用表单前读取配置的顺序。"""
        if self.notify_helper is None:
            self.notify_helper = NotificationHelper()
        return self.notify_helper

    @property
    def service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """返回已选择且当前运行中的通知客户端。"""
        if not self._notify_clients:
            logger.warning("尚未配置通知客户端，请检查配置")
            return None

        services = self.__get_notify_helper().get_services(
            name_filters=self._notify_clients
        )
        if not services:
            logger.warning("获取通知客户端实例失败，请检查配置")
            return None

        return services

    def get_state(self) -> bool:
        """返回插件是否已启用。"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """本插件不注册额外的远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """本插件不暴露自有 HTTP API。"""
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """拼装插件配置页面和默认配置。"""
        notify_helper = self.__get_notify_helper()
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                            'hint': '开启后插件将处于激活状态',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'model': 'notify_clients',
                                            'label': '启用命令菜单的通知客户端',
                                            'hint': '选择启用命令菜单的通知客户端',
                                            'persistent-hint': True,
                                            'items': [
                                                {"title": config.name, "value": config.name}
                                                for config in notify_helper.get_configs().values()
                                                if config.type in ["wechat", "telegram"]
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VTabs',
                        'props': {
                            'model': '_tabs',
                            'style': {
                                'margin-top': '8px',
                                'margin-bottom': '16px'
                            },
                            'stacked': False,
                            'fixed-tabs': False
                        },
                        'content': [
                            {
                                'component': 'VTab',
                                'props': {
                                    'value': 'preset_tab'
                                },
                                'text': '系统预置'
                            }, {
                                'component': 'VTab',
                                'props': {
                                    'value': 'custom_tab'
                                },
                                'text': '自定义'
                            }
                        ]
                    },
                    {
                        'component': 'VWindow',
                        'props': {
                            'model': '_tabs'
                        },
                        'content': [
                            {
                                'component': 'VWindowItem',
                                'props': {
                                    'value': 'preset_tab'
                                },
                                'content': [
                                    {
                                        'component': 'VRow',
                                        'content': [
                                            {
                                                'component': 'VCol',
                                                'props': {
                                                    "cols": 12
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VAceEditor',
                                                        'props': {
                                                            'modelvalue': 'preset_commands',
                                                            'lang': 'json',
                                                            'theme': 'monokai',
                                                            'style': (
                                                                'height: 35rem; font-size: 14px'
                                                            ),
                                                            'readonly': True
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                'component': 'VWindowItem',
                                'props': {
                                    'value': 'custom_tab'
                                },
                                'content': [
                                    {
                                        'component': 'VRow',
                                        'content': [
                                            {
                                                'component': 'VCol',
                                                'props': {
                                                    "cols": 12
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VAceEditor',
                                                        'props': {
                                                            'modelvalue': 'custom_commands',
                                                            'lang': 'json',
                                                            'theme': 'monokai',
                                                            'style': (
                                                                'height: 35rem; font-size: 14px'
                                                            )
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'props': {
                            'style': {
                                'margin-top': '12px'
                            }
                        },
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：企业微信目前仅支持3个一级菜单和5个二级菜单'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "custom_commands": self.__get_default_commands()
        }

    def get_page(self) -> None:
        """保持空钩子，使宿主不声明详情页能力。"""
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """本插件不注册后台服务。"""
        return []

    def stop_service(self) -> None:
        """本插件没有需要停止的后台服务。"""

    @eventmanager.register(ChainEventType.CommandRegister)
    def handle_command_register(self, event: Event):
        """按来源和客户端配置拦截或裁剪命令注册事件。"""
        if not event or not event.event_data:
            return

        event_data: CommandRegisterEventData = event.event_data

        logger.info(f"处理命令注册事件 - {event_data}")

        if event_data.cancel:
            logger.debug("该事件已被其他事件处理器处理，跳过后续操作")
            return

        if event_data.origin == "CommandChain":
            config = self.get_config() or {}
            config["preset_commands"] = json.dumps(
                event_data.commands,
                indent=4,
                ensure_ascii=False,
            )
            self.update_config(config=config)
            return

        if event_data.origin not in ["WeChat", "Telegram"]:
            logger.info(f"尚未支持的事件源: {event_data.origin}，跳过拦截")
            return

        event_data.source = self.plugin_name
        services = self.service_infos
        if not services or event_data.service not in services:
            event_data.cancel = True
            logger.warning(f"命令注册被拦截，{event_data}")
            return

        event_data.cancel = False
        custom_commands = (self._custom_commands or {}).get(event_data.service) or {}
        if not isinstance(custom_commands, Mapping):
            logger.warning(f"未能获取到 {event_data.service} 相关的自定义命令，跳过处理")
            return
        if not custom_commands:
            logger.info(f"未能获取到 {event_data.service} 相关的自定义命令，跳过处理")
            return

        logger.debug(f"Initial commands before processing: {event_data.commands}")
        for cmd_key in list(event_data.commands):
            command = event_data.commands[cmd_key]
            custom_command = custom_commands.get(cmd_key)
            if not isinstance(command, dict) or not isinstance(custom_command, Mapping):
                del event_data.commands[cmd_key]
                continue

            command["category"] = custom_command.get(
                "category", command.get("category")
            )
            command["description"] = custom_command.get(
                "description", command.get("description")
            )
        logger.debug(f"Final commands after processing: {event_data.commands}")

    @staticmethod
    def __get_default_commands() -> str:
        """返回自定义命令配置的示例值。"""
        return """{
    "通知渠道1": {
        "/cookiecloud": {
            "type": "preset",
            "description": "同步站点",
            "category": "站点"
        },
        "/sites": {
            "type": "preset",
            "description": "查询站点",
            "category": "站点"
        }
    },
    "通知渠道2": {
        "/restart": {
            "type": "preset",
            "description": "重启系统",
            "category": "管理"
        },
        "/version": {
            "type": "preset",
            "description": "当前版本",
            "category": "管理"
        }
    }
}"""
