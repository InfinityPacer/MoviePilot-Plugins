import concurrent.futures
import threading
import time
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import eventmanager, Event
from app.core.meta import MetaBase, MetaAnime, MetaVideo
from app.core.metainfo import is_anime
from app.db.transferhistory_oper import TransferHistoryOper
from app.log import logger
from app.modules.plex import Plex
from app.plugins import _PluginBase
from app.schemas.types import EventType, MediaType

lock = threading.Lock()


class PlexEdition(_PluginBase):
    # 插件名称
    plugin_name = "PlexEdition"
    # 插件描述
    plugin_desc = "根据入库记录修改Edition为电影版本/资源类型/特效信息。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/plexedition.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexedition"
    # 加载顺序
    plugin_order = 93
    # 可使用的用户级别
    auth_level = 1
    # Plex
    _plex = None
    # history_oper
    _history_oper = None

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
    # 运行线程数
    _thread_count = None
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self._plex = Plex().get_plex()
        self._history_oper = TransferHistoryOper()

        if not config:
            logger.info("Plex版本管理开启失败，无法获取插件配置")
            return False

        self._enabled = config.get("enabled")
        self._onlyonce = config.get("onlyonce")
        self._cron = config.get("cron")
        self._notify = config.get("notify")
        self._library_ids = config.get("library_ids")
        self._lock = config.get("lock")
        self._execute_transfer = config.get("execute_transfer")
        try:
            self._thread_count = int(config.get("thread_count", 5))
        except ValueError:
            self._thread_count = 5
        try:
            self._delay = int(config.get("delay", 200))
        except ValueError:
            self._delay = 200

        # 如果开启了入库后执行一次，延迟时间又不填，默认为200s
        if self._execute_transfer and not self._delay:
            self._delay = 200

        # 停止现有任务
        self.stop_service()

        # self._onlyonce = True
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._onlyonce:
            logger.info(f"PlexEdition服务，立即运行一次")
            self._scheduler.add_job(
                func=self.refresh_edition,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="PlexEdition",
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
            # 仅支持电影库
            if library.TYPE != "movie":
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
                                            'label': '锁定元数据'
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
                                                'html': '灵感来自于项目 <a href="https://github.com/x1ao4/plex-edition-manager" target="_blank" style="text-decoration: underline;">plex-edition-manager</a> ，特此感谢 <a href="https://github.com/x1ao4" target="_blank" style="text-decoration: underline;">x1ao4</a>'
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
                                            'text': '注意：如开启锁定元数据，则修改后需要在Plex中手动解锁才允许修改，'
                                                    '请先在测试媒体库验证无问题后再继续使用'
                                        }
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
            "cron": "30 0 * * *",
            "lock": False,
            "thread_count": 5,
            "execute_transfer": False,
            "delay": 200
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
            logger.info(f"PlexEdition定时服务启动，时间间隔 {self._cron} ")
            services.append({
                "id": "PlexEdition",
                "name": "PlexEdition",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.refresh_edition,
                "kwargs": {}
            })

        if not services:
            logger.info("PlexEdition定时服务未开启")

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

        if mediainfo.type != MediaType.MOVIE:
            return

        # 确定季度和集数信息，如果存在则添加前缀空格
        season_episode = f" {meta.season_episode}" if meta.season_episode else ""

        # 根据是否有延迟设置不同的日志消息
        delay_message = f"{self._delay} 秒后执行一次Edition服务" if self._delay else "准备执行一次Edition服务"
        logger.info(f"{mediainfo.title_year}{season_episode} 已入库，{delay_message}")

        if not self._scheduler:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)

        self._scheduler.remove_all_jobs()

        self._scheduler.add_job(
            func=self.refresh_edition,
            trigger="date",
            run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=self._delay),
            name="PlexEdition",
        )

        # 启动任务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def refresh_edition(self):
        with lock:
            libraries = self._get_libraries()
            logger.info(f"正在准备Edition的媒体库 {libraries}")
            self._loop_all(libraries=libraries, thread_count=self._thread_count)

    def _get_libraries(self):
        """获取媒体库信息"""
        libraries = {
            int(library.key): (int(library.key), "1", library.title, library.type)
            for library in self._plex.library.sections()
            if library.type == "movie" and library.key in self._library_ids  # 排除照片库
        }

        return libraries

    def _process_items(self, item):
        if item.type != "movie":
            logger.info(f"{item.title} is not movie, not support edit edition")
            return

        if item.editionTitle or not item.locations:
            return

        file_name = item.locations[0]
        tmdb_id = self._get_tmdb_id(item)
        histories = []
        if tmdb_id:
            histories = self._history_oper.get_by(tmdbid=tmdb_id, mtype="电影", dest=file_name)

        if not histories:
            histories = self._history_oper.get_by_title(title=file_name)

        if histories:
            history = histories[0]
            file_name = history.src if history.src else file_name

        is_anime_flag = is_anime(file_name)
        meta = MetaAnime(file_name, file_name, True) \
            if is_anime_flag else MetaVideo(file_name, file_name, True)

        if not meta.edition:
            logger.warn(f"{item.title}({item.ratingKey}) can't get edition, can't edit edition")
            return

        old_edition = item.editionTitle
        item.edit(**{
            "editionTitle.locked": 1 if self._lock else 0,
            "editionTitle.value": meta.edition
        })

        logger.info(f"{item.title}({item.ratingKey}) edition : {old_edition} -> {meta.edition}")

    def _list_items(self, library):
        if not library:
            return None
        section = self._plex.library.sectionByID(sectionID=library[0])
        items = section.search(libtype=section.TYPE, container_size=1000)
        logger.info(F"<{library[2]} {library[3]}> 类型共计{len(items)}个媒体")
        return items

    def _loop_all(self, libraries: dict, thread_count: int = None):
        """选择媒体库并遍历其中的每一个媒体。"""
        t = time.time()
        logger.info(f"正在运行Edition服务，线程数：{thread_count}，锁定元数据：{self._lock}")

        for library in libraries.values():
            if items := self._list_items(library):
                self._threads(datalist=items, func=self._process_items,
                              thread_count=thread_count)

        logger.info(f"运行完毕，用时 {time.time() - t} 秒")

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

    @staticmethod
    def _get_tmdb_id(item):
        """获取tmdb_id"""
        if not item:
            return None
        if item.guids:
            for guid in item.guids:
                if guid.id.startswith("tmdb://"):
                    tmdb_id = guid.id.split("//")[1]
                    return tmdb_id
        return None
