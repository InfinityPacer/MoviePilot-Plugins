"""洗版全流程编排：订阅创建、完成判定与破坏性历史清理。"""
import time
from typing import Callable, Optional

from app.log import logger
from app.schemas.types import MediaType

from ..engine.types import CompletionSignal
from ..shared.log import detail
from ..shared.subscribe import format_subscribe_desc, resolve_subscribe_media_type
from .priority import PriorityManager

BEST_VERSION_CLEAR_HISTORY_TTL_SECONDS = 72 * 3600


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
                 torrent_exists_fn: Optional[Callable] = None,
                 sleep_fn: Optional[Callable] = None,
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
        self._torrent_exists = torrent_exists_fn
        self._sleep = sleep_fn or time.sleep
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
        media_type = resolve_subscribe_media_type(subscribe)
        if not self._type_matches(media_type, self._best_version_type):
            return None
        is_movie = media_type == MediaType.MOVIE
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

    def handle_resource_download_history_clear(self, subscribe, context=None, episodes=None) -> bool:
        """清理旧整理记录并等待关联下载任务释放，允许继续下载时返回 True。

        仅整季洗版执行；分集洗版逐集替换，不做整季清理。clear_history_type 按媒体类型门控，
        源文件删除与历史下载种子移除均属于破坏性副作用。明确存在的旧 hash 最多等待
        3 分钟，查询失败最多等待 1 分钟，达到上限后降级放行。
        """
        if not subscribe.best_version:
            return True
        media_type = resolve_subscribe_media_type(subscribe)
        if not self._type_matches(media_type, self._clear_history_type):
            return True
        if not subscribe.best_version_full:
            detail(f"洗版清理：{format_subscribe_desc(subscribe)} 是分集洗版，不清理整季旧文件")
            return True
        tmdbid = subscribe.tmdbid
        if not tmdbid or not self._get_histories:
            return True
        season = self._history_season(subscribe)
        if media_type == MediaType.TV and not season:
            logger.warning(
                f"洗版清理：{format_subscribe_desc(subscribe)} 无法确定有效季号，"
                "为避免扩大清理范围，跳过旧整理记录清理"
            )
            return True
        histories = self._get_histories(tmdbid, subscribe.type, season) or []
        if not histories:
            logger.info(
                f"洗版清理：{format_subscribe_desc(subscribe)} 未找到匹配的整理记录，"
                f"查询季号={season or '无'}，跳过清理"
            )
            return True
        self.clear_transfer_src_histories(subscribe, histories)
        old_hashes = {
            self._field(history, "download_hash")
            for history in histories
            if self._field(history, "download_hash")
        }
        return self._wait_for_torrents_removed(subscribe=subscribe, download_hashes=old_hashes)

    def _wait_for_torrents_removed(self, subscribe, download_hashes: set[str]) -> bool:
        """每 5 秒确认旧 hash：查询失败等 1 分钟，明确存在等 3 分钟，超限后放行。"""
        if not download_hashes or not self._torrent_exists:
            # 删除事件由主程序异步处理，即使无法确认 hash，也保留固定的首轮处理窗口。
            self._sleep(5)
            return True
        pending_hashes = set(download_hashes)
        exists_wait = {download_hash: 0 for download_hash in pending_hashes}
        query_failure_wait = {download_hash: 0 for download_hash in pending_hashes}
        for waited_seconds in range(5, 181, 5):
            self._sleep(5)
            next_pending_hashes = set()
            for download_hash in pending_hashes:
                # DownloadFileDeleted 会跨下载器删除旧任务，确认时也必须跨下载器查询。
                exists = self._torrent_exists(download_hash)
                if exists is None:
                    query_failure_wait[download_hash] += 5
                    if query_failure_wait[download_hash] >= 60:
                        logger.warning(
                            f"洗版清理：{format_subscribe_desc(subscribe)} 累计 60 秒无法查询旧下载任务，"
                            f"降级放行 hash={download_hash}"
                        )
                        continue
                    next_pending_hashes.add(download_hash)
                    continue
                if exists:
                    exists_wait[download_hash] += 5
                    if exists_wait[download_hash] >= 180:
                        logger.warning(
                            f"洗版清理：{format_subscribe_desc(subscribe)} 旧下载任务持续存在 180 秒，"
                            f"降级放行 hash={download_hash}"
                        )
                        continue
                    next_pending_hashes.add(download_hash)
            pending_hashes = next_pending_hashes
            if not pending_hashes:
                logger.info(
                    f"洗版清理：{format_subscribe_desc(subscribe)} 旧下载任务确认完成，"
                    f"等待 {waited_seconds} 秒后继续下载"
                )
                return True
            detail(
                f"洗版清理：{format_subscribe_desc(subscribe)} 等待旧下载任务释放 "
                f"({waited_seconds}/180 秒)，剩余 {len(pending_hashes)} 个"
            )
        logger.warning(
            f"洗版清理：{format_subscribe_desc(subscribe)} 等待旧下载任务达到 180 秒总上限，"
            f"降级放行剩余 {len(pending_hashes)} 个 hash"
        )
        return True

    def _history_season(self, subscribe) -> Optional[str]:
        """按主程序整理历史口径把订阅季号转换为 Sxx。"""
        if self._season_of:
            return self._season_of(subscribe)
        season = subscribe.season
        if season is None:
            return None
        try:
            return f"S{int(season):02d}"
        except (TypeError, ValueError):
            logger.warning(
                f"洗版清理：{format_subscribe_desc(subscribe)} 季号无效，"
                f"无法匹配整理记录：{season}"
            )
            return None

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
        if self._clear_history_task_expired(task):
            self._remove_clear_history_task(key)
            detail(f"洗版整理拦截：TMDB {key} 的清理事务已超过 72 小时，丢弃且不删除媒体库文件")
            return False
        if self.clear_transfer_dest_histories(task):
            self._remove_clear_history_task(key)
            return True
        return False

    def cleanup_expired_clear_histories(self) -> int:
        """清理超过 72 小时或缺少有效时间戳的洗版文件清理事务。"""
        snapshots = self._read("best_version_clear_histories") if self._read else {}
        expired_keys = [
            str(key) for key, task in (snapshots or {}).items()
            if self._clear_history_task_expired(task)
        ]
        if not expired_keys or not self._update:
            return 0

        def updater(data: dict) -> dict:
            for key in expired_keys:
                data.pop(key, None)
            return data

        self._update("best_version_clear_histories", updater)
        return len(expired_keys)

    @staticmethod
    def _clear_history_task_expired(task: dict) -> bool:
        """判断破坏性清理事务是否仍处于允许消费的 72 小时窗口。"""
        created_at = (task or {}).get("time")
        if not isinstance(created_at, (int, float)):
            return True
        return time.time() - created_at > BEST_VERSION_CLEAR_HISTORY_TTL_SECONDS

    def _remove_clear_history_task(self, key: str):
        """按 TMDBID 删除已消费或失效的洗版清理事务。"""
        if not self._update:
            return

        def updater(data: dict) -> dict:
            data.pop(key, None)
            return data

        self._update("best_version_clear_histories", updater)

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

    @staticmethod
    def _type_matches(media_type: MediaType, type_setting) -> bool:
        """判断媒体类型是否落在洗版或清理范围：no/all/movie/tv/tv_episode。"""
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
