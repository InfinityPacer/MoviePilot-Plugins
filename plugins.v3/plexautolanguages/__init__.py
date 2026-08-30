"""根据 Plex 播放和媒体库事件自动选择剧集音轨及字幕语言。"""

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ruamel.yaml import YAML

from app.plugins import _PluginBase
from app.schemas.system import MediaServerConf, ServiceInfo
from app.sdk.logging import logger
from app.sdk.network import UrlUtils
from app.sdk.services import MediaServerHelper

from .languageprovider import LanguageProvider


class PlexAutoLanguages(_PluginBase):
    """在宿主媒体服务目录和插件数据目录之上运行 Plex 自动语言服务。"""
    # 插件名称
    plugin_name = "Plex自动语言"
    # 插件描述
    plugin_desc = "实现自动选择Plex电视节目的音轨和字幕语言。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/plexautolanguages.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexautolanguages_"
    # 加载顺序
    plugin_order = 96
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    mediaserver_helper = None
    # lang服务
    _lang_provider = None
    # Thread
    _lang_thread = None

    # 是否开启
    _enabled = False
    # 媒体服务器
    _mediaserver = None
    # 自动切换
    _auto_switch = None
    # 更新级别
    _update_level = "show"
    # 更新策略
    _update_strategy = "all"
    # 播放时触发
    _trigger_on_play = True
    # 扫描时触发
    _trigger_on_scan = True

    # 退出事件
    _event = threading.Event()

    # endregion

    default_yaml = Path(__file__).parent / "config/default.yaml"

    def __init__(self):
        super().__init__()
        self.mediaserver_helper = None
        self._lang_provider = None
        self._lang_thread = None
        self._enabled = False
        self._mediaserver = None
        self._auto_switch = False
        self._update_level = "show"
        self._update_strategy = "all"
        self._trigger_on_play = True
        self._trigger_on_scan = True
        self._event = threading.Event()

    @property
    def user_yaml(self) -> Path:
        """返回插件数据目录中的用户 YAML，避免修改随代码发布的资源。"""
        return self.get_data_path() / "user.yaml"

    def init_plugin(self, config: Optional[dict] = None):
        self.stop_service()
        self._event.clear()
        self.mediaserver_helper = MediaServerHelper()
        self._enabled = False
        self._mediaserver = None
        self._auto_switch = False
        if self._lang_thread and self._lang_thread.is_alive():
            logger.error("旧的自动语言线程尚未停止，本次配置不会启动新线程")
            return
        self._lang_provider = None
        self._lang_thread = None
        if not config:
            return
        self._enabled = bool(config.get("enabled"))
        self._mediaserver = config.get("mediaserver")
        self._auto_switch = bool(config.get("auto_switch"))
        self._update_level = config.get("update_level", "show")
        self._update_strategy = config.get("update_strategy", "all")
        self._trigger_on_play = bool(config.get("trigger_on_play", True))
        self._trigger_on_scan = bool(config.get("trigger_on_scan", True))
        if self._enabled and self._auto_switch:
            self.__start_auto_switch()

    @property
    def service_info(self) -> Optional[ServiceInfo]:
        """
        服务信息
        """
        if not self._mediaserver:
            logger.warning("尚未配置媒体服务器，请检查配置")
            return None

        if not self.mediaserver_helper:
            self.mediaserver_helper = MediaServerHelper()

        service = self.mediaserver_helper.get_service(name=self._mediaserver, type_filter="plex")
        if not service:
            logger.warning("获取媒体服务器实例失败，请检查配置")
            return None

        if not service.instance or service.instance.is_inactive():
            logger.warning(f"媒体服务器 {self._mediaserver} 未连接，请检查配置")
            return None

        return service

    @property
    def plex_config(self) -> Optional[MediaServerConf]:
        """
        Plex配置
        """
        if not self.service_info:
            return None
        if not self.service_info.config or not self.service_info.config.config:
            return None
        return self.service_info.config

    def __start_auto_switch(self):
        logger.info("正在准备停止服务")

        self.stop_service()

        if self._lang_thread and self._lang_thread.is_alive():
            logger.error("旧的自动语言线程尚未停止，取消本次启动")
            return

        logger.info("正在初始化相关服务")

        if not self.__check_plex_media_server():
            return

        try:
            self.__update_user_config()

            self._lang_provider = LanguageProvider(default_config_path=self.default_yaml,
                                                   user_config_path=self.user_yaml,
                                                   data_path=self.get_data_path(),
                                                   logger=logger)

            self._lang_thread = threading.Thread(target=self._lang_provider.start)
            self._lang_thread.daemon = True
            self._lang_thread.start()
        except Exception as e:
            logger.info("初始化失败，请检查配置信息：" + str(e))

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        if not self.mediaserver_helper:
            self.mediaserver_helper = MediaServerHelper()

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
                                    'md': 3
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
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'auto_switch',
                                            'label': '自动切换',
                                            'hint': '启用后将自动切换剧集语言',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'trigger_on_play',
                                            'label': '播放时触发',
                                            'hint': '播放文件是否触发语言更新',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'trigger_on_scan',
                                            'label': '扫描时触发',
                                            'hint': '扫描新文件时是否触发语言更新',
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
                                            'model': 'mediaserver',
                                            'label': '媒体服务器',
                                            'items': [{"title": config.name, "value": config.name}
                                                      for config in self.mediaserver_helper.get_configs().values()
                                                      if config.type == "plex"],
                                            'hint': '选择媒体服务器',
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
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'update_level',
                                            'label': '更新级别',
                                            'items': [
                                                {'title': '剧集', 'value': 'show'},
                                                {'title': '季', 'value': 'season'}
                                            ],
                                            'hint': '选择更新整个剧集或仅更新当前季',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'update_strategy',
                                            'label': '更新策略',
                                            'items': [
                                                {'title': '所有剧集', 'value': 'all'},
                                                {'title': '接下来的剧集', 'value': 'next'}
                                            ],
                                            'hint': '选择更新所有剧集或仅更新接下来的剧集',
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
                                    'cols': 12,
                                },
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
                                                    'href': 'https://github.com/RemiRigal/Plex-Auto-Languages',
                                                    'target': '_blank',
                                                    'style': 'text-decoration: underline;'
                                                },
                                                'content': [
                                                    {
                                                        'component': 'u',
                                                        'text': 'Plex Auto Languages'
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
                                                    'href': 'https://github.com/RemiRigal',
                                                    'target': '_blank',
                                                    'style': 'text-decoration: underline;'
                                                },
                                                'content': [
                                                    {
                                                        'component': 'u',
                                                        'text': 'RemiRigal'
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
                                                    'href': 'https://github.com/RemiRigal/Plex-Auto-Languages/blob/master/README.md',
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
                    }
                ],
            }
        ], {
            "enabled": False,
            "auto_switch": True,
            "update_level": "show",
            "update_strategy": "all",
            "trigger_on_play": True,
            "trigger_on_scan": True
        }

    def get_page(self) -> None:
        """本插件没有详情页。"""
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
        return []

    def stop_service(self) -> bool:
        """
        退出插件
        """
        try:
            if self._lang_provider:
                self._lang_provider.stop()
                logger.info("auto language has been requested to stop.")
            if self._lang_thread:
                self._lang_thread.join(timeout=10)  # 等待线程完成，增加超时避免死锁
                if self._lang_thread.is_alive():
                    logger.error("thread has not stopped after waiting 10 seconds")
                    return False
                else:
                    self._lang_thread = None
                    self._lang_provider = None
                    logger.info("thread has been joined successfully.")
            else:
                self._lang_provider = None
            self._event.set()  # 通知其他可能等待的线程
            self._event.clear()  # 立即重置事件状态
            return True
        except Exception as e:
            logger.error(f"Error stopping service: {e}", exc_info=True)  # 记录堆栈信息
            return False

    def __check_plex_media_server(self) -> bool:
        """检查Plex媒体服务器配置"""
        if not self.plex_config:
            logger.error(f"Plex 配置不正确，请检查")
            return False

        return True

    def __update_user_config(self):
        yaml = YAML()
        # 保留引号和注释
        yaml.preserve_quotes = True

        # 读取用户配置并保留注释
        with open(self.default_yaml, "r", encoding="utf-8") as stream:
            user_config = yaml.load(stream).get("plexautolanguages", {})

        # 更新 plex_config
        user_config["update_level"] = self._update_level
        user_config["update_strategy"] = self._update_strategy
        user_config["trigger_on_play"] = self._trigger_on_play
        user_config["trigger_on_scan"] = self._trigger_on_scan
        plex_config = user_config.get("plex", {})
        plex_config["url"] = UrlUtils.standardize_base_url(self.plex_config.config.get("host"))
        plex_config["token"] = self.plex_config.config.get("token")

        # 写回到 YAML 文件中并保留注释
        self.user_yaml.parent.mkdir(parents=True, exist_ok=True)
        with open(self.user_yaml, "w", encoding="utf-8") as stream:
            yaml.dump({"plexautolanguages": user_config}, stream)
