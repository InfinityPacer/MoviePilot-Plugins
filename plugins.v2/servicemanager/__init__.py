import threading
from typing import Any, Dict, List, Tuple

from apscheduler.triggers.cron import CronTrigger

from app.chain.site import SiteChain
from app.chain.subscribe import SubscribeChain
from app.chain.tmdb import TmdbChain
from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.scheduler import Scheduler

lock = threading.Lock()


class ServiceManager(_PluginBase):
    # 插件名称
    plugin_name = "服务管理"
    # 插件描述
    plugin_desc = "实现自定义服务管理。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/servicemanager.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "servicemanager_"
    # 加载顺序
    plugin_order = 29
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    # 是否开启
    _enabled = False
    # 恢复默认并停用
    _reset_and_disable = False
    # 站点数据刷新（cron 表达式）
    _sitedata_refresh = ""
    # 订阅搜索补全（cron 表达式）
    _subscribe_search = ""
    # 缓存清理（cron 表达式）
    _clear_cache = ""
    # 壁纸缓存（cron 表达式
    _random_wallpager = ""

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self._enabled = config.get("enabled", False)
        self._reset_and_disable = config.get("reset_and_disable", False)
        self._sitedata_refresh = config.get("sitedata_refresh")
        self._subscribe_search = config.get("subscribe_search")
        self._clear_cache = config.get("clear_cache")
        self._random_wallpager = config.get("random_wallpager")

        if self._reset_and_disable:
            self._enabled = False
            self._reset_and_disable = False
            config["enabled"] = False
            config["reset_and_disable"] = False
            self.update_config(config=config)
            Scheduler().init()
            logger.info("已恢复默认配置并停用插件")

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
                                    'md': 6
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
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'reset_and_disable',
                                            'label': '恢复默认并停用',
                                            'hint': '启用此选项将恢复默认配置并停用插件',
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
                                            'model': 'sitedata_refresh',
                                            'label': '站点数据刷新',
                                            'placeholder': '5位cron表达式',
                                            'hint': '设置站点数据刷新的周期，如 0 8 * * * 表示每天 8:00',
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
                                            'model': 'subscribe_search',
                                            'label': '订阅搜索补全',
                                            'placeholder': '5位cron表达式',
                                            'hint': '设置订阅搜索补全的周期，如 0 12 * * * 表示每天中午 12:00',
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
                                            'model': 'clear_cache',
                                            'label': '缓存清理',
                                            'placeholder': '5位cron表达式',
                                            'hint': '设置缓存清理任务的周期，如 0 3 * * * 表示每天凌晨 3:00',
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
                                            'model': 'random_wallpager',
                                            'label': '壁纸缓存',
                                            'placeholder': '5位cron表达式',
                                            'hint': '设置壁纸缓存更新的周期，如 0 6 * * * 表示每天早晨 6:00',
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
                                            'variant': 'tonal',
                                            'text': '注意：启用本插件后，默认的系统服务将失效，仅以本插件设置为准'
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
                                            'text': '注意：系统服务正在运行时，请慎重启停用，否则可能导致死锁等一系列问题'
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
            "reset_and_disable": False
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
            "kwargs": {} # 定时器参数,
            "func_kwargs": {} # 方法参数
        }]
        """
        if not self._enabled:
            return []

        services = []
        if self._sitedata_refresh:
            services.append({
                "id": "sitedata_refresh",
                "name": "站点数据刷新",
                "trigger": CronTrigger.from_crontab(self._sitedata_refresh),
                "func": SiteChain().refresh_userdatas
            })

        # 订阅搜索补全服务
        if settings.SUBSCRIBE_SEARCH and self._subscribe_search:
            services.append({
                "id": "subscribe_search",
                "name": "订阅搜索补全",
                "trigger": CronTrigger.from_crontab(self._subscribe_search),
                "func": SubscribeChain().search,
                "func_kwargs": {
                    "state": "R"
                }
            })

        # 缓存清理服务
        if self._clear_cache:
            services.append({
                "id": "clear_cache",
                "name": "缓存清理",
                "trigger": CronTrigger.from_crontab(self._clear_cache),
                "func": Scheduler().clear_cache
            })

        # 壁纸缓存更新服务
        if self._random_wallpager:
            services.append({
                "id": "random_wallpager",
                "name": "壁纸缓存",
                "trigger": CronTrigger.from_crontab(self._random_wallpager),
                "func": TmdbChain().get_trending_wallpapers
            })

        return services

    def stop_service(self):
        """
        退出插件
        """
        pass
