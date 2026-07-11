import concurrent.futures
import json
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import plexapi.utils
import pypinyin
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from plexapi.library import LibrarySection

from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import Event, eventmanager
from app.core.meta import MetaBase
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.modules.plex import Plex
from app.plugins import _PluginBase
from app.schemas import ServiceInfo
from app.schemas.types import EventType, NotificationType
from app.utils.string import StringUtils

lock = threading.Lock()
TYPES = {"movie": [1], "show": [2], "artist": [8, 9, 10]}


class PlexLocalization(_PluginBase):
    # 插件名称
    plugin_name = "Plex中文本地化"
    # 插件描述
    plugin_desc = "实现拼音排序、搜索及类型标签中文本地化功能。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/plexlocalization.png"
    # 插件版本
    plugin_version = "2.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexlocalization_"
    # 加载顺序
    plugin_order = 92
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    mediaserver_helper = None
    # 是否开启
    _enabled = False
    # 立即运行一次
    _onlyonce = False
    # 任务执行间隔
    _cron = None
    # 发送通知
    _notify = False
    # 需要处理的媒体库
    _libraries = None
    # 锁定元数据
    _lock = None
    # 入库后运行一次
    _execute_transfer = None
    # 入库后延迟执行时间
    _delay = None
    # 最近一次入库时间
    _transfer_time = None
    # 每批次处理数量
    _batch_size = None
    # timeout
    _timeout = 10
    # Plex 列表分页大小
    _page_size = 500
    # ratingKey 批量读取和验证的安全分块大小
    _metadata_chunk_size = 100
    # tags_json
    _tags_json = None
    # tags
    _tags = None
    # 运行线程数
    _thread_count = None
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    @staticmethod
    def __positive_int(value: Any, default: int) -> int:
        """读取正整数配置，非法值回退默认值。"""
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    def init_plugin(self, config: dict = None):
        self.mediaserver_helper = MediaServerHelper()
        if not config:
            return
        self._enabled = config.get("enabled")
        self._onlyonce = config.get("onlyonce")
        self._cron = config.get("cron")
        self._notify = config.get("notify")
        self._libraries = config.get("libraries", [])
        self._lock = config.get("lock")
        self._execute_transfer = config.get("execute_transfer")
        self._tags_json = config.get("tags_json")
        self._tags = self.__get_tags()
        self._thread_count = self.__positive_int(config.get("thread_count", 3), default=3)
        try:
            self._delay = int(config.get("delay", 300))
        except ValueError:
            self._delay = 300
        self._batch_size = self.__positive_int(config.get("batch_size", 100), default=100)

        # 如果开启了入库后运行一次，延迟时间又不填，默认为300s
        if self._execute_transfer and not self._delay:
            self._delay = 300

        # 停止现有任务
        self.stop_service()

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._onlyonce:
            logger.info(f"Plex中文本地化服务，立即运行一次")
            self._scheduler.add_job(
                func=self.localization,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="Plex中文本地化",
            )
            # 关闭一次性开关
            self._onlyonce = False

        config_mapping = {
            "enabled": self._enabled,
            "onlyonce": False,
            "cron": self._cron,
            "notify": self._notify,
            "libraries": self._libraries,
            "lock": self._lock,
            "tags_json": self._tags_json,
            "thread_count": self._thread_count,
            "execute_transfer": self._execute_transfer,
            "delay": self._delay,
            "batch_size": self._batch_size
        }
        self.update_config(config=config_mapping)

        # 启动任务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def service_infos(self, name_filters: Optional[List[str]] = None) -> Optional[Dict[str, ServiceInfo]]:
        """
        服务信息
        """
        services = self.mediaserver_helper.get_services(name_filters=name_filters, type_filter="plex")
        if not services:
            logger.warning("获取媒体服务器实例失败，请检查配置")
            return None

        active_services = {}
        for service_name, service_info in services.items():
            if service_info.instance.is_inactive():
                logger.warning(f"媒体服务器 {service_name} 未连接，请检查配置")
            else:
                active_services[service_name] = service_info

        if not active_services:
            logger.warning("没有已连接的媒体服务器，请检查配置")
            return None

        return active_services

    def service_info(self, name: str) -> Optional[ServiceInfo]:
        """
        服务信息
        """
        service = self.mediaserver_helper.get_service(name=name, type_filter="plex")
        if not service:
            logger.warning("获取媒体服务器实例失败，请检查配置")
            return None

        if service.instance.is_inactive():
            logger.warning(f"媒体服务器 {name} 未连接，请检查配置")
            return None

        return service

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
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                            'hint': '开启后插件将处于激活状态',
                                            'persistent-hint': True
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
                                            'model': 'notify',
                                            'label': '发送通知',
                                            'hint': '是否在特定事件发生时发送通知',
                                            'persistent-hint': True
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
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                            'hint': '插件将立即运行一次',
                                            'persistent-hint': True
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
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'lock',
                                            'label': '锁定元数据',
                                            'hint': '部分Plex版本只有锁定时才会生效',
                                            'persistent-hint': True
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
                                            'model': 'execute_transfer',
                                            'label': '入库后运行一次',
                                            'hint': '在媒体入库后运行一次操作',
                                            'persistent-hint': True
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
                                            'label': '打开标签设置窗口',
                                            'hint': '开启时弹出窗口以增加或修改标签',
                                            'persistent-hint': True
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
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VCronField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式',
                                            'hint': '使用cron表达式指定执行周期，如 0 8 * * *',
                                            'persistent-hint': True
                                        },
                                    }
                                ],
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'delay',
                                            'label': '延迟时间（秒）',
                                            'placeholder': '入库后延迟执行时间',
                                            'hint': '入库后延迟执行的时间（秒）',
                                            'persistent-hint': True
                                        },
                                    }
                                ],
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'thread_count',
                                            'label': '运行线程数',
                                            'hint': '执行任务时使用的线程数量，普通用户建议设置为 2 至 4',
                                            'persistent-hint': True
                                        },
                                    }
                                ],
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'batch_size',
                                            'label': '每批次处理数',
                                            'hint': '每次处理的最大元数据条数，数值越大会占用更多单任务内存',
                                            'persistent-hint': True
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
                                            'model': 'libraries',
                                            'label': '媒体库',
                                            'items': self.__get_service_library_options(),
                                            'hint': '选择要处理的媒体库',
                                            'persistent-hint': True
                                        },
                                    }
                                ],
                            },
                        ],
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
                                                            'href': 'https://github.com/sqkkyzx/plex_localization_zhcn',
                                                            'target': '_blank',
                                                            'style': 'text-decoration: underline;'
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'u',
                                                                'text': 'plex_localization_zhcn'
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'span',
                                                        'text': '、'
                                                    },
                                                    {
                                                        'component': 'a',
                                                        'props': {
                                                            'href': 'https://github.com/x1ao4/plex-localization-zh',
                                                            'target': '_blank',
                                                            'style': 'text-decoration: underline;'
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'u',
                                                                'text': 'plex-localization-zh'
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
                                                            'href': 'https://github.com/timmy0209',
                                                            'target': '_blank',
                                                            'style': 'text-decoration: underline;'
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'u',
                                                                'text': 'timmy0209'
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'span',
                                                        'text': '、'
                                                    },
                                                    {
                                                        'component': 'a',
                                                        'props': {
                                                            'href': 'https://github.com/sqkkyzx',
                                                            'target': '_blank',
                                                            'style': 'text-decoration: underline;'
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'u',
                                                                'text': 'sqkkyzx'
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'span',
                                                        'text': '、'
                                                    },
                                                    {
                                                        'component': 'a',
                                                        'props': {
                                                            'href': 'https://github.com/x1ao4',
                                                            'target': '_blank',
                                                            'style': 'text-decoration: underline;'
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'u',
                                                                'text': 'x1ao4'
                                                            }
                                                        ]
                                                    },
                                                    {
                                                        'component': 'span',
                                                        'text': '、'
                                                    },
                                                    {
                                                        'component': 'a',
                                                        'props': {
                                                            'href': 'https://github.com/anooki-c',
                                                            'target': '_blank',
                                                            'style': 'text-decoration: underline;'
                                                        },
                                                        'content': [
                                                            {
                                                                'component': 'u',
                                                                'text': 'anooki-c'
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
                                            'text': '注意：如开启锁定元数据，则本地化后需要在Plex中手动解锁才允许修改，'
                                                    '请先在测试媒体库验证无问题后再继续使用'
                                        }
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
                                    "title": "设置标签"
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
                                                                    'modelvalue': 'tags_json',
                                                                    'lang': 'json',
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
                                                                    'text': '注意：已预置常用标签的中英翻译，若需修改或新增可以在上述内容中添加'
                                                                }
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
            "notify": True,
            "cron": "0 1 * * *",
            "lock": False,
            "tags_json": self.__get_preset_tags_json(),
            "thread_count": 3,
            "execute_transfer": False,
            "delay": 300,
            "batch_size": 100
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
        if self._enabled and self._cron:
            logger.info(f"Plex中文本地化定时服务启动，时间间隔 {self._cron} ")
            return [{
                "id": "PlexLocalization",
                "name": "Plex中文本地化",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.localization,
                "kwargs": {}
            }]

    def stop_service(self):
        """
        退出插件
        """
        self._event.set()
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.info(str(e))

    def __get_tags(self) -> dict:
        """获取标签信息"""
        try:
            # 如果预置Json被清空，这里还原为默认Json
            if not self._tags_json:
                self._tags_json = self.__get_preset_tags_json()

            # 去掉以//开始的行
            tags_json = re.sub(r"//.*?\n", "", self._tags_json).strip()
            tags = json.loads(tags_json)
            return tags
        except Exception as e:
            logger.error(f"解析标签失败，已停用插件，请检查配置项，错误详情: {e}")
            self._enabled = False

    @staticmethod
    def __get_preset_tags_json() -> str:
        """获取预置Json"""
        desc = ("// 已预置常用标签的中英翻译\n"
                "// 若有标签需要修改或新增可以在下述内容中添加\n"
                "// 注意无关内容需使用 // 注释\n")
        config = """{
            "Anime": "动画",
            "Action": "动作",
            "Mystery": "悬疑",
            "Tv Movie": "电视电影",
            "Animation": "动画",
            "Crime": "犯罪",
            "Family": "家庭",
            "Fantasy": "奇幻",
            "Disaster": "灾难",
            "Adventure": "冒险",
            "Short": "短片",
            "Horror": "恐怖",
            "History": "历史",
            "Suspense": "悬疑",
            "Biography": "传记",
            "Sport": "运动",
            "Comedy": "喜剧",
            "Romance": "爱情",
            "Thriller": "惊悚",
            "Documentary": "纪录",
            "Indie": "独立",
            "Music": "音乐",
            "Sci-Fi": "科幻",
            "Western": "西部",
            "Children": "儿童",
            "Martial Arts": "武侠",
            "Drama": "剧情",
            "War": "战争",
            "Musical": "歌舞",
            "Film-noir": "黑色",
            "Science Fiction": "科幻",
            "Film-Noir": "黑色",
            "Food": "饮食",
            "War & Politics": "战争与政治",
            "Sci-Fi & Fantasy": "科幻与奇幻",
            "Mini-Series": "迷你剧",
            "Reality": "真人秀",
            "Home and Garden": "家居与园艺",
            "Game Show": "游戏节目",
            "Awards Show": "颁奖典礼",
            "News": "新闻",
            "Talk": "访谈",
            "Talk Show": "脱口秀",
            "Travel": "旅行",
            "Soap": "肥皂剧",
            "Rap": "说唱",
            "Adult": "成人"
        }"""
        return desc + config

    @eventmanager.register(EventType.TransferComplete)
    def execute_transfer(self, event: Event):
        """
        入库后运行一次
        """
        if not self._enabled:
            return

        if not self._execute_transfer:
            return

        event_info: dict = event.event_data
        if not event_info:
            return

        mediainfo: MediaInfo = event_info.get("mediainfo")
        meta: MetaBase = event_info.get("meta")
        if not mediainfo or not meta:
            return

        # 获取媒体信息，确定季度和集数信息，如果存在则添加前缀空格
        season_episode = f" {meta.season_episode}" if meta.season_episode else ""
        media_desc = f"{mediainfo.title_year}{season_episode}"

        # 如果最近一次入库时间为None，这里才进行赋值，否则可能是存在尚未执行的任务待执行
        if not self._transfer_time:
            self._transfer_time = datetime.now(tz=pytz.timezone(settings.TZ))

        # 根据是否有延迟设置不同的日志消息
        delay_message = f"{self._delay} 秒后运行一次本地化服务" if self._delay else "准备运行一次本地化服务"
        logger.info(f"{media_desc} 已入库，{delay_message}")

        if not self._scheduler:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)

        self._scheduler.remove_all_jobs()

        self._scheduler.add_job(
            func=self.__transfer_by_once,
            trigger="date",
            run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=self._delay),
            name="Plex中文本地化",
        )

        # 启动任务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def __transfer_by_once(self):
        """入库后运行一次"""
        if not self._transfer_time:
            logger.info("没有获取到最近一次的入库时间，取消执行本地化服务")
            return

        logger.info(f"正在运行一次本地化服务，入库时间 {self._transfer_time.strftime('%Y-%m-%d %H:%M:%S')}")

        adjusted_time = self._transfer_time - timedelta(minutes=5)
        logger.info(f"为保证入库数据完整性，前偏移5分钟后的时间：{adjusted_time.strftime('%Y-%m-%d %H:%M:%S')}")

        self.localization(added_time=int(adjusted_time.timestamp()))
        self._transfer_time = None

    def localization(self, added_time: Optional[int] = None):
        """本地化服务"""
        with lock:
            self._event.clear()
            logger.info(f"正在准备执行本地化服务")
            service_libraries = self.__get_service_libraries()
            if not service_libraries:
                logger.error(f"Plex 配置不正确，请检查")
                return
            logger.info(f"正在准备本地化的媒体库 {service_libraries}")
            self.__loop_all(service_libraries=service_libraries, thread_count=self._thread_count, added_time=added_time)

    def __get_service_library_options(self):
        """
        获取媒体库选项
        """
        library_options = []
        service_infos = self.service_infos()
        if not service_infos:
            return library_options

        # 获取所有媒体库
        for service in service_infos.values():
            plex = service.instance
            if not plex or not plex.get_plex():
                continue
            plex_server = plex.get_plex()
            libraries = sorted(plex_server.library.sections(), key=lambda x: x.key)
            # 遍历媒体库，创建字典并添加到列表中
            for library in libraries:
                # 排除照片库
                if library.TYPE == "photo":
                    continue
                library_dict = {
                    "title": f"{service.name} - {library.key}. {library.title} ({library.TYPE})",
                    "value": f"{service.name}.{library.key}"
                }
                library_options.append(library_dict)
        return library_options

    def __get_service_libraries(self) -> Optional[Dict[str, Dict[int, Any]]]:
        """
        获取 Plex 媒体库信息
        """
        if not self._libraries:
            return None

        service_libraries = defaultdict(set)

        # 1. 处理本地 _libraries，提取出 service_name 和 library_key
        for library in self._libraries:
            if not library:
                continue
            if "." in library:
                service_name, library_key = library.split(".", 1)
                service_libraries[service_name].add(library_key)

        # 2. 获取 service_infos 对象
        service_infos = self.service_infos(name_filters=list(service_libraries.keys()))
        if not service_infos:
            return None

        # 创建存放交集的字典，value 也是字典，key 为 int(library.key)，value 为 library 对象
        intersected_libraries = {}

        # 3. 遍历 service_infos，验证 Plex 实例并获取媒体库
        for service_name, library_keys in service_libraries.items():
            service_info = service_infos.get(service_name)
            if not service_info or not service_info.instance:
                continue

            plex = service_info.instance
            plex_server = plex.get_plex()
            if not plex_server:
                continue

            libraries = plex_server.library.sections()

            # 4. 获取 Plex 实例中的有效媒体库，进行比对
            remote_libraries = {
                int(library.key): library  # 键为 int(library.key)，值为 library 对象
                for library in libraries if library.TYPE != "photo"
            }

            # 计算本地库和远程库的交集，保留匹配的库
            matched_libraries = {
                key: library
                for key, library in remote_libraries.items()
                if str(key) in library_keys
            }

            # 如果存在交集，添加到最终结果
            if matched_libraries:
                intersected_libraries[service_name] = matched_libraries

        # 5. 返回交集
        return intersected_libraries if intersected_libraries else None

    def __list_rating_keys(self, plex: Plex, library: LibrarySection, type_id: int, is_collection: bool = False,
                           added_time: Optional[int] = None):
        """
        分页获取媒体项目。返回 ratingKey 列表及 complete/failed/stopped 状态。
        """
        if not library:
            return [], "complete"

        if is_collection:
            endpoint = f"/library/sections/{library.key}/collections"
        else:
            endpoint = f"/library/sections/{library.key}/all?type={type_id}"
            if added_time:
                endpoint += f"&addedAt>={added_time}"

        rating_keys = []
        offset = 0
        previous_page = None
        while True:
            if self._event.is_set():
                return rating_keys, "stopped"

            response = plex.get_data(
                endpoint=endpoint,
                headers={
                    "X-Plex-Container-Start": str(offset),
                    "X-Plex-Container-Size": str(self._page_size)
                },
                timeout=self._timeout
            )
            if self._event.is_set():
                return rating_keys, "stopped"
            if response is None or response.status_code >= 400:
                logger.warning(f"分页读取媒体项目失败，媒体库：{library.title}，offset={offset}")
                return rating_keys, "failed"

            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("响应体不是对象")
                if "MediaContainer" not in payload:
                    raise ValueError("缺少 MediaContainer")
                container = payload["MediaContainer"]
                if not isinstance(container, dict):
                    raise ValueError("MediaContainer 不是对象")
                page_items = container.get("Metadata", [])
                if not isinstance(page_items, list) \
                        or any(not isinstance(data, dict) for data in page_items):
                    raise ValueError("Metadata 不是对象列表")
                total_size_value = container.get("totalSize")
                total_size = int(total_size_value) if total_size_value is not None else None
                if total_size is not None and total_size < 0:
                    raise ValueError("totalSize 不能为负数")
            except (AttributeError, TypeError, ValueError) as e:
                logger.warning(f"分页响应解析失败，媒体库：{library.title}，offset={offset}，错误：{e}")
                return rating_keys, "failed"

            response_offset = container.get("offset")
            if response_offset is not None:
                try:
                    if int(response_offset) != offset:
                        logger.warning(f"分页响应位置不匹配，媒体库：{library.title}，"
                                       f"请求 offset={offset}，响应 offset={response_offset}")
                        return rating_keys, "failed"
                except (TypeError, ValueError):
                    logger.warning(f"分页响应位置无效，媒体库：{library.title}，offset={response_offset}")
                    return rating_keys, "failed"

            page_keys = [
                str(data.get("ratingKey"))
                for data in page_items
                if data.get("ratingKey") is not None
            ]
            if offset and page_items and page_items == previous_page:
                logger.warning(f"分页响应未推进，媒体库：{library.title}，offset={offset}")
                return rating_keys, "failed"

            rating_keys.extend(page_keys)
            logger.debug(f"媒体库 {library.title} 分页读取完成：offset={offset}，"
                         f"本页 {len(page_keys)} 条，累计 {len(rating_keys)} 条")

            next_offset = offset + len(page_items)
            if total_size is not None:
                if next_offset >= total_size:
                    break
                if not page_items:
                    logger.warning(f"分页响应提前结束，媒体库：{library.title}，offset={offset}，"
                                   f"totalSize={total_size}")
                    return rating_keys, "failed"
            elif not page_items or len(page_items) < self._page_size:
                break

            previous_page = page_items
            offset = next_offset

        if len(rating_keys):
            logger.info(f"<{library.title} {plexapi.utils.reverseSearchType(libtype=type_id)}> "
                        f"类型共计 {len(rating_keys)} 个{'合集' if is_collection else ''}")

        return rating_keys, "complete"

    def __fetch_item(self, plex: Plex, rating_key):
        """
        获取条目信息
        """
        endpoint = f"/library/metadata/{rating_key}"
        response = plex.get_data(endpoint=endpoint, timeout=self._timeout)
        if response is None or response.status_code >= 400:
            return None
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return datas[0] if datas else None

    def __fetch_all_items(self, plex: Plex, rating_keys):
        """
        批量获取条目
        """
        endpoint = f"/library/metadata/{','.join(rating_keys)}"
        response = plex.get_data(endpoint=endpoint, timeout=self._timeout)
        if response is None or response.status_code >= 400:
            return None
        items = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return items

    def __put_item_metadata(self, plex: Plex, rating_key: str, library_id: int, params: dict,
                            expected_sort_title: Optional[str], expected_tags: Dict[str, List[str]]) -> bool:
        """一次提交同一条目的全部元数据变更。最终状态由批次统一回读。"""
        response = plex.put_data(
            endpoint=f"/library/sections/{library_id}/all",
            params=params,
            timeout=self._timeout)
        if response is None or response.status_code >= 400:
            logger.warning(f"更新元数据失败，ratingKey={rating_key}，状态码："
                           f"{response.status_code if response is not None else '无响应'}")
            return False
        return True

    @staticmethod
    def __metadata_differences(item: Optional[dict], expected_sort_title: Optional[str],
                               expected_tags: Dict[str, List[str]]) -> List[str]:
        """比较 Plex 最终元数据与本次写入期望，返回差异说明。"""
        if not item:
            return ["无法读取最终状态"]

        differences = []
        if expected_sort_title is not None:
            actual_sort_title = item.get("titleSort")
            if actual_sort_title != expected_sort_title:
                differences.append(f"标题排序期望：{expected_sort_title}，实际：{actual_sort_title or ''}")

        for tag_type, target_tags in expected_tags.items():
            field_name = tag_type.capitalize()
            actual_tags = [tag.get("tag") for tag in item.get(field_name, []) if tag.get("tag")]
            if set(actual_tags) != set(target_tags):
                differences.append(f"{tag_type}标签期望：{target_tags}，实际：{actual_tags}")
        return differences

    @staticmethod
    def __empty_result_counts() -> Dict[str, int]:
        """创建批次统计，确保停止路径也参与守恒。"""
        return {"updated": 0, "failed": 0, "skipped": 0, "unprocessed": 0}

    @staticmethod
    def __merge_result_counts(target: Dict[str, int], source: Dict[str, int]):
        """把子块统计合并到业务批次。"""
        for key in target:
            target[key] += source[key]

    def __process_rating_key(self, plex: Plex, rating_key: str):
        """
        处理媒体标识
        """
        if not rating_key:
            return
        item = self.__fetch_item(plex=plex, rating_key=rating_key)
        if not item:
            return
        self.__process_item(plex=plex, item=item)

    def __process_items_batch(self, plex: Plex, rating_keys):
        """
        按固定 HTTP 子块处理业务批次，返回更新、失败、跳过和未处理数量。
        """
        result_counts = self.__empty_result_counts()
        for offset in range(0, len(rating_keys), self._metadata_chunk_size):
            chunk_keys = rating_keys[offset:offset + self._metadata_chunk_size]
            if self._event.is_set():
                result_counts["unprocessed"] += len(rating_keys) - offset
                break

            try:
                chunk_result = self.__process_items_chunk(plex=plex, rating_keys=chunk_keys)
            except Exception as e:
                logger.error(f"处理元数据子块失败，首个 ratingKey={chunk_keys[0] if chunk_keys else ''}: {e}",
                             exc_info=True)
                chunk_result = self.__empty_result_counts()
                chunk_result["failed"] = len(chunk_keys)
            self.__merge_result_counts(result_counts, chunk_result)
        return result_counts

    def __process_items_chunk(self, plex: Plex, rating_keys: List[str]) -> Dict[str, int]:
        """读取并处理一个不超过安全上限的 HTTP 子块。"""
        items = self.__fetch_all_items(plex=plex, rating_keys=rating_keys)
        if items is None:
            result_counts = self.__empty_result_counts()
            result_counts["failed"] = len(rating_keys)
            return result_counts
        return self.__process_loaded_items(plex=plex, rating_keys=rating_keys, items=items)

    def __process_loaded_items(self, plex: Plex, rating_keys: List[str], items: List[dict]) -> Dict[str, int]:
        """对已读取元数据执行逐条 PUT，并统一回读成功写入。"""
        result_counts = self.__empty_result_counts()
        items_by_rating_key = {
            str(item.get("ratingKey")): item
            for item in items
            if item and item.get("ratingKey") is not None
        }
        pending_verification = []

        for index, rating_key in enumerate(rating_keys):
            if self._event.is_set():
                result_counts["unprocessed"] += len(rating_keys) - index
                break

            item = items_by_rating_key.get(str(rating_key))
            if not item:
                result_counts["failed"] += 1
                logger.warning(f"批量读取条目缺失，ratingKey={rating_key}")
                continue

            try:
                edit_plan = self.__prepare_item_edit(item=item)
            except Exception as e:
                result_counts["failed"] += 1
                logger.error(f"处理条目失败，ratingKey={rating_key}: {e}", exc_info=True)
                continue

            if edit_plan is None:
                result_counts["skipped"] += 1
                continue

            if self._event.is_set():
                result_counts["unprocessed"] += len(rating_keys) - index
                break

            try:
                updated = self.__put_item_metadata(
                    plex=plex,
                    rating_key=edit_plan["rating_key"],
                    library_id=edit_plan["library_id"],
                    params=edit_plan["params"],
                    expected_sort_title=edit_plan["expected_sort_title"],
                    expected_tags=edit_plan["expected_tags"]
                )
            except Exception as e:
                result_counts["failed"] += 1
                logger.error(f"更新元数据异常，ratingKey={rating_key}: {e}", exc_info=True)
                continue
            if not updated:
                result_counts["failed"] += 1
                continue
            pending_verification.append(edit_plan)

        if not pending_verification:
            return result_counts

        if self._event.is_set():
            result_counts["failed"] += len(pending_verification)
            return result_counts

        verification_keys = [plan["rating_key"] for plan in pending_verification]
        final_items = self.__fetch_all_items(plex=plex, rating_keys=verification_keys)
        if final_items is None:
            result_counts["failed"] += len(pending_verification)
            return result_counts

        final_items_by_key = {
            str(item.get("ratingKey")): item
            for item in final_items
            if item and item.get("ratingKey") is not None
        }
        for plan in pending_verification:
            rating_key = plan["rating_key"]
            try:
                differences = self.__metadata_differences(
                    item=final_items_by_key.get(rating_key),
                    expected_sort_title=plan["expected_sort_title"],
                    expected_tags=plan["expected_tags"]
                )
            except Exception as e:
                result_counts["failed"] += 1
                logger.error(f"验证元数据异常，ratingKey={rating_key}: {e}", exc_info=True)
                continue
            if differences:
                result_counts["failed"] += 1
                logger.warning(f"更新元数据未完全生效，ratingKey={rating_key}，{'；'.join(differences)}")
                continue

            result_counts["updated"] += 1
            for message in plan["success_logs"]:
                logger.info(message)
        return result_counts

    def __process_item(self, plex: Plex, item: dict) -> Optional[bool]:
        """
        处理元数据。返回 True 表示更新成功，False 表示更新失败，None 表示无需处理。
        """
        if not item or item.get("ratingKey") is None:
            return None
        result = self.__process_loaded_items(
            plex=plex,
            rating_keys=[str(item.get("ratingKey"))],
            items=[item]
        )
        if result["updated"]:
            return True
        if result["failed"]:
            return False
        return None

    def __prepare_item_edit(self, item: dict) -> Optional[dict]:
        """计算单条元数据的原子编辑计划，不执行网络请求。"""
        if not item:
            return

        rating_key = item.get("ratingKey")
        library_id = item.get("librarySectionID")
        if not rating_key or not library_id:
            return

        item_type = item.get("type")
        if not item_type:
            return

        type_id = plexapi.utils.searchType(libtype=item_type)
        title = item.get("title", "")
        locked_fields = [field["name"] for field in item.get("Field") or [] if field.get("locked")]
        edit_params = {
            "type": type_id,
            "id": rating_key,
            "includeExternalMedia": 1
        }
        expected_sort_title = None
        sort_title_changed = False
        expected_tags = {}
        tag_updates = []
        current_sort_title = item.get("titleSort")

        # 如果标题排序没有锁定，尝试更新标题排序
        if "titleSort" in locked_fields:
            logger.debug(f"{title}: titleSort is locked, skip")
        else:
            if not current_sort_title or StringUtils.is_chinese(current_sort_title):
                generated_sort_title = self.__convert_to_pinyin(title)
                if generated_sort_title != title:
                    expected_sort_title = generated_sort_title
                    sort_title_changed = True
                    edit_params.update({
                        "titleSort.value": expected_sort_title,
                        "titleSort.locked": 1 if self._lock else 0
                    })

        tags: dict[str, list] = {
            "genre": [genre.get("tag") for genre in item.get("Genre", {})],  # 流派
            "style": [style.get("tag") for style in item.get("Style", {})],  # 风格
            "mood": [mood.get("tag") for mood in item.get("Mood", {})]  # 情绪
        }

        # 汉化标签
        for tag_type, tag_list in tags.items():
            if tag_list:
                # 如果标签类型没有锁定，尝试更新标签类型
                if tag_type in locked_fields:
                    logger.debug(f"{title}: {tag_type} is locked, skip")
                else:
                    target_tags = []
                    source_tags_to_remove = []
                    for tag in tag_list:
                        new_tag = self._tags.get(tag)
                        if new_tag:
                            tag_updates.append((tag, new_tag))
                            source_tags_to_remove.append(tag)
                        target_tag = new_tag or tag
                        if target_tag not in target_tags:
                            target_tags.append(target_tag)

                    if source_tags_to_remove:
                        expected_tags[tag_type] = target_tags
                        edit_params[f"{tag_type}.locked"] = 1 if self._lock else 0
                        for index, target_tag in enumerate(target_tags):
                            edit_params[f"{tag_type}[{index}].tag.tag"] = target_tag
                        # Plex 的 tag- 协议使用逗号分隔值；逐项预编码可保留标签内的特殊字符。
                        edit_params[f"{tag_type}[].tag.tag-"] = ",".join(
                            quote(str(tag)) for tag in source_tags_to_remove
                        )

        # Plex 会重置同一编辑请求中未携带的未锁定字段；标签变更时必须显式保持已有排序标题。
        if expected_tags and expected_sort_title is None \
                and current_sort_title and "titleSort" not in locked_fields:
            expected_sort_title = current_sort_title
            edit_params.update({
                "titleSort.value": current_sort_title,
                "titleSort.locked": 1 if self._lock else 0
            })

        if expected_sort_title is None and not expected_tags:
            logger.debug(f"{title}（ratingKey={rating_key}）无需更新，跳过")
            return None

        success_logs = []
        if sort_title_changed:
            success_logs.append(f"{title} < {expected_sort_title} >")
        for tag, new_tag in tag_updates:
            success_logs.append(f"{title}: {tag} → {new_tag}")
        return {
            "rating_key": str(rating_key),
            "library_id": library_id,
            "params": edit_params,
            "expected_sort_title": expected_sort_title,
            "expected_tags": expected_tags,
            "success_logs": success_logs
        }

    def __loop_all(self, service_libraries: Dict[str, Dict[int, Any]], thread_count: int = None,
                   added_time: Optional[int] = None):
        """
        选择媒体库并遍历其中的每一个媒体
        """
        if not self._tags:
            logger.warning("标签本地化配置不能为空，请检查")
            return

        logger.info(f"当前标签本地化配置为：{self._tags}")
        overall_start_time = time.time()
        thread_count = thread_count or 3
        logger.info(f"正在运行中文本地化，线程数：{thread_count}，锁定元数据：{self._lock}")

        overall_results = {"updated": 0, "failed": 0, "skipped": 0, "unprocessed": 0}
        completed_services = 0
        discovered_items = 0
        failed_services = 0
        stopped = False

        for service_name, libraries in service_libraries.items():
            if self._event.is_set():
                stopped = True
                break

            service = self.service_info(name=service_name)
            if not service or not service.instance:
                failed_services += 1
                logger.warning(f"获取媒体服务器 {service_name} 实例失败，跳过处理")
                continue

            service_start_time = time.time()
            logger.info(f"开始处理媒体服务器 {service.name}")

            # 生成所有需要处理的rating keys
            rating_keys, scan_status = self.__generate_all_rating_keys(
                plex=service.instance,
                libraries=libraries,
                with_collection=added_time is None,
                added_time=added_time
            )
            if scan_status == "stopped":
                stopped = True
                break
            if scan_status != "complete":
                failed_services += 1
                logger.warning(f"媒体服务器 {service.name} 枚举不完整，跳过本次处理")
                continue
            discovered_items += len(rating_keys)

            # 分批处理rating keys
            service_results = self.__process_rating_keys_in_batches(
                plex=service.instance,
                rating_keys=rating_keys,
                thread_count=thread_count,
                batch_size=self._batch_size
            )
            for key in overall_results:
                overall_results[key] += service_results[key]

            service_elapsed_time = time.time() - service_start_time
            if self._event.is_set():
                stopped = True
                logger.warning(f"媒体服务器 {service.name} 处理已停止，耗时 {service_elapsed_time:.2f} 秒")
                break
            completed_services += 1
            logger.info(f"媒体服务器 {service.name} 处理完成，耗时 {service_elapsed_time:.2f} 秒")

        overall_elapsed_time = time.time() - overall_start_time
        if added_time:
            formatted_added_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(added_time))
            message_text = f"最近一次入库时间：{formatted_added_time}，Plex本地化完成，用时 {overall_elapsed_time :.2f} 秒"
        else:
            message_text = f"Plex本地化完成，用时 {overall_elapsed_time :.2f} 秒"

        result_text = (f"完整服务 {completed_services}，失败服务 {failed_services}，发现 {discovered_items}，"
                       f"更新 {overall_results['updated']}，失败 {overall_results['failed']}，"
                       f"跳过 {overall_results['skipped']}，未处理 {overall_results['unprocessed']}")
        if stopped:
            logger.warning(f"Plex本地化已停止，{result_text}，用时 {overall_elapsed_time:.2f} 秒")
        elif failed_services:
            logger.warning(f"Plex本地化未完整完成，{result_text}，"
                           f"用时 {overall_elapsed_time:.2f} 秒")
        else:
            self.__send_message(title="【Plex中文本地化】", text=message_text)
            logger.info(f"{message_text}，{result_text}")

    def __generate_all_rating_keys(self, plex: Plex, libraries, with_collection: bool = True,
                                   added_time: Optional[int] = None):
        """
        生成所有库中唯一且保持首次发现顺序的 ratingKey 列表。
        """
        rating_keys = []
        seen_keys = set()

        def append_unique(keys):
            """保留跨类型和合集首次出现的 ratingKey。"""
            for rating_key in keys:
                if rating_key not in seen_keys:
                    seen_keys.add(rating_key)
                    rating_keys.append(rating_key)

        for library in libraries.values():
            library_types = TYPES.get(library.type, [])
            for type_id in library_types:
                keys, status = self.__list_rating_keys(
                    plex=plex,
                    library=library,
                    type_id=type_id,
                    added_time=added_time
                )
                if status != "complete":
                    return [], status
                append_unique(keys)

            if with_collection and library_types:
                keys, status = self.__list_rating_keys(
                    plex=plex,
                    library=library,
                    type_id=library_types[0],
                    is_collection=True
                )
                if status != "complete":
                    return [], status
                append_unique(keys)

        return rating_keys, "complete"

    def __process_rating_keys_in_batches(self, plex: Plex, rating_keys, thread_count, batch_size=100):
        """
        有界提交批次并汇总所有 ratingKey 的终态。
        """
        total_keys_count = len(rating_keys)
        total_batches = (total_keys_count + batch_size - 1) // batch_size

        logger.info(f"总条目：{total_keys_count}，每批处理条数：{batch_size}，总批次数：{total_batches}，准备开始执行")

        pending = {}
        completed_batches = 0
        failed_batches = 0
        total_results = {"updated": 0, "failed": 0, "skipped": 0, "unprocessed": 0}
        next_start = 0
        max_pending = thread_count * 2

        def collect_done(done_futures):
            """汇总已终结 Future，异常批次按失败处理。"""
            nonlocal completed_batches, failed_batches
            for future in done_futures:
                batch_index, batch_keys = pending.pop(future)
                try:
                    batch_results = future.result()
                    logger.debug(f"第{batch_index + 1}批次处理完成："
                                 f"更新 {batch_results['updated']}，失败 {batch_results['failed']}，"
                                 f"跳过 {batch_results['skipped']}，未处理 {batch_results['unprocessed']}")
                    completed_batches += 1
                    for key in total_results:
                        total_results[key] += batch_results[key]
                except Exception as e:
                    failed_batches += 1
                    total_results["failed"] += len(batch_keys)
                    logger.error(f"第{batch_index + 1}批次处理过程中发生错误: {e}", exc_info=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            while next_start < total_keys_count or pending:
                while next_start < total_keys_count and len(pending) < max_pending \
                        and not self._event.is_set():
                    batch_keys = rating_keys[next_start:next_start + batch_size]
                    future = executor.submit(self.__process_items_batch, plex, batch_keys)
                    pending[future] = (next_start // batch_size, batch_keys)
                    next_start += len(batch_keys)

                if self._event.is_set():
                    for future, (_, batch_keys) in list(pending.items()):
                        if future.cancel():
                            pending.pop(future)
                            total_results["unprocessed"] += len(batch_keys)

                if not pending:
                    break

                done, _ = concurrent.futures.wait(
                    pending,
                    return_when=concurrent.futures.FIRST_COMPLETED
                )
                collect_done(done)

            if next_start < total_keys_count:
                total_results["unprocessed"] += total_keys_count - next_start

        logger.info(f"处理完毕，完成批次数：{completed_batches}，异常批次数：{failed_batches}，"
                    f"更新条目：{total_results['updated']}，失败条目：{total_results['failed']}，"
                    f"跳过条目：{total_results['skipped']}，未处理条目：{total_results['unprocessed']}")
        return total_results

    @staticmethod
    def __extract_tags(datas: Any, attribute_name: str) -> list:
        """
        从实体对象列表中提取指定属性的值。
        :param datas: 实体对象列表。
        :param attribute_name: 要提取的属性名称。
        :return: 属性值列表。
        """
        return [getattr(data, attribute_name, None) for data in datas if
                getattr(data, attribute_name, None)]

    @staticmethod
    def __convert_to_pinyin(text):
        """将字符串转换为拼音首字母形式。"""
        str_a = pypinyin.pinyin(text, style=pypinyin.FIRST_LETTER)
        str_b = [str(str_a[i][0]).upper() for i in range(len(str_a))]
        return "".join(str_b).replace("：", ":").replace("（", "(").replace("）", ")").replace("，", ",")

    def __send_message(self, title: str, text: str):
        """
        发送消息
        """
        if not self._notify:
            return

        self.post_message(mtype=NotificationType.SiteMessage, title=title, text=text)
