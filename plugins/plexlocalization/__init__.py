import concurrent.futures
import json
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple

import pypinyin
import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import eventmanager, Event
from app.core.meta import MetaBase
from app.log import logger
from app.modules.plex import Plex
from app.plugins import _PluginBase
from app.schemas.types import EventType

lock = threading.Lock()


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

    # 是否开启
    _enabled = False
    # 立即执行一次
    _onlyonce = False
    # 任务执行间隔
    _cron = None
    # 开启通知
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
                                            'label': '开启通知',
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
                                            'label': '执行周期'
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
                                            'model': 'library_ids',
                                            'multiple': True,
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

    @eventmanager.register(EventType.TransferComplete)
    def after_transfer(self, event: Event):
        """
        发送通知消息
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
        with lock:
            logger.info(f"正在准备执行本地化服务")
            libraries = self.__get_libraries()
            logger.info(f"正在准备本地化的媒体库 {libraries}")
            service = PlexService(translate_tags=self._tags, lock_meta=self._lock,
                                  host=settings.PLEX_HOST, token=settings.PLEX_TOKEN)
            if service.login:
                service.loop_all(libraries=libraries, thread_count=self._thread_count)
            else:
                logger.info("本地化服务已取消")

    def __get_libraries(self):
        """获取媒体库信息"""
        libraries = {
            int(library.key): (int(library.key), TYPES[library.type], library.title, library.type)
            for library in self._plex.library.sections()
            if library.type != 'photo' and library.key in self._library_ids  # 排除照片库
        }

        return libraries

    def __get_tags(self) -> dict:
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


types = {"movie": 1, "show": 2, "artist": 8, "album": 9, 'track': 10}
TYPES = {"movie": [1], "show": [2], "artist": [8, 9, 10]}


class PlexService:
    # request.session
    _session = None
    # plex_host
    _host = None
    # plex_token
    _token = None
    # translate_tags
    _translate_tags = None
    # lock_meta
    _lock_meta = None
    # login
    login = False

    def __init__(self, translate_tags: dict, lock_meta=False, host: str = None, token: str = None):
        if translate_tags:
            self._translate_tags = translate_tags

        self._lock_meta = lock_meta

        if host and token:
            self._host = host
            self._token = token
            # 去除末尾的斜线（如果存在）
            if self._host.endswith("/"):
                self._host = self._host[:-1]
            # 确保URL以http://或https://开始
            if not self._host.startswith("http://") and not self._host.startswith("https://"):
                self._host = "http://" + self._host

            headers = {'X-Plex-Token': self._token, 'Accept': 'application/json', "Content-Type": "application/json"}
            self._session = requests.session()
            self._session.headers = headers
            result, message = self._login()
            self.login = result
            logger.info(message)

    def _login(self):
        try:
            friendly_name = self._session.get(url=self._host).json()['MediaContainer']['friendlyName']
            return True, f"已成功连接到服务器{friendly_name}"
        except Exception as e:
            logger.info(e)
            return False, "Plex服务器连接不成功，请检查配置文件是否正确"

    def _list_keys(self, select, is_coll: bool):
        types_index = {value: key for key, value in types.items()}

        endpoint = f'sections/{select[0]}/collections' if is_coll else f'sections/{select[0]}/all?type={select[1]}'
        datas = self._session.get(f'{self._host}/library/{endpoint}').json().get("MediaContainer", {}).get(
            "Metadata",
            [])
        keys = [data.get("ratingKey") for data in datas]

        if len(keys):
            if is_coll:
                logger.info(F"<{select[2]} {types_index[select[1]]}> 类型共计{len(keys)}个合集")
            else:
                logger.info(F"<{select[2]} {types_index[select[1]]}> 类型共计{len(keys)}个媒体")

        return keys

    def _get_metadata(self, rating_key):
        url = f'{self._host}/library/metadata/{rating_key}'
        return self._session.get(url=url).json()["MediaContainer"]["Metadata"][0]

    def _put_title_sort(self, select, rating_key, sort_title, lock_meta, is_coll: bool):
        endpoint = f'library/metadata/{rating_key}' if is_coll else f'library/sections/{select[0]}/all'
        self._session.put(
            url=f"{self._host}/{endpoint}",
            params={
                "type": select[1],
                "id": rating_key,
                "includeExternalMedia": 1,
                "titleSort.value": sort_title,
                "titleSort.locked": 1 if lock_meta else 0
            }
        )

    def _put_tag(self, select, rating_key, tag, addtag, tag_type, title, lock_meta):
        self._session.put(
            url=f"{self._host}/library/sections/{select[0]}/all",
            params={
                "type": select[1],
                "id": rating_key,
                f"{tag_type}.locked": 1 if lock_meta else 0,
                f"{tag_type}[0].tag.tag": addtag,
                f"{tag_type}[].tag.tag-": tag
            }
        )
        logger.info(f"{title} : {tag} → {addtag}")

    def _process_items(self, rating_key):
        metadata = self._get_metadata(rating_key)

        library_id = metadata['librarySectionID']

        is_coll, type_id = (False, types[metadata['type']]) \
            if metadata['type'] != 'collection' \
            else (True, types[metadata['subtype']])
        title = metadata["title"]
        title_sort = metadata.get("titleSort", "")
        tags: dict[str:list] = {
            'genre': [genre.get("tag") for genre in metadata.get('Genre', {})],  # 流派
            'style': [style.get("tag") for style in metadata.get('Style', {})],  # 风格
            'mood': [mood.get("tag") for mood in metadata.get('Mood', {})]  # 情绪
        }

        select = library_id, type_id

        # 更新标题排序
        if self._has_chinese(title_sort) or title_sort == "":
            title_sort = self._convert_to_pinyin(title)
            self._put_title_sort(select, rating_key, title_sort, self._lock_meta, is_coll)
            logger.info(f"{title} < {title_sort} >")

        # 汉化标签
        for tag_type, tag_list in tags.items():
            if tag_list:
                for tag in tag_list:
                    self._put_tag(select, rating_key, tag, new_tag, tag_type, title, self._lock_meta) \
                        if (new_tag := self._translate_tags.get(tag)) else None

    def loop_all(self, libraries: dict, thread_count: int = None):
        """选择媒体库并遍历其中的每一个媒体。"""
        if not self._translate_tags:
            logger.warn("标签本地化配置不能为空，请检查")
            return

        logger.info(f"当前标签本地化配置为：{self._translate_tags}")

        t = time.time()
        logger.info(f"正在运行中文本地化，线程数：{thread_count}，锁定元数据：{self._lock_meta}")

        for library in libraries.values():
            for type_id in library[1]:
                for is_coll in [False, True]:
                    if keys := self._list_keys((library[0], type_id, library[2]), is_coll):
                        self._threads(datalist=keys, func=self._process_items,
                                      thread_count=thread_count)

        logger.info(f'运行完毕，用时 {time.time() - t} 秒')

    @staticmethod
    def _has_chinese(string):
        """判断是否有中文"""
        for char in string:
            if '\u4e00' <= char <= '\u9fff':
                return True
        return False

    @staticmethod
    def _convert_to_pinyin(text):
        """将字符串转换为拼音首字母形式。"""
        str_a = pypinyin.pinyin(text, style=pypinyin.FIRST_LETTER)
        str_b = [str(str_a[i][0]).upper() for i in range(len(str_a))]
        return ''.join(str_b).replace("：", ":").replace("（", "(").replace("）", ")").replace("，", ",")

    @staticmethod
    def _threads(datalist, func, thread_count):
        """
        多线程处理模块
        :param datalist: 待处理数据列表
        :param func: 处理函数
        :param thread_count: 运行线程数
        :return:
        """

        def chunks(lst, n):
            """列表切片工具"""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        chunk_size = (len(datalist) + thread_count - 1) // thread_count  # 计算每个线程需要处理的元素数量
        list_chunks = list(chunks(datalist, chunk_size))  # 将 datalist 切分成 n 段

        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            result_items = list(executor.map(func, [item for chunk in list_chunks for item in chunk]))

        return result_items
