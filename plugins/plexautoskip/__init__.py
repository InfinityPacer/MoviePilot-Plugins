import threading
from pathlib import Path
from typing import Any, List, Dict, Tuple

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.plugins.plexautoskip.resources.log import getLogger
from app.plugins.plexautoskip.resources.server import getPlexServer
from app.plugins.plexautoskip.resources.settings import Settings
from app.plugins.plexautoskip.resources.skipper import Skipper
from app.schemas.types import EventType


class PlexAutoSkip(_PluginBase):
    # 插件名称
    plugin_name = "PlexAutoSkip"
    # 插件描述
    plugin_desc = "实现自动跳过Plex中片头、片尾以及类似的内容。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/PlexAutoSkip_C.png"
    # 插件版本
    plugin_version = "0.5"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexautoskip_"
    # 加载顺序
    plugin_order = 93
    # 可使用的用户级别
    auth_level = 1
    # Skipper
    _skipper = None
    # Thread
    _skipper_thread = None
    # Config
    _skipper_config = None

    # region 私有属性

    # 是否开启
    _enabled = False
    # 自动跳过
    _auto_skip = None
    # 退出事件
    _event = threading.Event()

    # endregion

    user_ini = Path(__file__).parent / "config/config.ini"
    default_ini = Path(__file__).parent / "setup/config.ini.sample"

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self.stop_service()

        self._enabled = config.get("enabled")
        self._auto_skip = config.get("auto_skip")
        if self._enabled and self._auto_skip:
            self._skipper_config = config.get("skipper_config", self.default_ini.read_text(encoding="utf-8"))
            self.user_ini.write_text(self._skipper_config, encoding="utf-8")
            self.__start_auto_skip()

    @staticmethod
    def __get_logger(plugin_name: str):
        """
        获取模块的logger
        """
        if plugin_name:
            loggers = getattr(logger, '_loggers', None)
            if loggers:
                logfile = Path("plugins") / f"{plugin_name}.log"
                _logger = loggers.get(logfile)
                if _logger:
                    return _logger
        return getLogger(__name__)

    def __start_auto_skip(self):
        logger.info("已开启PlexAutoSkip，正在准备停止历史服务")

        self.stop_service()

        logger.info("正在初始化相关服务")

        try:
            log = self.__get_logger(self.plugin_name.lower())
            skip_settings = Settings(logger=log)
            self.update_config({
                "enabled": self._enabled,
                "auto_skip": self._auto_skip,
                "skipper_config": self.user_ini.read_text(encoding="utf-8")
            })

            plex, sslopt = getPlexServer(skip_settings, log)

            if plex:
                self._skipper = Skipper(plex, skip_settings, log)
                self._skipper_thread = threading.Thread(target=self._skipper.start, args=(sslopt,))
                self._skipper_thread.start()
            else:
                log.error("Unable to establish Plex Server object via PlexAPI")
        except Exception as e:
            logger.info("PlexAutoSkip初始化失败，请检查配置信息：" + str(e))

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [{
            "cmd": "/switch_plex_skip",
            "event": EventType.PluginAction,
            "desc": "切换PlexAutoSkip",
            "category": "Plex",
            "data": {
                "action": "switch_plex_auto_skip"
            }
        }]

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
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        },
                                    }
                                ],
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'auto_skip',
                                            'label': '自动跳过',
                                        },
                                    }
                                ],
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'dialog_closed',
                                            'label': '打开配置文件窗口',
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VAlert',
                                'props': {
                                    'type': 'info',
                                    'variant': 'tonal'
                                },
                                'content': [
                                    {
                                        'component': 'span',
                                        'text': '基于 '
                                    },
                                    {
                                        'component': 'a',
                                        'props': {
                                            'href': 'https://github.com/mdhiggins/PlexAutoSkip',
                                            'target': '_blank',
                                            'style': 'text-decoration: underline;'
                                        },
                                        'content': [
                                            {
                                                'component': 'u',
                                                'text': 'PlexAutoSkip'
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'span',
                                        'text': ' 项目编写，特此感谢 '
                                    },
                                    {
                                        'component': 'a',
                                        'props': {
                                            'href': 'https://github.com/mdhiggins',
                                            'target': '_blank',
                                            'style': 'text-decoration: underline;'
                                        },
                                        'content': [
                                            {
                                                'component': 'u',
                                                'text': 'mdhiggins'
                                            }
                                        ]
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
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：本插件仍在完善阶段，可能存在导致性能消耗、异常退出等问题，请详细查阅 '
                                        },
                                        'content': [
                                            {
                                                'component': 'a',
                                                'props': {
                                                    'href': 'https://github.com/InfinityPacer/PlexAutoSkip/blob/master/README.md',
                                                    'target': '_blank'
                                                },
                                                'content': [
                                                    {
                                                        'component': 'u',
                                                        'text': 'README'
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
                        "component": "VDialog",
                        "props": {
                            "model": "dialog_closed",
                            "max-width": "60rem",
                            "overlay-class": "v-dialog--scrollable v-overlay--scroll-blocked",
                            "content-class": "v-card v-card--density-default v-card--variant-elevated rounded-t"
                        },
                        "content": [
                            {
                                "component": "VCard",
                                "props": {
                                    "title": "设置"
                                },
                                "content": [
                                    {
                                        "component": "VDialogCloseBtn",
                                        "props": {
                                            "model": "dialog_closed"
                                        }
                                    },
                                    {
                                        "component": "VCardText",
                                        "props": {},
                                        "content": [
                                            {
                                                'component': 'VRow',
                                                'content': [
                                                    {
                                                        'component': 'VCol',
                                                        'props': {
                                                            'cols': 12,
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'VAceEditor',
                                                                'props': {
                                                                    'modelvalue': 'skipper_config',
                                                                    'lang': 'yaml',
                                                                    'theme': 'monokai',
                                                                    'style': 'height: 30rem',
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
                                                            'cols': 12,
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'VAlert',
                                                                'props': {
                                                                    'type': 'info',
                                                                    'variant': 'tonal',
                                                                    'text': '注意：有关配置详情，请查阅 '
                                                                },
                                                                'content': [
                                                                    {
                                                                        'component': 'a',
                                                                        'props': {
                                                                            'href': 'https://github.com/InfinityPacer/PlexAutoSkip/wiki',
                                                                            'target': '_blank'
                                                                        },
                                                                        'content': [
                                                                            {
                                                                                'component': 'u',
                                                                                'text': 'Wiki'
                                                                            }
                                                                        ]
                                                                    }
                                                                ]
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        ], {
            "enabled": False,
            "auto_skip": True,
            "skipper_config": self.default_ini.read_text(encoding="utf-8")
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
        try:
            if self._skipper:
                self._skipper.stop()
                logger.info("Skipper has been requested to stop.")
            if self._skipper_thread:
                self._skipper_thread.join(timeout=10)  # 等待线程完成，增加超时避免死锁
                self._skipper_thread = None
                logger.info("Skipper thread has been joined successfully.")
            self._event.set()  # 通知其他可能等待的线程
            self._event.clear()  # 立即重置事件状态
        except Exception as e:
            logger.error(f"Error stopping PlexAutoSkip service: {e}", exc_info=True)  # 记录堆栈信息

    @eventmanager.register(EventType.PluginAction)
    def switch_auto_skip(self, event: Event = None):
        """
        切换Plex自动跳过
        """
        if not event:
            return
        event_data = event.event_data
        if not event_data or event_data.get("action") != "switch_plex_auto_skip":
            return

        if self._enabled:
            logger.info("接收到外部命令，正在切换自动跳过")
            self._auto_skip = not self._auto_skip
            if self._auto_skip:
                self.__start_auto_skip()
            else:
                self.stop_service()

            config = self.get_config()
            config["auto_skip"] = self._auto_skip
            self.update_config(config=config)

            status = "开启" if self._auto_skip else "关闭"
            self.post_message(channel=event.event_data.get("channel"),
                              title=f"【PlexAutoSkip】",
                              text=f"自动跳过已{status}",
                              userid=event.event_data.get("user"))
