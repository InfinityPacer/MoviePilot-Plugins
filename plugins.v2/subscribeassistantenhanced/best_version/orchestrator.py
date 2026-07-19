"""洗版全流程编排：按配置创建洗版订阅。"""
from typing import Callable, Optional

from app.log import logger
from app.schemas.types import MediaType

from ..shared.subscribe import (
    format_subscribe_desc,
    is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
    resolve_subscribe_media_type,
)
from .priority import PriorityManager


class BestVersionOrchestrator:
    """洗版全流程编排器，负责按配置创建洗版订阅。"""

    def __init__(self, priority_manager: PriorityManager,
                 subscribe_oper=None,
                 send_subscribe_added_fn: Optional[Callable] = None,
                 notify_fn: Optional[Callable] = None,
                 related_downloads_fn: Optional[Callable] = None,
                 best_version_type: str = "no",
                 plugin_name: str = "订阅助手（增强版）"):
        """注入洗版编排依赖与自动洗版范围。"""
        self._priority = priority_manager
        self._subscribe_oper = subscribe_oper
        self._send_subscribe_added = send_subscribe_added_fn
        self._notify = notify_fn
        self._related_downloads = related_downloads_fn
        self._best_version_type = best_version_type
        self._plugin_name = plugin_name

    def build_payload(self, subscribe) -> dict:
        """构建洗版订阅 payload，保留 episode_group。"""
        payload = {
            "name": subscribe.name,
            "tmdbid": subscribe.tmdbid,
            "season": subscribe.season,
            "episode_group": subscribe.episode_group,
            "save_path": subscribe.save_path,
            "sites": subscribe.sites,
            "filter": subscribe.filter,
            "filter_groups": subscribe.filter_groups,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        payload["best_version"] = 1
        payload["manual_total_episode"] = 0
        return payload

    def start_best_version(self, subscribe, mediainfo):
        """普通订阅完成后按配置自动创建洗版订阅。

        分集下载洗版只在历史上存在多次分集下载时创建，避免单次全集包完成后误进入洗版。
        """
        if not self._subscribe_oper or not mediainfo:
            return None
        if subscribe.best_version:
            return None
        media_type = resolve_subscribe_media_type(subscribe)
        if not self._type_matches(media_type, self._best_version_type):
            return None
        is_movie = media_type == MediaType.MOVIE
        if is_movie and self._movie_current_priority(subscribe) >= 100:
            logger.info(
                f"洗版编排：{format_subscribe_desc(subscribe)} "
                f"普通订阅完成资源已达顶档，跳过自动创建洗版订阅"
            )
            if self._notify:
                self._notify(
                    f"{format_subscribe_desc(subscribe)} 已达顶档，跳过洗版订阅",
                    image=mediainfo.get_message_image(),
                    link="#/subscribe/movie?tab=mysub",
                )
            return None
        if self._best_version_type == "tv_episode" and not is_movie:
            downloads = self._related_downloads(subscribe) if self._related_downloads else []
            download_count = len(downloads or [])
            if download_count <= 1:
                logger.info(
                    f"洗版编排：{format_subscribe_desc(subscribe)} 只找到 {download_count} 条分集下载记录，"
                    f"不是多次分集下载完成，跳过自动创建洗版订阅"
                )
                return None
        payload = {
            "best_version": 1,
            "season": subscribe.season,
            "episode_group": subscribe.episode_group,
            "save_path": subscribe.save_path,
            "sites": subscribe.sites,
            "filter": subscribe.filter,
            "filter_groups": subscribe.filter_groups,
        }
        # 普通剧集订阅完成后直接进入洗版，才能在新资源下载前执行整季既有版本清理。
        if not is_movie:
            payload["best_version_full"] = 1
        else:
            payload["current_priority"] = self._movie_current_priority(subscribe)
        payload = {key: value for key, value in payload.items() if value is not None}
        # 插件创建的订阅始终重新跟随 TMDB 总集数，不继承已完成订阅的手动锁定状态。
        payload["manual_total_episode"] = 0
        sid, err_msg = self._subscribe_oper.add(mediainfo=mediainfo, **payload)
        if sid:
            mode_label = "洗版"
            logger.info(
                f"洗版编排：{format_subscribe_desc(subscribe)} "
                f"原因=订阅完成，处理=已创建{mode_label}订阅（id={sid}）"
            )
            if self._send_subscribe_added:
                self._send_subscribe_added(sid, mediainfo, username=self._plugin_name)
            if self._notify:
                self._notify(
                    f"{format_subscribe_desc(subscribe)} 已添加{mode_label}订阅",
                    score=mediainfo.vote_average,
                    user=self._plugin_name,
                    image=mediainfo.get_message_image(),
                    link="#/subscribe/movie?tab=mysub" if is_movie else "#/subscribe/tv?tab=mysub",
                )
        elif self._notify:
            logger.error(
                f"洗版编排：{format_subscribe_desc(subscribe)} "
                f"原因=添加洗版订阅失败，处理=请检查订阅创建错误，错误={err_msg}"
            )
            self._notify(
                f"{format_subscribe_desc(subscribe)} 添加洗版订阅失败",
                reason=err_msg,
                follow_up="请检查订阅创建错误",
                diagnostic=True,
                image=mediainfo.get_message_image(),
            )
        return sid

    @staticmethod
    def _mode_label(subscribe) -> str:
        """按订阅实际洗版形态返回用户可见标签。"""
        if is_full_best_version_subscribe(subscribe):
            return "洗版"
        if is_tv_episode_best_version_subscribe(subscribe):
            return "分集洗版"
        return ""

    @staticmethod
    def _movie_current_priority(subscribe) -> int:
        """读取电影订阅当前质量优先级，空值按未建立质量基线处理。"""
        try:
            return int(subscribe.current_priority or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _type_matches(media_type: MediaType, type_setting) -> bool:
        """判断媒体类型是否落在自动洗版范围：no/all/movie/tv/tv_episode。"""
        if media_type == MediaType.UNKNOWN:
            return False
        if type_setting == "no":
            return False
        if type_setting == "all":
            return True
        if type_setting == "movie":
            return media_type == MediaType.MOVIE
        if type_setting in ("tv", "tv_episode"):
            return media_type == MediaType.TV
        return False
