import threading
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import ServiceInfo
from app.schemas.types import EventType, NotificationType

lock = threading.Lock()


class PlexRefreshRecent(_PluginBase):
    # 插件名称
    plugin_name = "Plex元数据刷新"
    # 插件描述
    plugin_desc = "定时通知Plex刷新最近入库元数据。"
    # 插件图标
    plugin_icon = "Plex_A.png"
    # 插件版本
    plugin_version = "1.6"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexrefreshrecent_"
    # 加载顺序
    plugin_order = 90
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    mediaserver_helper = None
    # 是否开启
    _enabled = False
    # 任务执行间隔
    _cron = None
    # 时间范围
    _offset_days = "0"
    # 立即运行一次
    _onlyonce = False
    # 发送通知
    _notify = False
    # limit
    _limit = None
    # 强制刷新
    _force = False
    # 媒体服务器
    _mediaservers = None
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self.mediaserver_helper = MediaServerHelper()
        if not config:
            return

        self._enabled = config.get("enabled")
        self._cron = config.get("cron")
        self._notify = config.get("notify")
        self._onlyonce = config.get("onlyonce")
        self._force = config.get("force")
        self._mediaservers = config.get("mediaservers")
        try:
            self._offset_days = int(config.get("offset_days", 3))
        except ValueError:
            self._offset_days = 3

        try:
            self._limit = int(config.get("limit", 1000))
        except ValueError:
            self._limit = 1000

        # 停止现有任务
        self.stop_service()

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._onlyonce:
            logger.info(f"Plex元数据刷新服务启动，立即运行一次")
            self._scheduler.add_job(
                func=self.refresh_recent,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="Plex元数据刷新",
            )

            # 关闭一次性开关
            self._onlyonce = False

        self.update_config(
            {
                "onlyonce": False,
                "cron": self._cron,
                "enabled": self._enabled,
                "offset_days": self._offset_days,
                "notify": self._notify,
                "limit": self._limit,
                "force": self._force,
                "mediaservers": self._mediaservers
            }
        )

        # 启动任务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        服务信息
        """
        if not self._mediaservers:
            logger.warning("尚未配置媒体服务器，请检查配置")
            return None

        services = self.mediaserver_helper.get_services(name_filters=self._mediaservers, type_filter="plex")
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

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [
            {
                "cmd": "/refresh_plex_recent",
                "event": EventType.PluginAction,
                "desc": "Plex元数据刷新",
                "category": "",
                "data": {"action": "refresh_plex_recent_event"},
            }
        ]

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
                                'props': {'cols': 12, 'md': 3},
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
                                'props': {'cols': 12, 'md': 3},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'force',
                                            'label': '强制刷新',
                                            'hint': '无论是否已存在，将重新刷新元数据',
                                            'persistent-hint': True
                                        },
                                    }
                                ],
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 3},
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
                                'props': {'cols': 12, 'md': 3},
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
                            },
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
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
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'offset_days',
                                            'label': '几天内',
                                            'hint': '从当前日期往前几天内的数据',
                                            'persistent-hint': True
                                        },
                                    }
                                ],
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'limit',
                                            'label': '最大元数据数量',
                                            'hint': '一次刷新的最大元数据条数',
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
                                            'model': 'mediaservers',
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
                    }
                ]
            }
        ], {
            "enabled": False,
            "notify": True,
            "cron": "0 */3 * * *",
            "offset_days": "3",
            "limit": 1000
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
            logger.info(f"刷新Plex最近入库元数据定时服务启动，时间间隔 {self._cron} ")
            services.append({
                "id": "PlexRefreshRecent",
                "name": "Plex元数据刷新",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.refresh_recent,
                "kwargs": {}
            })

        if not services:
            logger.info("Plex元数据刷新定时服务未开启")

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
            print(str(e))

    @eventmanager.register(EventType.PluginAction)
    def refresh_recent(self, event: Event = None):
        """刷新最近元数据"""
        if event:
            logger.info(f"event： {event}")
            event_data = event.event_data
            if not event_data or event_data.get("action") != "refresh_plex_recent_event":
                return

        if not self.__check_plex_media_server():
            return

        with lock:
            logger.info(f"准备刷新最近入库元数据")
            msg = ""
            try:
                success, count = self.__refresh_plex()
                # 发送通知
                if self._notify:
                    if success:
                        msg = f"元数据刷新完成，刷新条数：{count}"
                    else:
                        msg = "元数据刷新失败，请检查日志"
            except Exception as e:
                logger.error(e)
                msg = f"元数据刷新失败，失败原因：{e}"

        logger.info(f"已完成最近入库元数据刷新")
        if self._notify:
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title=f"【Plex最近{self._offset_days}天元数据刷新】",
                text=msg
            )

    def __refresh_plex(self) -> [bool, int]:
        """刷新Plex"""
        if not self.__check_plex_media_server():
            return False, 0

        refreshed_count = 0
        for service in self.service_infos().values():
            try:
                plex = service.instance.get_plex()
                if not plex:
                    logger.warning(f"{service.name} 获取 Plex 实例失败，请检查配置")
                    continue
                logger.info(f"准备对 {service.name} 进行元数据刷新")
                timestamp = self.__get_timestamp(offset_day=-int(self._offset_days))
                library_items = service.instance.get_plex().library.search(limit=self._limit, **{"addedAt>": timestamp})

                refreshed_items = {}
                for item in library_items:
                    self.__refresh_metadata(item, refreshed_items)
                    refreshed_count += len(refreshed_items)
                logger.info(f"{service.name} 元数据刷新已完成，刷新条数：{len(refreshed_items)}")
            except Exception as e:
                logger.error(f"{service.name} 刷新最近元数据过程中发生异常，{e}")

        return True, refreshed_count

    def __refresh_metadata(self, item, refreshed_items):
        """
        递归刷新媒体元数据，但避免重复刷新已处理的项目
        :param item: 要刷新的 Plex 媒体项
        :param refreshed_items: 字典，用于记录已刷新的项目的ratingKey，避免重复刷新
        """
        parent_rating_key = getattr(item, "parentRatingKey", None)
        grandparent_rating_key = getattr(item, "grandparentRatingKey", None)

        summary = getattr(item, "summary", "")

        parent_title = getattr(item, "parentTitle", None)
        grandparent_title = getattr(item, "grandparentTitle", None)

        parent_info = f"{parent_title} " if parent_title else ""
        grandparent_info = f"{grandparent_title} " if grandparent_title else ""

        # 检查当前项是否已刷新或其任一上级是否已刷新
        if (item.ratingKey in refreshed_items or
                (parent_rating_key and parent_rating_key in refreshed_items) or
                (grandparent_rating_key and grandparent_rating_key in refreshed_items)):
            logger.info(f"父级已刷新，跳过此项：{grandparent_info}{parent_info}{item.title} ({item.type})")
            return

        # 目前摘要为空且不是季度时，才进行刷新元数据处理
        if item.TYPE != "season":
            if self._force or not summary:
                # 触发元数据刷新
                item.refresh()
                logger.info(f"刷新元数据已请求：{grandparent_info}{parent_info}{item.title} ({item.type})")
                # 标记此项目已刷新
                refreshed_items[item.ratingKey] = True
        else:
            logger.info(f"Summary不为空，无需刷新：{grandparent_info}{parent_info}{item.title} ({item.type})")

    @staticmethod
    def __get_date(offset_day: int) -> str:
        """
        获取相对于当前日期偏移指定天数的日期字符串
        :param offset_day: 偏移天数，正数表示未来，负数表示过去
        :return: 偏移后的日期字符串，格式为 "YYYY-MM-DD"
        """
        current_time = datetime.now()
        target_time = current_time + timedelta(days=offset_day)
        target_date = target_time.strftime("%Y-%m-%d")
        return target_date

    @staticmethod
    def __get_timestamp(offset_day: int) -> int:
        """
       获取相对于当前日期偏移指定天数的时间戳
       :param offset_day: 偏移天数，正数表示未来，负数表示过去
       :return: 偏移后的时间戳
       """
        current_time = datetime.now()
        target_time = current_time + timedelta(days=offset_day)
        target_timestamp = int(target_time.timestamp())
        return target_timestamp

    def __check_plex_media_server(self) -> bool:
        """
        检查Plex媒体服务器配置
        """
        if not self.service_infos():
            logger.error(f"Plex 配置不正确，请检查")
            return False
        return True
