import copy
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional

import plexapi
import plexapi.utils
import pypinyin
import pytz
import zhconv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from plexapi.library import LibrarySection

from app.chain.mediaserver import MediaServerChain
from app.chain.tmdb import TmdbChain
from app.core.config import settings
from app.core.context import MediaInfo
from app.core.event import eventmanager, Event
from app.core.meta import MetaBase
from app.log import logger
from app.modules.plex import Plex
from app.plugins import _PluginBase
from app.plugins.plexpersonmeta.helper import RatingInfo, cache_with_logging, tmdb_media_cache, douban_media_cache, \
    tmdb_person_cache
from app.schemas import MediaPerson
from app.schemas.types import EventType, MediaType, NotificationType
from app.utils.string import StringUtils

lock = threading.Lock()


class PlexPersonMeta(_PluginBase):
    # 插件名称
    plugin_name = "Plex演职人员刮削"
    # 插件描述
    plugin_desc = "实现刮削演职人员中文名称及角色。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/plexpersonmeta.png"
    # 插件版本
    plugin_version = "1.2"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexpersonmeta_"
    # 加载顺序
    plugin_order = 91
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    # tmdb_chain
    tmdbchain = None
    # media_server_chain
    mschain = None

    # Plex
    _plex = None
    # plex_server
    _plex_server = None
    # 是否开启
    _enabled = False
    # 立即运行一次
    _onlyonce = False
    # 任务执行间隔
    _cron = None
    # 发送通知
    _notify = False
    # 需要处理的媒体库
    _library_ids = None
    # 锁定元数据
    _lock = None
    # 入库后运行一次
    _execute_transfer = None
    # 入库后延迟执行时间
    _delay = None
    # 刮削类型
    _scrap_type = None
    # 移除非中文演员
    _remove_no_zh = None
    # 豆瓣辅助识别
    _douban_scrap = None
    # 最近一次入库时间
    _transfer_time = None
    # timeout
    _timeout = 10
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self.tmdbchain = TmdbChain()
        self.mschain = MediaServerChain()

        self._plex = Plex()
        self._plex_server = self._plex.get_plex()

        if not config:
            return

        self._enabled = config.get("enabled")
        self._onlyonce = config.get("onlyonce")
        self._cron = config.get("cron")
        self._notify = config.get("notify")
        self._library_ids = config.get("library_ids", [])
        self._lock = config.get("lock")
        self._execute_transfer = config.get("execute_transfer")
        self._scrap_type = config.get("scrap_type", "all")
        self._remove_no_zh = config.get("remove_no_zh", False)
        self._douban_scrap = config.get("douban_scrap", True)
        try:
            self._delay = int(config.get("delay", 200))
        except ValueError:
            self._delay = 200

        # 如果开启了入库后运行一次，延迟时间又不填，默认为200s
        if self._execute_transfer and not self._delay:
            self._delay = 200

        # 停止现有任务
        self.stop_service()

        # 启动服务
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._onlyonce:
            logger.info(f"{self.plugin_name}服务，立即运行一次")
            self._scheduler.add_job(
                func=self.scrap_library,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name=f"{self.plugin_name}",
            )
            # 关闭一次性开关
            self._onlyonce = False
            config["onlyonce"] = False
            self.update_config(config=config)

        # 启动服务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
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
        if self._enabled and self._cron:
            logger.info(f"{self.plugin_name}定时服务启动，时间间隔 {self._cron} ")
            return [{
                "id": "PlexPersonMeta",
                "name": f"{self.plugin_name}服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.scrap_library,
                "kwargs": {}
            }]

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
                                            'persistent-hint': True,
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
                                            'label': '发送通知',
                                            'hint': '是否在特定事件发生时发送通知',
                                            'persistent-hint': True,
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
                                            'hint': '插件将立即运行一次',
                                            'persistent-hint': True,
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
                                            'hint': '开启后元数据将锁定，须手工解锁后才允许修改',
                                            'persistent-hint': True,
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
                                            'label': '入库后运行一次',
                                            'hint': '在媒体入库后运行一次操作',
                                            'persistent-hint': True,
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
                                            'model': 'douban_scrap',
                                            'label': '豆瓣辅助识别',
                                            'hint': '提高识别率的同时将会降低性能',
                                            'persistent-hint': True,
                                        }
                                    }
                                ]
                            },
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
                            #                 'model': 'remove_no_zh',
                            #                 'label': '删除非中文演员',
                            #                 'hint': '开启后将删除所有非中文演员',
                            #                 'persistent-hint': True,
                            #             }
                            #         }
                            #     ]
                            # }
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
                                            'label': '运行周期',
                                            'placeholder': '5位cron表达式',
                                            'hint': '使用cron表达式指定运行周期，如 0 8 * * *',
                                            'persistent-hint': True,
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
                                            'placeholder': '入库后延迟运行时间',
                                            'hint': '入库后延迟运行的时间（秒）',
                                            'persistent-hint': True,
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
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'scrap_type',
                                            'label': '刮削条件',
                                            'items': [
                                                {'title': '全部', 'value': 'all'},
                                                {'title': '演员非中文', 'value': 'name'},
                                                {'title': '角色非中文', 'value': 'role'},
                                            ],
                                            'hint': '选择刮削条件',
                                            'persistent-hint': True,
                                        }
                                    }
                                ]
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
                                            'model': 'library_ids',
                                            'label': '媒体库',
                                            'items': self.__get_library_options(),
                                            'hint': '选择要处理的媒体库',
                                            'persistent-hint': True,
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
                                            'variant': 'tonal',
                                            'text': 'Plex 的 API 实现较为复杂，我在尝试为 actor.tag.tagKey 赋值时遇到了问题，'
                                                    '如果您对此有所了解，请不吝赐教，可以通过新增一个 issue 与我联系，特此感谢'
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
                                                'html': '基于 <a href="https://github.com/jxxghp/MoviePilot-Plugins" target="_blank" style="text-decoration: underline;">官方插件</a> 编写，并参考了 <a href="https://github.com/Bespertrijun/PrettyServer" target="_blank" style="text-decoration: underline;">PrettyServer</a> 项目，特此感谢 <a href="https://github.com/jxxghp" target="_blank" style="text-decoration: underline;">jxxghp</a>、<a href="https://github.com/Bespertrijun" target="_blank" style="text-decoration: underline;">Bespertrijun</a>'
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
                                            'text': '注意：如刮削没有达到预期的效果，请尝试在Plex中修改配置，设置->在线媒体资源->发现更多->停用发现来源'
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
                                            'text': '注意：如开启锁定元数据，则刮削后需要在Plex中手动解锁才允许修改，'
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
            "cron": "0 1 * * *",
            "lock": False,
            "execute_transfer": False,
            "delay": 200,
            "scrap_type": "all",
            "remove_no_zh": False,
            "douban_scrap": True
        }

    def get_page(self) -> List[dict]:
        pass

    @eventmanager.register(EventType.TransferComplete)
    def scrap_rt(self, event: Event):
        """
        根据事件实时刮削演员信息
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

        # 获取媒体信息，确定季度和集数信息，如果存在则添加前缀空格
        season_episode = f" {meta.season_episode}" if meta.season_episode else ""
        media_desc = f"{mediainfo.title_year}{season_episode}"

        # 如果最近一次入库时间为None，这里才进行赋值，否则可能是存在尚未执行的任务待执行
        if not self._transfer_time:
            self._transfer_time = datetime.now(tz=pytz.timezone(settings.TZ))

        # 根据是否有延迟设置不同的日志消息
        delay_message = f"{self._delay} 秒后运行一次{self.plugin_name}服务" if self._delay else f"准备运行一次{self.plugin_name}服务"
        logger.info(f"{media_desc} 已入库，{delay_message}")

        if not self._scheduler:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)

        self._scheduler.remove_all_jobs()

        self._scheduler.add_job(
            func=self.__scrap_by_transfer,
            trigger="date",
            run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=self._delay),
            name=f"{self.plugin_name}",
        )

        # 启动任务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def __scrap_by_transfer(self):
        """入库后运行一次"""
        if not self._transfer_time:
            logger.info(f"没有获取到最近一次的入库时间，取消执行{self.plugin_name}服务")
            return

        logger.info(f"正在运行一次{self.plugin_name}服务，入库时间 {self._transfer_time.strftime('%Y-%m-%d %H:%M:%S')}")

        adjusted_time = self._transfer_time - timedelta(minutes=5)
        logger.info(f"为保证入库数据完整性，前偏移5分钟后的时间：{adjusted_time.strftime('%Y-%m-%d %H:%M:%S')}")

        self.scrap_library_by_added_time(added_time=int(adjusted_time.timestamp()))
        self._transfer_time = None

    def scrap_library(self):
        """
        刮削媒体库中所有媒体的演员信息
        """
        if not self.__check_plex_media_server():
            return

        with lock:
            start_time = time.time()
            libraries = self.__get_libraries().values()
            for library in libraries:
                logger.info(f"开始刮削媒体库 {library.title} 的演员信息 ...")
                try:
                    rating_items = self.__list_rating_items(library=library)
                    if not rating_items:
                        logger.info(f"媒体库 {library.title} 没有找到任何媒体信息，跳过刮削")
                        continue

                    self.__scrap_rating_items(rating_items=rating_items)
                    logger.info(f"媒体库 {library.title} 的演员信息刮削完成")
                except Exception as e:
                    logger.error(f"媒体库 {library.title} 刮削过程中出现异常，{str(e)}")

            elapsed_time = time.time() - start_time
            message_text = f"{self.plugin_name}完成，用时 {elapsed_time:.2f} 秒"

            self.__send_message(title=f"【{self.plugin_name}】", text=message_text)
            logger.info(message_text)

    def scrap_library_by_added_time(self, added_time: int):
        """根据入库时间刮削媒体库中的演员信息"""
        if not self.__check_plex_media_server():
            return

        with lock:
            start_time = time.time()
            library_keys = set(self.__get_libraries().keys())
            rating_items = {}
            episode_items = {}
            recent_added_items = self.__list_rating_items_by_added(added_time=added_time)

            for rating_item in recent_added_items:
                section_id = rating_item.get("librarySectionID")
                if section_id not in library_keys:
                    continue
                rating_key = rating_item.get("ratingKey")
                if not rating_key:
                    continue

                rating_type = rating_item.get("type")
                # 先获取show和movie的key，后续直接进行刮削
                if rating_type in ["show", "movie"]:
                    rating_items[rating_key] = rating_item
                # 如果是季，这里直接当成show进行处理
                elif rating_type == "season":
                    parent_key = self.__extract_key_from_url(rating_item.get("parentKey"))
                    if parent_key and parent_key not in rating_items:
                        try:
                            rating_items[parent_key] = self.__fetch_item(rating_key=parent_key)
                        except Exception as e:
                            logger.error(f"媒体项 {rating_item.get('parentTitle')} 获取详细信息失败，{e}")
                # 如果是集的，先判断对应的父级key是否已经在rating_keys中增加，如果是，则忽略，如果不是，则追加到集的key中，后续独立进行刮削
                elif rating_type == "episode":
                    parent_key = self.__extract_key_from_url(rating_item.get("grandparentKey"))
                    if parent_key and parent_key not in rating_items:
                        episode_items.setdefault(parent_key, []).append(rating_item)

            logger.info(f"开始刮削最近入库的演员信息 ...")
            if not rating_items and not episode_items:
                logger.info(f"最近入库没有找到任何符合条件的媒体信息，跳过刮削")
            else:
                self.__scrap_rating_items(rating_items=list(rating_items.values()))
                self.__scrap_episode_items(episode_items=episode_items)

            elapsed_time = time.time() - start_time
            formatted_added_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(added_time))
            message_text = f"最近一次入库时间：{formatted_added_time}，{self.plugin_name}完成，用时 {elapsed_time:.2f} 秒"

            self.__send_message(title=f"【{self.plugin_name}】", text=message_text)
            logger.info(message_text)

    def __scrap_rating_items(self, rating_items: list):
        """刮削媒体库中的媒体项"""
        for rating_item in rating_items:
            if self.__check_external_interrupt():
                return
            info = self.__get_rating_info(item=rating_item)
            if not info or info.type not in ["movie", "show"]:
                continue
            item = {}
            try:
                item = self.__fetch_item(rating_key=info.key)
                if not item:
                    continue
                logger.info(f"开始刮削 {info.title} 的演员信息 ...")
                self.__scrap_item(item=item)
                logger.info(f"{info.title} 的演员信息刮削完成")
            except Exception as e:
                logger.error(f"媒体项 {info.title} 刮削过程中出现异常，{str(e)}")

            if info.type == "show" and item:
                logger.info(f"<{info.title}> 类型为 show，准备进行剧集刮削")
                self.__scrap_episodes(item=item)

    def __scrap_episode_items(self, episode_items: dict):
        """刮削剧集的媒体信息"""
        for parent_key, episodes in episode_items.items():
            if self.__check_external_interrupt():
                return
            item = self.__fetch_item(rating_key=parent_key)
            if not item:
                continue
            self.__scrap_episodes(item=item, episodes=episodes)

    def __scrap_episodes(self, item: dict, episodes: Optional[dict] = None):
        """刮削剧集"""
        info = self.__get_rating_info(item=item)
        if not info or info.type != "show":
            return

        try:
            # 如果 episodes 为空，这里获取所有的 episodes 进行刮削
            episodes_provided_all = episodes is None
            if episodes_provided_all:
                episodes = self.__list_episodes(rating_key=info.key)

            if not episodes:
                logger.info(f"<{info.title}> 没有找到任何剧集信息，取消剧集刮削")
            else:
                if episodes_provided_all:
                    logger.info(
                        f"<{info.title}> 共计 {item.get('childCount', 0)} 季 {len(episodes)} 集，准备进行剧集刮削")
                else:
                    logger.info(f"<{info.title}> 共计 {len(episodes)} 集，准备进行剧集刮削")

            for episode in episodes:
                if self.__check_external_interrupt():
                    return
                episode_info = self.__get_rating_info(item=episode, parent_item=item)
                if not episode_info or episode_info.type != "episode":
                    continue
                try:
                    episode_item = self.__fetch_item(rating_key=episode_info.key)
                    if not episode_item:
                        continue
                    logger.info(f"开始刮削 {episode_info.title} 的演员信息 ...")
                    self.__scrap_item(item=episode_item, info=episode_info)
                    logger.info(f"{episode_info.title} 的演员信息刮削完成")
                except Exception as e:
                    logger.error(f"媒体项 {episode_info.title} 刮削过程中出现异常，{str(e)}")
        except Exception as e:
            logger.error(f"媒体项 {info.title} 刮削剧集过程中出现异常，{str(e)}")

    def __scrap_item(self, item: dict, info: Optional[RatingInfo] = None):
        """
        刮削媒体服务器中的条目
        """
        if not item:
            return

        if not info:
            info = self.__get_rating_info(item=item)

        if not info or not info.tmdbid:
            logger.warn(f"{info.title} 未找到tmdbid，无法识别媒体信息")
            return

        logger.info(f"{info.title} 正在获取 TMDB 媒体信息")
        mediainfo = self.__get_tmdb_media(tmdbid=info.tmdbid,
                                          title=info.search_title,
                                          mtype=MediaType.MOVIE if item.get("type") == "movie" else MediaType.TV)
        if not mediainfo:
            logger.warn(f"{info.title} TMDB 未识别到媒体信息")
            return

        try:
            if self.__need_trans_actor(item):
                self.__update_peoples(item=item, mediainfo=mediainfo, info=info)
            else:
                logger.info(f"{info.title} 的人物信息已是中文，无需更新")
        except Exception as e:
            logger.error(f"{info.title} 更新人物信息时出错：{str(e)}")

    def __need_trans_actor(self, item: dict) -> bool:
        """
        是否需要处理人物信息
        """
        actors = item.get("Role", [])
        if not actors:
            return False

        field_to_check = None
        if self._scrap_type == "name":
            field_to_check = "tag"
        elif self._scrap_type == "role":
            field_to_check = "role"

        if field_to_check:
            for actor in actors:
                # 检查特定字段，且字段不能为空
                field_value = actor.get(field_to_check)
                if field_value and not StringUtils.is_chinese(field_value):
                    return True
        else:
            for actor in actors:
                # 刮削为 all 时，检查 tag 和 role 两个字段，且字段不能均为空
                tag_value = actor.get("tag")
                role_value = actor.get("role")
                if (tag_value and not StringUtils.is_chinese(tag_value)) or \
                        (role_value and not StringUtils.is_chinese(role_value)):
                    return True

        return False

    def __update_peoples(self, item: dict, mediainfo: MediaInfo, info: Optional[RatingInfo] = None):
        """处理媒体项中的人物信息"""
        """
        item 的数据结构：
        {
            "Director": [{
                "id": 119824,
                "filter": "director=119824",
                "tag": "Christopher Nolan",
                "tagKey": "5d776825880197001ec9038e",
                "thumb": "https://metadata-static.plex.tv/people/5d776825880197001ec9038e.jpg"
            }],
            "Writer": [{
                "id": 119825,
                "filter": "writer=119825",
                "tag": "Christopher Nolan",
                "tagKey": "5d776825880197001ec9038e",
                "thumb": "https://metadata-static.plex.tv/people/5d776825880197001ec9038e.jpg"
            }],
            "Role": [{
                "id": 94414,
                "filter": "actor=94414",
                "tag": "Cillian Murphy",
                "tagKey": "5d776825880197001ec90394",
                "role": "J. Robert Oppenheimer",
                "thumb": "https://metadata-static.plex.tv/e/people/ef539a37a16672a1a8d20f272b338c6b.jpg"
            }, {
                "id": 119826,
                "filter": "actor=119826",
                "tag": "Emily Blunt",
                "tagKey": "5d7768265af944001f1f6689",
                "role": "Kitty Oppenheimer",
                "thumb": "https://metadata-static.plex.tv/7/people/7a290c167719a107b03c15922013d211.jpg"
            }]
        }
        """
        if not mediainfo:
            return

        title = info.title if info and info.title else item.get("title")
        actors = item.get("Role", [])
        trans_actors = []

        # 将 mediainfo.actors 转换为字典，以 original_name、name、alias 和拼音为键
        actor_dict = {}
        for actor in mediainfo.actors:
            name = actor.get("name")
            original_name = actor.get("original_name")
            if name:
                actor_dict[name] = actor
                if StringUtils.is_chinese(name):
                    actor_dict[self.__to_pinyin(name)] = actor
            if original_name:
                actor_dict[original_name] = actor
            person_tmdbid = actor.get("id")
            if person_tmdbid:
                logger.info(f"{name} 正在获取 TMDB 人物信息")
                person_detail = self.__get_tmdb_person_detail(person_tmdbid=person_tmdbid)
                if person_detail:
                    cn_name = self.__get_chinese_name(person=person_detail)
                    if cn_name:
                        actor["name"] = cn_name
                    if person_detail.also_known_as:
                        actor["also_known_as"] = person_detail.also_known_as
                        for alias in person_detail.also_known_as:
                            actor_dict[alias] = actor

        # 使用TMDB信息更新人物
        for actor in actors:
            if self.__check_external_interrupt():
                return
            tag_value = actor.get("tag")
            role_value = actor.get("role")
            if not tag_value:
                continue

            # 批量赋值 original_name 属性，以便后续能够拿到原始值，避免翻译不一致时，豆瓣无法正确获取值
            original_actor = actor_dict.get(tag_value)
            if original_actor:
                actor["original_name"] = original_actor.get("original_name")

            if StringUtils.is_chinese(tag_value) and StringUtils.is_chinese(role_value):
                logger.debug(f"{tag_value} 已是中文数据，无需更新")
                trans_actors.append(actor)
                continue
            try:
                trans_actor = self.__update_people_by_tmdb(people=actor, people_dict=actor_dict)
                if trans_actor:
                    trans_actors.append(trans_actor)
                else:
                    trans_actors.append(actor)
            except Exception as e:
                logger.error(f"{title} TMDB 更新人物信息失败：{str(e)}")

        # 使用豆瓣信息更新人物
        if self._douban_scrap:
            # 如果全部人物信息都已经是中文数据，无需使用豆瓣信息更新
            if all(StringUtils.is_chinese(actor.get("tag", "")) and StringUtils.is_chinese(actor.get("role", "")) for
                   actor in trans_actors):
                logger.info(f"{title} 的人物信息已是中文，无需使用豆瓣信息更新")
            else:
                # 存在人物信息还不是中文数据，使用豆瓣信息进行更新
                logger.info(f"{title} 正在获取豆瓣媒体信息")
                douban_actors = self.__get_douban_actors(imdbid=mediainfo.imdb_id,
                                                         title=mediainfo.title,
                                                         mtype=mediainfo.type,
                                                         year=mediainfo.year,
                                                         season=mediainfo.season,
                                                         season_years=tuple(sorted(mediainfo.season_years.items())))
                if douban_actors:
                    # 将 douban_actors 转换为字典，以 latin_name 和 name 和拼音为键
                    douban_actor_dict = {}
                    for actor in douban_actors:
                        name = actor.get("name")
                        latin_name = actor.get("latin_name")
                        if name:
                            douban_actor_dict[name] = actor
                            if StringUtils.is_chinese(name):
                                douban_actor_dict[self.__to_pinyin(name)] = actor
                        if latin_name:
                            douban_actor_dict[latin_name] = actor
                            douban_actor_dict[self.__standardize_name_order(latin_name)] = actor

                    for actor in trans_actors:
                        if self.__check_external_interrupt():
                            return
                        try:
                            tag_value = actor.get("tag")
                            role_value = actor.get("role")
                            if StringUtils.is_chinese(tag_value) and StringUtils.is_chinese(role_value):
                                logger.debug(f"{tag_value} 已是中文数据，无需使用豆瓣信息更新")
                                continue

                            updated_actor = self.__update_people_by_douban(people=actor,
                                                                           people_dict=douban_actor_dict)
                            if updated_actor:
                                actor.update(updated_actor)
                        except Exception as e:
                            logger.error(f"{title} 豆瓣更新人物信息失败：{str(e)}")

        if trans_actors:
            try:
                self.__put_actors(item=item, actors=trans_actors)
                logger.info(f"{title} 的中文人物信息更新完成")
            except Exception as e:
                logger.error(f"{title} 的中文人物信息更新失败：{str(e)}")

    def __put_actors(self, item: dict, actors: list):
        """更新演员信息"""
        if not item or not actors:
            return

        rating_key = item.get("ratingKey")
        if not rating_key:
            return

        # 创建actors_param字典
        actors_param = {}
        for i, actor in enumerate(actors):
            actors_param[f"actor[{i}].tag.tag"] = actor.get("tag", "")
            actors_param[f"actor[{i}].tagging.text"] = actor.get("role", "")
            actors_param[f"actor[{i}].tag.thumb"] = actor.get("thumb", "")
            actors_param[f"actor[{i}].tag.tagKey"] = actor.get("tagKey", "")

        params = {
            "actor.locked": 1 if self._lock else 0
        }
        params.update(actors_param)

        endpoint = f"library/metadata/{rating_key}"
        self._plex.put_data(
            endpoint=endpoint,
            params=params,
            timeout=self._timeout
        )

    def __update_people_by_tmdb(self, people: dict, people_dict: dict) -> Optional[dict]:
        """更新人物信息，返回替换后的人物信息"""
        """
        people 的数据结构:
        {
            "id": 94414,
            "filter": "actor=94414",
            "tag": "Cillian Murphy",
            "tagKey": "5d776825880197001ec90394",
            "role": "J. Robert Oppenheimer",
            "thumb": "https://metadata-static.plex.tv/e/people/ef539a37a16672a1a8d20f272b338c6b.jpg"
        }

        people_dict 的数据结构:
        [{
            "adult": False,
            "gender": 2,
            "id": 2037,
            "known_for_department": "Acting",
            "name": "基利安·墨菲",
            "original_name": "Cillian Murphy",
            "popularity": 48.424,
            "profile_path": "/dm6V24NjjvjMiCtbMkc8Y2WPm2e.jpg",
            "cast_id": 3,
            "character": "J. Robert Oppenheimer",
            "credit_id": "613a940d9653f60043e380df",
            "order": 0
        }, {
            "adult": False,
            "gender": 1,
            "id": 5081,
            "known_for_department": "Acting",
            "name": "艾米莉·布朗特",
            "original_name": "Emily Blunt",
            "popularity": 94.51,
            "profile_path": "/5nCSG5TL1bP1geD8aaBfaLnLLCD.jpg",
            "cast_id": 161,
            "character": "Kitty Oppenheimer",
            "credit_id": "6328c918524978007e9f1a7f",
            "order": 1
        }]
        """
        if not people_dict:
            return None

        # 返回的人物信息
        ret_people = copy.deepcopy(people)

        # 查找对应的 TMDB 人物信息
        person_name = people.get("tag")
        person_name_lower = self.__remove_spaces_and_lower(person_name)
        person_pinyin = self.__to_pinyin(person_name)

        # 构建一个包含所有潜在键的列表后，再进行逐一获取
        potential_keys = [person_name, person_name_lower, person_pinyin]
        person_detail = next((people_dict[key] for key in potential_keys if key in people_dict), None)

        # 从 TMDB 演员中匹配中文名称、角色和简介
        if not person_detail:
            logger.debug(f"人物 {person_name} 未找到中文数据")
            return None

        # 名称
        if StringUtils.is_chinese(person_name):
            logger.debug(f"{person_name} 已是中文名称，无需更新")
        else:
            cn_name = self.__get_chinese_field_value(people=person_detail, field="name")
            if cn_name:
                logger.debug(f"{person_name} 从 TMDB 获取到中文名称：{cn_name}")
                ret_people["tag"] = cn_name
            else:
                logger.debug(f"{person_name} 从 TMDB 未能获取到中文名称")

        # 角色
        character = people.get("role")
        if StringUtils.is_chinese(character):
            logger.debug(f"{person_name} 已是中文角色，无需更新")
        else:
            cn_character = self.__get_chinese_field_value(people=person_detail, field="character")
            if cn_character:
                logger.debug(f"{person_name} 从 TMDB 获取到中文角色：{cn_character}")
                ret_people["role"] = cn_character
            else:
                logger.debug(f"{person_name} 从 TMDB 未能获取到中文角色")

        return ret_people

    def __update_people_by_douban(self, people: dict, people_dict: dict) -> Optional[dict]:
        """从豆瓣信息中更新人物信息"""
        """
        people 的数据结构:
        {
            "id": 94414,
            "filter": "actor=94414",
            "tag": "Cillian Murphy",
            "tagKey": "5d776825880197001ec90394",
            "role": "J. Robert Oppenheimer",
            "thumb": "https://metadata-static.plex.tv/e/people/ef539a37a16672a1a8d20f272b338c6b.jpg"
            "original_name": "Cillian Murphy"
        }

        people_dict 的数据结构
        {
          "name": "丹尼尔·克雷格",
          "roles": [
            "演员",
            "制片人",
            "配音"
          ],
          "title": "丹尼尔·克雷格（同名）英国,英格兰,柴郡,切斯特影视演员",
          "url": "https://movie.douban.com/celebrity/1025175/",
          "user": null,
          "character": "饰 詹姆斯·邦德 James Bond 007",
          "uri": "douban://douban.com/celebrity/1025175?subject_id=27230907",
          "avatar": {
            "large": "https://qnmob3.doubanio.com/view/celebrity/raw/public/p42588.jpg?imageView2/2/q/80/w/600/h/3000/format/webp",
            "normal": "https://qnmob3.doubanio.com/view/celebrity/raw/public/p42588.jpg?imageView2/2/q/80/w/200/h/300/format/webp"
          },
          "sharing_url": "https://www.douban.com/doubanapp/dispatch?uri=/celebrity/1025175/",
          "type": "celebrity",
          "id": "1025175",
          "latin_name": "Daniel Craig"
        }
        """
        if not people_dict:
            return people

        # 返回的人物信息
        ret_people = copy.deepcopy(people)

        # 查找对应的豆瓣人物信息
        person_name = people.get("tag")
        original_name = people.get("original_name")
        also_known_as = people.get("also_known_as", [])
        person_name_lower = self.__remove_spaces_and_lower(person_name)
        person_pinyin = self.__to_pinyin(person_name)

        # 构建一个包含所有潜在键的列表后，再进行逐一获取
        potential_keys = [person_name, original_name] + also_known_as + [person_name_lower, person_pinyin]
        person_detail = next((people_dict[key] for key in potential_keys if key in people_dict), None)

        # 从豆瓣演员中匹配中文名称、角色和简介
        if not person_detail:
            logger.debug(f"人物 {person_name} 未找到中文数据")
            return None

        # 名称
        if StringUtils.is_chinese(person_name):
            logger.debug(f"{person_name} 已是中文名称，无需更新")
        else:
            cn_name = self.__get_chinese_field_value(people=person_detail, field="name")
            if cn_name:
                logger.debug(f"{person_name} 从豆瓣中获取到中文名称：{cn_name}")
                ret_people["tag"] = cn_name
            else:
                logger.debug(f"{person_name} 从豆瓣未能获取到中文名称")

        # 角色
        character = people.get("role")
        if StringUtils.is_chinese(character):
            logger.debug(f"{person_name} 已是中文角色，无需更新")
        else:
            cn_character = self.__get_chinese_field_value(people=person_detail, field="character")
            if cn_character:
                # "饰 詹姆斯·邦德 James Bond 007"
                cn_character = re.sub(r"饰\s+", "", cn_character)
                cn_character = re.sub("演员", "", cn_character)
                if cn_character:
                    logger.debug(f"{person_name} 从豆瓣中获取到中文角色：{cn_character}")
                    ret_people["role"] = cn_character
                else:
                    logger.debug(f"{person_name} 从豆瓣未能获取到中文角色")
            else:
                logger.debug(f"{person_name} 从豆瓣未能获取到中文角色")

        return ret_people

    @cache_with_logging(tmdb_person_cache, "PERSON")
    def __get_tmdb_person_detail(self,
                                 person_tmdbid: int) -> Optional[MediaPerson]:
        """获取TMDB媒体信息"""
        try:
            person_detail = self.tmdbchain.person_detail(int(person_tmdbid))
            return person_detail
        except Exception as e:
            logger.error(f"{person_tmdbid} TMDB 识别人员信息时出错：{str(e)}")
            return None

    @cache_with_logging(tmdb_media_cache, "TMDB")
    def __get_tmdb_media(self,
                         tmdbid: int,
                         title: str,
                         mtype: MediaType = MediaType.TV) -> Optional[MediaInfo]:
        """获取TMDB媒体信息"""
        try:
            mediainfo = self.chain.recognize_media(mtype=mtype, tmdbid=tmdbid)
            return mediainfo
        except Exception as e:
            logger.error(f"{title} TMDB 识别媒体信息时出错：{str(e)}")
            return None

    @cache_with_logging(douban_media_cache, "豆瓣")
    def __get_douban_actors(self,
                            title: str,
                            imdbid: Optional[str] = None,
                            mtype: Optional[MediaType] = None,
                            year: Optional[str] = None,
                            season: Optional[int] = None,
                            season_years: Any = None) -> List[dict]:
        """获取豆瓣演员信息"""

        def fetch_actors(fetch_title: str,
                         fetch_imdbid: Optional[str] = None,
                         fetch_mtype: Optional[MediaType] = None,
                         fetch_year: Optional[str] = None,
                         fetch_season: Optional[int] = None) -> Optional[List[dict]]:
            try:
                sleep_time = 5 + int(time.time()) % 7
                logger.debug(f"随机休眠 {sleep_time}秒 ...")
                time.sleep(sleep_time)
                doubaninfo = self.chain.match_doubaninfo(name=fetch_title,
                                                         imdbid=fetch_imdbid,
                                                         mtype=fetch_mtype,
                                                         year=fetch_year,
                                                         season=fetch_season)
                if doubaninfo:
                    item = self.chain.douban_info(doubaninfo.get("id")) or {}
                    if item:
                        return (item.get("actors") or []) + (item.get("directors") or [])
                    else:
                        logger.debug(f"未找到豆瓣详情：{fetch_title}({fetch_year})")
                        return None
                else:
                    logger.debug(f"未找到豆瓣信息：{fetch_title}({fetch_year})")
                    return None
            except Exception as e:
                logger.error(f"{fetch_title} 豆瓣识别媒体信息时出错：{str(e)}")
                return None

        douban_actors = []

        if season_years and len(season_years) > 1:
            for season, year in season_years:
                actors = fetch_actors(fetch_title=title, fetch_mtype=mtype, fetch_year=year,
                                      fetch_season=season)
                if actors:
                    douban_actors.extend(actors)
        else:
            actors = fetch_actors(fetch_title=title, fetch_imdbid=imdbid, fetch_mtype=mtype, fetch_year=year,
                                  fetch_season=season)
            if actors:
                douban_actors.extend(actors)

        return douban_actors if douban_actors else None

    @staticmethod
    def __get_chinese_name(person: MediaPerson) -> Optional[str]:
        """
        获取TMDB别名中的中文名
        """
        try:
            # 如果人物名称已经是中文，则直接返回，不再繁简转换
            if StringUtils.is_chinese(person.name):
                return person.name
            also_known_as = person.also_known_as or []
            if also_known_as:
                for name in also_known_as:
                    if name and StringUtils.is_chinese(name):
                        # 使用cn2an将繁体转化为简体
                        return zhconv.convert(name, "zh-hans")
        except Exception as err:
            logger.error(f"获取人物中文名失败：{err}")
        return None

    @staticmethod
    def __get_chinese_field_value(people: dict, field: str) -> Optional[str]:
        """
        获取TMDB的中文名称
        """
        """
        people 的数据结构
        {
            "adult": False,
            "gender": 2,
            "id": 2037,
            "known_for_department": "Acting",
            "name": "基利安·墨菲",
            "original_name": "Cillian Murphy",
            "popularity": 48.424,
            "profile_path": "/dm6V24NjjvjMiCtbMkc8Y2WPm2e.jpg",
            "cast_id": 3,
            "character": "J. Robert Oppenheimer",
            "credit_id": "613a940d9653f60043e380df",
            "order": 0
        }
        """
        try:
            field_value = people.get(field, "")
            if field_value and StringUtils.is_chinese(field_value):
                return field_value
        except Exception as e:
            logger.error(f"获取人物{field}失败：{e}")
        return None

    def __get_library_options(self):
        """获取媒体库选项"""
        if not self.__check_plex_media_server():
            return []

        library_options = []
        # 获取所有媒体库
        libraries = self._plex_server.library.sections()
        # 遍历媒体库，创建字典并添加到列表中
        for library in libraries:
            # 仅支持电影、剧集媒体库
            if library.TYPE != "show" and library.TYPE != "movie":
                continue
            library_dict = {
                "title": f"{library.key}. {library.title} ({library.TYPE})",
                "value": library.key
            }
            library_options.append(library_dict)
        library_options = sorted(library_options, key=lambda x: x["value"])
        return library_options

    def __get_libraries(self):
        """获取媒体库信息"""
        libraries = {
            int(library.key): library
            for library in self._plex_server.library.sections()
            if library.key in self._library_ids
        }

        return libraries

    @staticmethod
    def __get_season_episode(item: Dict) -> str:
        """获取剧集的季和集信息"""
        season_number = item.get("parentIndex", "0")
        episode_number = item.get("index", "0")
        return f"s{str(season_number).zfill(2)}e{str(episode_number).zfill(2)}"

    @staticmethod
    def __get_rating_info(item: dict, parent_item: Optional[dict] = None) -> Optional[RatingInfo]:
        """获取媒体项目信息"""
        if not item:
            return None

        key = item.get("ratingKey")
        if not key:
            return None

        rating_type = item.get("type")
        title = item.get("title", key)
        search_title = title

        # 获取 TMDB ID
        tmdbid = (PlexPersonMeta.__get_tmdb_id(item=parent_item) if parent_item
                  else PlexPersonMeta.__get_tmdb_id(item=item))

        # 如果是剧集，调整标题格式
        if rating_type == "episode":
            parent_title = parent_item.get("title") if parent_item else item.get("grandparentTitle", title)
            title = f"{parent_title} - {PlexPersonMeta.__get_season_episode(item=item)} - {title}"
            search_title = parent_title

        return RatingInfo(key=key,
                          type=rating_type,
                          title=title,
                          search_title=search_title,
                          tmdbid=tmdbid)

    def __list_rating_items(self, library: LibrarySection):
        """获取所有媒体项目"""
        if not library:
            return []

        endpoint = f"/library/sections/{library.key}/all?type={plexapi.utils.searchType(libtype=library.TYPE)}"

        response = self._plex.get_data(endpoint=endpoint, timeout=self._timeout)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))

        if len(datas):
            logger.info(f"<{library.title} {library.TYPE}> "
                        f"类型共计 {len(datas)} 个")

        return datas

    def __list_rating_items_by_added(self, added_time: int):
        """获取最近入库媒体"""
        endpoint = f"/library/all?addedAt>={added_time}"
        response = self._plex.get_data(endpoint=endpoint, timeout=self._timeout)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return datas

    def __list_episodes(self, rating_key, ):
        """获取show的所有剧集"""
        endpoint = f"/library/metadata/{rating_key}/allLeaves"

        response = self._plex.get_data(endpoint=endpoint, timeout=self._timeout)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))

        return datas

    def __fetch_item(self, rating_key):
        """
        获取条目信息
        """
        endpoint = f"/library/metadata/{rating_key}"
        response = self._plex.get_data(endpoint=endpoint, timeout=self._timeout)
        datas = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return datas[0] if datas else None

    def __fetch_all_items(self, rating_keys):
        """
        批量获取条目。
        :param rating_keys: 需要获取的条目的评级键列表。
        :return: 获取的所有条目列表。
        """
        endpoint = f"/library/metadata/{','.join(rating_keys)}"
        response = self._plex.get_data(endpoint=endpoint, timeout=self._timeout)
        items = (response
                 .json()
                 .get("MediaContainer", {})
                 .get("Metadata", []))
        return items

    @staticmethod
    def __get_tmdb_id(item) -> Optional[int]:
        """获取 tmdb_id"""
        if not item:
            return None
        guids = item.get("Guid", [])
        if not guids:
            return None
        for guid in guids:
            guid_id = guid.get("id", "")
            if guid_id.startswith("tmdb://"):
                parts = guid_id.split("tmdb://")
                if len(parts) == 2 and parts[1].isdigit():
                    return int(parts[1])
        return None

    def __send_message(self, title: str, text: str):
        """
        发送消息
        """
        if not self._notify:
            return

        self.post_message(mtype=NotificationType.SiteMessage, title=title, text=text)

    def __check_plex_media_server(self) -> bool:
        """检查Plex媒体服务器配置"""
        if not settings.MEDIASERVER:
            logger.error(f"媒体库配置不正确，请检查")
            return False

        if "plex" not in settings.MEDIASERVER:
            logger.error(f"没有启用Plex媒体库，请检查")
            return False

        if not self._plex_server:
            logger.error(f"Plex配置不正确，请检查")
            return False

        return True

    def __check_external_interrupt(self, service: Optional[str] = None) -> bool:
        """
        检查是否有外部中断请求，并记录相应的日志信息
        """
        if self._event.is_set():
            logger.warning(f"外部中断请求，{service if service else self.plugin_name} 服务停止")
            return True
        return False

    @staticmethod
    def __to_pinyin(string) -> str:
        """将中文字符串转换为拼音，没有空格分隔"""
        return pypinyin.slug(string, separator="", style=pypinyin.Style.NORMAL, strict=False).lower()

    @staticmethod
    def __standardize_name_order(name) -> str:
        """将英文名标准化为统一的顺序（姓在前，名在后）"""
        parts = name.split()
        if len(parts) == 2:
            return f"{parts[1]} {parts[0]}"
        return name

    @staticmethod
    def __remove_spaces_and_lower(string) -> str:
        """去除字符串中的空格并转换为小写"""
        return string.replace(" ", "").lower()

    @staticmethod
    def __extract_key_from_url(url: str) -> Optional[str]:
        """从URL中提取key"""
        match = re.search(r'/library/metadata/(\d+)', url)
        return match.group(1) if match else None
