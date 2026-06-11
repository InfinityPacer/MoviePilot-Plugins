"""域 ⑤：洗版编排入口 + 洗版完成判定 + 洗版清理。"""
import time
from typing import Callable, Optional

from app.log import logger

from ..engine.types import CompletionSignal
from ..shared.log import detail
from ..shared.subscribe import format_subscribe_desc
from .priority import PriorityManager


class BestVersionOrchestrator:
    """洗版全流程编排。

    洗版清理涉及删除源文件 / 媒体库文件，均经注入回调执行，避免流程直接绑定下载器或文件系统实现。
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
                 notify_fn: Optional[Callable] = None,
                 season_of_fn: Optional[Callable] = None,
                 best_version_type: str = "no",
                 clear_history_type: str = "no"):
        """注入洗版流程依赖、自动洗版范围与破坏性清理范围。"""
        self._priority = priority_manager
        self._evaluate = evaluate_fn
        self._subscribe_oper = subscribe_oper
        self._read = task_data_read
        self._update = task_data_update
        self._get_histories = get_histories_fn
        self._delete_media_file = delete_media_file_fn
        self._delete_history = delete_history_fn
        self._send_dfd = send_download_file_deleted_fn
        self._notify = notify_fn
        self._season_of = season_of_fn
        self._best_version_type = best_version_type
        self._clear_history_type = clear_history_type

    def check_complete(self, subscribe, mediainfo,
                       no_exists_episodes: Optional[list] = None) -> bool:
        """洗版完成判定：priority 达标 + F 稳定 + 目标范围全覆盖。"""
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
        """订阅完成后按洗版类型自动创建洗版订阅（best_version=1）。

        name/tmdbid/type 由 mediainfo 提供，payload 只带洗版相关设置（季/剧集组/保存路径/站点/过滤）。
        """
        if not self._subscribe_oper or not mediainfo:
            return None
        if subscribe.best_version:
            return None
        if not self._type_matches(subscribe, self._best_version_type):
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
        payload = {key: value for key, value in payload.items() if value is not None}
        sid, _err = self._subscribe_oper.add(mediainfo=mediainfo, **payload)
        if sid:
            logger.info(f"洗版编排：{format_subscribe_desc(subscribe)} 订阅完成后自动创建洗版订阅（id={sid}）")
        return sid

    def handle_resource_download_history_clear(self, subscribe, context=None, episodes=None):
        """ResourceDownload 阶段：洗版下载前清理旧整理记录的源文件 + 源历史，并发 DownloadFileDeleted。

        仅整季洗版（best_version_full）执行——分集洗版逐集替换、整季清理无意义；清理为破坏性操作。
        ``clear_history_type=no`` 关闭清理，其余取值按媒体类型限制范围；源文件删除经注入回调，单测 mock 不真删。
        """
        if not subscribe.best_version:
            return
        if not self._type_matches(subscribe, self._clear_history_type):
            return
        if not subscribe.best_version_full:
            detail(f"洗版清理：{format_subscribe_desc(subscribe)} 非整季洗版，跳过历史清理（分集洗版逐集替换）")
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
        """删源文件 + 源整理历史，并对每条记录发 DownloadFileDeleted（携带旧 download_hash，
        主程序据此移除历史下载的旧种子）。删除前把记录快照存入 best_version_clear_histories，
        key 统一用 str(tmdbid)，供 TransferIntercept 阶段按媒体 tmdb_id 消费（两侧 str 一致避免漏删）。"""
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

        logger.info(f"洗版清理：{format_subscribe_desc(subscribe)} 开始清理 {len(histories)} 条整理记录的源文件（不可逆）")
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

    def handle_history_clear(self, event):
        """TransferIntercept 阶段：按快照删除旧媒体库目标文件，成功后移除该快照。"""
        data = event.event_data
        if not data or data.cancel:
            return
        mediainfo = data.mediainfo
        tmdb_id = mediainfo.tmdb_id if mediainfo else None
        if tmdb_id is None or not self._read:
            return
        key = str(tmdb_id)
        snapshots = self._read("best_version_clear_histories") or {}
        task = snapshots.get(key)
        if not task:
            return
        if self.clear_transfer_dest_histories(task):
            def updater(data: dict) -> dict:
                data.pop(key, None)
                return data
            if self._update:
                self._update("best_version_clear_histories", updater)

    def clear_transfer_dest_histories(self, task) -> bool:
        """删除快照内每条整理记录的媒体库目标文件（dest_fileitem，非源文件、非种子）；空记录也视为成功。"""
        histories = (task or {}).get("histories") or []
        if histories:
            detail(f"洗版整理拦截：清理 {len(histories)} 条整理记录对应的媒体库目标文件（不可逆）")
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
        """媒体类型是否落在洗版/清理范围内：no=全不匹配；all=全匹配；movie/tv/tv_episode 按订阅类型匹配。"""
        if type_setting == "no":
            return False
        if type_setting == "all":
            return True
        is_movie = subscribe.type == "电影"
        if type_setting == "movie":
            return is_movie
        if type_setting in ("tv", "tv_episode"):
            return not is_movie
        return False

    @staticmethod
    def _field(history, name):
        """兼容 TransferHistory 对象与 dict 两种历史记录形态的取值。"""
        if isinstance(history, dict):
            return history.get(name)
        return getattr(history, name, None)

    @staticmethod
    def _history_to_dict(history) -> dict:
        """历史记录转 dict 存快照：对象用 to_dict()，已是 dict 直接用。"""
        if isinstance(history, dict):
            return history
        to_dict = getattr(history, "to_dict", None)
        return to_dict() if callable(to_dict) else dict(getattr(history, "__dict__", {}))
