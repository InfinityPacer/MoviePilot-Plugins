import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional, Type

import pytz
from app.db import db_query
from app.db.models import TransferHistory
from app.plugins import _PluginBase
from app.schemas import TransferInfo
from app.schemas.types import EventType, MediaSource, MediaType
from app.sdk.config import settings
from app.sdk.events import eventmanager, Event
from app.sdk.logging import logger
from app.sdk.media import MediaInfo, MetaBase
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import and_
from sqlalchemy.orm import Session

lock = threading.Lock()


class PlexMatch(_PluginBase):
    # 插件名称
    plugin_name = "PlexMatch"
    # 插件描述
    plugin_desc = "实现入库时添加 .plexmatch 文件，提高识别准确率。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/plexmatch.png"
    # 插件版本
    plugin_version = "1.5"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "plexmatch_"
    # 加载顺序
    plugin_order = 95
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    # 是否开启
    _enabled = False
    # 是否覆盖
    _overwrite = False
    # 根据历史记录一次性补全
    _complete_all = False

    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):

        if not config:
            return

        self._enabled = config.get("enabled")
        self._overwrite = config.get("overwrite")
        self._complete_all = config.get("complete_all")

        # 停止现有任务
        self.stop_service()

        # 启动服务
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._complete_all:
            logger.info(f"{self.plugin_name}，一次性补全服务，立即运行一次")
            self._scheduler.add_job(
                func=self.__complete_by_history,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name=f"{self.plugin_name}",
            )
            # 关闭一次性开关
            self._complete_all = False
            config["complete_all"] = False
            self.update_config(config=config)

        # 启动服务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """本插件不注册远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """本插件不暴露自有 HTTP API。"""
        return []

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
        return []

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
                                            'persistent-hint': True
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
                                            'model': 'overwrite',
                                            'label': '覆盖 .plexmatch 文件',
                                            'hint': '是否覆盖已有文件',
                                            'persistent-hint': True
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
                                            'model': 'complete_all',
                                            'label': '补全 .plexmatch 文件',
                                            'hint': '根据历史记录一次性补全，执行后自动关闭',
                                            'persistent-hint': True
                                        },
                                    }
                                ],
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
                                            'text': '注意：.plexmatch 相关内容请查阅 '
                                        },
                                        'content': [
                                            {
                                                'component': 'a',
                                                'props': {
                                                    'href': 'https://support.plex.tv/articles/plexmatch',
                                                    'target': '_blank'
                                                },
                                                'content': [
                                                    {
                                                        'component': 'u',
                                                        'text': 'Plex官方教程'
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
                                            'text': '注意：启用覆盖功能时，若指定路径下已存在 .plexmatch 文件，该文件将被替换，请慎重开启'
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
                                            'text': '注意：仅适配了MoviePilot默认的重命名目录结构，电影和电视剧均会生成 .plexmatch 文件，但目前仅电视剧会生效'
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：根据历史记录一次性补全，可能会触发Plex重新扫描已入库媒体文件的片头片尾，请慎重使用'
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
            "overwrite": False,
            "complete_all": False
        }

    def get_page(self) -> Optional[List[dict]]:
        """本插件没有详情页。"""
        return None

    @eventmanager.register(EventType.TransferComplete)
    def execute_transfer(self, event: Event):
        """
        入库后执行一次服务
        """
        if not self._enabled:
            return

        event_info: dict = event.event_data
        if not event_info:
            return

        mediainfo: MediaInfo = event_info.get("mediainfo")
        meta: MetaBase = event_info.get("meta")
        transfer_info: TransferInfo = event_info.get("transferinfo")
        if not mediainfo or not meta or not transfer_info:
            return
        if mediainfo.type not in (MediaType.MOVIE, MediaType.TV):
            return

        # 获取媒体信息，确定季度和集数信息，如果存在则添加前缀空格
        season_episode = f" {meta.season_episode}" if meta.season_episode else ""
        media_desc = f"{mediainfo.title_year}{season_episode}"

        logger.info(f"{media_desc} 已入库，正在准备运行一次 PlexMatch 服务")

        tmdb_id = self.__get_tmdb_id(
            media_source=mediainfo.media_source,
            media_id=mediainfo.media_id,
        )
        if not tmdb_id:
            logger.info(f"{media_desc} 没有有效的 TMDB 媒体身份，跳过 PlexMatch 服务")
            return

        self.__add_plexmatch_file(title=mediainfo.title,
                                  tmdb_id=tmdb_id,
                                  file_path=str(transfer_info.target_item.path) if transfer_info.target_item else None,
                                  mtype=mediainfo.type)

    def __complete_by_history(self):
        """
        补全历史记录
        """
        histories = self.__list_transfer_histories(db=None)
        if not histories:
            logger.info("没有获取到相关的历史记录，取消补全")
            return

        for history in histories:
            if self.__check_external_interrupt(service=f"{self.plugin_name}"):
                return
            media_type = MediaType(history.type)
            if media_type not in (MediaType.MOVIE, MediaType.TV):
                continue
            tmdb_id = self.__get_tmdb_id(
                media_source=history.media_source,
                media_id=history.media_id,
            )
            if not tmdb_id:
                continue
            self.__add_plexmatch_file(title=history.title,
                                      tmdb_id=tmdb_id,
                                      file_path=history.dest,
                                      mtype=media_type)

    @staticmethod
    def __get_tmdb_id(media_source: Optional[MediaSource | str], media_id: Optional[str]) -> Optional[str]:
        """仅从有效的 TMDB 媒体身份中提取 Plex 可识别的 ID。"""
        normalized_id = str(media_id).strip() if media_id is not None else ""
        if media_source != MediaSource.TMDB or not normalized_id or normalized_id == "0":
            return None
        return normalized_id

    def __add_plexmatch_file(self, title: str, tmdb_id: str, file_path: str,
                             mtype: MediaType = MediaType.TV) -> bool:
        """添加.plexmatch文件"""
        keyword = f"{title}（{tmdb_id}）-> {file_path}"
        logger.info(f"{keyword} 正在准备添加 .plexmatch 文件")
        try:
            if mtype not in (MediaType.MOVIE, MediaType.TV):
                logger.info(f"{title} 的媒体类型 {mtype.value} 不支持 PlexMatch，跳过处理")
                return False
            if not tmdb_id:
                logger.warning(f"{title} 的 TMDB ID {tmdb_id} 无效，跳过处理")
                return False

            path = Path(file_path) if file_path else None
            if not path or not path.exists():
                logger.warning(f"目标路径 {path} 不存在，跳过处理")
                return False

            if mtype == MediaType.TV:
                parent_path = path.parent.parent if path.is_file() else path.parent
            else:
                parent_path = path.parent if path.is_file() else path

            plexmatch_file = parent_path / ".plexmatch"
            logger.info(f".plexmatch 文件路径为 {plexmatch_file}")
            if plexmatch_file.exists() and not self._overwrite:
                logger.info(f".plexmatch 文件已存在且未开启覆盖，跳过处理")
                return False

            hints = f"tmdbid: {tmdb_id} #{title} TMDB编号"
            with plexmatch_file.open('w', encoding='utf-8') as file:
                file.write(hints)

            logger.info(f"{keyword} 已添加 .plexmatch 文件至 {plexmatch_file}")
            return True
        except Exception as e:
            logger.error(f"处理 {keyword} 时发生错误: {e}")
            return False

    def __check_external_interrupt(self, service: str) -> bool:
        """
        检查是否有外部中断请求，并记录相应的日志信息
        """
        if self._event.is_set():
            logger.warning(f"外部中断请求，{service}服务停止")
            return True
        return False

    @staticmethod
    @db_query
    def __list_transfer_histories(db: Optional[Session]) -> list[Type[TransferHistory]]:
        """获取具有有效 TMDB 媒体身份且整理成功的历史记录。"""
        result = db.query(TransferHistory).filter(and_(
            TransferHistory.type.in_([MediaType.MOVIE.value, MediaType.TV.value]),
            TransferHistory.media_source == MediaSource.TMDB.value,
            TransferHistory.media_id.is_not(None),
            TransferHistory.media_id != "",
            TransferHistory.media_id != "0",
            TransferHistory.status)
        ).all()
        return result
