import concurrent.futures
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import Event, eventmanager
from app.core.meta import MetaAnime, MetaBase, MetaVideo
from app.core.metainfo import is_anime
from app.db.transferhistory_oper import TransferHistoryOper
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import ServiceInfo
from app.schemas.types import EventType, MediaType

lock = threading.Lock()


class PlexEdition(_PluginBase):
    # 插件名称
    plugin_name = "PlexEdition"
    # 插件描述
    plugin_desc = "根据入库记录修改Edition为电影版本/资源类型/特效信息。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/plexedition.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexedition"
    # 加载顺序
    plugin_order = 94
    # 可使用的用户级别
    auth_level = 1
    # Plex
    _plex = None

    # region 私有属性
    mediaserver_helper = None
    history_oper = None
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
    # 运行线程数
    _thread_count = None
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self.history_oper = TransferHistoryOper()
        self.mediaserver_helper = MediaServerHelper()
        if not config:
            return False
        self._onlyonce = config.get("onlyonce")
        self._cron = config.get("cron")
        self._notify = config.get("notify")
        self._libraries = config.get("libraries")
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

        # 如果开启了入库后运行一次，延迟时间又不填，默认为200s
        if self._execute_transfer and not self._delay:
            self._delay = 200

        # 停止现有任务
        self.stop_service()

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
            "libraries": self._libraries,
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
                                        }
                                    }
                                ]
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
                                        }
                                    }
                                ]
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
                                        }
                                    }
                                ]
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
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式',
                                            'hint': '使用cron表达式指定执行周期，如 0 8 * * *',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
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
                                            'placeholder': '入库后延迟执行时间',
                                            'hint': '入库后延迟执行的时间（秒）',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
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
                                            'hint': '执行任务时使用的线程数量',
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
                                            'model': 'libraries',
                                            'label': '媒体库',
                                            'items': self.__get_service_library_options(),
                                            'hint': '选择要处理的媒体库',
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
        delay_message = f"{self._delay} 秒后运行一次Edition服务" if self._delay else "准备运行一次Edition服务"
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
            logger.info(f"正在准备执行Edition服务")
            service_libraries = self.__get_service_libraries()
            if not service_libraries:
                logger.error(f"Plex 配置不正确，请检查")
                return
            logger.info(f"正在准备Edition的媒体库 {service_libraries}")
            self.__loop_all(service_libraries=service_libraries, thread_count=self._thread_count)

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
                for library in libraries if library.TYPE == "movie"
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

    def __process_items(self, item):
        """
        处理单个媒体项
        """
        if item.type != "movie":
            logger.info(f"{item.title} is not movie, not support edit edition")
            return

        if item.editionTitle or not item.locations:
            return

        locked_fields = [field.name for field in item.fields if field.locked]
        if "editionTitle" in locked_fields:
            logger.debug(f"{item.title}: titleSort is locked, skip")
        else:
            file_name = item.locations[0]
            tmdb_id = self.__get_tmdb_id(item)
            histories = []
            if tmdb_id:
                histories = self.history_oper.get_by(tmdbid=tmdb_id, mtype="电影", dest=file_name)

            if not histories:
                histories = self.history_oper.get_by_title(title=file_name)

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

    @staticmethod
    def __list_items(library):
        """
        获取指定媒体库中的所有媒体项
        """
        if not library:
            return None
        items = library.search(container_size=1000)
        logger.info(f"{library.title} 类型共计{len(items)}个媒体")
        return items

    def __loop_all(self, service_libraries: Dict[str, Dict[int, Any]], thread_count: int = None):
        """
        选择媒体库并遍历其中的每一个媒体。
        """
        overall_start_time = time.time()
        thread_count = thread_count or 5  # 默认线程数为5
        logger.info(f"正在运行Edition服务，线程数：{thread_count}，锁定元数据：{self._lock}")

        for service_name, libraries in service_libraries.items():
            service = self.service_info(name=service_name)
            if not service or not service.instance:
                logger.info(f"获取媒体服务器 {service_name} 实例失败，跳过处理")
                continue

            service_start_time = time.time()
            logger.info(f"开始处理媒体服务器 {service_name}")

            for library_id, library_details in libraries.items():
                if items := self.__list_items(library_details):
                    self.__threads(datalist=items, func=self.__process_items,
                                   thread_count=thread_count)

            service_elapsed_time = time.time() - service_start_time
            logger.info(f"媒体服务器 {service_name} 处理完成，耗时 {service_elapsed_time:.2f} 秒")

        overall_elapsed_time = time.time() - overall_start_time
        logger.info(f"所有媒体服务器处理完毕，总耗时 {overall_elapsed_time:.2f} 秒")

    @staticmethod
    def __threads(datalist, func, thread_count):
        """
        多线程处理模块，每个线程处理部分数据
        :param datalist: 待处理数据列表
        :param func: 处理函数
        :param thread_count: 运行线程数
        """

        def chunks(lst, n):
            """列表切片工具，将列表分成几个块。"""
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        chunk_size = (len(datalist) + thread_count - 1) // thread_count
        list_chunks = list(chunks(datalist, chunk_size))

        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            tasks = [executor.submit(func, item) for chunk in list_chunks for item in chunk]
            for task in concurrent.futures.as_completed(tasks):
                task.result()

    @staticmethod
    def __get_tmdb_id(item):
        """获取tmdb_id"""
        if not item:
            return None
        if item.guids:
            for guid in item.guids:
                if guid.id.startswith("tmdb://"):
                    tmdb_id = guid.id.split("//")[1]
                    return tmdb_id
        return None
