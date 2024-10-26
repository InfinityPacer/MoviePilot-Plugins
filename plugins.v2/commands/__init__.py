import json
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.core.event import Event, eventmanager
from app.helper.notification import NotificationHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import ServiceInfo
from app.schemas.event import CommandRegisterEventData
from app.schemas.types import ChainEventType

lock = threading.Lock()


class Commands(_PluginBase):
    # 插件名称
    plugin_name = "命令管理"
    # 插件描述
    plugin_desc = "实现微信、Telegram等客户端的命令管理。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/commands.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "commands_"
    # 加载顺序
    plugin_order = 29
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    notify_helper = None
    # 是否开启
    _enabled = False
    # 通知客户端
    _notify_clients = None
    # 自定义指令
    _custom_commands = None

    # endregion

    def init_plugin(self, config: dict = None):
        self.notify_helper = NotificationHelper()
        if not config:
            return

        self._enabled = config.get("enabled") or False
        self._notify_clients = config.get("notify_clients") or []
        try:
            self._custom_commands = json.loads(config.get("custom_commands")) or {}
        except Exception as e:
            logger.error(f"自定义命令格式错误，请检查，{e}")
            self._custom_commands = {}

    @property
    def service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        服务信息
        """
        if not self._notify_clients:
            logger.warning("尚未配置通知客户端，请检查配置")
            return None

        services = self.notify_helper.get_services(name_filters=self._notify_clients)
        if not services:
            logger.warning("获取通知客户端实例失败，请检查配置")
            return None

        return services

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
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
                                            'items': [{"title": config.name, "value": config.name}
                                                      for config in self.notify_helper.get_configs().values()
                                                      if config.type in ["wechat", "telegram"]]
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
                                                            'style': 'height: 35rem; font-size: 14px',
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
                                                            'style': 'height: 35rem; font-size: 14px'
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

    def get_page(self) -> List[dict]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        pass

    def stop_service(self):
        """
        退出插件
        """
        pass

    @eventmanager.register(ChainEventType.CommandRegister)
    def handle_command_register(self, event: Event):
        """
        处理 CommandRegister 事件
        :param event: 事件数据
        """
        if not event or not event.event_data:
            return

        event_data: CommandRegisterEventData = event.event_data

        logger.info(f"处理命令注册事件 - {event_data}")

        if event_data.cancel:
            logger.debug(f"该事件已被其他事件处理器处理，跳过后续操作")
            return

        event_data.source = self.__class__.__name__
        if event_data.origin == "CommandChain":
            # 每次传递，都更新预置指令
            config = self.get_config()
            config["preset_commands"] = json.dumps(event_data.commands, indent=4, ensure_ascii=False)
            self.update_config(config=config)
            # 尚未支持统一管理菜单，目前 CommandChain 暂不拦截
            return
            # # 如果没有选择任何的通知客户端，不拦截，传递到各个服务实例后再逐一处理清理菜单
            # if not self.service_infos:
            #     return

        if event_data.origin not in ["WeChat", "Telegram"]:
            logger.info(f"尚未支持的事件源: {event_data.origin}，跳过拦截")
            return

        # 如果不在选择的服务实例中，则直接拦截
        if not self.service_infos or event_data.service not in self.service_infos.keys():
            event_data.cancel = True
            logger.warning(f"命令注册被拦截，{event_data}")
            return
        else:
            event_data.cancel = False
            custom_commands = self._custom_commands.get(event_data.service) or {}
            if not custom_commands:
                logger.info(f"未能获取到 {event_data.service} 相关的自定义命令，跳过处理")
                return
            else:
                # 遍历并更新 event_data.commands
                logger.debug(f"Initial commands before processing: {event_data.commands}")
                commands = event_data.commands
                for cmd_key in list(commands.keys()):
                    if cmd_key in custom_commands:
                        # 只覆盖 category 和 description 字段
                        category = commands[cmd_key]["category"]
                        description = commands[cmd_key]["description"]
                        commands[cmd_key]["category"] = custom_commands[cmd_key].get("category", category)
                        commands[cmd_key]["description"] = custom_commands[cmd_key].get("description", description)
                    else:
                        # 如果命令不在自定义命令中，则从 event_data.commands 中移除
                        del event_data.commands[cmd_key]
                logger.debug(f"Final commands after processing: {event_data.commands}")

    @staticmethod
    def __get_default_commands():
        """
        获取自定义默认值指令
        """
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
