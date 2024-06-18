import concurrent.futures
import json
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional

import plexapi.utils
import pypinyin
import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from plexapi.library import LibrarySection
from requests import Session

from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import Event, eventmanager
from app.core.meta import MetaBase
from app.log import logger
from app.modules.plex import Plex
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType

lock = threading.Lock()
TYPES = {"movie": [1], "show": [2], "artist": [8, 9, 10]}


class PlexLocalization(_PluginBase):
    # 插件名称
    plugin_name = "Plex中文本地化"
    # 插件描述
    plugin_desc = "实现拼音排序、搜索及类型标签中文本地化功能。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/plexlocalization.png"
    # 插件版本
    plugin_version = "1.5"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexlocalization_"
    # 加载顺序
    plugin_order = 91
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    # Plex
    _plex = None
    # plex_host
    _plex_host = None
    # session
    _plex_session = None
    # 是否开启
    _enabled = False
    # 立即运行一次
    _onlyonce = False
    # 任务执行间隔
    _cron = None
    # 发送通知
    _notify = False
    # 需要处理的媒体库
    _library_ids = None
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

    def init_plugin(self, config: dict = None):
        self._plex_host = settings.PLEX_HOST
        self._plex_host = self.__adapt_base_url(host=self._plex_host)
        self._plex_session = self.__adapt_plex_session()
        self._plex = Plex().get_plex()

        if not config:
            logger.info("Plex中文本地化开启失败，无法获取插件配置")
            return False

        self._enabled = config.get("enabled")
        self._onlyonce = config.get("onlyonce")
        self._cron = config.get("cron")
        self._notify = config.get("notify")
        self._library_ids = config.get("library_ids")
        self._lock = config.get("lock")
        self._execute_transfer = config.get("execute_transfer")
        self._tags_json = config.get("tags_json")
        self._tags = self.__get_tags()
        try:
            self._thread_count = int(config.get("thread_count", 5))
        except ValueError:
            self._thread_count = 5
        try:
            self._delay = int(config.get("delay", 300))
        except ValueError:
            self._delay = 300
        try:
            self._batch_size = int(config.get("batch_size", 100))
        except ValueError:
            self._batch_size = 100

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
            "library_ids": self._library_ids,
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
        if not settings.MEDIASERVER:
            logger.error(f"媒体库配置不正确，请检查")

        if "plex" not in settings.MEDIASERVER:
            logger.error(f"Plex配置不正确，请检查")

        if not self._plex:
            self._plex = Plex().get_plex()

        # 获取所有媒体库
        libraries = self._plex.library.sections()
        # 生成媒体库选项列表
        library_options = []

        # 遍历媒体库，创建字典并添加到列表中
        for library in libraries:
            # 排除照片库
            if library.TYPE == "photo":
                continue
            library_dict = {
                "title": f"{library.key}. {library.title} ({library.TYPE})",
                "value": library.key
            }
            library_options.append(library_dict)

        library_options = sorted(library_options, key=lambda x: x["value"])

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
                                            'persistent-hint': True,
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
                                            'persistent-hint': True,
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
                                            'persistent-hint': True,
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
                                            'hint': '电影合集只有锁定时才会生效',
                                            'persistent-hint': True,
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
                                            'persistent-hint': True,
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
                                            'persistent-hint': True,
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式',
                                            'hint': '使用cron表达式指定执行周期，如 0 8 * * *',
                                            'persistent-hint': True,
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
                                            'persistent-hint': True,
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
                                            'hint': '执行任务时使用的线程数量',
                                            'persistent-hint': True,
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
                                            'hint': '每次处理的最大元数据条数',
                                            'persistent-hint': True,
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
                                            'model': 'library_ids',
                                            'label': '媒体库',
                                            'items': library_options,
                                            'hint': '选择要处理的媒体库',
                                            'persistent-hint': True,
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
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal'
                                        },
                                        'content': [
                                            {
                                                'component': 'div',
                                                'html': '基于 <a href="https://github.com/sqkkyzx/plex_localization_zhcn" target="_blank" style="text-decoration: underline;">plex_localization_zhcn</a>、<a href="https://github.com/x1ao4/plex-localization-zh" target="_blank" style="text-decoration: underline;">plex-localization-zh</a> 项目编写，特此感谢 <a href="https://github.com/timmy0209" target="_blank" style="text-decoration: underline;">timmy0209</a>、<a href="https://github.com/sqkkyzx" target="_blank" style="text-decoration: underline;">sqkkyzx</a>、<a href="https://github.com/x1ao4" target="_blank" style="text-decoration: underline;">x1ao4</a>、<a href="https://github.com/anooki-c" target="_blank" style="text-decoration: underline;">anooki-c</a>'
                                            },
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
            "thread_count": 5,
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
        services = []

        if self._enabled and self._cron:
            logger.info(f"Plex中文本地化定时服务启动，时间间隔 {self._cron} ")
            services.append({
                "id": "PlexLocalization",
                "name": "Plex中文本地化",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.localization,
                "kwargs": {}
            })

        if not services:
            logger.info("Plex中文本地化服务定时服务未开启")

        return services

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown()
                    self._event.clear()
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
            tags_json = re.sub(r'//.*?\n', '', self._tags_json).strip()
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
        if not self._plex:
            logger.error("Plex配置不正确，请检查")
            return

        with lock:
            logger.info(f"正在准备执行本地化服务")
            libraries = self.__get_libraries()
            logger.info(f"正在准备本地化的媒体库 {libraries}")

            self.__loop_all(libraries=libraries, thread_count=self._thread_count, added_time=added_time)

    def __get_libraries(self):
        """获取媒体库信息"""
        libraries = {
            int(library.key): library
            for library in self._plex.library.sections()
            if library.type != 'photo' and library.key in self._library_ids  # 排除照片库
        }

        return libraries

    def __list_rating_keys(self, library: LibrarySection, type_id: int, is_collection: bool,
                           added_time: Optional[int] = None):
        """获取所有媒体项目"""
        if not library:
            return []

        if is_collection:
            endpoint = f"/library/sections/{library.key}/collections"
        else:
            endpoint = f"/library/sections/{library.key}/all?type={type_id}"
            if added_time:
                endpoint += f"&addedAt>={added_time}"

        response = self._plex_session.get(url=self.__adapt_request_url(endpoint), timeout=10)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        rating_keys = [data.get("ratingKey") for data in datas]

        if len(rating_keys):
            logger.info(f"<{library.title} {plexapi.utils.reverseSearchType(libtype=type_id)}> "
                        f"类型共计 {len(rating_keys)} 个{'合集' if is_collection else ''}")

        return rating_keys

    def __fetch_item(self, rating_key):
        """
        获取条目信息
        """
        endpoint = f"/library/metadata/{rating_key}"
        response = self._plex_session.get(self.__adapt_request_url(endpoint), timeout=10)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return datas[0] if datas else None

    def __fetch_all_items(self, rating_keys):
        """
        批量获取条目。
        :param rating_keys: 需要获取的条目的评级键列表。
        :return: 获取的所有条目列表。
        """
        endpoint = f"/library/metadata/{','.join(rating_keys)}"
        response = self._plex_session.get(self.__adapt_request_url(endpoint), timeout=10)
        items = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return items

    def __put_title_sort(self, rating_key: str, library_id: int, type_id: int, is_collection: bool, sort_title: str):
        """更新标题排序"""
        endpoint = f'library/metadata/{rating_key}' if is_collection else f'library/sections/{library_id}/all'
        self._plex_session.put(
            url=self.__adapt_request_url(endpoint),
            params={
                "type": type_id,
                "id": rating_key,
                "includeExternalMedia": 1,
                "titleSort.value": sort_title,
                "titleSort.locked": 1 if self._lock else 0
            }, timeout=10)

    def __put_tag(self, rating_key: str, library_id: int, type_id: str, tag, new_tag, tag_type):
        """更新标签"""
        endpoint = f"/library/sections/{library_id}/all"
        self._plex_session.put(
            url=self.__adapt_request_url(endpoint),
            params={
                "type": type_id,
                "id": rating_key,
                f"{tag_type}.locked": 1 if self._lock else 0,
                f"{tag_type}[0].tag.tag": new_tag,
                f"{tag_type}[].tag.tag-": tag
            }, timeout=10)

    def __process_rating_key(self, rating_key: str):
        """
        处理媒体标识
        """
        if not rating_key:
            return
        item = self.__fetch_item(rating_key=rating_key)
        if not item:
            return
        self.__process_item(item=item)

    def __process_items_batch(self, rating_keys):
        """
        获取并处理一批评级键对应的条目
        """
        items = self.__fetch_all_items(rating_keys=rating_keys)
        for item in items:
            self.__process_item(item)

    def __process_item(self, item: dict):
        """
        处理元数据
        """
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
        is_collection = item_type != "collection"

        title = item.get("title", "")
        title_sort = item.get("titleSort", "")

        # 更新标题排序
        if self.__has_chinese(title_sort) or title_sort == "":
            title_sort = self.__convert_to_pinyin(title)
            self.__put_title_sort(rating_key=rating_key,
                                  library_id=library_id,
                                  type_id=type_id,
                                  is_collection=is_collection,
                                  sort_title=title_sort)
            logger.info(f"{title} < {title_sort} >")

        tags: dict[str, list] = {
            "genre": [genre.get("tag") for genre in item.get('Genre', {})],  # 流派
            "style": [style.get("tag") for style in item.get('Style', {})],  # 风格
            "mood": [mood.get("tag") for mood in item.get('Mood', {})]  # 情绪
        }

        # 汉化标签
        for tag_type, tag_list in tags.items():
            if tag_list:
                for tag in tag_list:
                    new_tag = self._tags.get(tag)
                    if new_tag:
                        self.__put_tag(rating_key=rating_key,
                                       library_id=library_id,
                                       type_id=type_id,
                                       tag=tag,
                                       new_tag=new_tag,
                                       tag_type=tag_type)
                        logger.info(f"{title} : {tag} → {new_tag}")

    def __loop_all(self, libraries: dict, thread_count: int = None, added_time: Optional[int] = None):
        """选择媒体库并遍历其中的每一个媒体。"""
        if not self._tags:
            logger.warn("标签本地化配置不能为空，请检查")
            return

        logger.info(f"当前标签本地化配置为：{self._tags}")
        start_time = time.time()
        thread_count = thread_count or 5
        logger.info(f"正在运行中文本地化，线程数：{thread_count}，锁定元数据：{self._lock}")

        # 生成所有需要处理的rating keys
        if added_time:
            rating_keys = self.__generate_all_rating_keys(libraries=libraries,
                                                          with_collection=False,
                                                          added_time=added_time)
        else:
            rating_keys = self.__generate_all_rating_keys(libraries=libraries,
                                                          with_collection=True)

        # 分批处理rating keys
        self.__process_rating_keys_in_batches(rating_keys=rating_keys,
                                              thread_count=thread_count,
                                              batch_size=self._batch_size)

        elapsed_time = time.time() - start_time
        if added_time:
            formatted_added_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(added_time))
            message_text = f"最近一次入库时间：{formatted_added_time}，Plex本地化完成，用时 {elapsed_time:.2f} 秒"
        else:
            message_text = f"Plex本地化完成，用时 {elapsed_time:.2f} 秒"

        self.__send_message(title="【Plex中文本地化】", text=message_text)

        logger.info(message_text)

    def __generate_all_rating_keys(self, libraries, with_collection: bool = True, added_time: Optional[int] = None):
        """生成所有库中项目的rating keys列表"""
        # 使用集合来自动去除重复的rating keys
        rating_keys_set = set()
        for library in libraries.values():
            library_types = TYPES.get(library.type, [])
            for type_id in library_types:
                if with_collection:
                    rating_keys_set.update(self.__list_rating_keys(library, type_id, False))
                    rating_keys_set.update(self.__list_rating_keys(library, type_id, True))
                else:
                    rating_keys_set.update(self.__list_rating_keys(library, type_id, False, added_time))
        return list(rating_keys_set)

    def __process_rating_keys_in_batches(self, rating_keys, thread_count, batch_size=100):
        """分批处理rating keys列表"""
        total_keys_count = len(rating_keys)
        total_batches = (total_keys_count + batch_size - 1) // batch_size

        logger.info(f"总条目：{total_keys_count}，每批处理条数：{batch_size}，总批次数：{total_batches}，准备开始执行")

        futures = {}
        successful_batches = 0  # 成功处理的批次数

        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            # 提交所有批次处理任务
            for i in range(0, total_keys_count, batch_size):
                batch_keys = rating_keys[i:i + batch_size]
                future = executor.submit(self.__process_items_batch, batch_keys)
                futures[future] = i // batch_size

            # 实时处理每个future的完成
            for future in concurrent.futures.as_completed(futures):
                batch_index = futures[future]
                try:
                    future.result()
                    logger.debug(f"第{batch_index + 1}批次处理成功")
                    successful_batches += 1
                except Exception as e:
                    logger.error(f"第{batch_index + 1}批次处理过程中发生错误: {e}", exc_info=True)

        # 打印处理完毕后的结果
        logger.info(f"处理完毕，成功批次数：{successful_batches}")

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
    def __has_chinese(string):
        """判断是否有中文"""
        for char in string:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    @staticmethod
    def __convert_to_pinyin(text):
        """将字符串转换为拼音首字母形式。"""
        str_a = pypinyin.pinyin(text, style=pypinyin.FIRST_LETTER)
        str_b = [str(str_a[i][0]).upper() for i in range(len(str_a))]
        return ''.join(str_b).replace("：", ":").replace("（", "(").replace("）", ")").replace("，", ",")

    @staticmethod
    def __adapt_base_url(host: str) -> str:
        """
        标准化提供的主机地址，确保它以http://或https://开头，并且以斜杠(/)结尾。
        """
        # 移除尾部斜杠，如果有的话，然后确保最后是以斜杠结束
        if not host.endswith("/"):
            host = host + "/"
        # 确保URL以http://或https://开始
        if not host.startswith("http://") and not host.startswith("https://"):
            host = "http://" + host
        return host

    def __adapt_request_url(self, endpoint: str):
        """
        适配请求的URL，确保每个请求的URL是完整的，基于已经设置的_plex_host
        用于在发送请求前自动处理和修正请求的URL
        """
        # 如果URL不是完整的HTTP或HTTPS URL，则将_plex_host添加到URL前
        if not endpoint.startswith(('http://', 'https://')):
            endpoint = f"{self._plex_host.rstrip('/')}/{endpoint.lstrip('/')}"
        return endpoint

    @staticmethod
    def __adapt_plex_session() -> Session:
        """
        创建并配置一个针对Plex服务的requests.Session实例
        这个会话包括特定的头部信息，用于处理所有的Plex请求
        """
        # 设置请求头部，通常包括验证令牌和接受/内容类型头部
        headers = {
            "X-Plex-Token": settings.PLEX_TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        session = requests.session()
        session.headers = headers
        return session

    def __send_message(self, title: str, text: str):
        """
        发送消息
        """
        if not self._notify:
            return

        self.post_message(mtype=NotificationType.SiteMessage, title=title, text=text)
