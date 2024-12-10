import random
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.chain.subscribe import SubscribeChain
from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import eventmanager, Event
from app.core.metainfo import MetaInfo
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.models import Subscribe
from app.db.subscribe_oper import SubscribeOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.event import ResourceSelectionEventData, ResourceDownloadEventData
from app.schemas.types import EventType, ChainEventType, MediaType, NotificationType

lock = threading.Lock()


class SubscribeAssistant(_PluginBase):
    # 插件名称
    plugin_name = "订阅助手"
    # 插件描述
    plugin_desc = "测试插件，尚未发布，请勿使用。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/subscribeassistant.png"
    # 插件版本
    plugin_version = "0.0.1"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "subscribeassistant_"
    # 加载顺序
    plugin_order = 10
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    downloadhistory_oper = None
    subscribe_oper = None
    # 是否开启
    _enabled = False
    # 是否发送通知
    _notify = False
    # 是否立即运行一次
    _onlyonce = False
    # 下载检查周期
    _download_check_interval = False
    # 下载超时自动删除
    _auto_delete = False
    # 删除后触发搜索补全
    _auto_completion_search = False
    # 超时删除时间（小时）
    _delete_timeout = 3
    # 排除标签
    _delete_exclude_tags = None
    # 自动待定最近上线剧集订阅
    _auto_tv_pending = False
    # 订阅下载时自动待定
    _auto_download_pending = False
    # 最新上线剧集待定天数
    _auto_tv_pending_days = 0
    # 待定检查周期
    _auto_pending_cron = None
    # 洗版类型
    _auto_best_type = "no"
    # 洗版检查周期
    _auto_best_cron = None
    # 洗版次数
    _auto_best_count = 1
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self.downloadhistory_oper = DownloadHistoryOper()
        self.subscribe_oper = SubscribeOper()
        if not config:
            return

        self._enabled = config.get("enabled", False)
        self._notify = config.get("notify", False)
        self._onlyonce = config.get("onlyonce", False)
        self._download_check_interval = config.get("download_check_interval", 5)
        self._auto_delete = config.get("auto_delete", True)
        self._auto_completion_search = config.get("auto_completion_search", True)
        self._delete_exclude_tags = config.get("delete_exclude_tags", "H&R")
        self._auto_tv_pending = config.get("auto_tv_pending", True)
        self._auto_pending_cron = config.get("auto_pending_cron", "0 12 * * *")
        self._auto_download_pending = config.get("auto_download_pending", True)
        self._auto_best_type = config.get("auto_best_type", "no")
        self._auto_best_cron = config.get("auto_best_cron", "0 15 * * *")
        self._delete_timeout = self.__get_int_config(config, "delete_timeout", 3)
        self._auto_tv_pending_days = self.__get_int_config(config, "auto_tv_pending_days", 14)
        self._auto_best_count = self.__get_int_config(config, "auto_best_count", 1)

        # 停止现有任务
        self.stop_service()

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        self._scheduler.start()
        if self._onlyonce:
            logger.info("订阅助手服务，立即运行一次")
            self._scheduler.add_job(
                func=self.auto_check,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="订阅助手",
            )
            self._onlyonce = False

        self.__update_config()

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
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'download_check_interval',
                                            'label': '下载检查周期',
                                            'items': [
                                                {'title': '5分钟', 'value': '5'},
                                                {'title': '10分钟', 'value': '15'},
                                                {'title': '30分钟', 'value': '30'},
                                                {'title': '60分钟', 'value': '60'}
                                            ],
                                            'hint': '设置下载检查的周期，定时检查下载任务状态',
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
                                            'model': 'auto_pending_cron',
                                            'label': '待定检查周期',
                                            'hint': '设置待定检查的周期，如 0 12 * * *',
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
                                            'model': 'auto_best_cron',
                                            'label': '洗版检查周期',
                                            'hint': '设置洗版检查的周期，如 0 15 * * *',
                                            'persistent-hint': True
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
                            'stacked': True,
                            'fixed-tabs': True
                        },
                        'content': [
                            {
                                'component': 'VTab',
                                'props': {
                                    'value': 'delete_tab'
                                },
                                'text': '自动删除'
                            },
                            {
                                'component': 'VTab',
                                'props': {
                                    'value': 'pending_tab'
                                },
                                'text': '自动待定'
                            },
                            {
                                'component': 'VTab',
                                'props': {
                                    'value': 'best_tab'
                                },
                                'text': '自动洗版'
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
                                    'value': 'delete_tab'
                                },
                                'content': [
                                    {
                                        'component': 'VRow',
                                        'props': {
                                            'style': {
                                                'margin-top': '0px'
                                            }
                                        },
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
                                                            'model': 'auto_delete',
                                                            'label': '下载超时自动删除',
                                                            'hint': '订阅下载超时将自动删除种子',
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
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'auto_completion_search',
                                                            'label': '删除后触发搜索补全',
                                                            'hint': '种子删除后将自动触发搜索补全',
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
                                                        'component': 'VTextField',
                                                        'props': {
                                                            'model': 'delete_timeout',
                                                            'label': '下载超时时间',
                                                            'type': 'number',
                                                            "min": "0",
                                                            'hint': '下载任务超时的小时数，N小时内未完成则视为超时',
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
                                                        'component': 'VTextField',
                                                        'props': {
                                                            'model': 'delete_exclude_tags',
                                                            'label': '排除标签',
                                                            'hint': '需要排除的标签，多个标签用逗号分隔',
                                                            'persistent-hint': True
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
                                    'value': 'pending_tab'
                                },
                                'content': [
                                    {
                                        'component': 'VRow',
                                        'props': {
                                            'style': {
                                                'margin-top': '0px'
                                            }
                                        },
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
                                                            'model': 'auto_download_pending',
                                                            'label': '订阅下载时自动待定',
                                                            'hint': '订阅下载时，自动标记为待定状态，避免提前完成订阅',
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
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'auto_tv_pending',
                                                            'label': '自动待定最近上线剧集订阅',
                                                            'hint': '订阅新上线剧集时，自动标记为待定状态，避免提前完成订阅',
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
                                                    'md': 12
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VTextField',
                                                        'props': {
                                                            'model': 'auto_tv_pending_days',
                                                            'label': '最新上线剧集待定天数',
                                                            'type': 'number',
                                                            "min": "0",
                                                            'hint': 'TMDB中上线日期加上设置的天数大于当前日期，则视为待定',
                                                            'persistent-hint': True
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
                                    'value': 'best_tab'
                                },
                                'content': [
                                    {
                                        'component': 'VRow',
                                        'props': {
                                            'style': {
                                                'margin-top': '0px'
                                            }
                                        },
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
                                                            'model': 'auto_best_type',
                                                            'label': '洗版类型',
                                                            'items': [
                                                                {'title': '全部', 'value': 'all'},
                                                                {'title': '关闭', 'value': 'no'},
                                                                {'title': '电影', 'value': 'movie'},
                                                                {'title': '电视剧', 'value': 'tv'}
                                                            ],
                                                            'hint': '选择需要自动洗版的类型',
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
                                                        'component': 'VTextField',
                                                        'props': {
                                                            'model': 'auto_best_count',
                                                            'label': '洗版次数',
                                                            'type': 'number',
                                                            "min": "1",
                                                            'hint': '洗版达到对应次数后自动完成，为空时按系统默认处理',
                                                            'persistent-hint': True
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
                            },
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
                                            'variant': 'tonal',
                                            'text': '注意：相关订阅状态说明，请参阅'
                                        },
                                        'content': [
                                            {
                                                'component': 'a',
                                                'props': {
                                                    'href': 'https://github.com/jxxghp/MoviePilot/pull/3330',
                                                    'target': '_blank'
                                                },
                                                'content': [
                                                    {
                                                        'component': 'u',
                                                        'text': '#3330'
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
        ], {
            "enabled": False,
            "download_check_interval": 5,
            "auto_delete": True,
            "auto_completion_search": True,
            "delete_timeout": 3,
            "delete_exclude_tags": "H&R",
            "auto_tv_pending": True,
            "auto_download_pending": True,
            "auto_tv_pending_days": 14,
            "auto_pending_cron": "0 12 * * *",
            "auto_best_type": "no",
            "auto_best_cron": "0 15 * * *"
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
        if not self._enabled:
            return []

        services = []
        if self._download_check_interval and (self._auto_delete or self._auto_download_pending):
            services.append({
                "id": f"{self.__class__.__name__}_download",
                "name": f"下载检查",
                "trigger": "interval",
                "func": self.download_check,
                "kwargs": {"minutes": self._download_check_interval}
            })
        if self._auto_tv_pending and self._auto_pending_cron:
            services.append({
                "id": f"{self.__class__.__name__}_pending",
                "name": f"待定检查",
                "trigger": CronTrigger.from_crontab(self._auto_pending_cron),
                "func": self.tv_pending_check,
                "kwargs": {}
            })
        if self._auto_best_type != "no" and self._auto_best_cron:
            services.append({
                "id": f"{self.__class__.__name__}_best_version",
                "name": f"洗版检查",
                "trigger": CronTrigger.from_crontab(self._auto_best_cron),
                "func": self.best_version_check,
                "kwargs": {}
            })
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

    @staticmethod
    def __get_int_config(config: dict, key: str, default: int) -> int:
        """
        获取int配置项
        """
        try:
            return int(config.get(key, default))
        except (ValueError, TypeError):
            return default

    def __update_config(self):
        """
        更新配置
        """
        config = {
            "enabled": self._enabled,
            "notify": self._notify,
            "onlyonce": self._onlyonce,
            "download_check_interval": self._download_check_interval,
            "auto_delete": self._auto_delete,
            "auto_completion_search": self._auto_completion_search,
            "delete_exclude_tags": self._delete_exclude_tags,
            "auto_tv_pending": self._auto_tv_pending,
            "auto_pending_cron": self._auto_pending_cron,
            "auto_download_pending": self._auto_download_pending,
            "auto_best_cron": self._auto_best_cron,
            "auto_best_type": self._auto_best_type,
            "delete_timeout": self._delete_timeout,
            "auto_tv_pending_days": self._auto_tv_pending_days,
            "auto_best_count": self._auto_best_count,
        }
        self.update_config(config=config)

    def auto_check(self):
        """
        订阅自动检查
        """
        self.download_check()
        self.tv_pending_check()
        self.best_version_check()

    def download_check(self):
        """
        下载检查
        """
        self.download_delete_check()
        self.download_pending_check()

    def pending_check(self):
        """
        待定检查
        """
        self.download_pending_check()
        self.tv_pending_check()

    def download_delete_check(self):
        """
        下载超时删除检查
        """
        pass

    def download_pending_check(self):
        """
        下载待定检查
        """
        pass

    def tv_pending_check(self):
        """
        剧集订阅待定检查
        """
        if not self._auto_tv_pending:
            return

        subscribes = self.subscribe_oper.list(state="N,R,P")
        if not subscribes:
            return

        for subscribe in subscribes:
            self.__process_tv_pending(subscribe)

    def best_version_check(self):
        """
        洗版检查
        """
        pass

    @eventmanager.register(EventType.SubscribeAdded)
    def handle_subscribe_added_event(self, event: Event = None):
        """
        处理订阅添加事件
        """
        try:
            # 验证事件数据
            if not event or not event.event_data:
                logger.warning("收到的订阅事件为空或缺少数据，跳过处理")
                return

            # 自动待定功能未开启
            if not self._auto_tv_pending:
                logger.debug("自动待定功能未开启，跳过订阅事件处理")
                return

            sub_id = event.event_data.get("subscribe_id")
            username = event.event_data.get("username")
            mediainfo_dict = event.event_data.get("mediainfo")

            # 缺少订阅 ID 或媒体信息
            if not sub_id or not mediainfo_dict:
                logger.warning(f"订阅事件数据缺失，跳过处理。订阅 ID: {sub_id}, 媒体信息: {mediainfo_dict}")
                return

            logger.debug(f"接收到订阅添加事件，来自用户: {username}, 订阅 ID: {sub_id}, 数据: {mediainfo_dict}")

            # 获取订阅信息和媒体信息
            subscribe = self.subscribe_oper.get(sub_id)
            mediainfo = MediaInfo()
            mediainfo.from_dict(mediainfo_dict)

            # 订阅或媒体信息获取失败
            if not subscribe or not mediainfo:
                logger.error(f"订阅 ID {sub_id} 的订阅信息获取失败，媒体标题: {mediainfo_dict.get('title_year')}")
                return

            # 调用公共方法处理订阅
            self.__process_tv_pending(subscribe, mediainfo)
        except Exception as e:
            # 捕获所有异常并记录错误日志
            logger.error(f"处理订阅添加事件时发生错误: {str(e)}")

    @eventmanager.register(EventType.SubscribeComplete)
    def handle_subscribe_complete_event(self, event: Event = None):
        """
        处理订阅完成事件
        """
        pass

    @eventmanager.register(EventType.DownloadAdded)
    def handle_download_added_event(self, event: Event = None):
        """
        处理下载添加事件
        """
        pass

    @eventmanager.register(ChainEventType.ResourceSelection)
    def handle_resource_selection(self, event: Event):
        """
        处理资源选择事件
        """
        if not event or not event.event_data:
            return

        event_data: ResourceSelectionEventData = event.event_data

        event_data.source = self.plugin_name
        event_data.updated = True
        event_data.updated_contexts = []

    @eventmanager.register(ChainEventType.ResourceDownload)
    def handle_resource_download(self, event: Event):
        """
        处理资源下载事件
        """
        if not event or not event.event_data:
            return

        event_data: ResourceDownloadEventData = event.event_data
        if event_data.cancel:
            logger.debug(f"该事件已被其他事件处理器处理，跳过后续操作")
            return

        # event_data.source = self.plugin_name
        # event_data.cancel = True
        # event_data.reason = "未能满足下载要求"

    def __process_tv_pending(self, subscribe: Subscribe, mediainfo: Optional[MediaInfo] = None):
        """
        处理剧集自动待定
        :param subscribe: 订阅对象
        :param mediainfo: 媒体信息对象
        """
        try:
            if not subscribe:
                return

            # 检查订阅状态是否可处理
            if subscribe.state not in ["N", "R", "P"]:
                logger.debug(f"{subscribe.name if not mediainfo else mediainfo.title} [{subscribe.id}]"
                             f"当前状态为 {subscribe.state}，状态不允许处理，跳过处理")
                return

            # 检查订阅类型是否为电视剧
            if subscribe.type != "电视剧":
                logger.debug(f"{subscribe.name} 的类型为 {subscribe.type}，非 TV 类型，跳过处理")
                return

            # 自动识别媒体信息
            if not mediainfo:
                mediainfo = self.__recognize_media(subscribe)

            if not mediainfo:
                logger.warning(f"{subscribe.name} 未能识别到媒体信息，跳过处理")
                return

            meta = MetaInfo(subscribe.name)
            meta.year = subscribe.year
            meta.begin_season = subscribe.season or None
            meta.type = MediaType.TV

            # 检查媒体类型是否为 TV
            if mediainfo.type != MediaType.TV:
                logger.debug(
                    f"{mediainfo.title_year} [{subscribe.id}]类型为 {mediainfo.type}，非 TV 类型，跳过处理")
                return

            # 检查季信息是否存在
            if not mediainfo.season_info:
                logger.warning(f"{mediainfo.title_year} 的 season_info 为空，跳过处理")
                return

            # 查找与当前订阅季数匹配的首播日期 (air_date)
            season = subscribe.season
            air_day = None
            for season_info in mediainfo.season_info:
                if season_info.get("season_number") == season:
                    air_day = season_info.get("air_date")
                    break

            if not air_day:
                # 未找到与订阅季数匹配的首播日期
                logger.warning(f"{mediainfo.title} 未找到与订阅季数 {season} 对应的 air_date，跳过处理")
                return

            # 解析上线日期
            try:
                air_date = datetime.strptime(air_day, "%Y-%m-%d")
            except ValueError:
                # 首播日期格式错误
                logger.error(f"{mediainfo.title} 的 air_date 格式错误：{air_day}，跳过处理")
                return

            # 判断是否符合 auto_tv_pending_days 的要求
            pending_date = air_date + timedelta(days=self._auto_tv_pending_days)
            current_date = datetime.now()

            logger.debug(f"{mediainfo.title_year} [{subscribe.id}]，上线日期: {air_date}，"
                         f"待定天数：{self._auto_tv_pending_days}，当前日期: {current_date}")

            # 判断目标状态
            if subscribe.state == "P" and pending_date <= current_date:
                # 如果当前状态是待定 (P)，但不再符合待定条件，更新为已处理 (R)
                target_state = "R"
                logger.debug(
                    f"{mediainfo.title_year} [{subscribe.id}]，季数 {season} 当前状态为 'P'，"
                    f"不符合待定条件，目标状态更新为 'R'")
            elif subscribe.state != "P" and pending_date > current_date:
                # 如果当前状态不是待定 (P)，但符合待定条件，更新为待定 (P)
                target_state = "P"
                logger.debug(
                    f"{mediainfo.title_year} [{subscribe.id}]，季数 {season} 当前状态非 'P'，"
                    f"符合待定条件，目标状态更新为 'P'")
            else:
                # 否则保持当前状态
                target_state = subscribe.state
                logger.debug(
                    f"{mediainfo.title_year} [{subscribe.id}]，季数 {season} 当前状态无需变更，保持为 {target_state}")

            # 如果订阅状态已是目标状态，无需更新
            if subscribe.state == target_state:
                return

            # 如果当前状态为 "N"，且目标状态已确定非 "N"，触发补全搜索
            if subscribe.state == "N" and target_state != "N":
                random_minutes = random.uniform(3, 5)
                logger.info(f"新增订阅触发补全搜索任务，标题：{mediainfo.title_year} [{subscribe.id}]，"
                            f"任务将在 {random_minutes:.2f} 分钟后触发")
                timer = threading.Timer(random_minutes * 60, lambda: SubscribeChain().search(sid=subscribe.id))
                timer.start()

            # 更新订阅状态
            logger.info(f"{mediainfo.title_year} [{subscribe.id}]，"
                        f"季数 {season} 状态从 {subscribe.state} 更新为 {target_state}")
            self.subscribe_oper.update(subscribe.id, {"state": target_state})

            # 消息推送
            if self._notify:
                # 构造消息文本
                text_parts = []
                if mediainfo.vote_average:
                    text_parts.append(f"评分：{mediainfo.vote_average}")
                if subscribe.username:
                    text_parts.append(f"来自用户：{subscribe.username}")
                if air_day:
                    text_parts.append(f"上线日期：{air_day}")
                # 将非空部分拼接成完整的文本
                text = "，".join(text_parts) if text_parts else ""

                # 构造跳转链接
                if mediainfo.type == MediaType.TV:
                    link = settings.MP_DOMAIN('#/subscribe/tv?tab=mysub')
                else:
                    link = settings.MP_DOMAIN('#/subscribe/movie?tab=mysub')

                # 构造标题，根据状态动态调整
                if target_state == "P":
                    title = f"{mediainfo.title_year} {meta.season} 已标记待定"
                else:
                    title = f"{mediainfo.title_year} {meta.season} 已标记订阅中"

                # 推送消息
                self.post_message(
                    mtype=NotificationType.Subscribe,
                    title=title,
                    text=text,
                    image=mediainfo.get_message_image(),
                    link=link,
                    # username=subscribe.username
                )
        except Exception as e:
            # 捕获异常并记录错误日志
            logger.error(f"处理订阅 ID {subscribe.id} 时发生错误: {str(e)}")

    def __recognize_media(self, subscribe: Subscribe) -> Optional[MediaInfo]:
        """
        param subscribe: 订阅对象
        """
        meta = MetaInfo(subscribe.name)
        meta.year = subscribe.year
        meta.begin_season = subscribe.season or None
        try:
            meta.type = MediaType(subscribe.type)
        except ValueError:
            logger.error(f"订阅 {subscribe.name} 类型错误：{subscribe.type}")
            return None
        try:
            # 识别媒体信息
            mediainfo: MediaInfo = self.chain.recognize_media(
                meta=meta,
                mtype=meta.type,
                tmdbid=subscribe.tmdbid,
                doubanid=subscribe.doubanid,
                cache=False
            )
            if not mediainfo:
                logger.warning(
                    f"未识别到媒体信息，标题：{subscribe.name}，tmdbid：{subscribe.tmdbid}，doubanid：{subscribe.doubanid}")
                return None
            return mediainfo
        except Exception as e:
            logger.error(f"识别媒体信息时发生错误，订阅 ID {subscribe.id}，标题：{subscribe.name}，错误信息：{str(e)}")
            return None
