import threading
import time
from dataclasses import fields
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional, Union, Type, TypeVar

import pytz
from app.helper.sites import SitesHelper
from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel

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
from app.plugins.hitandrun.helper import TorrentHelper, TimeHelper
from app.plugins.hitandrun.hnrconfig import HNRConfig, SiteConfig, NotifyMode
from app.schemas import NotificationType
from app.schemas.types import EventType
from app.utils.string import StringUtils

lock = threading.Lock()
T = TypeVar('T', bound=BaseModel)


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
    torrenthelper = None
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
        self.torrenthelper = TorrentHelper(self._downloader)

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
                                            'label': '站点H&R插件',
                                            'hint': '选择参与配置的H&R插件',
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
                                            'model': 'hr_ratio',
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
            "hr_ratio": 99,
            "hr_duration": 144,
            "hr_deadline_days": 14,
            "additional_seed_time": 24,
            "site_config_str": self.__get_demo_config()
        }

    def get_page(self) -> List[dict]:
        # 种子明细
        torrent_tasks: Dict[str, TorrentTask] = self.__get_and_parse_data(key="torrents", model=TorrentTask)

        if not torrent_tasks:
            return [
                {
                    'component': 'div',
                    'text': '暂无数据',
                    'props': {
                        'class': 'text-center',
                    }
                }
            ]
        else:
            data_list = list(torrent_tasks.values())
            # 按time倒序排序
            data_list = sorted(data_list, key=lambda x: x.time or 0, reverse=True)

        # 种子数据明细
        torrent_trs = []
        for data in data_list:
            site_config = self.__get_site_config(site_name=data.site_name)
            additional_seed_time = site_config.additional_seed_time or 0.0
            remain_time = data.remain_time(additional_seed_time=additional_seed_time)
            torrent_tr = {
                'component': 'tr',
                'props': {
                    'class': 'text-sm'
                },
                'content': [
                    {
                        'component': 'td',
                        'props': {
                            'class': 'whitespace-nowrap break-keep text-high-emphasis'
                        },
                        'text': data.site_name
                    },
                    {
                        'component': 'td',
                        'html': f'<span style="font-size: .85rem;">{data.title}</span>' +
                                (f'<br><span style="font-size: 0.75rem;">{data.description}</span>'
                                 if data.description else "")
                    },
                    {
                        'component': 'td',
                        'text': StringUtils.str_filesize(data.size)
                    },
                    {
                        'component': 'td',
                        'text': round(data.ratio or 0, 2)
                    },
                    {
                        'component': 'td',
                        'text': data.format_general(value=data.seeding_time / 3600)
                    },
                    {
                        'component': 'td',
                        'props': {
                            'class': 'whitespace-nowrap break-keep'
                        },
                        'text': data.format_general(value=remain_time)
                    },
                    {
                        'component': 'td',
                        'props': {
                            'class': 'whitespace-nowrap break-keep'
                        },
                        'text': data.format_duration(value=data.hr_duration,
                                                     additional_time=additional_seed_time)
                    },
                    {
                        'component': 'td',
                        'props': {
                            'class': 'whitespace-nowrap break-keep'
                        },
                        'text': data.hr_status.to_chinese()
                    },

                    {
                        'component': 'td',
                        'props': {
                            'class': 'text-no-wrap'
                        },
                        'text': "已删除" if data.deleted else "正常"
                    }
                ]
            }
            torrent_trs.append(torrent_tr)

        # 拼装页面
        return [
            {
                'component': 'VRow',
                'content': self.__get_total_elements() + [
                    # 种子明细
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 12,
                        },
                        'content': [
                            {
                                'component': 'VTable',
                                'props': {
                                    'hover': True
                                },
                                'content': [
                                    {
                                        'component': 'thead',
                                        'props': {
                                            'class': 'text-no-wrap'
                                        },
                                        'content': [
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '站点'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '标题'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '大小'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '分享率'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '做种时间'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '剩余时间'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': 'H&R时间'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '进度'
                                            },
                                            {
                                                'component': 'th',
                                                'props': {
                                                    'class': 'text-start ps-4'
                                                },
                                                'text': '状态'
                                            }
                                        ]
                                    },
                                    {
                                        'component': 'tbody',
                                        'content': torrent_trs
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def __get_total_elements(self) -> List[dict]:
        """
        组装汇总元素
        """
        # 获取统计数据
        statistic_info = self.__get_data(key="statistic")
        # 任务总数
        total_count = statistic_info.get("total_count") or "N/A"
        # # 待确认
        # pending_count = statistic_info.get("pending") or "N/A"
        # 进行中
        in_progress_count = statistic_info.get("in_progress") or "N/A"
        # 已满足
        compliant_count = statistic_info.get("compliant") or "N/A"
        # 已删除
        deleted_count = statistic_info.get("deleted") or "N/A"
        # # 其他
        # other_count = statistic_info.get("other") or "N/A"

        return [
            self.__create_stat_card("任务数", "/plugin_icon/seed.png", str(total_count)),
            self.__create_stat_card("进行中", "/plugin_icon/upload.png", str(in_progress_count)),
            self.__create_stat_card("已满足", "/plugin_icon/Overleaf_A.png", str(compliant_count)),
            self.__create_stat_card("已删除", "/plugin_icon/delete.png", str(deleted_count))
        ]

    @staticmethod
    def __create_stat_card(title: str, icon_path: str, count: str):
        """
        创建一个统计卡片组件
        """
        return {
            'component': 'VCol',
            'props': {
                'cols': 12,
                'md': 3,
                'sm': 6
            },
            'content': [
                {
                    'component': 'VCard',
                    'props': {
                        'variant': 'tonal',
                    },
                    'content': [
                        {
                            'component': 'VCardText',
                            'props': {
                                'class': 'd-flex align-center',
                            },
                            'content': [
                                {
                                    'component': 'VAvatar',
                                    'props': {
                                        'rounded': True,
                                        'variant': 'text',
                                        'class': 'me-3'
                                    },
                                    'content': [
                                        {
                                            'component': 'VImg',
                                            'props': {
                                                'src': icon_path
                                            }
                                        }
                                    ]
                                },
                                {
                                    'component': 'div',
                                    'content': [
                                        {
                                            'component': 'span',
                                            'props': {
                                                'class': 'text-caption'
                                            },
                                            'text': title
                                        },
                                        {
                                            'component': 'div',
                                            'props': {
                                                'class': 'd-flex align-center flex-wrap'
                                            },
                                            'content': [
                                                {
                                                    'component': 'span',
                                                    'props': {
                                                        'class': 'text-h6'
                                                    },
                                                    'text': count
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
                triggers = TimeHelper.random_even_scheduler(num_executions=4,
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

    # region Check

    def check(self):
        """
        检查服务
        """
        if not self._downloader:
            return

        with lock:
            logger.info("开始检查H&R下载任务 ...")
            torrent_tasks = self.__get_and_parse_data(key="torrents", model=TorrentTask)
            unmanaged_tasks = self.__get_and_parse_data(key="unmanaged", model=TorrentTask)
            histories = self.__get_and_parse_data(key="downloads", model=TorrentHistory)

            seeding_torrents = self.torrenthelper.get_torrents()
            seeding_torrents_dict = {
                self.torrenthelper.get_torrent_hashes(torrents=torrent):
                    torrent for torrent in seeding_torrents}

            # 检查种子标签变更情况
            self.__update_seeding_tasks_based_on_tags(torrent_tasks=torrent_tasks,
                                                      unmanaged_tasks=unmanaged_tasks,
                                                      histories=histories,
                                                      seeding_torrents_dict=seeding_torrents_dict)

            torrent_check_hashes = list(torrent_tasks.keys())
            if not torrent_tasks or not torrent_check_hashes:
                logger.info("没有需要检查的H&R下载任务")
                return

            logger.info(f"共有 {len(torrent_check_hashes)} 个任务正在H&R，开始检查任务状态")

            # 获取到当前所有做种数据中需要被检查的种子数据
            check_torrents = [seeding_torrents_dict[th] for th in torrent_check_hashes if th in seeding_torrents_dict]

            # 更新H&R任务列表中在下载器中删除的种子为删除状态
            self.__update_undeleted_torrents_missing_in_downloader(torrent_tasks, torrent_check_hashes, check_torrents)

            # 先更新H&R任务的最新状态，上下传，分享率，做种时间等
            self.__update_torrent_tasks_state(torrents=check_torrents, torrent_tasks=torrent_tasks)

            # 更新H&R状态
            for torrent_task in torrent_tasks.values():
                try:
                    self.__update_hr_status(torrent_task=torrent_task)
                except Exception as e:
                    logger.error(f"更新H&R下载任务状态过程中出现异常，{e}")

            # 更新统计数据
            self.__update_and_save_statistic_info(torrent_tasks)

            # 更新H&R任务
            self.__save_data(key="torrents", value=torrent_tasks)

            logger.info("H&R下载任务检查完成")

    def __update_torrent_tasks_state(self, torrents: List[Any], torrent_tasks: Dict[str, TorrentTask]):
        """
        更新H&R任务的最新状态，上下传，分享率，做种时间等
        """
        for torrent in torrents:
            torrent_hash = self.torrenthelper.get_torrent_hashes(torrents=torrent)
            torrent_task = torrent_tasks.get(torrent_hash, None)
            # 如果找不到种子任务，说明不在管理的种子范围内，直接跳过
            if not torrent_task:
                continue

            torrent_info = self.torrenthelper.get_torrent_info(torrent=torrent)

            # 更新上传量、下载量、分享率、做种时间
            torrent_task.downloaded = torrent_info.get("downloaded", 0)
            torrent_task.uploaded = torrent_info.get("uploaded", 0)
            torrent_task.ratio = torrent_info.get("ratio", 0.0)
            torrent_task.seeding_time = torrent_info.get("seeding_time", 0)

    def __update_seeding_tasks_based_on_tags(self, torrent_tasks: Dict[str, TorrentTask],
                                             unmanaged_tasks: Dict[str, TorrentTask],
                                             histories: Dict[str, TorrentHistory],
                                             seeding_torrents_dict: Dict[str, Any]):
        if not self._hnr_config.downloader == "qbittorrent":
            logger.info("同步H&R种子标签记录目前仅支持qbittorrent")
            return

        # 初始化汇总信息
        added_tasks = []
        reset_tasks = []
        removed_tasks = []
        # 基于 seeding_torrents_dict 的信息更新或添加到 torrent_tasks
        for torrent_hash, torrent in seeding_torrents_dict.items():
            tags = self.torrenthelper.get_torrent_tags(torrent=torrent)
            # 判断是否包含H&R标签
            if self._hnr_config.hit_and_run_tag in tags:
                # 如果包含H&R标签又不在H&R任务中，则需要加入管理
                if torrent_hash not in torrent_tasks:
                    # 检查该种子是否在 unmanaged_tasks 中
                    if torrent_hash in unmanaged_tasks:
                        # 如果在 unmanaged_tasks 中，移除并转移到 torrent_tasks
                        torrent_task = unmanaged_tasks.pop(torrent_hash)
                        torrent_tasks[torrent_hash] = torrent_task
                        added_tasks.append(torrent_task)
                        logger.info(f"站点 {torrent_task.site_name}，"
                                    f"H&R种子任务再次加入：{torrent_task.identifier}")
                    else:
                        # 否则，创建一个新的任务
                        torrent_task = self.__convert_torrent_info_to_task(torrent=torrent, histories=histories)
                        torrent_tasks[torrent_hash] = torrent_task
                        added_tasks.append(torrent_task)
                        logger.info(f"站点 {torrent_task.site_name}，"
                                    f"H&R种子任务加入：{torrent_task.identifier}")
                # 包含H&R标签又在H&R任务中，这里额外处理一个特殊逻辑，就是种子在H&R任务中可能被标记删除但实际上又还在下载器中，这里进行重置
                else:
                    torrent_task = torrent_tasks[torrent_hash]
                    if torrent_task.deleted:
                        torrent_task.deleted = False
                        reset_tasks.append(torrent_task)
                        logger.info(
                            f"站点 {torrent_task.site_name}，在下载器中找到已标记删除的H&R任务对应的种子信息，"
                            f"更新H&R任务状态为正常：{torrent_task.identifier}")
            else:
                # 不包含H&R标签但又在H&R任务中，则移除管理
                if torrent_hash in torrent_tasks:
                    # 如果种子不符合H&R条件但在 torrent_tasks 中，移除并加入 unmanaged_tasks
                    torrent_task = torrent_tasks.pop(torrent_hash)
                    unmanaged_tasks[torrent_hash] = torrent_task
                    removed_tasks.append(torrent_task)
                    logger.info(f"站点 {torrent_task.site_name}，"
                                f"H&R种子任务移除：{torrent_task.identifier}")

        self.__save_data(key="torrents", value=torrent_tasks)
        self.__save_data(key="unmanaged", value=unmanaged_tasks)

        # 发送汇总消息
        if added_tasks:
            self.__log_and_send_torrent_task_update_message(title="【H&R种子任务加入】", status="纳入H&R管理",
                                                            reason="H&R标签添加", torrent_tasks=added_tasks)
        if removed_tasks:
            self.__log_and_send_torrent_task_update_message(title="【H&R种子任务移除】", status="移除H&R管理",
                                                            reason="H&R标签移除", torrent_tasks=removed_tasks)
        if reset_tasks:
            self.__log_and_send_torrent_task_update_message(title="【H&R任务状态更新】", status="更新H&R状态为正常",
                                                            reason="在下载器中找到已标记删除的H&R任务对应的种子信息",
                                                            torrent_tasks=reset_tasks)

    def __update_undeleted_torrents_missing_in_downloader(self, torrent_tasks: Dict[str, TorrentTask],
                                                          torrent_check_hashes: List[str], torrents: List[Any]):
        """
        处理已经被删除，但是任务记录中还没有被标记删除的种子
        """
        # 先通过获取的全量种子，判断已经被删除，但是任务记录中还没有被标记删除的种子
        torrent_all_hashes = self.torrenthelper.get_torrent_hashes(torrents=torrents)
        missing_hashes = [hash_value for hash_value in torrent_check_hashes if hash_value not in torrent_all_hashes]
        undeleted_hashes = [hash_value for hash_value in missing_hashes if not torrent_tasks[hash_value].deleted]

        if not undeleted_hashes:
            return

        # 初始化汇总信息
        delete_tasks = []
        for hash_value in undeleted_hashes:
            # 获取对应的任务信息
            torrent_task = torrent_tasks[hash_value]
            # 标记为已删除
            torrent_task.deleted = True
            # 处理日志相关内容
            delete_tasks.append(torrent_task)
            site_name = torrent_task.site_name
            torrent_title = torrent_task.title
            torrent_desc = torrent_task.description
            logger.info(
                f"站点：{site_name}，无法在下载器中找到对应种子信息，更新H&R任务状态为已删除，种子：{torrent_title}|{torrent_desc}")

        self.__log_and_send_torrent_task_update_message(title="【H&R任务状态更新】", status="更新H&R状态为已删除",
                                                        reason="无法在下载器中找到对应的种子信息",
                                                        torrent_tasks=delete_tasks)

    def __update_and_save_statistic_info(self, torrent_tasks: Dict[str, TorrentTask]):
        """
        更新并保存统计信息
        """
        total_count, pending_count, in_progress_count, compliant_count, deleted_count, other_count = 0, 0, 0, 0, 0, 0

        statistic_info = self.__get_data(key="statistic")
        archived_tasks = self.__get_and_parse_data(key="archived", model=TorrentTask)
        combined_tasks = {**torrent_tasks, **archived_tasks}

        for task in combined_tasks.values():
            if task.deleted:
                deleted_count += 1

            if task.hit_and_run:
                total_count += 1
                if task.hr_status == HNRStatus.PENDING:
                    pending_count += 1
                elif task.hr_status == HNRStatus.IN_PROGRESS:
                    in_progress_count += 1
                elif task.hr_status == HNRStatus.COMPLIANT:
                    compliant_count += 1
                else:
                    other_count += 1

        # 更新统计信息
        statistic_info.update({
            "total_count": total_count,
            "pending": pending_count,
            "in_progress": in_progress_count,
            "compliant": compliant_count,
            "deleted": deleted_count,
            "other": other_count
        })

        logger.info(f"H&R任务统计数据，总任务数：{total_count}，待确认：{pending_count}，"
                    f"进行中：{in_progress_count}，已满足：{compliant_count}，已删除：{deleted_count}，其他：{other_count}")

        self.__save_data(key="statistic", value=statistic_info)

    # endregion

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
        处理H&R下载任务事件
        """
        if not self.__validate_and_log_event(event,
                                             event_type_desc="H&R下载任务",
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

            torrent = self.torrenthelper.get_torrents(torrent_hashes=torrent_hash)
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

        self.__init_hr_status(torrent_task=torrent_task)

        if not torrent_task.hit_and_run:
            logger.info(f"站点 {torrent_task.site_name}，种子 {torrent_task.identifier} 没有激活H&R，跳过处理")
            return

        self.__save_torrent_tasks(torrent_tasks=torrent_task)
        self.__set_hit_and_run_tag(torrent_task=torrent_task)

        self.__send_hr_message(torrent_task=torrent_task, title="【H&R种子任务下载】")

    def __update_hr_status(self, torrent_task: TorrentTask):
        """
        更新H&R状态
        """
        if not torrent_task.hit_and_run:
            return

        site_config = self.__get_site_config(site_name=torrent_task.site_name)
        additional_seed_time = site_config.additional_seed_time or 0
        required_seeding_time = (torrent_task.hr_duration + additional_seed_time)

        # 更新种子状态和记录日志
        meets_requirements = self.__meets_hr_requirements(
            torrent_task=torrent_task,
            additional_seed_time=additional_seed_time,
            required_ratio=site_config.hr_ratio
        )

        if meets_requirements:
            torrent_task.hr_status = HNRStatus.COMPLIANT
            self.__remove_hit_and_run_tag(torrent_task)
            self.__send_hr_message(torrent_task=torrent_task, title="【H&R种子任务已完成】")

        status_description = "已满足" if meets_requirements else "仍未满足"
        logger.info(
            f"种子 {torrent_task.identifier} {status_description} H&R 要求，"
            f"做种时间: {self.__format_hour(torrent_task.seeding_time)} 小时，"
            f"所需做种时间: {self.__format_hour(required_seeding_time, 'hour')} 小时，"
            f"所需分享率: {torrent_task.ratio:.1f}")

    @staticmethod
    def __meets_hr_requirements(torrent_task: TorrentTask, additional_seed_time: float, required_ratio: float) -> bool:
        """
        检查是否满足做种时间和分享率要求
        """
        seeding_time_ok = (torrent_task.seeding_time and torrent_task.hr_duration and
                           torrent_task.seeding_time > (torrent_task.hr_duration + additional_seed_time) * 3600)
        ratio_ok = torrent_task.ratio and torrent_task.ratio > required_ratio
        return seeding_time_ok or ratio_ok

    def __init_hr_status(self, torrent_task: TorrentTask):
        """
        初始化H&R状态
        """
        site_config = self.__get_site_config(site_name=torrent_task.site_name)

        # 如果站点已经激活全局H&R，则强制标识为H&R种子
        if site_config.hr_active:
            torrent_task.hit_and_run = True

        if torrent_task.hit_and_run:
            torrent_task.hr_ratio = site_config.hr_ratio
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
        self.__save_data(key="torrents", value=existing_torrent_tasks)

    def __update_hit_and_run_tag(self, torrent_task: TorrentTask, add: bool):
        """
        更新H&R标签
        :param torrent_task: 包含种子信息的 TorrentTask 实例
        :param add: 如果为 True，则添加 H&R 标签；否则移除 H&R 标签
        """
        if not torrent_task or not torrent_task.hash:
            return

        if not torrent_task.hit_and_run:
            return

        torrent = self.torrenthelper.get_torrents(torrent_hashes=torrent_task.hash)
        if not torrent:
            logger.warn(f"下载器中没有获取到 torrent_hash: {torrent_task.hash} 的种子信息")
            return

        try:
            tags = self.torrenthelper.get_torrent_tags(torrent=torrent)
            hnr_tag = self._hnr_config.hit_and_run_tag
            if add:
                if hnr_tag not in tags:
                    tags.append(hnr_tag)
                    self.torrenthelper.set_torrent_tag(torrent_hash=torrent_task.hash, tags=tags)
            else:
                if hnr_tag in tags:
                    tags.remove(hnr_tag)
                    self.torrenthelper.remove_torrent_tag(torrent_hash=torrent_task.hash, tags=[hnr_tag])
        except Exception as e:
            action = "添加" if add else "移除"
            logger.error(f"{action}标签时出错：{str(e)}")

    def __set_hit_and_run_tag(self, torrent_task: TorrentTask):
        """
        设置H&R标签
        :param torrent_task: 包含种子信息的 TorrentTask 实例
        """
        self.__update_hit_and_run_tag(torrent_task, add=True)

    def __remove_hit_and_run_tag(self, torrent_task: TorrentTask):
        """
        移除H&R标签
        :param torrent_task: 包含种子信息的 TorrentTask 实例
        """
        self.__update_hit_and_run_tag(torrent_task, add=False)

    def __save_and_cleanup_downloads(self, torrent_hash: str, torrent_data: Union[dict, TorrentInfo],
                                     task_type: TaskType = TaskType.NORMAL) -> Optional[TorrentHistory]:
        """
        保存下载记录并清理30天前的记录
        """
        torrent_history = self.__create_torrent_history(torrent_hash=torrent_hash,
                                                        torrent_data=torrent_data,
                                                        task_type=task_type)

        downloads: Dict[str, dict] = self.__get_data(key="downloads")

        # 添加新的下载记录
        downloads[torrent_hash] = torrent_history.to_dict()

        # 获取当前时间和30天前的时间戳
        current_time = time.time()
        cutoff_time = current_time - 30 * 24 * 60 * 60

        # 清理7天以前的下载记录
        downloads = {key: value for key, value in downloads.items() if value.get("time", current_time) > cutoff_time}

        # 保存更新后的下载记录
        self.__save_data(key="downloads", value=downloads)

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

    def __convert_torrent_info_to_task(self, torrent: Any, histories: Dict[str, TorrentHistory]) \
            -> Optional[TorrentTask]:
        """
        根据提供的 torrent 和历史数据将 torrent 信息转换成 torrent 任务
        """
        torrent_info = self.torrenthelper.get_torrent_info(torrent=torrent)
        torrent_hash = torrent_info.get("hash", "")
        if not torrent_hash:
            return None

        torrent_history = histories.get(torrent_hash)
        if torrent_history:
            torrent_task = TorrentTask.parse_obj(torrent_history.to_dict())
        else:
            site_id, site_name = self.torrenthelper.get_site_by_torrent(torrent=torrent)
            if not site_name:
                return None
            torrent_task = TorrentTask.parse_obj({
                "site": site_id,
                "site_name": site_name,
                "hash": torrent_info.get("hash", ""),
                "title": torrent_info.get("title", ""),
                "size": torrent_info.get("total_size", 0),
                # "pubdate": None,
                # "description": None,
                # "page_url": None,
                # "ratio": torrent_info.get("ratio", 0),
                # "downloaded": torrent_info.get("downloaded", 0),
                # "uploaded": torrent_info.get("uploaded", 0),
                # "seeding_time": torrent_info.get("seeding_time", 0),
                "time": torrent_info.get("add_on", time.time()),
                "hit_and_run": True,
                "deleted": False,
                "task_type": TaskType.NORMAL
            })

        if not torrent_task:
            return None

        torrent_task.hit_and_run = True
        self.__init_hr_status(torrent_task=torrent_task)
        return torrent_task

    def __get_site_config(self, site_name: str) -> Optional[SiteConfig]:
        """"获取站点配置"""
        if not self._hnr_config:
            return None
        return self._hnr_config.get_site_config(site_name=site_name)

    def __get_and_parse_data(self, key: str, model: Type[T]) -> Dict[str, T]:
        """
        获取插件数据
        """
        if not key:
            return {}

        raw_data: Dict[str, dict] = self.__get_data(key=key)
        return {k: model.parse_obj(v) for k, v in raw_data.items()}

    def __get_data(self, key: str):
        """获取插件数据"""
        if not key:
            return {}

        return self.get_data(key=key) or {}

    def __save_data(self, key: str, value: Any):
        """保存插件数据"""
        if not key:
            return

        self.save_data(key=key, value=value)

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

        if config.hr_ratio <= 0:
            return False, "H&R分享率必须大于0"

        return True, "所有配置项都有效"

    def __validate_and_fix_config(self, config: dict = None) -> [bool, str]:
        """
        检查并修正配置值
        """
        if not config:
            return False, ""

        try:
            hnr_config = HNRConfig.parse_obj(obj=config)

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
        excludes = {"check_period", "site_infos", "site_configs"}
        config_mapping = self._hnr_config.to_dict(exclude=excludes)
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

    def __build_hr_message_text(self, torrent_task: TorrentTask):
        """
        构建关于 H&R 事件的消息文本
        """

        def format_comparison(actual, required, unit):
            comparison = "大于" if actual >= required else "小于"
            return f"{actual:.1f} {unit}，{comparison} {required:.1f} {unit}"

        site_config = self.__get_site_config(site_name=torrent_task.site_name)
        additional_seed_time = site_config.additional_seed_time or 0

        msg_parts = []

        if torrent_task.hr_status == HNRStatus.COMPLIANT:
            seeding_hours = torrent_task.seeding_time / 3600
            required_seeding_hours = (torrent_task.hr_duration + additional_seed_time)
            required_ratio = site_config.hr_ratio

            label_mapping = {
                "site_name": ("站点", str),
                "task_type": ("类型", TorrentTask.format_to_chinese),
                "title": ("标题", str),
                "description": ("描述", str),
                "seeding_time": (
                    "做种时间", lambda x: format_comparison(seeding_hours, required_seeding_hours, "小时")),
                "ratio": ("分享率", lambda x: format_comparison(x, required_ratio, "")),
                "hr_status": ("状态", TorrentTask.format_to_chinese),
            }
        else:
            label_mapping = {
                "site_name": ("站点", str),
                "task_type": ("类型", TorrentTask.format_to_chinese),
                "title": ("标题", str),
                "description": ("描述", str),
                "size": ("大小", TorrentTask.format_size),
                "hr_duration": ("时间",
                                lambda x: TorrentTask.format_duration(value=x,
                                                                      additional_time=additional_seed_time,
                                                                      suffix=" 小时")),
                "hr_deadline_days": ("期限", lambda x: TorrentTask.format_general(value=x, suffix=" 天")),
                "hr_status": ("状态", TorrentTask.format_to_chinese),
            }

        for key, (label, formatter) in label_mapping.items():
            value = getattr(torrent_task, key, None)
            if value is not None:
                formatted_value = formatter(value)
                if formatted_value:
                    msg_parts.append(f"{label}：{formatted_value}")

        return "\n".join(msg_parts)

    def __send_hr_message(self, torrent_task, title: str):
        """
        发送命中 H&R 种子消息
        """
        if self._hnr_config.notify == NotifyMode.ALWAYS:
            msg_text = self.__build_hr_message_text(torrent_task)
            self.post_message(mtype=NotificationType.SiteMessage, title=title, text=msg_text)

    def __log_and_send_torrent_task_update_message(self, title: str, status: str, reason: str,
                                                   torrent_tasks: List[TorrentTask]):
        """
        记录和发送任务更新消息
        """
        if self._hnr_config.notify == NotifyMode.ALWAYS and torrent_tasks:
            sites_names = ', '.join({task.site_name or "N/A" for task in torrent_tasks})
            first_title = torrent_tasks[0].title or "N/A"
            count = len(torrent_tasks)
            msg = f"站点：{sites_names}\n内容：{first_title} 等 {count} 个种子已经{status}\n原因：{reason}"
            logger.info(f"{title}，{msg}")
            self.__send_message(title=title, message=msg)

    def __send_message(self, title: str, message: str):
        """发送消息"""
        self.post_message(mtype=NotificationType.Plugin, title=f"【{title}】", text=message)

    @staticmethod
    def __format_hour(number: float, unit: str = "second") -> str:
        """
        格式化数字，限制小数点后一位
        """
        if unit == "second":
            return f"{number / 3600:.1f}"
        elif unit == "minute":
            return f"{number / 60:.1f}"
        elif unit == "hour":
            return f"{number:.1f}"
        return ""

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
  # hr_ratio: 2.0 （与全局配置保持一致，无需单独设置，注释处理）
  # H&R激活，站点是否已启用全站H&R，开启后所有种子均视为H&R种子
  hr_active: false

- # 站点名称，用于标识适用于哪个站点
  site_name: '皇后'
  # H&R时间（小时），站点默认的H&R时间，做种时间达到H&R时间后移除标签
  hr_duration: 36.0
  # 附加做种时间（小时），在H&R时间上额外增加的做种时长
  # additional_seed_time: 24.0 （与全局配置保持一致，无需单独设置，注释处理）
  # 分享率，做种时期望达到的分享比例，达到目标分享率后移除标签
  hr_ratio: 2.0
  # H&R激活，站点是否已启用全站H&R，开启后所有种子均视为H&R种子
  hr_active: true"""
