"""洗版全流程编排：订阅创建、完成判定与破坏性历史清理。"""
import time
from typing import Callable, Optional

from app.log import logger
from app.schemas.types import MediaType

from ..engine.types import CompletionSignal
from ..shared.log import detail
from ..shared.subscribe import format_subscribe_desc
from .priority import PriorityManager


class BestVersionOrchestrator:
    """洗版全流程编排器。

    洗版清理涉及删除源文件与媒体库文件，均经注入回调执行，避免流程直接绑定下载器或文件系统实现。
    """

    def __init__(self, priority_manager: PriorityManager,
                 evaluate_fn: Callable,
                 subscribe_oper=None,
                 task_data_read: Optional[Callable] = None,
                 task_data_update: Optional[Callable] = None,
                 get_histories_fn: Optional[Callable] = None,
                 delete_media_file_fn: Optional[Callable] = None,
                 delete_history_fn: Optional[Callable] = None,
                 send_download_file_deleted_fn: Optional[Callable] = None,
                 send_subscribe_added_fn: Optional[Callable] = None,
                 notify_fn: Optional[Callable] = None,
                 season_of_fn: Optional[Callable] = None,
                 related_downloads_fn: Optional[Callable] = None,
                 best_version_type: str = "no",
                 clear_history_type: str = "no",
                 plugin_name: str = "订阅助手（增强版）"):
        """注入洗版编排依赖、自动洗版范围与破坏性清理范围。"""
        self._priority = priority_manager
        self._evaluate = evaluate_fn
        self._subscribe_oper = subscribe_oper
        self._read = task_data_read
        self._update = task_data_update
        self._get_histories = get_histories_fn
        self._delete_media_file = delete_media_file_fn
        self._delete_history = delete_history_fn
        self._send_dfd = send_download_file_deleted_fn
        self._send_subscribe_added = send_subscribe_added_fn
        self._notify = notify_fn
        self._season_of = season_of_fn
        self._related_downloads = related_downloads_fn
        self._best_version_type = best_version_type
        self._clear_history_type = clear_history_type
        self._plugin_name = plugin_name

    def check_complete(self, subscribe, mediainfo,
                       no_exists_episodes: Optional[list] = None) -> bool:
        """洗版完成判定：priority 达标 + F 稳定 + SeasonScope 目标集全覆盖。"""
        if not self._priority.is_complete(subscribe):
            return False

        signal: CompletionSignal = self._evaluate(subscribe, mediainfo)
        if not signal.stable:
            return False

        if no_exists_episodes:
            return False

        return True

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
        return payload

    def start_best_version(self, subscribe, mediainfo):
        """普通订阅完成后按配置自动创建洗版订阅。

        分集下载洗版只在历史上存在多次分集下载时创建，避免单次全集包完成后误进入洗版。
        """
        if not self._subscribe_oper or not mediainfo:
            return None
        if subscribe.best_version:
            return None
        if not self._type_matches(subscribe, self._best_version_type):
            return None
        is_movie = self._is_movie(subscribe)
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
        # 普通剧集订阅完成后直接进入全集洗版，才能在新资源下载前执行整季旧版本清理。
        if not is_movie:
            payload["best_version_full"] = 1
        payload = {key: value for key, value in payload.items() if value is not None}
        sid, _err = self._subscribe_oper.add(mediainfo=mediainfo, **payload)
        if sid:
            logger.info(f"洗版编排：{format_subscribe_desc(subscribe)} 已创建洗版订阅（id={sid}）")
            if self._send_subscribe_added:
                self._send_subscribe_added(sid, mediainfo, username=self._plugin_name)
            if self._notify:
                text = f"评分：{mediainfo.vote_average}，来自用户：{self._plugin_name}"
                self._notify(
                    f"{format_subscribe_desc(subscribe)} 已添加洗版订阅",
                    text,
                    image=mediainfo.get_message_image(),
                    link="#/subscribe/movie?tab=mysub" if is_movie else "#/subscribe/tv?tab=mysub",
                )
        return sid

    def handle_resource_download_history_clear(self, subscribe, context=None, episodes=None):
        """ResourceDownload 阶段清理旧整理记录的源文件，并发送 DownloadFileDeleted。

        仅整季洗版执行；分集洗版逐集替换，不做整季清理。clear_history_type 按媒体类型门控，
        源文件删除与历史下载种子移除均属于破坏性副作用。
        """
        if not subscribe.best_version:
            return
        if not self._type_matches(subscribe, self._clear_history_type):
            return
        if not subscribe.best_version_full:
            detail(f"洗版清理：{format_subscribe_desc(subscribe)} 是分集洗版，不清理整季旧文件")
            return
        tmdbid = subscribe.tmdbid
        if not tmdbid or not self._get_histories:
            return
        season = self._season_of(subscribe) if self._season_of else subscribe.season
        histories = self._get_histories(tmdbid, subscribe.type, season) or []
        if not histories:
            return
        self.clear_transfer_src_histories(subscribe, histories)

    def clear_transfer_src_histories(self, subscribe, histories):
        """删除源文件与整理历史，并保存 TransferIntercept 阶段消费的清理快照。

        快照 key 统一为 str(tmdbid)，避免写入与读取类型不一致；旧媒体库目标文件必须等
        主程序整理新文件前再删，因此由后续 TransferIntercept 消费。
        """
        tmdbid = str(subscribe.tmdbid or "")
        if not tmdbid:
            return

        def updater(data: dict) -> dict:
            data[tmdbid] = {
                "subscribe_id": subscribe.id,
                "subscribe_desc": format_subscribe_desc(subscribe),
                "histories": [self._history_to_dict(h) for h in histories],
                "time": time.time(),
            }
            return data

        if self._update:
            self._update("best_version_clear_histories", updater)

        logger.info(f"洗版清理：{format_subscribe_desc(subscribe)} 开始删除 {len(histories)} 条旧整理记录的源文件（不可逆）")
        for history in histories:
            src_fileitem = self._field(history, "src_fileitem")
            if src_fileitem and self._delete_media_file:
                self._delete_media_file(src_fileitem)
            if self._send_dfd:
                self._send_dfd(self._field(history, "src"), self._field(history, "download_hash"))
            history_id = self._field(history, "id")
            if history_id is not None and self._delete_history:
                self._delete_history(history_id)

        if self._notify:
            self._notify(
                f"{format_subscribe_desc(subscribe)} 即将开始洗版下载",
                f"已删除 {len(histories)} 条整理记录对应的源文件",
            )

    def handle_history_clear(self, event) -> bool:
        """TransferIntercept 阶段按清理快照删除旧媒体库目标文件，成功后移除快照。"""
        data = event.event_data
        if not data or data.cancel:
            return False
        mediainfo = data.mediainfo
        tmdb_id = mediainfo.tmdb_id if mediainfo else None
        if tmdb_id is None or not self._read:
            return False
        key = str(tmdb_id)
        snapshots = self._read("best_version_clear_histories") or {}
        task = snapshots.get(key)
        if not task:
            return False
        if self.clear_transfer_dest_histories(task):
            def updater(data: dict) -> dict:
                data.pop(key, None)
                return data
            if self._update:
                self._update("best_version_clear_histories", updater)
            return True
        return False

    def clear_transfer_dest_histories(self, task) -> bool:
        """删除清理快照中的媒体库目标文件；空快照也视为已处理。"""
        histories = (task or {}).get("histories") or []
        if histories:
            detail(f"洗版整理拦截：删除 {len(histories)} 条旧整理记录对应的媒体库文件（不可逆）")
        for history in histories:
            dest_fileitem = history.get("dest_fileitem") if isinstance(history, dict) else None
            if dest_fileitem and self._delete_media_file:
                self._delete_media_file(dest_fileitem)
        if self._notify:
            self._notify(
                f"{(task or {}).get('subscribe_desc', '洗版订阅')} 即将开始洗版整理",
                f"已删除 {len(histories)} 条整理记录对应的媒体库文件",
            )
        return True

    def _type_matches(self, subscribe, type_setting) -> bool:
        """判断媒体类型是否落在洗版或清理范围：no/all/movie/tv/tv_episode。"""
        if type_setting == "no":
            return False
        if type_setting == "all":
            return True
        is_movie = self._is_movie(subscribe)
        if type_setting == "movie":
            return is_movie
        if type_setting in ("tv", "tv_episode"):
            return not is_movie
        return False

    @staticmethod
    def _is_movie(subscribe) -> bool:
        """按主程序媒体类型枚举判断电影，兼容 DB 字符串与枚举对象。"""
        media_type = getattr(subscribe, "type", None)
        if isinstance(media_type, MediaType):
            return media_type == MediaType.MOVIE
        value = getattr(media_type, "value", media_type)
        return value == MediaType.MOVIE.value

    @staticmethod
    def _field(history, name):
        """兼容 TransferHistory 对象与 dict 两种整理记录形态。"""
        if isinstance(history, dict):
            return history.get(name)
        return getattr(history, name, None)

    @staticmethod
    def _history_to_dict(history) -> dict:
        """把整理记录转换为可持久化到清理快照的 dict。"""
        if isinstance(history, dict):
            return history
        to_dict = getattr(history, "to_dict", None)
        return to_dict() if callable(to_dict) else dict(getattr(history, "__dict__", {}))
