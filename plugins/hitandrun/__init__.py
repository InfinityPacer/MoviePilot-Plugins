import random
import threading
import time
from dataclasses import fields
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional, Union

import pytz
from app.helper.sites import SitesHelper
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.context import TorrentInfo, Context
from app.core.event import eventmanager, Event
from app.core.plugin import PluginManager
from app.db.site_oper import SiteOper
from app.log import logger
from app.modules.qbittorrent import Qbittorrent
from app.modules.transmission import Transmission
from app.plugins import _PluginBase
from app.plugins.hitandrun.entities import TorrentTask, HNRStatus, TorrentHistory, TaskType
from app.plugins.hitandrun.hnrconfig import HNRConfig, SiteConfig, NotifyMode
from app.schemas import NotificationType
from app.schemas.types import EventType

lock = threading.Lock()


class HitAndRun(_PluginBase):
    # 插件名称
    plugin_name = "H&R助手"
    # 插件描述
    plugin_desc = "监听下载、订阅、刷流等行为，对H&R种子进行自动标签管理。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/hitandrun.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "hitandrun_"
    # 加载顺序
    plugin_order = 24
    # 可使用的用户级别
    auth_level = 2

    # region 私有属性

    pluginmanager = None
    siteshelper = None
    siteoper = None
    systemconfig = None
    qb = None
    tr = None
    # H&R助手配置
    _hnr_config = None
    # 下载器
    _downloader = None

    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self.pluginmanager = PluginManager()
        self.siteshelper = SitesHelper()
        self.siteoper = SiteOper()
        if not config:
            return

        result, reason = self.__validate_and_fix_config(config=config)

        if not result and not self._hnr_config:
            self.__update_config_if_error(config=config, error=reason)
            return

        self.stop_service()

        if not self.__setup_downloader():
            return

        self._downloader = self.__get_downloader()

        if self._hnr_config.onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._hnr_config.onlyonce = False

            logger.info(f"立即运行一次{self.plugin_name}服务")
            self._scheduler.add_job(
                func=self.check,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name=f"{self.plugin_name}",
            )

            self._scheduler.add_job(
                func=self.auto_monitor,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name=f"{self.plugin_name}",
            )

            if self._scheduler.get_jobs():
                # 启动服务
                self._scheduler.print_jobs()
                self._scheduler.start()

        self.__update_config()

    def get_state(self) -> bool:
        return self._hnr_config and self._hnr_config.enabled

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
                                            'model': 'enable_site_config',
                                            'label': '站点独立配置',
                                            'hint': '启用站点独立配置',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 3
                                },
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "dialog_closed",
                                            "label": "打开站点配置窗口",
                                            'hint': '点击弹出窗口以修改站点配置',
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
                            },
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
                                            'model': 'sites',
                                            'label': '站点列表',
                                            'hint': '选择参与配置的站点',
                                            'persistent-hint': True,
                                            'items': self.__get_site_options()
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
                                            'model': 'notify',
                                            'label': '发送通知',
                                            'items': [
                                                {'title': '不发送', 'value': 'none'},
                                                {'title': '仅异常时发送', 'value': 'on_error'},
                                                {'title': '发送所有通知', 'value': 'always'}
                                            ],
                                            'hint': '是否在特定事件发生时发送通知',
                                            'persistent-hint': True,
                                        }
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
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'downloader',
                                            'label': '下载器',
                                            'items': [
                                                {'title': 'Qbittorrent', 'value': 'qbittorrent'},
                                                # {'title': 'Transmission', 'value': 'transmission'}
                                            ],
                                            'hint': '选择下载器',
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
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'brush_plugin',
                                            'label': '站点刷流插件',
                                            'hint': '选择参与配置的刷流插件',
                                            'persistent-hint': True,
                                            'items': self.__get_plugin_options()
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
                                    'md': 4,
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'hit_and_run_tag',
                                            'label': '种子标签',
                                            'hint': '标记为H&R种子时添加的标签',
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
                                            'model': 'hr_duration',
                                            'label': 'H&R时间（小时）',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '做种时间达到H&R时间后移除标签',
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
                                            'model': 'hr_deadline_days',
                                            'label': '满足H&R要求的期限（天）',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '需在此天数内满足H&R要求的期限',
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
                                            'model': 'additional_seed_time',
                                            'label': '附加做种时间（小时）',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '在H&R时间上额外增加的做种时间',
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
                                            'model': 'ratio',
                                            'label': '分享率',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '达到目标分享率后移除标签',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        "content": [
                            # {
                            #     'component': 'VCol',
                            #     'props': {
                            #         'cols': 12,
                            #         'md': 4
                            #     },
                            #     'content': [
                            #         {
                            #             'component': 'VSwitch',
                            #             'props': {
                            #                 'model': 'auto_monitor',
                            #                 'label': '自动监控（实验性功能）',
                            #                 'hint': '启用后将定时监控站点个人H&R页面',
                            #                 'persistent-hint': True
                            #             }
                            #         }
                            #     ]
                            # },

                        ]
                    },
                    # {
                    #     'component': 'VRow',
                    #     'content': [
                    #         {
                    #             'component': 'VCol',
                    #             'props': {
                    #                 'cols': 12,
                    #             },
                    #             'content': [
                    #                 {
                    #                     'component': 'VAlert',
                    #                     'props': {
                    #                         'type': 'info',
                    #                         'variant': 'tonal',
                    #                         'text': '注意：开启自动监控后，将按随机周期访问站点个人H&R页面'
                    #                     }
                    #                 }
                    #             ]
                    #         },
                    #     ]
                    # },
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：本插件仍在完善阶段，同时并未适配所有场景，如RSS订阅等'
                                        }
                                    }
                                ]
                            },
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：本插件并不能完全适配所有站点，请以实际使用情况为准'
                                        }
                                    }
                                ]
                            },
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：本插件可能导致H&R种子被错误识别，严重甚至导致站点封号，请慎重使用'
                                        }
                                    }
                                ]
                            },
                        ]
                    },
                    {
                        "component": "VDialog",
                        "props": {
                            "model": "dialog_closed",
                            "max-width": "65rem",
                            "overlay-class": "v-dialog--scrollable v-overlay--scroll-blocked",
                            "content-class": "v-card v-card--density-default v-card--variant-elevated rounded-t"
                        },
                        "content": [
                            {
                                "component": "VCard",
                                "props": {
                                    "title": "设置站点配置"
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
                                                                    'modelvalue': 'site_config_str',
                                                                    'lang': 'yaml',
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
                                                                    'variant': 'tonal'
                                                                },
                                                                'content': [
                                                                    {
                                                                        'component': 'span',
                                                                        'text': '注意：只有启用站点独立配置时，该配置项才会生效'
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
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "notify": "always",
            "downloader": "qbittorrent",
            "hit_and_run_tag": "H&R",
            "spider_period": 720,
            "ratio": 99,
            "hr_duration": 144,
            "hr_deadline_days": 14,
            "additional_seed_time": 24,
            "site_config_str": self.__get_demo_config()
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
        if not self._hnr_config:
            return []

        services = []

        if self._hnr_config.enabled:

            services.append({
                "id": f"{self.__class__.__name__}Check",
                "name": f"{self.plugin_name}检查服务",
                "trigger": "interval",
                "func": self.check,
                "kwargs": {"minutes": self._hnr_config.check_period}
            })

            if self._hnr_config.auto_monitor:
                # 每天执行4次，随机在8点~23点之间执行
                triggers = self.__random_even_scheduler(num_executions=4,
                                                        begin_hour=8,
                                                        end_hour=23)
                for trigger in triggers:
                    services.append({
                        "id": f"{self.__class__.__name__}|Monitor|{trigger.hour}:{trigger.minute}",
                        "name": f"{self.plugin_name}监控服务",
                        "trigger": "cron",
                        "func": self.auto_monitor,
                        "kwargs": {
                            "hour": trigger.hour,
                            "minute": trigger.minute
                        }
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

    def check(self):
        """
        检查服务
        """
        pass

    def auto_monitor(self):
        """
        监控服务
        """
        pass

    @eventmanager.register(EventType.DownloadAdded)
    def handle_download_added_event(self, event: Event = None):
        """
        处理下载添加事件，支持普通下载和RSS订阅
        """
        if not self.__validate_and_log_event(event, event_type_desc="下载任务"):
            return

        torrent_hash = event.event_data.get("hash")
        context: Context = event.event_data.get("context")

        if not torrent_hash or not context or not context.torrent_info:
            logger.info("没有获取到有效的种子任务信息，跳过处理")
            return

        torrent_info = context.torrent_info

        # 现阶段，由于获取下载来源涉及主程序大幅调整，暂时处理方案为，如果没有种子详情（页面详情）的，均认为是RSS订阅
        task_type = TaskType.NORMAL if torrent_info.description else TaskType.RSS_SUBSCRIBE
        self.__process_event(torrent_hash=torrent_hash, torrent_data=torrent_info, task_type=task_type)

    @eventmanager.register(EventType.PluginAction)
    def handle_brushflow_event(self, event: Event = None):
        """
        处理刷流下载任务事件
        """
        # {'action': 'brushflow_download_added', 'hash': '4dd8acdf4bcf34f915652467df7c007dd4a86381',
        #  'data': {'site': 5, 'site_name': '皇后', 'title': '群星 - 广州影音展15周年 HiFi鉴赏① 2022 - FLAC 分轨',
        #           'size': 389577441, 'pubdate': '2024-07-31 19:50:11', 'description': None, 'imdbid': None,
        #           'page_url': 'https://open.cd/plugin_details.php?id=161393&hit=1', 'date_elapsed': '2時44分',
        #           'freedate': None, 'uploadvolumefactor': 1, 'downloadvolumefactor': 0, 'hit_and_run': False,
        #           'volume_factor': '免费', 'freedate_diff': '', 'ratio': 0, 'downloaded': 0, 'uploaded': 0,
        #           'seeding_time': 0, 'deleted': False, 'time': 1722436530.449227}}
        if not self.__validate_and_log_event(event,
                                             event_type_desc="刷流下载任务",
                                             action_required="brushflow_download_added"):
            return

        torrent_hash = event.event_data.get("hash")
        torrent_data = event.event_data.get("data")
        self.__process_event(torrent_hash, torrent_data, TaskType.BRUSH)

    @staticmethod
    def __validate_and_log_event(event, event_type_desc: str, action_required: str = None):
        """
        验证事件是否有效并记录日志
        """
        if not event or not event.event_data:
            return False

        if action_required and event.event_data.get("action") != action_required:
            return False

        logger.info(f"触发{event_type_desc}事件: {event.event_type} | {event.event_data}")
        return True

    def __process_event(self, torrent_hash: str, torrent_data: Union[dict, TorrentInfo], task_type: TaskType):
        """
        通用事件处理逻辑
        """
        with lock:
            if not torrent_hash or not torrent_data:
                logger.info("没有获取到有效的种子任务信息，跳过处理")
                return

            torrent = self.__get_torrents(torrent_hashes=torrent_hash)
            if not torrent:
                logger.warn(f"下载器中没有获取到 torrent_hash: {torrent_hash} 的种子信息，跳过处理")
                return

            # 保存种子下载记录
            self.__save_and_cleanup_downloads(torrent_hash=torrent_hash, torrent_data=torrent_data, task_type=task_type)
            # 处理种子任务
            self.__process_torrent_task(torrent_hash=torrent_hash, torrent_data=torrent_data, task_type=task_type)

    def __process_torrent_task(self, torrent_hash: str, torrent_data: Union[dict, TorrentInfo], task_type: TaskType):
        """
        处理并保存种子任务
        """
        torrent_task = self.__create_torrent_task(torrent_hash=torrent_hash,
                                                  torrent_data=torrent_data,
                                                  task_type=task_type)

        if torrent_task.site not in self._hnr_config.sites:
            logger.info(f"站点 {torrent_task.site_name} 没有启用 H&R 管理，跳过处理")
            return

        self.__adjust_hr_status(torrent_task=torrent_task)
        self.__save_torrent_tasks(torrent_tasks=torrent_task)

        if not torrent_task.hit_and_run:
            return

        self.__set_hit_and_run_tag(torrent_task=torrent_task)
        self.__send_hr_message(torrent_task=torrent_task)

    def __adjust_hr_status(self, torrent_task: TorrentTask):
        """
        调整和保存H&R状态
        """
        site_config = self.__get_site_config(site_name=torrent_task.site_name)

        # 如果站点已经激活全局H&R，则强制标识为H&R种子
        if site_config.hr_active:
            torrent_task.hit_and_run = True

        if torrent_task.hit_and_run:
            torrent_task.hr_duration = site_config.hr_duration
            torrent_task.hr_deadline_days = site_config.hr_deadline_days
            torrent_task.hr_status = HNRStatus.IN_PROGRESS
        else:
            torrent_task.hr_status = HNRStatus.UNRESTRICTED

    def __save_torrent_tasks(self, torrent_tasks: Union[TorrentTask, List[TorrentTask]]):
        """
        保存或更新单个或多个种子任务数据
        """
        if not torrent_tasks:
            return

        # 确保输入总是列表形式，方便统一处理
        if isinstance(torrent_tasks, TorrentTask):
            torrent_tasks = [torrent_tasks]

        existing_torrent_tasks: Dict[str, dict] = self.__get_data(key="torrents")

        # 使用字典解析和 update 方法批量更新数据
        updates = {task.hash: task.to_dict() for task in torrent_tasks}
        existing_torrent_tasks.update(updates)

        # 一次性保存所有更新
        self.save_data(key="torrents", value=existing_torrent_tasks)

    def __set_hit_and_run_tag(self, torrent_task: TorrentTask):
        """
        设置H&R标签
        """
        if not torrent_task and not torrent_task.hash:
            return

        if not torrent_task.hit_and_run:
            return

        # 这里重新获取一次种子，避免出现tags冲突的问题
        torrent = self.__get_torrents(torrent_hashes=torrent_task.hash)
        if not torrent:
            logger.warn(f"下载器中没有获取到 torrent_hash: {torrent_task.hash} 的种子信息")
            return

        try:
            tags = self.__get_torrent_tags(torrent=torrent)
            tags.append(self._hnr_config.hit_and_run_tag)
            self.__set_torrent_tag(torrent_hash=torrent_task.hash, tags=tags)
        except Exception as e:
            logger.error(f"设置标签时出错：{str(e)}")

    def __save_and_cleanup_downloads(self, torrent_hash: str, torrent_data: Union[dict, TorrentInfo],
                                     task_type: TaskType = TaskType.NORMAL) -> Optional[TorrentHistory]:
        """
        保存下载记录并清理7天前的记录
        """
        torrent_history = self.__create_torrent_history(torrent_hash=torrent_hash,
                                                        torrent_data=torrent_data,
                                                        task_type=task_type)

        downloads: Dict[str, dict] = self.__get_data(key="downloads")

        # 添加新的下载记录
        downloads[torrent_hash] = torrent_history.to_dict()

        # 获取当前时间和7天前的时间戳
        current_time = time.time()
        cutoff_time = current_time - 7 * 24 * 60 * 60

        # 清理7天以前的下载记录
        downloads = {key: value for key, value in downloads.items() if value.get("time", current_time) > cutoff_time}

        # 保存更新后的下载记录
        self.save_data(key="downloads", value=downloads)

        return torrent_history

    @staticmethod
    def __create_torrent_instance(torrent_hash: str, torrent_data: Union[dict, TorrentInfo], cls,
                                  task_type: TaskType) -> Union[TorrentHistory, TorrentTask]:
        """创建种子实例"""
        if isinstance(torrent_data, TorrentInfo):
            result = cls.from_torrent_info(torrent_info=torrent_data)
        else:
            allowed_fields = {field.name for field in fields(TorrentInfo)}
            # 过滤数据，只保留 TorrentInfo 数据类中的字段
            filtered_data = {key: value for key, value in torrent_data.items() if key in allowed_fields}
            # 创建指定类的实例
            result = cls(**filtered_data)

        result.hash = torrent_hash
        result.task_type = task_type
        return result

    @staticmethod
    def __create_torrent_history(torrent_hash: str, torrent_data: Union[dict, TorrentInfo],
                                 task_type: TaskType) -> TorrentHistory:
        """创建种子信息"""
        return HitAndRun.__create_torrent_instance(torrent_hash, torrent_data, TorrentHistory, task_type)

    @staticmethod
    def __create_torrent_task(torrent_hash: str, torrent_data: Union[dict, TorrentInfo],
                              task_type: TaskType) -> TorrentTask:
        """创建种子任务"""
        return HitAndRun.__create_torrent_instance(torrent_hash, torrent_data, TorrentTask, task_type)

    def __get_site_config(self, site_name: str) -> Optional[SiteConfig]:
        """"获取站点配置"""
        if not self._hnr_config:
            return None
        return self._hnr_config.get_site_config(site_name=site_name)

    def __get_data(self, key: str):
        """获取插件数据"""
        if not key:
            return {}
        return self.get_data(key=key) or {}

    def __setup_downloader(self) -> bool:
        """
        根据下载器类型初始化下载器实例
        """
        if not self._hnr_config:
            return False

        self.qb = Qbittorrent()
        # self.tr = Transmission()

        if self._hnr_config.downloader == "qbittorrent":
            if self.qb.is_inactive():
                self.__log_and_notify_error("发生异常：Qbittorrent未连接")
                return False
        # elif self._hnr_config.downloader == "transmission":
        #     if self.tr.is_inactive():
        #         self.__log_and_notify_error("发生异常：Transmission未连接")
        #         return False

        return True

    def __get_downloader(self) -> Optional[Union[Transmission, Qbittorrent]]:
        """
        根据类型返回下载器实例
        """
        if not self._hnr_config:
            return None

        if self._hnr_config.downloader == "qbittorrent":
            return self.qb
        # elif self._hnr_config.downloader == "transmission":
        #     return self.tr
        else:
            return None

    def __get_torrents(self, torrent_hashes: Union[str, List[str]]) -> Optional[Any]:
        """
        获取下载器中的种子信息
        如果 `torrent_hashes` 只包含一个值，返回该种子的具体信息
        如果包含多个值，返回包含所有种子信息的列表
        """
        if not torrent_hashes:
            return None

        # 处理单个种子哈希的情况，确保其被视为列表
        if isinstance(torrent_hashes, str):
            torrent_hashes = [torrent_hashes]

        torrents, error = self._downloader.get_torrents(ids=torrent_hashes)
        if error:
            logger.warn("连接下载器出错，将在下个时间周期重试")
            return None

        # 如果只有一个种子哈希，直接返回该种子的信息
        if len(torrent_hashes) == 1:
            return torrents[0] if torrents else None

        return torrents

    def __set_torrent_tag(self, torrent_hash: str, tags: list):
        """
        设置种子标签
        """
        try:
            unique_tags = list(set(tags))
            if self._hnr_config.downloader == "qbittorrent":
                self._downloader.set_torrents_tag(ids=torrent_hash, tags=unique_tags)
            else:
                self._downloader.set_torrent_tag(ids=torrent_hash, tags=unique_tags)
        except Exception as e:
            logger.error(f"无法为 torrent_hash: {torrent_hash} 设置标签，错误: {e}")

    def __get_torrent_tags(self, torrent: Any) -> list[str]:
        """
        获取种子标签
        """
        try:
            if self._hnr_config.downloader == "qbittorrent":
                tags = torrent.get("tags", "").split(",")
            else:
                tags = torrent.labels or []

            return list(set(tag.strip() for tag in tags if tag.strip()))
        except Exception as e:
            logger.error(f"获取种子标签失败，错误: {e}")
            return []

    @staticmethod
    def __validate_config(config: HNRConfig) -> (bool, str):
        """
        验证配置是否有效
        """
        if not config.enabled and not config.onlyonce:
            return True, "插件未启用，无需进行验证"

        if not config.downloader:
            return False, "下载器不能为空"

        if config.hr_duration <= 0:
            return False, "H&R时间必须大于0"

        if config.hr_deadline_days <= 0:
            return False, "H&R满足要求的期限必须大于0"

        if config.ratio <= 0:
            return False, "分享率必须大于0"

        return True, "所有配置项都有效"

    def __validate_and_fix_config(self, config: dict = None) -> [bool, str]:
        """
        检查并修正配置值
        """
        if not config:
            return False, ""

        try:
            # 使用字典推导来提取所有字段，并用config中的值覆盖默认值
            hnr_config = HNRConfig.from_dict(data=config)

            result, reason = self.__validate_config(config=hnr_config)
            if result:
                # 过滤掉已删除的站点并保存
                if hnr_config.sites:
                    site_id_to_public_status = {site.get("id"): site.get("public") for site in
                                                self.siteshelper.get_indexers()}
                    hnr_config.sites = [
                        site_id for site_id in hnr_config.sites
                        if site_id in site_id_to_public_status and not site_id_to_public_status[site_id]
                    ]

                    site_infos = {}
                    for site_id in hnr_config.sites:
                        site_info = self.siteoper.get(site_id)
                        if site_info:
                            site_infos[site_id] = site_info
                    hnr_config.site_infos = site_infos

                self._hnr_config = hnr_config
                return True, ""
            else:
                self._hnr_config = None
                return result, reason
        except Exception as e:
            self._hnr_config = None
            logger.error(e)
            return False, str(e)

    def __update_config_if_error(self, config: dict = None, error: str = None):
        """异常时停用插件并保存配置"""
        if config:
            if config.get("enabled", False) or config.get("onlyonce", False):
                config["enabled"] = False
                config["onlyonce"] = False
                self.__log_and_notify_error(
                    f"配置异常，已停用{self.plugin_name}，原因：{error}" if error else f"配置异常，已停用{self.plugin_name}，请检查")
            self.update_config(config)

    def __update_config(self):
        """保存配置"""
        config_mapping = self._hnr_config.to_dict()
        del config_mapping["check_period"]
        del config_mapping["site_infos"]
        del config_mapping["site_configs"]
        self.update_config(config_mapping)

    def __get_site_options(self):
        """获取当前可选的站点"""
        site_options = [{"title": site.get("name"), "value": site.get("id")}
                        for site in self.siteshelper.get_indexers()]
        return site_options

    def __get_plugin_options(self) -> List[dict]:
        """获取插件选项列表"""
        # 获取运行的插件选项
        running_plugins = self.pluginmanager.get_running_plugin_ids()

        # 需要检查的插件名称
        filter_plugins = {"BrushFlow", "BrushFlowLowFreq"}

        # 获取本地插件列表
        local_plugins = self.pluginmanager.get_local_plugins()

        # 初始化插件选项列表
        plugin_options = []

        # 从本地插件中筛选出符合条件的插件
        for local_plugin in local_plugins:
            if local_plugin.id in running_plugins and local_plugin.id in filter_plugins:
                plugin_options.append({
                    "title": f"{local_plugin.plugin_name} v{local_plugin.plugin_version}",
                    "value": local_plugin.id,
                    "name": local_plugin.plugin_name
                })

        # 重新编号，保证显示为 1. 2. 等
        for index, option in enumerate(plugin_options, start=1):
            option["title"] = f"{index}. {option['title']}"

        return plugin_options

    def __log_and_notify_error(self, message):
        """
        记录错误日志并发送系统通知
        """
        logger.error(message)
        self.systemmessage.put(message, title=self.plugin_name)

    @staticmethod
    def __build_hr_message_text(torrent_task: TorrentTask):
        """
        构建关于 H&R 事件的消息文本
        """
        msg_parts = []
        label_mapping = {
            "site_name": ("站点", str),
            "task_type": ("类型", TorrentTask.format_to_chinese),
            "title": ("标题", str),
            "description": ("描述", str),
            "size": ("大小", TorrentTask.format_size),
            "hr_status": ("状态", TorrentTask.format_to_chinese),
            "hr_duration": ("时间", TorrentTask.format_duration),
            "hr_deadline_days": ("期限", TorrentTask.format_deadline_days),
        }

        for key, (label, formatter) in label_mapping.items():
            value = getattr(torrent_task, key, None)
            if value is not None:
                formatted_value = formatter(value)
                if formatted_value:
                    msg_parts.append(f"{label}：{formatted_value}")

        return "\n".join(msg_parts)

    def __send_hr_message(self, torrent_task, title: str = "【H&R种子下载】"):
        """
        发送命中 H&R 种子消息
        """
        if self._hnr_config.notify == NotifyMode.ALWAYS:
            msg_text = self.__build_hr_message_text(torrent_task)
            self.post_message(mtype=NotificationType.SiteMessage, title=title, text=msg_text)

    def __send_message(self, title: str, message: str):
        """发送消息"""
        if self._hnr_config.notify:
            self.post_message(mtype=NotificationType.Plugin, title=f"【{title}】", text=message)

    def __check_required_plugin_installed(self, plugin_id: str) -> (bool, str):
        """
        检查指定的依赖插件是否已安装
        """
        plugin_names = {
            "BrushFlow": "站点刷流",
            "BrushFlowLowFreq": "站点刷流（低频版）"
        }

        plugin_name = plugin_names.get(plugin_id, "未知插件")

        # 获取本地插件列表
        local_plugins = self.pluginmanager.get_local_plugins()

        # 检查指定的插件是否已启用
        plugin = next((p for p in local_plugins if p.id == plugin_id and p.installed), None)
        if not plugin:
            return False, f"{plugin_name}未安装"

        return True, f"{plugin_name}已安装"

    @staticmethod
    def __get_demo_config():
        """获取默认配置"""
        return """####### 配置说明 BEGIN #######
# 1. 此配置文件专门用于设定各站点的特定配置，包括做种时间、H&R激活状态等。
# 2. 配置项通过数组形式组织，每个站点的配置作为数组的一个元素，以‘-’标记开头。
# 3. 如果某站点的具体配置项与全局配置相同，则无需单独设置该项，默认采用全局配置。
####### 配置说明 END #######

- # 站点名称，用于标识适用于哪个站点
  site_name: '彩虹岛'
  # H&R时间（小时），站点默认的H&R时间，做种时间达到H&R时间后移除标签
  hr_duration: 120.0
  # 附加做种时间（小时），在H&R时间上额外增加的做种时长
  additional_seed_time: 24.0
  # 分享率，做种时期望达到的分享比例，达到目标分享率后移除标签
  # ratio: 2.0 （与全局配置保持一致，无需单独设置，注释处理）
  # H&R激活，站点是否已启用全站H&R，开启后所有种子均视为H&R种子
  hr_active: false

- # 站点名称，用于标识适用于哪个站点
  site_name: '皇后'
  # H&R时间（小时），站点默认的H&R时间，做种时间达到H&R时间后移除标签
  hr_duration: 36.0
  # 附加做种时间（小时），在H&R时间上额外增加的做种时长
  # additional_seed_time: 24.0 （与全局配置保持一致，无需单独设置，注释处理）
  # 分享率，做种时期望达到的分享比例，达到目标分享率后移除标签
  ratio: 2.0
  # H&R激活，站点是否已启用全站H&R，开启后所有种子均视为H&R种子
  hr_active: true"""

    @staticmethod
    def __random_even_scheduler(num_executions: int = 1,
                                begin_hour: int = 7,
                                end_hour: int = 23) -> List[datetime]:
        """
        按执行次数尽可能平均生成随机定时器
        :param num_executions: 执行次数
        :param begin_hour: 计划范围开始的小时数
        :param end_hour: 计划范围结束的小时数
        """
        trigger_times = []
        start_time = datetime.now().replace(hour=begin_hour, minute=0, second=0, microsecond=0)
        end_time = datetime.now().replace(hour=end_hour, minute=0, second=0, microsecond=0)

        # 计算范围内的总分钟数
        total_minutes = int((end_time - start_time).total_seconds() / 60)
        # 计算每个执行时间段的平均长度
        segment_length = total_minutes // num_executions

        for i in range(num_executions):
            # 在每个段内随机选择一个点
            start_segment = segment_length * i
            end_segment = start_segment + segment_length
            minute = random.randint(start_segment, end_segment - 1)
            trigger_time = start_time + timedelta(minutes=minute)
            trigger_times.append(trigger_time)

        return trigger_times
