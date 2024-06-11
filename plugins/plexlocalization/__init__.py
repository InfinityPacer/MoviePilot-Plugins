import concurrent.futures
import json
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple

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
from app.schemas.types import EventType

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
    plugin_version = "1.3"
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
    # Plex
    _plex = None

    # region 私有属性

    # plex_host
    _plex_host = None
    # session
    _plex_session = None
    # 是否开启
    _enabled = False
    # 立即执行一次
    _onlyonce = False
    # 任务执行间隔
    _cron = None
    # 发送通知
    _notify = False
    # 需要处理的媒体库
    _library_ids = None
    # 锁定元数据
    _lock = None
    # 入库后执行一次
    _execute_transfer = None
    # 入库后延迟执行时间
    _delay = None
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

        # 如果开启了入库后执行一次，延迟时间又不填，默认为300s
        if self._execute_transfer and not self._delay:
            self._delay = 300

        # 停止现有任务
        self.stop_service()

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        self._onlyonce = True
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
            "delay": self._delay
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
            logger.info(f"媒体库配置不正确，请检查")

        if "plex" not in settings.MEDIASERVER:
            logger.info(f"Plex配置不正确，请检查")

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
                                            'hint': '电影合集只有锁定时才会生效'
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
                                            'label': '入库后执行一次'
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式'
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'delay',
                                            'label': '延迟时间（秒）',
                                            'placeholder': '入库后延迟执行时间'
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'thread_count',
                                            'label': '运行线程数',
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
                                            'items': library_options
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
            "delay": 300
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
    def after_transfer(self, event: Event):
        """
        入库后执行一次
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

        # 确定季度和集数信息，如果存在则添加前缀空格
        season_episode = f" {meta.season_episode}" if meta.season_episode else ""

        # 根据是否有延迟设置不同的日志消息
        delay_message = f"{self._delay} 秒后执行一次本地化服务" if self._delay else "准备执行一次本地化服务"
        logger.info(f"{mediainfo.title_year}{season_episode} 已入库，{delay_message}")

        if not self._scheduler:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)

        self._scheduler.remove_all_jobs()

        self._scheduler.add_job(
            func=self.localization,
            trigger="date",
            run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=self._delay),
            name="Plex中文本地化",
        )

        # 启动任务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def localization(self):
        """本地化服务"""
        with lock:
            logger.info(f"正在准备执行本地化服务")
            libraries = self.__get_libraries()
            logger.info(f"正在准备本地化的媒体库 {libraries}")

            self.__loop_all(libraries=libraries, thread_count=self._thread_count)

    def __get_libraries(self):
        """获取媒体库信息"""
        libraries = {
            int(library.key): library
            for library in self._plex.library.sections()
            if library.type != 'photo' and library.key in self._library_ids  # 排除照片库
        }

        return libraries

    def __list_rating_key(self, library: LibrarySection, type_id: int, is_collection: bool):
        """获取所有媒体项目"""
        if not library:
            return []

        if is_collection:
            endpoint = f"/library/sections/{library.key}/collections"
        else:
            endpoint = f"/library/sections/{library.key}/all?type={type_id}"

        response = self._plex_session.get(self.__adapt_request_url(endpoint))
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        rating_keys = [data.get("ratingKey") for data in datas]

        if len(rating_keys):
            logger.info(f"<{library.title} {plexapi.utils.reverseSearchType(libtype=type_id)}> "
                        f"类型共计 {len(rating_keys)} 个{'合集' if is_collection else ''}")

        # if rating_keys:
        # items = self.fetch_all_items(section=section, rating_keys=rating_keys)

        return rating_keys

    def __fetch_item(self, rating_key):
        """
        获取条目信息
        """
        endpoint = f"/library/metadata/{rating_key}"
        response = self._plex_session.get(self.__adapt_request_url(endpoint))
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return datas[0] if datas else None

    @staticmethod
    def fetch_all_items(section, rating_keys, page_size=200):
        """
        根据指定的分页大小，批量获取条目。

        :param section: 用于获取条目的区域。
        :param rating_keys: 需要获取的条目的评级键列表。
        :param page_size: 每批次获取的条目数量。
        :return: 获取的所有条目列表。
        """
        # 初始化结果列表
        all_items = []
        # 计算总页数
        total_pages = (len(rating_keys) + page_size - 1) // page_size

        # 分批次处理每一页
        for page in range(total_pages):
            # 计算每一页的起始和结束索引
            start_index = page * page_size
            end_index = start_index + page_size
            # 获取当前页的评级键
            current_keys = rating_keys[start_index:end_index]

            # 调用fetchItems获取当前页的条目
            items = section.fetchItems(ekey=current_keys,
                                       container_start=0,
                                       container_size=page_size,
                                       maxresults=len(current_keys))

            # 将获取的条目添加到结果列表
            all_items.extend(items)
        return all_items

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
            })

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
            })

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

    def __loop_all(self, libraries: dict, thread_count: int = None):
        """选择媒体库并遍历其中的每一个媒体。"""
        if not self._tags:
            logger.warn("标签本地化配置不能为空，请检查")
            return

        logger.info(f"当前标签本地化配置为：{self._tags}")
        t = time.time()
        logger.info(f"正在运行中文本地化，线程数：{thread_count}，锁定元数据：{self._lock}")

        args_list = []
        for library in libraries.values():
            library_types = TYPES.get(library.type, [])
            for type_id in library_types:
                for is_collection in [False, True]:
                    args_list.append((library, type_id, is_collection))

        # 使用多线程获取所有项目列表
        items_list = self.__threads(self.__list_rating_key, args_list, thread_count or len(args_list))

        # 处理所有项目
        for items in items_list:
            if items:
                self.__threads(self.__process_rating_key, [(item,) for item in items], thread_count or len(items))
        logger.info(f'运行完毕，用时 {time.time() - t} 秒')

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
    def __threads(func, args_list, thread_count):
        """
        多线程处理模块
        :param func: 处理函数
        :param args_list: 参数列表，每个元素是一个参数元组，包含传递给func的参数
        :param thread_count: 运行线程数
        :return: 处理后的结果列表
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            results = list(executor.map(lambda args: func(*args), args_list))
        return results

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
        这个钩子函数用于在发送请求前自动处理和修正请求的URL
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
