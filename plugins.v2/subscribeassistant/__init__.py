import json
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple, Optional, Union, Callable

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.chain.subscribe import SubscribeChain
from app.core.config import settings
from app.core.context import MediaInfo, Context, TorrentInfo
from app.core.event import eventmanager, Event
from app.core.metainfo import MetaInfo
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.models import Subscribe
from app.db.subscribe_oper import SubscribeOper
from app.helper.downloader import DownloaderHelper
from app.log import logger
from app.modules.qbittorrent import Qbittorrent
from app.modules.transmission import Transmission
from app.plugins import _PluginBase
from app.schemas import ServiceInfo
from app.schemas.event import ResourceDownloadEventData, ResourceSelectionEventData
from app.schemas.subscribe import Subscribe as SchemaSubscribe
from app.schemas.types import EventType, ChainEventType, MediaType, NotificationType

lock = threading.RLock()


class SubscribeAssistant(_PluginBase):
    # 插件名称
    plugin_name = "订阅助手"
    # 插件描述
    plugin_desc = "实现多场景管理系统订阅与状态同步。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/subscribeassistant.png"
    # 插件版本
    plugin_version = "1.3"
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
    downloader_helper = None
    downloadhistory_oper = None
    subscribe_oper = None
    # 是否开启
    _enabled = False
    # 是否发送通知
    _notify = False
    # 是否立即运行一次
    _onlyonce = False
    # 下载检查周期
    _download_check_interval = 5
    # 下载超时自动删除
    _auto_download_delete = False
    # 删除后触发搜索补全
    _auto_search_when_delete = False
    # 跳过超时记录
    _skip_timeout = True
    # 超时删除时间（小时）
    _download_timeout = 3
    # 超时记录清理时间（小时）
    _timeout_history_cleanup = 24
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
    # 洗版类型集合
    _auto_best_types = set()
    # 洗版检查周期
    _auto_best_cron = None
    # 洗版天数
    _auto_best_remaining_days = 60
    # 重置任务
    _reset_task = False
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self.downloader_helper = DownloaderHelper()
        self.downloadhistory_oper = DownloadHistoryOper()
        self.subscribe_oper = SubscribeOper()
        if not config:
            return

        self._enabled = config.get("enabled", False)
        self._notify = config.get("notify", False)
        self._onlyonce = config.get("onlyonce", False)
        self._auto_download_delete = config.get("auto_download_delete", True)
        self._auto_search_when_delete = config.get("auto_search_when_delete", True)
        self._delete_exclude_tags = config.get("delete_exclude_tags", "H&R")
        self._auto_tv_pending = config.get("auto_tv_pending", True)
        self._auto_pending_cron = config.get("auto_pending_cron", "0 12 * * *")
        self._auto_download_pending = config.get("auto_download_pending", True)
        self._skip_timeout = config.get("skip_timeout", True)
        self._reset_task = config.get("reset_task", False)
        self._auto_best_type = config.get("auto_best_type", "no")
        type_mapping = {
            "tv": {MediaType.TV},
            "movie": {MediaType.MOVIE},
            "all": {MediaType.TV, MediaType.MOVIE}
        }
        self._auto_best_types = type_mapping.get(self._auto_best_type, set())
        self._auto_best_cron = config.get("auto_best_cron", "0 15 * * *")
        self._download_check_interval = self.__get_float_config(config, "download_check_interval", 5)
        self._download_timeout = self.__get_float_config(config, "download_timeout", 3)
        self._timeout_history_cleanup = self.__get_float_config(config, "timeout_history_cleanup", 0) or None
        self._auto_tv_pending_days = self.__get_float_config(config, "auto_tv_pending_days", 14)
        self._auto_best_remaining_days = self.__get_float_config(config, "auto_best_remaining_days", 0) or None

        # 停止现有任务
        self.stop_service()

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        self._scheduler.start()
        if self._reset_task:
            logger.info("订阅助手服务，即将开始重置任务")
            self._scheduler.add_job(
                func=self.reset_task,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="订阅助手",
            )
            self._reset_task = False

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
                                    'md': 3
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'reset_task',
                                            'label': '重置数据',
                                            'hint': '将重置所有待定订阅及清理相关任务',
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
                                                {'title': '5分钟', 'value': 5},
                                                {'title': '10分钟', 'value': 15},
                                                {'title': '30分钟', 'value': 30},
                                                {'title': '60分钟', 'value': 60}
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
                                                    'md': 4
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'auto_download_delete',
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
                                                    'md': 4
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'auto_search_when_delete',
                                                            'label': '删除后触发搜索补全',
                                                            'hint': '种子删除后将自动触发搜索补全',
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
                                                            'model': 'skip_timeout',
                                                            'label': '跳过超时记录',
                                                            'hint': '跳过最近超时删除的种子，避免再次下载超时',
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
                                                            'model': 'download_timeout',
                                                            'label': '下载超时时间',
                                                            'type': 'number',
                                                            "min": "0",
                                                            'hint': 'N小时内未完成下载任务视为超时',
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
                                                            'model': 'timeout_history_cleanup',
                                                            'label': '超时记录清理时间',
                                                            'type': 'number',
                                                            "min": "0",
                                                            'hint': '定时清理N小时前的超时种子记录',
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
                                                            'hint': 'TMDB中上映日期加上设置的天数大于当前日期，则视为待定',
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
                                                            'model': 'auto_best_remaining_days',
                                                            'label': '洗版天数',
                                                            'type': 'number',
                                                            "min": "1",
                                                            'hint': '达到指定天数后自动完成，若有下载则按最新时间计算，为空时按默认处理',
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
            "auto_download_delete": True,
            "auto_search_when_delete": True,
            "skip_timeout": True,
            "download_timeout": 3,
            "timeout_history_cleanup": 24,
            "delete_exclude_tags": "H&R",
            "auto_tv_pending": True,
            "auto_download_pending": True,
            "auto_tv_pending_days": 7,
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
        if self._download_check_interval and (self._auto_download_delete or self._auto_download_pending):
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
    def __get_float_config(config: dict, key: str, default: float) -> float:
        """
        获取int配置项
        """
        try:
            return float(config.get(key, default))
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
            "auto_download_delete": self._auto_download_delete,
            "auto_search_when_delete": self._auto_search_when_delete,
            "delete_exclude_tags": self._delete_exclude_tags,
            "auto_tv_pending": self._auto_tv_pending,
            "auto_pending_cron": self._auto_pending_cron,
            "auto_download_pending": self._auto_download_pending,
            "auto_best_cron": self._auto_best_cron,
            "auto_best_type": self._auto_best_type,
            "skip_timeout": self._skip_timeout,
            "download_timeout": self._download_timeout,
            "timeout_history_cleanup": self._timeout_history_cleanup,
            "auto_tv_pending_days": self._auto_tv_pending_days,
            "auto_best_remaining_days": self._auto_best_remaining_days,
            "reset_task": self._reset_task,
        }
        self.update_config(config=config)

    def reset_task(self):
        """
        重置任务
        """
        subscribes = self.subscribe_oper.list("P")
        logger.info(f"开始重置任务，共有 {len(subscribes)} 个待定订阅任务")
        for subscribe in subscribes:
            self.subscribe_oper.update(sid=subscribe.id, payload={"state": "R"})
            logger.info(f"待定订阅 {self.__format_subscribe(subscribe)} 已重置订阅状态为 R")

        self.__save_data("subscribes", {})
        self.__save_data("torrents", {})
        self.__save_data("deletes", {})
        logger.info("已重置所有订阅任务、下载种子任务和超时删除记录")

    def auto_check(self):
        """
        订阅自动检查
        """
        self.tv_pending_check()
        self.download_check()
        self.best_version_check()

    def download_check(self):
        """
        下载检查
        """
        if not self._auto_download_delete or not self._auto_download_pending:
            return

        logger.info("开始清理超时种子记录...")
        self.process_delete_task()
        logger.info("超时种子记录清理完成...")

        logger.info("开始检查下载种子任务...")
        self.process_download_task()
        logger.info("下载种子任务检查完成...")

    def tv_pending_check(self):
        """
        剧集订阅待定检查
        """
        if not self._auto_tv_pending:
            return

        subscribes = self.subscribe_oper.list(state="N,R,P")
        if not subscribes:
            return

        logger.info("开始检查剧集待定...")
        self.process_tv_pending(subscribes)
        logger.info("剧集待定检查完成...")

    def best_version_check(self):
        """
        洗版检查
        """
        subscribes = self.subscribe_oper.list(state="N,R,P")
        if not subscribes:
            return

        logger.info("开始检查订阅洗版...")
        self.process_best_version_complete(subscribes)
        logger.info("订阅洗版检查完成...")

    @eventmanager.register(EventType.SubscribeDeleted)
    def handle_subscribe_deleted_event(self, event: Event = None):
        """
        处理订阅删除事件
        """
        try:
            # 验证事件数据
            if not event or not event.event_data:
                return

            subscribe_id = event.event_data.get("subscribe_id")
            subscribe_dict = event.event_data.get("subscribe_info")
            logger.debug(f"接收到订阅删除事件，订阅 ID: {subscribe_id}，数据：{subscribe_dict}")
            self.clear_tasks(subscribe_id=subscribe_id, subscribe=subscribe_dict)
        except Exception as e:
            logger.error(f"处理订阅删除事件时发生错误: {str(e)}")

    @eventmanager.register(EventType.SubscribeAdded)
    def handle_subscribe_added_event(self, event: Event = None):
        """
        处理订阅添加事件
        """
        try:
            # 验证事件数据
            if not event or not event.event_data:
                return

            # 自动待定功能未开启
            if not self._auto_tv_pending:
                logger.debug("自动待定功能未开启，跳过处理")
                return

            subscribe_id = event.event_data.get("subscribe_id")
            username = event.event_data.get("username")
            mediainfo_dict = event.event_data.get("mediainfo")

            logger.debug(f"接收到订阅添加事件，来自用户: {username}, 订阅 ID: {subscribe_id}, 数据: {mediainfo_dict}")

            # 缺少订阅信息或媒体信息
            if not subscribe_id or not mediainfo_dict:
                logger.warning(f"订阅事件数据缺失，跳过处理。订阅 ID: {subscribe_id}, 媒体信息: {mediainfo_dict}")
                return

            # 获取订阅信息和媒体信息
            subscribe = self.subscribe_oper.get(subscribe_id)
            mediainfo = MediaInfo()
            mediainfo.from_dict(mediainfo_dict)

            # 订阅或媒体信息获取失败
            if not subscribe or not mediainfo:
                logger.error(f"订阅 ID {subscribe_id} 的订阅信息获取失败，媒体标题: {mediainfo_dict.get('title_year')}")
                return

            if subscribe.best_version:
                logger.debug(f"{self.__format_subscribe(subscribe)} 为洗版订阅，跳过处理")
                return

            # 调用公共方法处理订阅
            self.process_tv_pending([(subscribe, mediainfo)])
        except Exception as e:
            logger.error(f"处理订阅添加事件时发生错误: {str(e)}")

    @eventmanager.register(EventType.SubscribeComplete)
    def handle_subscribe_complete_event(self, event: Event = None):
        """
        处理订阅完成事件
        """
        try:
            # 验证事件数据
            if not event or not event.event_data:
                return

            subscribe_id = event.event_data.get("subscribe_id")
            subscribe_dict = event.event_data.get("subscribe_info")
            mediainfo_dict = event.event_data.get("mediainfo")

            logger.debug(f"接收到订阅完成事件，订阅数据：{subscribe_dict}，媒体数据：{mediainfo_dict}")

            # 订阅完成清理订阅任务数据
            self.clear_tasks(subscribe_id=subscribe_id, subscribe=subscribe_dict)

            if not self._auto_best_types:
                logger.debug("自动洗版功能未开启，跳过处理")
                return

            # 缺少订阅信息或媒体信息
            if not subscribe_dict or not mediainfo_dict:
                logger.warning(f"订阅事件数据缺失，跳过处理。订阅数据: {subscribe_dict}, 媒体信息: {mediainfo_dict}")
                return

            # 获取订阅信息和媒体信息
            mediainfo = MediaInfo()
            mediainfo.from_dict(mediainfo_dict)

            # 调用公共方法处理订阅
            self.process_best_version(subscribe_dict=subscribe_dict, mediainfo=mediainfo)
        except Exception as e:
            logger.error(f"处理订阅完成事件时发生错误: {str(e)}")

    @eventmanager.register(EventType.DownloadAdded)
    def handle_download_added_event(self, event: Event = None):
        """
        处理下载添加事件
        """
        try:
            # 验证事件数据
            if not event or not event.event_data:
                return

            # 下载超时删除/下载自动待定功能未开启
            if not self._auto_download_delete or not self._auto_download_pending:
                logger.debug("下载超时删除/下载自动待定功能未开启，跳过处理")
                return

            torrent_hash = event.event_data.get("hash")
            context: Context = event.event_data.get("context")
            downloader = event.event_data.get("downloader")
            episodes = list(event.event_data.get("episodes", []))
            username = event.event_data.get("username")
            source = event.event_data.get("source")

            logger.debug(f"接收到下载添加事件，来自用户: {username}, 数据: {event.event_data}")

            subscribe_info, subscribe = self.__get_subscribe_by_source(source=source)
            if not subscribe_info or not subscribe:
                logger.debug(f"未能找到订阅信息，跳过处理")
                return

            service = self.__get_downloader_service(downloader=downloader)
            if not service:
                logger.info(f"触发添加下载事件，但没有获取到下载器 {downloader} 服务，跳过处理")
                return

            if not torrent_hash or not context or not context.torrent_info:
                logger.info("没有获取到有效的种子任务信息，跳过处理")
                return

            torrent = self.__get_torrents(downloader=service.instance, torrent_hashes=torrent_hash)
            if not torrent:
                logger.info(f"没有在下载器中获取到 {torrent_hash} 种子信息，跳过处理")
                return

            # 更新订阅下载任务
            self.__with_lock_and_update_subscribe_tasks(method=self.__update_subscribe_torrent_task,
                                                        subscribe=subscribe,
                                                        torrent_hash=torrent_hash,
                                                        torrent_info=context.torrent_info,
                                                        episodes=episodes,
                                                        downloader=downloader)

            self.__with_lock_and_update_torrent_tasks(
                method=lambda tasks: tasks.update({
                    torrent_hash: {
                        "hash": torrent_hash,
                        "subscribe_id": subscribe.id if subscribe else None,
                        "subscribe_info": subscribe_info,
                        "episodes": episodes,
                        "username": username,
                        "downloader": downloader,
                        "site_id": context.torrent_info.site,
                        "site_name": context.torrent_info.site_name,
                        "title": context.torrent_info.title,
                        "description": context.torrent_info.description,
                        "enclosure": context.torrent_info.enclosure,
                        "page_url": context.torrent_info.page_url,
                        "pending_check": self._auto_download_pending,
                        "timeout_check": self._auto_download_delete,
                        "time": time.time(),
                    }
                })
            )
        except Exception as e:
            logger.error(f"处理下载添加事件时发生错误: {str(e)}")

    @eventmanager.register(ChainEventType.ResourceSelection)
    def handle_resource_selection_event(self, event: Event):
        """
        处理资源选择事件
        """
        if not event or not event.event_data:
            return

        event_data: ResourceSelectionEventData = event.event_data
        if not event_data.contexts:
            return

        # event_data.updated = True
        # event_data.updated_contexts = []
        # return

        if not self._skip_timeout:
            return

        delete_tasks = self.__get_data("deletes") or {}
        if not delete_tasks:
            return

        updated = False
        update_contexts = event_data.updated_contexts or event_data.contexts or []
        for context in list(update_contexts):
            torrent_info = context.torrent_info
            if not torrent_info:
                continue
            for torrent_task in delete_tasks.values():
                if self.__compare_torrent_info_and_task(torrent_info=torrent_info, torrent_task=torrent_task):
                    logger.debug(f"存在超时删除的种子信息，跳过，context：{context}")
                    update_contexts.remove(context)
                    updated = True
                    continue
        if updated:
            event_data.updated = True
            event_data.updated_contexts = update_contexts
            event_data.source = self.plugin_name

    @eventmanager.register(etype=ChainEventType.ResourceDownload, priority=9999)
    def handle_resource_download_event(self, event: Event):
        """
        处理资源下载事件
        """
        if not event or not event.event_data:
            return

        event_data: ResourceDownloadEventData = event.event_data
        if event_data.cancel:
            logger.debug(f"该事件已被其他事件处理器处理，跳过后续操作")
            return

        # 下载自动待定功能未开启
        if not self._auto_download_pending:
            logger.debug("下载自动待定功能未开启，跳过处理")
            return

        # 获取种子信息
        context: Context = event_data.context
        downloader = event_data.downloader
        episodes = list(event_data.episodes or [])
        if not context or not context.torrent_info:
            logger.info("没有获取到有效的种子任务信息，跳过处理")
            return

        # 查找订阅信息
        subscribe_info, subscribe = self.__get_subscribe_by_source(source=event_data.origin)
        if not subscribe_info or not subscribe:
            logger.debug(f"未能找到订阅信息，跳过处理")
            return

        # 更新订阅下载任务
        self.__with_lock_and_update_subscribe_tasks(method=self.__update_subscribe_torrent_task,
                                                    subscribe=subscribe,
                                                    torrent_info=context.torrent_info,
                                                    episodes=episodes,
                                                    downloader=downloader,
                                                    pending=True,
                                                    update_priority=True)

        # 更新订阅信息为待定
        logger.debug(f"{self.__format_subscribe(subscribe)} 已更新为待定状态")
        if subscribe.state != "P":
            self.subscribe_oper.update(subscribe.id, {"state": "P"})

    def __get_downloader_service(self, downloader: str) -> Optional[ServiceInfo]:
        """
        获取下载器服务
        """
        service = self.downloader_helper.get_service(name=downloader)
        if not service:
            logger.error(f"{downloader} 获取下载器实例失败，请检查配置")
            return None

        if service.instance.is_inactive():
            logger.error(f"下载器 {downloader} 未连接")
            return None

        return service

    @staticmethod
    def __get_torrents(downloader: Optional[Union[Qbittorrent, Transmission]],
                       torrent_hashes: Optional[Union[str, List[str]]] = None) -> Optional[Any]:
        """
        获取下载器中的种子信息
        :param downloader: 下载器实例
        :param torrent_hashes: 单个种子哈希或包含多个种子 hash 的列表
        :return: 单个种子的具体信息或包含多个种子信息的列表
        """
        if not downloader:
            logger.warning(f"获取下载器实例失败，请稍后重试")
            return None

        # 处理单个种子哈希的情况，确保其被视为列表
        if isinstance(torrent_hashes, str):
            torrent_hashes = [torrent_hashes]

        torrents, error = downloader.get_torrents(ids=torrent_hashes)
        if error:
            logger.warning(f"连接下载器出错，请稍后重试")
            return None

        # 如果只有一个种子哈希，直接返回该种子的信息
        if torrent_hashes and len(torrent_hashes) == 1:
            return torrents[0] if torrents else None

        return torrents

    @staticmethod
    def __delete_torrents(downloader: Optional[Union[Qbittorrent, Transmission]],
                          torrent_hashes: Optional[Union[str, List[str]]] = None) -> bool:
        """
        删除下载器中的种子
        :param downloader: 下载器实例
        :param torrent_hashes: 单个种子哈希或包含多个种子 hash 的列表
        :return: 单个种子的具体信息或包含多个种子信息的列表
        """
        if not downloader:
            logger.warning(f"获取下载器实例失败，请稍后重试")
            return False

        # 处理单个种子哈希的情况，确保其被视为列表
        if isinstance(torrent_hashes, str):
            torrent_hashes = [torrent_hashes]

        deleted = downloader.delete_torrents(delete_file=True, ids=torrent_hashes)
        if not deleted:
            logger.warning(f"删除种子过程中发生异常，请检查")
            return False

        return deleted

    @staticmethod
    def __get_torrent_tags(torrent: Any, dl_type: str) -> list[str]:
        """
        获取种子标签
        """
        try:
            if dl_type == "qbittorrent":
                tags = torrent.get("tags", "").split(",")
            else:
                tags = torrent.labels or []

            return list(set(tag.strip() for tag in tags if tag.strip()))
        except Exception as e:
            logger.error(f"获取种子标签失败，错误: {e}")
            return []

    @staticmethod
    def __get_torrent_info(torrent: Any, dl_type: str) -> dict:
        """
        获取种子信息
        """
        date_now = int(time.time())
        # QB
        if dl_type == "qbittorrent":
            """
            {
              "added_on": 1693359031,
              "amount_left": 0,
              "auto_tmm": false,
              "availability": -1,
              "category": "tJU",
              "completed": 67759229411,
              "completion_on": 1693609350,
              "content_path": "/mnt/sdb/qb/downloads/Steel.Division.2.Men.of.Steel-RUNE",
              "dl_limit": -1,
              "dlspeed": 0,
              "download_path": "",
              "downloaded": 67767365851,
              "downloaded_session": 0,
              "eta": 8640000,
              "f_l_piece_prio": false,
              "force_start": false,
              "hash": "116bc6f3efa6f3b21a06ce8f1cc71875",
              "infohash_v1": "116bc6f306c40e072bde8f1cc71875",
              "infohash_v2": "",
              "last_activity": 1693609350,
              "magnet_uri": "magnet:?xt=",
              "max_ratio": -1,
              "max_seeding_time": -1,
              "name": "Steel.Division.2.Men.of.Steel-RUNE",
              "num_complete": 1,
              "num_incomplete": 0,
              "num_leechs": 0,
              "num_seeds": 0,
              "priority": 0,
              "progress": 1,
              "ratio": 0,
              "ratio_limit": -2,
              "save_path": "/mnt/sdb/qb/downloads",
              "seeding_time": 615035,
              "seeding_time_limit": -2,
              "seen_complete": 1693609350,
              "seq_dl": false,
              "size": 67759229411,
              "state": "stalledUP",
              "super_seeding": false,
              "tags": "",
              "time_active": 865354,
              "total_size": 67759229411,
              "tracker": "https://tracker",
              "trackers_count": 2,
              "up_limit": -1,
              "uploaded": 0,
              "uploaded_session": 0,
              "upspeed": 0
            }
            """
            # ID
            torrent_id = torrent.get("hash")
            # 标题
            torrent_title = torrent.get("name")
            # 下载时间
            if (not torrent.get("added_on")
                    or torrent.get("added_on") < 0):
                dltime = 0
            else:
                dltime = date_now - torrent.get("added_on")
            # 做种时间
            if (not torrent.get("completion_on")
                    or torrent.get("completion_on") < 0):
                seeding_time = 0
            else:
                seeding_time = date_now - torrent.get("completion_on")
            # 分享率
            ratio = torrent.get("ratio") or 0
            # 上传量
            uploaded = torrent.get("uploaded") or 0
            # 平均上传速度 Byte/s
            if dltime:
                avg_upspeed = int(uploaded / dltime)
            else:
                avg_upspeed = uploaded
            # 已未活动 秒
            if (not torrent.get("last_activity")
                    or torrent.get("last_activity") < 0):
                iatime = 0
            else:
                iatime = date_now - torrent.get("last_activity")
            # 下载量
            downloaded = torrent.get("downloaded")
            # 种子大小
            total_size = torrent.get("total_size")
            # 目标大小
            target_size = torrent.get("size")
            # 添加时间
            add_on = (torrent.get("added_on") or 0)
            add_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(add_on))
            # 种子标签
            tags = torrent.get("tags")
            # tracker
            tracker = torrent.get("tracker")
            # state
            state = torrent.get("state")
        # TR
        else:
            # ID
            torrent_id = torrent.hashString
            # 标题
            torrent_title = torrent.name
            # 做种时间
            if (not torrent.date_done
                    or torrent.date_done.timestamp() < 1):
                seeding_time = 0
            else:
                seeding_time = date_now - int(torrent.date_done.timestamp())
            # 下载耗时
            if (not torrent.date_added
                    or torrent.date_added.timestamp() < 1):
                dltime = 0
            else:
                dltime = date_now - int(torrent.date_added.timestamp())
            # 下载量
            downloaded = int(torrent.total_size * torrent.progress / 100)
            # 分享率
            ratio = torrent.ratio or 0
            # 上传量
            uploaded = int(downloaded * torrent.ratio)
            # 平均上传速度
            if dltime:
                avg_upspeed = int(uploaded / dltime)
            else:
                avg_upspeed = uploaded
            # 未活动时间
            if (not torrent.date_active
                    or torrent.date_active.timestamp() < 1):
                iatime = 0
            else:
                iatime = date_now - int(torrent.date_active.timestamp())
            # 种子大小
            total_size = torrent.total_size
            # 目标大小
            target_size = torrent.size_when_done
            # 添加时间
            add_on = (torrent.date_added.timestamp() if torrent.date_added else 0)
            add_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(add_on))
            # 种子标签
            tags = torrent.get("tags")
            # tracker
            tracker = torrent.get("tracker")
            # state
            state = torrent.status
        return {
            "hash": torrent_id,
            "title": torrent_title,
            "seeding_time": seeding_time,
            "ratio": ratio,
            "uploaded": uploaded,
            "downloaded": downloaded,
            "avg_upspeed": avg_upspeed,
            "iatime": iatime,
            "dltime": dltime,
            "total_size": total_size,
            "target_size": target_size,
            "add_time": add_time,
            "add_on": add_on,
            "tags": tags,
            "tracker": tracker,
            "state": state,
        }

    @staticmethod
    def __get_torrent_completion_status(torrent_info: dict) -> Tuple[bool, float]:
        """
        获取种子的完成状态和相关时间信息
        :param torrent_info: 包含种子信息的字典，必须包含种子状态、下载大小、总大小等字段
        :return: 返回一个元组，第一个元素是布尔值，表示种子是否完成，第二个元素是完成的时间（如果已完成，返回0；否则返回下载时间）
        """
        if not torrent_info:
            return False, -1

        # 如果种子正在做种，说明已完成
        torrent_state = torrent_info.get("state")
        if torrent_state in ["seeding", "seed_pending"]:
            return True, 0

        # 如果存在做种时间，说明已完成
        if torrent_info.get("seeding_time"):
            return True, 0

        # 如果种子的已下载大小大于目标大小，说明已完成
        if torrent_info.get("downloaded") >= torrent_info.get("target_size"):
            return True, 0

        return False, torrent_info.get("dltime")

    def __get_subscribe_by_source(self, source: str) -> Tuple[Optional[dict], Optional[Subscribe]]:
        """
        从来源获取订阅信息
        """
        if not source or "|" not in source:
            logger.debug("未找到有效的订阅来源信息，跳过处理")
            return None, None

        prefix, json_data = source.split("|", 1)
        if prefix != "Subscribe":
            logger.debug(f"source 前缀不符合订阅预期值: {prefix}，跳过处理")
            return None, None

        try:
            subscribe_dict = json.loads(json_data)
        except Exception as e:
            logger.error(f"解析 source 数据失败，source: {json_data}, 错误: {e}")
            return None, None

        subscribe_id = subscribe_dict.get("id")
        subscribe = self.subscribe_oper.get(subscribe_id)
        return subscribe_dict, subscribe

    def process_delete_task(self):
        """
        清理超时种子记录
        """
        self.__with_lock_and_update_delete_tasks(method=self.__process_delete_task)

    def __process_delete_task(self, torrent_tasks: dict):
        """
        清理超时种子记录
        :param torrent_tasks: 种子任务字典
        """
        if not torrent_tasks:
            return

        if not self._timeout_history_cleanup:
            logger.debug("未配置超时记录清理时间，跳过处理")
            return

        if self._timeout_history_cleanup <= 0:
            logger.debug("超时记录清理时间小于等于0，跳过处理")
            return

        current_time = time.time()
        timeout_threshold = self._timeout_history_cleanup * 3600

        # 遍历torrent_tasks字典，移除超时的记录
        for torrent_hash in list(torrent_tasks.keys()):
            torrent_task = torrent_tasks[torrent_hash]
            delete_time = torrent_task.get("delete_time")
            if not delete_time:
                del torrent_tasks[torrent_hash]
                continue
            elapsed_time = current_time - delete_time
            if elapsed_time > timeout_threshold:
                logger.info(f"超时种子记录 {torrent_hash} 已满足清理时间，删除任务")
                del torrent_tasks[torrent_hash]

    def process_download_task(self):
        """
        处理下载种子任务并清理异常种子
        """
        if not self._auto_download_delete or not self._auto_download_pending:
            return

        with lock:
            # 获取订阅任务和种子任务数据
            subscribe_tasks = self.__get_data(key="subscribes")
            torrent_tasks = self.__get_data(key="torrents")
            # 处理下载种子任务
            self.__process_download_task(subscribe_tasks=subscribe_tasks, torrent_tasks=torrent_tasks)
            # 重置订阅待定状态
            self.__reset_subscribe_task_pending(subscribe_tasks=subscribe_tasks)
            # 保存更新后的数据
            self.__save_data(key="subscribes", value=subscribe_tasks)
            self.__save_data(key="torrents", value=torrent_tasks)

    def __process_download_task(self, subscribe_tasks: dict, torrent_tasks: dict):
        """
        处理下载种子任务并清理异常种子
        :param subscribe_tasks: 订阅任务字典
        :param torrent_tasks: 下载任务字典
        """
        # 用于存储异常的种子
        invalid_torrent_hashes = []
        triggered_subscribe_ids = set()
        for torrent_hash, torrent_task in list(torrent_tasks.items()):
            subscribe_id = torrent_task.get("subscribe_id")
            subscribe_info = torrent_task.get("subscribe_info")
            username = torrent_task.get("username")
            downloader = torrent_task.get("downloader")
            site_id = torrent_task.get("site_id")
            site_name = torrent_task.get("site_name")
            title = torrent_task.get("title")
            description = torrent_task.get("description")
            enclosure = torrent_task.get("enclosure")
            page_url = torrent_task.get("page_url")
            pending_check = torrent_task.get("pending_check")
            timeout_check = torrent_task.get("timeout_check")
            torrent_time = torrent_task.get("time")
            torrent_desc = f"{title} | {description} ({torrent_hash})"

            subscribe_task = subscribe_tasks.get(str(subscribe_id))
            if not subscribe_task:
                logger.debug(f"未找到相关的订阅信息，种子任务: {torrent_desc}")
                invalid_torrent_hashes.append(torrent_hash)
                continue

            subscribe = self.subscribe_oper.get(subscribe_id)
            if not subscribe:
                logger.debug(f"数据库中未找到相关的订阅信息，种子任务: {torrent_desc}")
                invalid_torrent_hashes.append(torrent_hash)
                continue

            if not self.__match_subscribe(subscribe=subscribe, subscribe_task=subscribe_task):
                logger.debug(f"关联的订阅信息与当前订阅信息不匹配，种子任务: {torrent_desc}")
                invalid_torrent_hashes.append(torrent_hash)
                continue

            if not self.__check_subscribe_status(subscribe=subscribe):
                continue

            subscribe_torrent_tasks = subscribe_task.get("torrent_tasks") or []
            subscribe_torrent_task = {}
            for task in subscribe_torrent_tasks:
                if task.get("hash") == torrent_hash:
                    subscribe_torrent_task = task
                    break

            if not subscribe_torrent_task:
                logger.debug(f"未找到对应的订阅种子任务，种子任务: {torrent_desc}")
                invalid_torrent_hashes.append(torrent_hash)
                continue

            service = self.__get_downloader_service(downloader=downloader)
            if not service:
                logger.debug(f"获取下载器 {downloader} 实例失败，请检查配置，种子任务: {torrent_desc}")
                invalid_torrent_hashes.append(torrent_hash)
                continue

            torrent = self.__get_torrents(downloader=service.instance, torrent_hashes=torrent_hash)
            if not torrent:
                logger.debug(f"没有获取到对应的种子详情，种子可能已被删除，种子任务: {torrent_desc}")
                invalid_torrent_hashes.append(torrent_hash)
                continue

            torrent_info = self.__get_torrent_info(torrent=torrent, dl_type=service.type)
            if not torrent_info:
                invalid_torrent_hashes.append(torrent_hash)
                logger.debug(f"没有获取到对应的种子详情，可能是不支持的种子类型，种子任务: {torrent_desc}")
                continue

            is_completed, download_time = self.__get_torrent_completion_status(torrent_info=torrent_info)
            if is_completed:
                logger.info(f"种子 {torrent_desc} 已完成，将从订阅任务中移除")

                if torrent_hash in torrent_tasks:
                    del torrent_tasks[torrent_hash]

                subscribe_task["torrent_tasks"] = [
                    task for task in subscribe_torrent_tasks if task.get("hash") != torrent_hash
                ]
            else:
                logger.debug(f"种子任务 {torrent_desc} 尚未完成，下载时长 {download_time / 3600 :.2f}")
                if not timeout_check or not self._auto_download_delete:
                    continue

                if download_time < self._download_timeout * 3600:
                    continue

                if self._delete_exclude_tags:
                    torrent_tags = self.__get_torrent_tags(torrent=torrent, dl_type=service.type)
                    if torrent_tags:
                        intersection_tags = set(self._delete_exclude_tags.split(",")) & set(torrent_tags)
                        if intersection_tags:
                            logger.debug(
                                f"种子任务 {torrent_desc} 已超时，但满足不删除标签 {intersection_tags}，跳过处理")
                            continue

                logger.info(f"种子任务 {torrent_desc} 已超时，即将删除并从订阅任务中移除")
                self.__delete_torrents(downloader=service.instance, torrent_hashes=torrent_hash)

                if torrent_hash in torrent_tasks:
                    del torrent_tasks[torrent_hash]

                subscribe_task["torrent_tasks"] = [
                    task for task in subscribe_torrent_tasks if task.get("hash") != torrent_hash
                ]

                # 记录删除记录
                self.__with_lock_and_update_delete_tasks(method=self.__update_or_add_delete_tasks,
                                                         torrent_task=torrent_task)

                # 处理删除后续逻辑
                self.__handle_timeout_seed_deletion(subscribe=subscribe, subscribe_task=subscribe_task,
                                                    torrent_task=torrent_task,
                                                    triggered_subscribe_ids=triggered_subscribe_ids)

        self.__clean_invalid_torrents(invalid_torrent_hashes, subscribe_tasks, torrent_tasks)

    def __reset_subscribe_task_pending(self, subscribe_tasks: dict):
        """
       重置订阅待定状态

       :param subscribe_tasks: 订阅任务
       """
        if not subscribe_tasks:
            return
        for subscribe_id, subscribe_task in subscribe_tasks.items():
            subscribe = self.subscribe_oper.get(sid=subscribe_id)
            if not self.__check_subscribe_status(subscribe=subscribe):
                continue
            pending = self.__get_subscribe_task_pending(subscribe_task=subscribe_task)
            # 如果当前订阅状态为待定，且订阅任务不为待定状态，则更新为订阅中
            if subscribe.state == "P" and not pending:
                self.subscribe_oper.update(subscribe.id, {"state": "R"})
                logger.info(f"{self.__format_subscribe(subscribe)} 状态从 {subscribe.state} 更新为 R")

    def __handle_timeout_seed_deletion(self, subscribe: Subscribe, subscribe_task: dict, torrent_task: dict,
                                       triggered_subscribe_ids: set):
        """
        处理删除超时种子后续相关任务

        :param subscribe: 订阅信息
        :param subscribe_task: 订阅任务
        :param torrent_task: 种子任务
        :param triggered_subscribe_ids: 已触发的订阅任务
        """
        if not subscribe:
            return

        media_type = MediaType(subscribe.type)
        update_data = {}
        if media_type == MediaType.TV:
            episodes = torrent_task.get("episodes") or []
            note = set(subscribe.note or [])
            episodes_set = set(episodes)
            note = list(note - episodes_set)
            update_data["note"] = note
            if subscribe.total_episode:
                start_episode = subscribe.start_episode - 1 if subscribe.start_episode else 0
                lack_episode = subscribe.total_episode - start_episode - len(note)
                update_data["lack_episode"] = lack_episode
            else:
                update_data["lack_episode"] = subscribe.total_episode
        elif media_type == MediaType.MOVIE:
            update_data["note"] = []
        # 如果是洗版，这里还需要处理优先级
        if subscribe.best_version:
            update_data["current_priority"] = subscribe_task.get("current_priority", subscribe.current_priority) or 0
        if update_data:
            self.subscribe_oper.update(subscribe.id, update_data)

        random_minutes = random.uniform(3, 5)
        completion_time = f"{random_minutes:.2f} 分钟"

        # 消息推送
        if self._notify:
            # 构建消息内容
            msg_parts = []
            if torrent_task.get("title"):
                msg_parts.append(f"标题：{torrent_task.get('title')}")
            if torrent_task.get("description"):
                msg_parts.append(f"内容：{torrent_task.get('description')}")
            if self._auto_search_when_delete:
                msg_parts.append(f"补全：将在 {completion_time} 后触发搜索")
            # 拼接消息文本
            msg_text = "\n".join(msg_parts)
            # 推送消息
            self.post_message(
                mtype=NotificationType.Subscribe,
                title=f"{self.__format_subscribe_desc(subscribe=subscribe)} 订阅种子超时删除",
                text=msg_text,
                image=self.__get_subscribe_image(subscribe),
            )

        if not self._auto_search_when_delete:
            return

        # 如果这个订阅已经触发过补全搜索任务，直接返回
        if subscribe.id in triggered_subscribe_ids:
            return
        triggered_subscribe_ids.add(subscribe.id)
        logger.info(f"{self.__format_subscribe(subscribe)}，删除超时种子触发补全搜索任务，"
                    f"任务将在 {random_minutes:.2f} 分钟后触发")
        timer = threading.Timer(random_minutes * 60,
                                lambda: SubscribeChain().search(sid=subscribe.id))
        timer.start()

    def __clean_invalid_torrents(self, invalid_torrent_hashes: list, subscribe_tasks: dict, torrent_tasks: dict):
        """
        清理异常种子

        :param invalid_torrent_hashes: 异常种子哈希列表
        :param subscribe_tasks: 所有订阅任务
        :param torrent_tasks: 所有下载任务
        """
        # 从 subscribe_tasks 中移除与异常种子相关的订阅任务
        for torrent_hash in invalid_torrent_hashes:
            # 从 torrent_tasks 中移除异常种子
            torrent_task = torrent_tasks.get(torrent_hash)
            if not torrent_task:
                continue
            torrent_desc = self.__get_torrent_desc(torrent_hash, torrent_task)
            logger.info(f"清理异常种子：{torrent_desc}")
            del torrent_tasks[torrent_hash]

            # 从订阅任务中移除异常种子
            for subscribe_task in subscribe_tasks.values():
                subscribe_task["torrent_tasks"] = [
                    task for task in subscribe_task.get("torrent_tasks", []) if task.get("hash") != torrent_hash
                ]

    @staticmethod
    def __get_torrent_desc(torrent_hash: str, torrent_task: dict) -> str:
        """
        获取种子的描述信息

        :param torrent_hash: 种子hash
        :param torrent_task: 种子任务

        :return: 种子的描述字符串
        """
        title = torrent_task.get("title")
        description = torrent_task.get("description")
        return f"{title} | {description} ({torrent_hash})"

    def process_tv_pending(self, subscribes: [Subscribe | tuple[Subscribe, MediaInfo]]):
        """
        处理剧集自动待定
        :param subscribes: 订阅对象列表
        """
        if not self._auto_tv_pending or not subscribes:
            return

        self.__with_lock_and_update_subscribe_tasks(method=self.__process_tv_pending, subscribes=subscribes)

    def __process_tv_pending(self, subscribe_tasks: dict, subscribes: [Subscribe | tuple[Subscribe, MediaInfo]]):
        """
        处理剧集自动待定
        :param subscribe_tasks: 订阅任务字典
        :param subscribes: 订阅对象列表
        """
        for data in subscribes:
            if isinstance(data, tuple):
                subscribe, mediainfo = data
            else:
                subscribe = data
                mediainfo = None
            try:
                # 检查订阅是否为洗版订阅
                if subscribe.best_version:
                    logger.debug(f"{self.__format_subscribe(subscribe)} 为洗版订阅，跳过处理")
                    continue

                # 检查订阅状态是否可处理
                if not self.__check_subscribe_status(subscribe=subscribe):
                    continue

                # 检查订阅类型是否为电视剧
                if subscribe.type != MediaType.TV.value:
                    logger.debug(f"{subscribe.name} 的类型为 {subscribe.type}，非 TV 类型，跳过处理")
                    continue

                # 自动识别媒体信息
                if not mediainfo:
                    mediainfo = self.__recognize_media(subscribe)

                if not mediainfo:
                    continue

                # 检查媒体类型是否为 TV
                if mediainfo.type != MediaType.TV:
                    logger.debug(
                        f"{self.__format_subscribe(subscribe)} 类型为 {mediainfo.type}，非 TV 类型，跳过处理")
                    continue

                # 检查季信息是否存在
                if not mediainfo.season_info:
                    logger.warning(f"{self.__format_subscribe(subscribe)} 的 season_info 为空，跳过处理")
                    continue

                # 查找与当前订阅季数匹配的上映日期 (air_date)
                season = subscribe.season
                air_day = None
                for season_info in mediainfo.season_info:
                    if season_info.get("season_number") == season:
                        air_day = season_info.get("air_date")
                        continue

                if not air_day:
                    # 未找到与订阅季数匹配的上映日期
                    logger.warning(f"{mediainfo.title} 未找到与订阅季数 {season} 对应的 air_date，跳过处理")
                    continue

                # 解析上映日期
                try:
                    air_date = datetime.strptime(air_day, "%Y-%m-%d")
                except ValueError:
                    # 上映日期格式错误
                    logger.error(f"{mediainfo.title} 的 air_date 格式错误：{air_day}，跳过处理")
                    continue

                # 判断是否符合 auto_tv_pending_days 的要求
                pending_date = air_date + timedelta(days=self._auto_tv_pending_days)
                current_date = datetime.now()

                logger.debug(f"{self.__format_subscribe(subscribe)}，上映日期: {air_date}，"
                             f"待定天数：{self._auto_tv_pending_days}，当前日期: {current_date}")

                tv_pending = pending_date > current_date

                # 如果当前状态为 "N"，且需要待定处理，则触发补全搜索
                if subscribe.state == "N" and tv_pending:
                    random_minutes = random.uniform(3, 5)
                    logger.info(f"{self.__format_subscribe(subscribe)}，新增订阅触发补全搜索任务，"
                                f"任务将在 {random_minutes:.2f} 分钟后触发")
                    timer = threading.Timer(random_minutes * 60, lambda: SubscribeChain().search(sid=subscribe.id))
                    timer.start()

                subscribe_task, exists = self.__initialize_subscribe_task(subscribe=subscribe,
                                                                          subscribe_tasks=subscribe_tasks)

                # 更新订阅待定状态
                updated = self.__update_subscribe_tv_pending_task(subscribe=subscribe,
                                                                  subscribe_task=subscribe_task,
                                                                  pending=tv_pending)

                # 更新订阅状态，如果订阅任务没有被其他场景待定，则这里使用目标状态，如果已被其他场景修改，则这里使用待定状态更新
                pending = self.__get_subscribe_task_pending(subscribe_task=subscribe_task)
                target_state = subscribe.state

                if pending and subscribe.state != "P":
                    target_state = "P"
                elif not pending and subscribe.state == "P":
                    target_state = "R"

                if subscribe.state == target_state:
                    # 如果订阅目标状态一致，但是订阅待定状态已变更，也推送消息
                    if updated:
                        self.__send_tv_pending_msg(subscribe=subscribe, mediainfo=mediainfo,
                                                   air_day=air_day, tv_pending=tv_pending)
                    continue

                logger.info(f"{self.__format_subscribe(subscribe)} 订阅状态从 {subscribe.state} 更新为 {target_state}")
                self.subscribe_oper.update(subscribe.id, {"state": target_state})

                if updated:
                    self.__send_tv_pending_msg(subscribe=subscribe, mediainfo=mediainfo,
                                               air_day=air_day, tv_pending=tv_pending)

            except Exception as e:
                # 捕获异常并记录错误日志
                logger.error(f"处理订阅 ID {subscribe.id} 时发生错误: {str(e)}")

    def __send_tv_pending_msg(self, subscribe: Subscribe, mediainfo: MediaInfo, air_day: str, tv_pending: bool):
        """
        发送剧集待定消息
        :param subscribe: 订阅信息
        :param mediainfo: 媒体信息
        :param air_day: 上映日期
        :param tv_pending: 待定状态
        """
        if not self._notify:
            return

        # 构造消息文本
        text_parts = []
        if mediainfo.vote_average:
            text_parts.append(f"评分：{mediainfo.vote_average}")
        if subscribe.username:
            text_parts.append(f"来自用户：{subscribe.username}")
        if air_day:
            text_parts.append(f"上映日期：{air_day}")
        # 将非空部分拼接成完整的文本
        text = "，".join(text_parts) if text_parts else ""

        # 构造跳转链接
        if mediainfo.type == MediaType.TV:
            link = settings.MP_DOMAIN('#/subscribe/tv?tab=mysub')
        else:
            link = settings.MP_DOMAIN('#/subscribe/movie?tab=mysub')

        meta = MetaInfo(subscribe.name)
        meta.year = subscribe.year
        meta.begin_season = subscribe.season or None
        meta.type = mediainfo.type

        # 构造标题，根据状态动态调整
        if tv_pending:
            title = f"{mediainfo.title_year} {meta.season} 满足上映待定，已标记待定"
        else:
            title = f"{mediainfo.title_year} {meta.season} 不再满足上映待定，已标记订阅中"

        # 推送消息
        self.post_message(
            mtype=NotificationType.Subscribe,
            title=title,
            text=text,
            image=mediainfo.get_message_image(),
            link=link,
            # username=subscribe.username
        )

    def __recognize_media(self, subscribe: Subscribe) -> Optional[MediaInfo]:
        """
        识别媒体信息
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

    def __get_data(self, key: str) -> dict:
        """
        获取插件数据
        """
        return self.get_data(key=key) or {}

    def __save_data(self, key: str, value: Any) -> dict:
        """
        保存插件数据
        """
        return self.save_data(key=key, value=value)

    @staticmethod
    def __match_subscribe(subscribe: Subscribe, subscribe_task: dict) -> bool:
        """
        判断是否为同一个订阅
        """
        # 如果不存在或为空，则返回 False
        if not subscribe or not subscribe_task:
            return False

        # 判断ID
        if subscribe.id != subscribe_task.get("id") or subscribe.name != subscribe_task.get("name"):
            return False

        # 判断 tmdbid
        if subscribe.tmdbid and subscribe_task.get("tmdbid") != subscribe.tmdbid:
            return False

        # 判断 doubanid
        if subscribe.doubanid and subscribe_task.get("doubanid") != subscribe.doubanid:
            return False

        return True

    @staticmethod
    def __format_subscribe(subscribe: Subscribe) -> str:
        """
        格式化订阅信息
        """
        if not subscribe:
            return "无效的订阅信息"

        # 基于订阅类型拼接不同的字符串格式
        mediatype = MediaType(subscribe.type)
        if mediatype == MediaType.TV:
            return f"剧集: {subscribe.name} ({subscribe.year}) 季{subscribe.season} [{subscribe.id}]"
        elif mediatype == MediaType.MOVIE:
            return f"电影: {subscribe.name} ({subscribe.year}) [{subscribe.id}]"
        else:
            return f"未知类型: {subscribe.name} ({subscribe.year}) [{subscribe.id}]"

    def __format_subscribe_desc(self, subscribe: Subscribe, mediainfo: Optional[MediaInfo] = None) -> Optional[str]:
        """
        格式化订阅描述信息
        """
        if not subscribe:
            return None

        if not mediainfo:
            mediainfo = self.__recognize_media(subscribe=subscribe)

        if mediainfo:
            meta = MetaInfo(subscribe.name)
            meta.year = subscribe.year
            meta.begin_season = subscribe.season or None
            meta.type = mediainfo.type

            subscribe_desc = f"{mediainfo.title_year} {meta.season}" \
                if mediainfo.type == MediaType.TV else f"{mediainfo.title_year}"
            return subscribe_desc
        else:
            self.__format_subscribe(subscribe=subscribe)

    @staticmethod
    def __compare_torrent_info_and_task(torrent_info: TorrentInfo, torrent_task: dict) -> bool:
        """
        判断 torrent_info 和 task 是否一致
        :param torrent_info: TorrentInfo 实例
        :param torrent_task: 任务字典
        :return: 如果一致返回 True，不一致返回 False
        """
        if not torrent_info:
            return False

        # 如果 torrent_info.enclosure 和 task.enclosure 都不为空且一致
        if torrent_info.enclosure and torrent_task.get("enclosure") and torrent_task.get(
                "enclosure") == torrent_info.enclosure:
            return True

        # 如果 torrent_info.page_url 和 task.page_url 都不为空且一致
        if torrent_info.page_url and torrent_task.get("page_url") and torrent_task.get(
                "page_url") == torrent_info.page_url:
            return True

        # 如果都没有匹配到，返回 False
        return False

    def clear_tasks(self, subscribe_id: int, subscribe: dict):
        """
        清理任务
        :param subscribe_id: 订阅 ID
        :param subscribe: 订阅信息
        """
        self.__with_lock_and_update_subscribe_tasks(
            method=self.__clear_subscribe_tasks, subscribe_id=subscribe_id
        )
        self.__with_lock_and_update_torrent_tasks(
            method=self.__clear_torrent_tasks, subscribe_id=subscribe_id
        )

    @staticmethod
    def __clear_subscribe_tasks(subscribe_tasks: dict, subscribe_id: int):
        """
        清理订阅任务
        :param subscribe_tasks: 订阅任务字典
        :param subscribe_id: 订阅 ID
        """
        subscribe_id = str(subscribe_id)
        subscribe_tasks.pop(subscribe_id, None)

    @staticmethod
    def __clear_torrent_tasks(torrent_tasks: dict, subscribe_id: int):
        """
        清理种子任务
        :param torrent_tasks: 种子任务字典
        :param subscribe_id: 订阅 ID
        """
        for k in list(torrent_tasks.keys()):
            if torrent_tasks[k].get("subscribe_id") == subscribe_id:
                del torrent_tasks[k]

    @staticmethod
    def __update_or_add_delete_tasks(delete_tasks: dict, torrent_task: dict):
        """
        更新已删除种子任务
        :param delete_tasks: 已删除种子任务
        :param torrent_task: 种子任务
        """
        if not torrent_task:
            return
        torrent_hash = torrent_task.get("hash")
        torrent_task["delete_time"] = time.time()
        delete_tasks[torrent_hash] = torrent_task

    def __update_subscribe_torrent_task(self, subscribe_tasks: dict, subscribe: Subscribe,
                                        torrent_hash: Optional[str] = None,
                                        torrent_info: Optional[TorrentInfo] = None, episodes: list[int] = None,
                                        downloader: str = None, pending: bool = False,
                                        update_priority=False) -> Optional[dict]:
        """
        更新订阅种子任务，支持移除完成任务、更新或新增种子任务
        :param subscribe_tasks: 订阅任务字典
        :param subscribe: 订阅对象
        :param torrent_hash: 可选，种子的 hash 值
        :param torrent_info: 可选，种子信息
        :param episodes: 可选，需要下载的集数
        :param downloader: 可选，下载器
        :param pending: 可选，是否将种子任务标记为待定
        :param update_priority：可选，更新优先级
        :return: 返回更新后的订阅任务对象，或者移除任务后的任务信息
        """
        if not subscribe or subscribe_tasks is None:
            return None

        # 获取或初始化订阅任务
        subscribe_task, exists = self.__initialize_subscribe_task(subscribe, subscribe_tasks)

        # 更新或新增种子任务
        self.__update_or_add_subscribe_torrent_task(subscribe_task, torrent_hash, torrent_info,
                                                    episodes, downloader, pending)

        # 更新优先级
        if update_priority:
            subscribe_task["current_priority"] = subscribe.current_priority

        return subscribe_task

    def __update_or_add_subscribe_torrent_task(self, subscribe_task: dict, torrent_hash: Optional[str] = None,
                                               torrent_info: Optional[TorrentInfo] = None,
                                               episodes: list[int] = None,
                                               downloader: str = None,
                                               pending: bool = False) -> bool:
        """
        更新或新增订阅种子任务
        :param subscribe_task: 订阅任务
        :param torrent_hash: 种子hash
        :param torrent_info: 种子数据
        :param episodes: 需要下载的集数
        :param downloader: 下载器
        :param pending: 是否待定
        """
        if not subscribe_task:
            return False

        torrent_tasks = subscribe_task.setdefault("torrent_tasks", [])
        for task in torrent_tasks:
            if torrent_hash:
                # 如果已经有相同的 torrent_hash，直接返回
                if task.get("hash") == torrent_hash:
                    return False
                # 如果任务没有 hash 且信息匹配，更新 hash
                if not task.get("hash") and self.__compare_torrent_info_and_task(torrent_info, task):
                    task.update({
                        "hash": torrent_hash,
                        "episodes": episodes,
                        "downloader": downloader
                    })
                    return True
            else:
                if self.__compare_torrent_info_and_task(torrent_info, task):
                    return False

        if not torrent_info:
            return False

        # 如果未找到匹配任务，初始化一个新的 torrent_task
        torrent_tasks.append({
            "hash": torrent_hash,
            "site_id": torrent_info.site,
            "site_name": torrent_info.site_name,
            "title": torrent_info.title,
            "description": torrent_info.description,
            "enclosure": torrent_info.enclosure,
            "page_url": torrent_info.page_url,
            "episodes": episodes,
            "downloader": downloader,
            "time": time.time(),
            "pending": pending,
            "pending_time": time.time() if pending else None
        })
        return True

    def __update_subscribe_tv_pending_task(self, subscribe: Subscribe, subscribe_task: dict,
                                           pending: bool = False) -> bool:
        """
        更新订阅任务剧集待定状态
        :param subscribe: 订阅对象
        :param subscribe_task: 订阅任务
        :param pending: 是否设置为剧集待定
        """
        if not subscribe or subscribe_task is None:
            return False

        if subscribe_task.get("tv_pending", False) == pending:
            logger.debug(f"{self.__format_subscribe(subscribe)} 当前订阅剧集待定状态无需变更")
            return False

        # 更新 tv_pending 状态
        if pending:
            logger.debug(f"{self.__format_subscribe(subscribe)} 当前订阅剧集待定状态更新为待定")
            subscribe_task["tv_pending"] = True
            subscribe_task["tv_pending_time"] = time.time()
        else:
            logger.debug(f"{self.__format_subscribe(subscribe)} 当前订阅剧集待定状态更新为订阅中")
            subscribe_task["tv_pending"] = False
            subscribe_task["tv_pending_time"] = None

        return True

    def __get_subscribe_task_pending(self, subscribe_task: dict) -> bool:
        """
        获取待定状态
        :param subscribe_task: 订阅任务
        """
        if not subscribe_task:
            return False

        if subscribe_task.get("tv_pending"):
            return True

        return self.__get_subscribe_task_download_pending(subscribe_task=subscribe_task)

    @staticmethod
    def __get_subscribe_task_download_pending(subscribe_task: dict) -> bool:
        """
        获取待定状态
        :param subscribe_task: 订阅任务
        """
        if not subscribe_task:
            return False

        for task in subscribe_task.get("torrent_tasks", []):
            if task.get("hash") and task.get("pending"):
                return True

        return False

    def __initialize_subscribe_task(self, subscribe: Subscribe, subscribe_tasks: dict) -> tuple[dict, bool]:
        """
        初始化订阅任务，或者获取已有的订阅任务
        :param subscribe: 订阅对象
        :param subscribe_tasks: 订阅任务列表
        :return: 订阅任务，是否已存在
        """
        subscribe_id = str(subscribe.id)
        subscribe_task = subscribe_tasks.get(subscribe_id)

        # 判断现有任务是否存在且一致
        if subscribe_task:
            match = self.__match_subscribe(subscribe=subscribe, subscribe_task=subscribe_task)
            if match:
                return subscribe_task, True
            else:
                # 订阅信息不一致，记录日志并删除旧的订阅任务
                logger.info(f"订阅任务不一致，删除原任务：ID={subscribe_id}, Name={subscribe_task.get('name')}, "
                            f"Subscribe_task={subscribe_task}")
                subscribe_tasks.pop(subscribe_id)

        # 创建新的订阅任务
        subscribe_task = {
            "id": subscribe.id,
            "name": subscribe.name,
            "year": subscribe.year,
            "type": subscribe.type,
            "season": subscribe.season,
            "tmdbid": subscribe.tmdbid,
            "imdbid": subscribe.imdbid,
            "tvdbid": subscribe.tvdbid,
            "doubanid": subscribe.doubanid,
            "bangumiid": subscribe.bangumiid,
            "best_version": subscribe.best_version,
            "current_priority": subscribe.current_priority,
            "tv_pending": False,
            "tv_pending_time": None,
            "torrent_tasks": []
        }
        subscribe_tasks[subscribe_id] = subscribe_task
        return subscribe_task, False

    @staticmethod
    def __get_subscribe_image(subscribe: Subscribe):
        """
        返回订阅图片地址
        """
        if subscribe.backdrop:
            return subscribe.backdrop.replace("original", "w500")
        if subscribe.poster:
            return subscribe.poster.replace("original", "w500")
        return ""

    def process_best_version_complete(self, subscribes: list[Subscribe]):
        """
        处理自动洗版完成检查
        :param subscribes: 订阅对象列表
        """
        if not self._auto_best_types or not subscribes:
            return

        if not self._auto_best_remaining_days:
            logger.debug("未配置洗版天数，跳过处理")
            return

        if self._auto_best_remaining_days <= 0:
            logger.debug("洗版天数小于等于0，跳过处理")
            return

        for subscribe in subscribes:
            if not subscribe.best_version:
                continue

            # 优先级已经是洗版完成，跳过
            if subscribe.current_priority == 100:
                logger.debug(f"{self.__format_subscribe(subscribe)} 优先级已标识为洗版完成，跳过处理")
                continue

            # 获取最后更新的日期，优先使用 last_update，否则使用创建日期
            last_update_date_str = subscribe.last_update or subscribe.date
            if not last_update_date_str:
                logger.debug(f"{self.__format_subscribe(subscribe)} 没有有效的日期，跳过处理")
                continue

                # 将字符串转换为 datetime 对象
            try:
                last_update_date = datetime.strptime(last_update_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # 如果日期格式不匹配，跳过此条订阅
                logger.warning(f"{self.__format_subscribe(subscribe)} 的日期格式不匹配，跳过处理")
                continue

            # 计算距离当前的天数
            remaining_days = (datetime.now() - last_update_date).total_seconds() / 86400
            logger.info(f"{self.__format_subscribe(subscribe)} 距离上次更新 {remaining_days:.2f} 天")

            if remaining_days >= self._auto_best_remaining_days:
                # 如果剩余天数已大于洗版天数，则更新优先级为100，标识为洗版完成
                logger.info(f"{self.__format_subscribe(subscribe)} 已满足洗版天数，更新优先级为 100")
                self.subscribe_oper.update(sid=subscribe.id, payload={"current_priority": 100})
            else:
                logger.info(f"订阅 {self.__format_subscribe(subscribe)} 尚未满足洗版天数，跳过处理")

    def process_best_version(self, subscribe_dict: dict, mediainfo: MediaInfo):
        """
        处理自动洗版
        """
        if not subscribe_dict:
            return

        subscribe_dict.pop("id", None)
        model_fields = SchemaSubscribe.__fields__
        for key in list(subscribe_dict.keys()):
            if key not in model_fields:
                subscribe_dict.pop(key)
        subscribe = SchemaSubscribe(**subscribe_dict)

        if subscribe.best_version:
            logger.debug(f"{self.__format_subscribe(subscribe)} 已为洗版订阅，跳过处理")
            return

        if MediaType(subscribe.type) not in self._auto_best_types:
            logger.debug(f"{self.__format_subscribe(subscribe)}，尚未开启自动洗版，跳过处理")
            return

        # 自动识别媒体信息
        if not mediainfo:
            mediainfo = self.__recognize_media(subscribe)

        if not mediainfo:
            return

        # 更新订阅字典
        subscribe_dict["best_version"] = True
        subscribe_dict["username"] = self.plugin_name
        subscribe_dict["state"] = "N"
        fields_to_pop = [
            "name", "year", "type", "tmdbid", "imdbid", "tvdbid", "doubanid", "bangumiid",
            "poster", "backdrop", "vote", "description", "date", "last_update", "note", "state", "current_priority"
        ]
        for field in fields_to_pop:
            subscribe_dict.pop(field, None)
        if mediainfo.type == MediaType.TV:
            subscribe_dict["lack_episode"] = subscribe_dict.get("total_episode")

        # 添加订阅
        sid, err_msg = self.subscribe_oper.add(mediainfo=mediainfo,
                                               **subscribe_dict)

        subscribe_desc = self.__format_subscribe_desc(subscribe=subscribe, mediainfo=mediainfo)

        if sid:
            logger.info(f"{subscribe_desc} 已成功添加洗版订阅 (ID: {sid})")
            # 发送事件
            eventmanager.send_event(EventType.SubscribeAdded, {
                "subscribe_id": sid,
                "username": self.plugin_name,
                "mediainfo": mediainfo.to_dict(),
            })
        else:
            logger.error(f"{subscribe_desc} 添加洗版订阅失败，错误信息: {err_msg}")

        if not self._notify:
            return

        if not sid:
            self.post_message(
                mtype=NotificationType.Subscribe,
                title=f"{subscribe_desc} 添加洗版订阅失败！",
                text=err_msg,
                image=mediainfo.get_message_image()
            )
        else:
            if mediainfo.type == MediaType.TV:
                link = settings.MP_DOMAIN('#/subscribe/tv?tab=mysub')
            else:
                link = settings.MP_DOMAIN('#/subscribe/movie?tab=mysub')
            self.post_message(
                mtype=NotificationType.Subscribe,
                title=f"{subscribe_desc} 已添加洗版订阅",
                text=f"评分：{mediainfo.vote_average}，来自用户：{self.plugin_name}",
                image=mediainfo.get_message_image(),
                link=link,
                # username=subscribe.username
            )

    def __with_lock_and_update_subscribe_tasks(self, method: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """
        使用锁获取并更新订阅任务数据
        :param method: 需要执行的操作，接收当前数据字典并进行修改
        :param *args: 额外的位置参数
        :param **kwargs: 额外的关键字参数
        """
        with lock:
            try:
                # 获取数据
                tasks = self.__get_data(key="subscribes")

                # 执行需要的操作
                method(tasks, *args, **kwargs)

                # 保存修改后的数据
                self.__save_data(key="subscribes", value=tasks)
            except Exception as e:
                # 处理异常
                logger.error(f"Error during {method.__name__}: {e}")

    def __with_lock_and_update_torrent_tasks(self, method: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        """
        使用锁获取并更新下载任务数据
        :param method: 需要执行的操作，接收当前数据字典并进行修改
        :param *args: 额外的位置参数
        :param **kwargs: 额外的关键字参数
        """
        with lock:
            try:
                # 获取数据
                tasks = self.__get_data(key="torrents")

                # 执行需要的操作
                method(tasks, *args, **kwargs)

                # 保存修改后的数据
                self.__save_data(key="torrents", value=tasks)
            except Exception as e:
                # 处理异常
                logger.error(f"Error during {method.__name__}: {e}")

    def __with_lock_and_update_delete_tasks(self, method: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        with lock:
            try:
                # 获取数据
                tasks = self.__get_data(key="deletes")

                # 执行需要的操作
                method(tasks, *args, **kwargs)

                # 保存修改后的数据
                self.__save_data(key="deletes", value=tasks)
            except Exception as e:
                # 处理异常
                logger.error(f"Error during {method.__name__}: {e}")

    def __check_subscribe_status(self, subscribe: Subscribe) -> bool:
        """
        检查订阅状态是否符合要求
        """
        if not subscribe:
            return False

        # 检查订阅状态是否可处理
        if subscribe.state not in ["N", "R", "P"]:
            logger.debug(
                f"{self.__format_subscribe(subscribe)} 当前状态为 {subscribe.state}，状态不允许处理，跳过处理")
            return False
        return True
