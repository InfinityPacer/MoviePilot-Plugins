import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from app.core.context import MediaInfo
from app.core.event import eventmanager, Event
from app.db.downloadhistory_oper import DownloadHistoryOper
from app.db.subscribe_oper import SubscribeOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.event import ResourceSelectionEventData, ResourceDownloadEventData
from app.schemas.types import EventType, ChainEventType, MediaType

lock = threading.Lock()


class SubscribeAssistant(_PluginBase):
    # 插件名称
    plugin_name = "订阅助手"
    # 插件描述
    plugin_desc = "实现多场景管理系统订阅与状态同步。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/subscribeassistant.png"
    # 插件版本
    plugin_version = "1.0"
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
    # 洗版类型
    _auto_best_type = "no"
    # 洗版次数
    _auto_best_count = 1

    # endregion

    def init_plugin(self, config: dict = None):
        self.downloadhistory_oper = DownloadHistoryOper()
        self.subscribe_oper = SubscribeOper()
        if not config:
            return

        self._enabled = config.get("enabled", False)
        self._notify = config.get("notify", False)
        self._onlyonce = config.get("onlyonce", False)
        self._auto_delete = config.get("auto_delete", True)
        self._auto_completion_search = config.get("auto_completion_search", True)
        self._delete_exclude_tags = config.get("delete_exclude_tags", "H&R")
        self._auto_tv_pending = config.get("auto_tv_pending", True)
        self._auto_download_pending = config.get("auto_download_pending", True)
        self._auto_best_type = config.get("auto_best_type", "no")
        self._delete_timeout = self.__get_int_config(config, "delete_timeout", 3)
        self._auto_tv_pending_days = self.__get_int_config(config, "auto_tv_pending_days", 14)
        self._auto_best_count = self.__get_int_config(config, "auto_best_count", 1)

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
                                                            'label': '超时删除时间',
                                                            'type': 'number',
                                                            "min": "0",
                                                            'hint': '下载超时后的删除时间（小时）',
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
                                                            'model': 'auto_tv_pending',
                                                            'label': '自动待定最近上线剧集订阅',
                                                            'hint': '订阅新上线剧集时，自动标记为待定状态，避免提前完成订阅',
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
                                                            'model': 'auto_download_pending',
                                                            'label': '订阅下载时自动待定',
                                                            'hint': '订阅下载时，自动标记为待定状态，避免提前完成订阅',
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
                    }
                ]
            }
        ], {
            "enabled": False,
            "auto_delete": True,
            "auto_completion_search": True,
            "delete_timeout": 3,
            "delete_exclude_tags": "H&R",
            "auto_tv_pending": True,
            "auto_download_pending": True,
            "auto_tv_pending_days": 14,
            "auto_best_type": "no",
            "auto_best_count": 1
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
        if not self._enabled or not self._auto_delete:
            return []

        services = [{
            "id": f"{self.__class__.__name__}_AutoCheck",
            "name": f"下载超时检查",
            "trigger": "interval",
            "func": self.auto_delete_check,
            "kwargs": {"minutes": 5}
        }]
        return services

    def stop_service(self):
        """
        退出插件
        """
        pass

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
            "auto_delete": self._auto_delete,
            "auto_completion_search": self._auto_completion_search,
            "delete_exclude_tags": self._delete_exclude_tags,
            "auto_tv_pending": self._auto_tv_pending,
            "auto_download_pending": self._auto_download_pending,
            "auto_best_type": self._auto_best_type,
            "delete_timeout": self._delete_timeout,
            "auto_tv_pending_days": self._auto_tv_pending_days,
            "auto_best_count": self._auto_best_count,
        }
        self.update_config(config=config)

    def auto_delete_check(self):
        """
        下载超时自动删除检查
        """
        pass

    def auto_pending_check(self):
        """
        自动待定检查
        """
        pass

    def auto_best_version_check(self):
        """
        自动洗版检查
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

            if not sub_id or not mediainfo_dict:
                # 缺少订阅 ID 或媒体信息
                logger.warning(f"订阅事件数据缺失，跳过处理。订阅 ID: {sub_id}, 媒体信息: {mediainfo_dict}")
                return

            logger.debug(f"接收到订阅添加事件，来自用户: {username}, 订阅 ID: {sub_id}, 数据: {mediainfo_dict}")

            # 获取订阅信息和媒体信息
            subscribe = self.subscribe_oper.get(sub_id)
            mediainfo = MediaInfo().from_dict(mediainfo_dict)

            # 订阅或媒体信息获取失败
            if not subscribe or not mediainfo:
                logger.error(f"订阅 ID {sub_id} 的订阅信息获取失败，媒体标题: {mediainfo_dict.get('title_year')}")
                return

            # 检查订阅状态是否可处理
            if subscribe.state not in ["N", "R"]:
                logger.debug(f"媒体标题 {mediainfo.title_year}（{sub_id}）当前状态为 {subscribe.state}，"
                             f"状态不允许处理，跳过逻辑")
                return

            # 检查媒体类型是否为 TV
            if mediainfo.type != MediaType.TV:
                logger.debug(f"媒体标题 {mediainfo.title_year}（{sub_id}）类型为 {mediainfo.type}，非 TV 类型，跳过处理")
                return

            # 检查季信息是否存在
            if not mediainfo.season_info:
                logger.warning(f"媒体标题 {mediainfo.title_year} 的 season_info 为空，跳过处理")
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
                logger.warning(f"媒体标题 {mediainfo.title} 未找到与订阅季数 {season} 对应的 air_date，跳过处理")
                return

            # 解析上线日期
            try:
                air_date = datetime.strptime(air_day, "%Y-%m-%d")
            except ValueError:
                # 首播日期格式错误
                logger.error(f"媒体标题 {mediainfo.title} 的 air_date 格式错误：{air_day}，跳过处理")
                return

            # 判断是否符合 auto_tv_pending_days 的要求
            pending_date = air_date + timedelta(days=self._auto_tv_pending_days)
            current_date = datetime.now()

            if pending_date <= current_date:
                # 不符合待定条件
                logger.debug(f"媒体标题 {mediainfo.title_year}（{sub_id}），季数 {season} 不符合待定条件，"
                             f"上线日期+待定天数: {pending_date}, 当前日期: {current_date}，忽略处理")
            else:
                # 符合待定条件，更新订阅状态为 "P"
                logger.info(f"媒体标题 {mediainfo.title_year}（{sub_id}），季数 {season} 符合待定条件，更新订阅状态为 'P'")
                self.subscribe_oper.update(subscribe.id, {"state": "P"})
        except Exception as e:
            # 捕获所有异常并记录错误日志
            logger.exception(f"处理订阅添加事件时发生错误: {str(e)}")

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
