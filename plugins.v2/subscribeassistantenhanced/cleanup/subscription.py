"""订阅清理编排：下载前清源记录，整理前清旧目标文件。"""
import re
import time
from typing import Callable, Optional

from app.core.metainfo import MetaInfo
from app.log import logger
from app.schemas.types import MediaType
from app.utils.string import StringUtils

from ..shared.log import detail
from ..shared.subscribe import (
    format_subscribe_desc,
    is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
    resolve_subscribe_media_type,
)

SUBSCRIPTION_CLEANUP_TTL_SECONDS = 72 * 3600
SUBSCRIPTION_CLEANUP_SNAPSHOT_KEY = "subscription_cleanup_histories"


class SubscriptionCleanup:
    """订阅清理事务编排器。

    事务顺序固定为：保存快照、删除旧源文件、发送 DownloadFileDeleted、删除整理记录、
    等待旧 hash 释放；目标媒体库文件延迟到 TransferIntercept 阶段按快照删除。
    """

    def __init__(self,
                 task_data_read: Optional[Callable] = None,
                 task_data_update: Optional[Callable] = None,
                 get_histories_fn: Optional[Callable] = None,
                 delete_media_file_fn: Optional[Callable] = None,
                 delete_history_fn: Optional[Callable] = None,
                 send_download_file_deleted_fn: Optional[Callable] = None,
                 notify_fn: Optional[Callable] = None,
                 get_subscribe_image_fn: Optional[Callable] = None,
                 season_of_fn: Optional[Callable] = None,
                 torrent_exists_fn: Optional[Callable] = None,
                 sleep_fn: Optional[Callable] = None,
                 cleanup_history_type: str = "no",
                 cleanup_history_scenes: Optional[list] = None):
        """注入清理事务依赖和媒体类型/场景门控配置。"""
        self._read = task_data_read
        self._update = task_data_update
        self._get_histories = get_histories_fn
        self._delete_media_file = delete_media_file_fn
        self._delete_history = delete_history_fn
        self._send_dfd = send_download_file_deleted_fn
        self._notify = notify_fn
        self._get_subscribe_image = get_subscribe_image_fn
        self._season_of = season_of_fn
        self._torrent_exists = torrent_exists_fn
        self._sleep = sleep_fn or time.sleep
        self._cleanup_history_type = cleanup_history_type
        self._cleanup_history_scenes = list(cleanup_history_scenes or [])

    def handle_resource_download_history_clear(self, subscribe, context=None, episodes=None) -> bool:
        """清理旧整理记录并等待关联下载任务释放，允许继续下载时返回 True。

        订阅清理只在媒体类型和场景都命中配置时进入破坏性事务。剧集按本次目标集过滤整理记录；
        明确存在的旧 hash 最多等待 3 分钟，查询失败最多等待 1 分钟，达到上限后降级放行。
        """
        media_type = resolve_subscribe_media_type(subscribe)
        if not self._cleanup_enabled_for(subscribe, media_type):
            return True
        scene = self._cleanup_scene(subscribe)
        mode_label = self._cleanup_scene_label(scene, media_type)
        if scene == "best_version" and media_type == MediaType.TV and context and getattr(context, "torrent_info", None):
            actual_episodes, source = self._download_resource_episodes(context=context, episodes=episodes)
            target_episodes = self._subscribe_target_episodes(subscribe)
            if actual_episodes and target_episodes and not set(target_episodes).issubset(actual_episodes):
                self._notify_history_clear_skipped(
                    subscribe=subscribe,
                    context=context,
                    target_episodes=target_episodes,
                    actual_episodes=actual_episodes,
                    source=source,
                )
                return True
        tmdbid = subscribe.tmdbid
        if not tmdbid or self._get_histories is None:
            return True
        season = self._history_season(subscribe) if media_type == MediaType.TV else None
        if media_type == MediaType.TV and season is None:
            logger.warning(
                f"订阅清理：{format_subscribe_desc(subscribe)} {mode_label}无法确定有效季号，"
                "为避免扩大清理范围，跳过旧整理记录清理"
            )
            return True
        target_episodes = []
        if media_type == MediaType.TV:
            target_episodes = self._clear_target_episodes(subscribe, context=context, episodes=episodes, scene=scene)
            if not target_episodes:
                logger.warning(
                    f"订阅清理：{format_subscribe_desc(subscribe)} {mode_label}无法确定本次目标集，"
                    "为避免扩大清理范围，跳过旧整理记录清理"
                )
                return True
        histories = self._get_histories(tmdbid, subscribe.type, season) or []
        if media_type == MediaType.TV:
            histories = self._filter_histories_by_episodes(histories, target_episodes)
        if not histories:
            logger.info(
                f"订阅清理：{format_subscribe_desc(subscribe)} {mode_label}未找到匹配的整理记录，"
                f"查询季号={season or '无'}，跳过清理"
            )
            return True
        self.clear_transfer_src_histories(
            subscribe=subscribe,
            histories=histories,
            media_type=media_type,
            season=season,
            scene=scene,
            target_episodes=target_episodes,
        )
        old_hashes = {
            self._field(history, "download_hash")
            for history in histories
            if self._field(history, "download_hash")
        }
        return self._wait_for_torrents_removed(subscribe=subscribe, download_hashes=old_hashes)

    def _clear_target_episodes(self, subscribe, context=None, episodes=None, scene: str = "") -> list[int]:
        """返回订阅清理目标集范围；洗版用订阅范围，其余场景用本次资源范围。"""
        if scene == "best_version":
            return self._subscribe_target_episodes(subscribe)
        target_episodes, _source = self._download_resource_episodes(context=context, episodes=episodes)
        return target_episodes

    @staticmethod
    def _subscribe_target_episodes(subscribe) -> list[int]:
        """返回剧集订阅明确声明的目标集数范围。"""
        if not subscribe or not subscribe.total_episode:
            return []
        start_episode = subscribe.start_episode or 1
        return list(range(start_episode, subscribe.total_episode + 1))

    @staticmethod
    def _normalize_episode_numbers(episodes) -> list[int]:
        """规整事件或标题中的集数，忽略不能转换为正整数的值。"""
        normalized = set()
        for episode in episodes or []:
            try:
                number = int(episode)
            except (TypeError, ValueError):
                continue
            if number > 0:
                normalized.add(number)
        return sorted(normalized)

    def _download_resource_episodes(self, context=None, episodes=None) -> tuple[list[int], str]:
        """按下载事件、上下文和资源标题顺序解析本次资源覆盖的集数。"""
        event_episodes = self._normalize_episode_numbers(episodes)
        if event_episodes:
            return event_episodes, "下载事件"

        selected_episodes = self._normalize_episode_numbers(
            getattr(context, "selected_episodes", None)
        )
        if selected_episodes:
            return selected_episodes, "下载上下文"

        torrent_info = getattr(context, "torrent_info", None)
        if not torrent_info:
            return [], ""
        meta = MetaInfo(
            title=getattr(torrent_info, "title", "") or "",
            subtitle=getattr(torrent_info, "description", "") or "",
        )
        title_episodes = self._normalize_episode_numbers(meta.episode_list)
        if title_episodes:
            return title_episodes, "资源标题"
        return [], ""

    @staticmethod
    def _history_episode_numbers(history) -> set[int]:
        """解析整理记录中的 E01、E01-E03 或逗号分隔集数，用于按集收窄范围。"""
        raw = SubscriptionCleanup._field(history, "episodes")
        if not raw:
            return set()
        text = str(raw)
        numbers = set()
        for start, end in re.findall(r"E?(\d+)\s*-\s*E?(\d+)", text, flags=re.IGNORECASE):
            first, last = int(start), int(end)
            if first <= last:
                numbers.update(range(first, last + 1))
        for number in re.findall(r"(?<!\d)(?:E)?(\d+)(?!\d)", text, flags=re.IGNORECASE):
            numbers.add(int(number))
        return {number for number in numbers if number > 0}

    @classmethod
    def _filter_histories_by_episodes(cls, histories, target_episodes: list[int]):
        """只保留与目标集有交集的整理记录；无法判断集数的记录不参与剧集按集清理。"""
        targets = set(target_episodes or [])
        if not targets:
            return []
        return [
            history for history in histories or []
            if cls._history_episode_numbers(history) & targets
        ]

    def _notify_history_clear_skipped(self, subscribe, context, target_episodes: list[int],
                                      actual_episodes: list[int], source: str):
        """全集资源范围不足时保留旧文件，并发送可人工核对的保护通知。"""
        torrent_info = getattr(context, "torrent_info", None)
        torrent_title = getattr(torrent_info, "title", "") if torrent_info else ""
        target_desc = StringUtils.format_ep(target_episodes) if target_episodes else "未知"
        actual_desc = StringUtils.format_ep(actual_episodes) if actual_episodes else "未知"
        source_desc = source or "未知来源"
        logger.warning(
            f"订阅清理：{format_subscribe_desc(subscribe)} "
            f"原因=全集资源未覆盖订阅目标范围（目标集数={target_desc}，资源集数={actual_desc}，"
            f"来源={source_desc}，种子={torrent_title}），处理=已跳过历史清理，后续=请人工核对资源覆盖范围"
        )
        if self._notify:
            image = self._get_subscribe_image(subscribe) if self._get_subscribe_image else None
            self._notify(
                f"{format_subscribe_desc(subscribe)} 洗版资源未覆盖目标范围，已跳过历史清理",
                text=(
                    f"目标集数：{target_desc}\n"
                    f"资源集数：{actual_desc}\n"
                    f"种子：{torrent_title}"
                ),
                follow_up="请人工核对资源覆盖范围",
                diagnostic=True,
                image=image,
            )

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
                            f"订阅清理：{format_subscribe_desc(subscribe)} {self._mode_label(subscribe)}"
                            "累计 60 秒无法查询旧下载任务，"
                            f"降级放行 hash={download_hash}"
                        )
                        continue
                    next_pending_hashes.add(download_hash)
                    continue
                if exists:
                    exists_wait[download_hash] += 5
                    if exists_wait[download_hash] >= 180:
                        logger.warning(
                            f"订阅清理：{format_subscribe_desc(subscribe)} {self._mode_label(subscribe)}"
                            "旧下载任务持续存在 180 秒，"
                            f"降级放行 hash={download_hash}"
                        )
                        continue
                    next_pending_hashes.add(download_hash)
            pending_hashes = next_pending_hashes
            if not pending_hashes:
                logger.info(
                    f"订阅清理：{format_subscribe_desc(subscribe)} {self._mode_label(subscribe)}旧下载任务确认完成，"
                    f"等待 {waited_seconds} 秒后继续下载"
                )
                return True
            detail(
                f"订阅清理：{format_subscribe_desc(subscribe)} {self._mode_label(subscribe)}等待旧下载任务释放 "
                f"({waited_seconds}/180 秒)，剩余 {len(pending_hashes)} 个"
            )
        logger.warning(
            f"订阅清理：{format_subscribe_desc(subscribe)} {self._mode_label(subscribe)}"
            "等待旧下载任务达到 180 秒总上限，"
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
                f"订阅清理：{format_subscribe_desc(subscribe)} {self._mode_label(subscribe)}季号无效，"
                f"无法匹配整理记录：{season}"
            )
            return None

    def clear_transfer_src_histories(self, subscribe, histories, media_type: Optional[MediaType] = None,
                                     season: Optional[str] = None, scene: Optional[str] = None,
                                     target_episodes: Optional[list[int]] = None):
        """删除源文件与整理历史，并保存 TransferIntercept 阶段消费的清理快照。

        快照 key 按媒体身份、场景和目标集生成；旧媒体库目标文件必须等主程序整理新文件前再删，
        因此由后续 TransferIntercept 按同一媒体和集范围消费，避免同 TMDB 并发下载互相覆盖。
        """
        tmdbid = str(subscribe.tmdbid or "")
        if not tmdbid:
            return
        subscribe_image = self._get_subscribe_image(subscribe) if self._get_subscribe_image else None
        media_type = media_type or resolve_subscribe_media_type(subscribe)
        season = season if season is not None else (self._history_season(subscribe) if media_type == MediaType.TV else None)
        scene = scene or self._cleanup_scene(subscribe)
        target_episodes = self._normalize_episode_numbers(target_episodes)
        task_key = self._task_key(
            tmdbid=subscribe.tmdbid,
            media_type=media_type,
            season=season,
            scene=scene,
            target_episodes=target_episodes,
        )

        def updater(data: dict) -> dict:
            data[task_key] = {
                "subscribe_id": subscribe.id,
                "subscribe_desc": format_subscribe_desc(subscribe),
                "subscribe_image": subscribe_image,
                "tmdbid": subscribe.tmdbid,
                "type": media_type.value if isinstance(media_type, MediaType) else str(media_type or ""),
                "season": season,
                "scene": scene,
                "target_episodes": target_episodes,
                "mode_label": self._cleanup_scene_label(scene, media_type),
                "histories": [self._history_to_dict(h) for h in histories],
                "time": time.time(),
            }
            return data

        if self._update:
            self._update(SUBSCRIPTION_CLEANUP_SNAPSHOT_KEY, updater)

        mode_label = self._cleanup_scene_label(scene, media_type)
        logger.info(
            f"订阅清理：{format_subscribe_desc(subscribe)} {mode_label}开始删除 "
            f"{len(histories)} 条旧整理记录的源文件（不可逆）"
        )
        source_file_deleted = 0
        source_paths = []
        download_notice_total = 0
        download_notice_sent = 0
        history_delete_total = 0
        history_deleted = 0
        for history in histories:
            src_fileitem = self._field(history, "src_fileitem")
            if src_fileitem and self._delete_media_file:
                self._delete_media_file(src_fileitem)
                source_file_deleted += 1
            source_path = self._fileitem_path(src_fileitem) or self._field(history, "src")
            if source_path:
                source_paths.append(str(source_path))
            if src_fileitem:
                download_notice_total += 1
                if self._send_dfd:
                    self._send_dfd(self._field(history, "src"), self._field(history, "download_hash"))
                    download_notice_sent += 1
            history_id = self._field(history, "id")
            if history_id is not None:
                history_delete_total += 1
            if history_id is not None and self._delete_history:
                self._delete_history(history_id)
                history_deleted += 1

        logger.info(
            f"订阅清理：{format_subscribe_desc(subscribe)} {mode_label}源文件清理完成，"
            f"整理记录 {history_deleted}/{history_delete_total} 条，"
            f"源文件 {source_file_deleted}/{len(histories)} 个，"
            f"下载记录通知 {download_notice_sent}/{download_notice_total} 个"
        )

        if self._notify:
            self._notify(
                f"{format_subscribe_desc(subscribe)} "
                f"即将开始{mode_label}下载，已删除 {len(histories)} 条整理记录对应的源文件",
                text=self._single_episode_cleanup_text(target_episodes, source_paths),
                image=subscribe_image,
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
        snapshots = self._read(SUBSCRIPTION_CLEANUP_SNAPSHOT_KEY) or {}
        task_key, task = self._match_clear_history_task(key, data, snapshots)
        if not task:
            return False
        if self._clear_history_task_expired(task):
            detail(f"订阅整理拦截：TMDB {key} 的清理事务已超过 72 小时，丢弃且不删除媒体库文件")
            return False
        if self.clear_transfer_dest_histories(task):
            self._remove_clear_history_task(task_key)
            return True
        return False

    def _match_clear_history_task(self, tmdb_key: str, event_data, snapshots: dict) -> tuple[Optional[str], Optional[dict]]:
        """按媒体身份和整理目标集匹配待消费清理事务，避免同 TMDB 不同集互相覆盖。"""
        event_episodes = self._event_target_episodes(event_data)
        event_media_type = self._event_media_type(event_data)
        event_season = self._event_season(event_data, event_media_type)
        for key, task in (snapshots or {}).items():
            task_tmdbid = str((task or {}).get("tmdbid") or key)
            if task_tmdbid != tmdb_key:
                continue
            task_type = task.get("type")
            if event_media_type and task_type and task_type != event_media_type.value:
                continue
            if task_type == MediaType.TV.value and task.get("season") is not None:
                if event_season is None or task.get("season") != event_season:
                    continue
            task_episodes = set(self._normalize_episode_numbers(task.get("target_episodes")))
            if task_episodes:
                if not event_episodes or not (task_episodes & set(event_episodes)):
                    continue
            return str(key), task
        return None, None

    def _event_target_episodes(self, event_data) -> list[int]:
        """从整理拦截事件的 meta、源文件或目标路径解析本次整理集数。"""
        meta = getattr(event_data, "meta", None)
        episodes = self._normalize_episode_numbers(getattr(meta, "episode_list", None))
        if episodes:
            return episodes
        fileitem = getattr(event_data, "fileitem", None)
        path_text = " ".join(
            str(value) for value in (
                getattr(fileitem, "path", None),
                getattr(event_data, "target_path", None),
            )
            if value
        )
        return sorted(self._path_episode_numbers(path_text))

    @staticmethod
    def _path_episode_numbers(text: str) -> set[int]:
        """从文件路径解析显式集数标记，避免把 Sxx、年份、分辨率等数字当作集数。"""
        if not text:
            return set()
        numbers = set()
        for start, end in re.findall(r"(?i)(?:S\d{1,4})?E(\d{1,4})\s*-\s*(?:S\d{1,4})?E?(\d{1,4})", text):
            first, last = int(start), int(end)
            if first <= last:
                numbers.update(range(first, last + 1))
        for number in re.findall(r"(?i)S\d{1,4}E(\d{1,4})(?!\d)", text):
            numbers.add(int(number))
        for number in re.findall(r"(?i)(?<![A-Z0-9])E(\d{1,4})(?!\d)", text):
            numbers.add(int(number))
        for number in re.findall(r"第\s*(\d{1,4})\s*[集话話]", text):
            numbers.add(int(number))
        return {number for number in numbers if number > 0}

    @staticmethod
    def _event_media_type(event_data) -> Optional[MediaType]:
        """从整理拦截事件媒体信息解析媒体类型，缺失时不作为匹配条件。"""
        mediainfo = getattr(event_data, "mediainfo", None)
        media_type = getattr(mediainfo, "type", None)
        if isinstance(media_type, MediaType):
            return media_type
        if isinstance(media_type, str):
            try:
                return MediaType(media_type)
            except ValueError:
                return None
        return None

    @staticmethod
    def _event_season(event_data, media_type: Optional[MediaType]) -> Optional[str]:
        """按整理拦截事件季号生成主程序整理历史使用的 Sxx 口径。"""
        if media_type != MediaType.TV:
            return None
        mediainfo = getattr(event_data, "mediainfo", None)
        meta = getattr(event_data, "meta", None)
        meta_season = getattr(meta, "begin_season", None)
        season = meta_season if meta_season is not None else getattr(mediainfo, "season", None)
        if season is None:
            return None
        try:
            return f"S{int(season):02d}"
        except (TypeError, ValueError):
            return None

    def cleanup_expired_clear_histories(self) -> int:
        """清理超过 72 小时或缺少有效时间戳的订阅清理事务。"""
        snapshots = self._read(SUBSCRIPTION_CLEANUP_SNAPSHOT_KEY) if self._read else {}
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

        self._update(SUBSCRIPTION_CLEANUP_SNAPSHOT_KEY, updater)
        return len(expired_keys)

    @staticmethod
    def _clear_history_task_expired(task: dict) -> bool:
        """判断破坏性清理事务是否仍处于允许消费的 72 小时窗口。"""
        created_at = (task or {}).get("time")
        if not isinstance(created_at, (int, float)):
            return True
        return time.time() - created_at > SUBSCRIPTION_CLEANUP_TTL_SECONDS

    def _remove_clear_history_task(self, key: str):
        """按事务键删除已消费或失效的订阅清理事务。"""
        if not self._update:
            return

        def updater(data: dict) -> dict:
            data.pop(key, None)
            return data

        self._update(SUBSCRIPTION_CLEANUP_SNAPSHOT_KEY, updater)

    def clear_transfer_dest_histories(self, task) -> bool:
        """删除清理快照中的媒体库目标文件；空快照也视为已处理。"""
        histories = (task or {}).get("histories") or []
        mode_label = (task or {}).get("mode_label") or "订阅"
        if histories:
            detail(f"订阅整理拦截：{mode_label}删除 {len(histories)} 条旧整理记录对应的媒体库文件（不可逆）")
        dest_paths = []
        for history in histories:
            dest_fileitem = history.get("dest_fileitem") if isinstance(history, dict) else None
            if dest_fileitem and self._delete_media_file:
                self._delete_media_file(dest_fileitem)
            dest_path = self._fileitem_path(dest_fileitem) or (history.get("dest") if isinstance(history, dict) else None)
            if dest_path:
                dest_paths.append(str(dest_path))
        dest_file_total = sum(
            1 for history in histories
            if isinstance(history, dict) and history.get("dest_fileitem")
        )
        logger.info(
            f"订阅整理拦截：{(task or {}).get('subscribe_desc', '订阅')} "
            f"{mode_label}媒体库文件清理完成，目标文件 {dest_file_total}/{len(histories)} 个"
        )
        if self._notify:
            self._notify(
                f"{(task or {}).get('subscribe_desc', '订阅')} "
                f"即将开始{mode_label}整理，已删除 {len(histories)} 条整理记录对应的媒体库文件",
                text=self._single_episode_cleanup_text((task or {}).get("target_episodes"), dest_paths),
                image=(task or {}).get("subscribe_image"),
            )
        return True

    @staticmethod
    def _fileitem_path(fileitem) -> Optional[str]:
        """从整理记录序列化的 FileItem 中取路径，用于单集清理通知。"""
        if isinstance(fileitem, dict):
            return fileitem.get("path")
        return None

    @classmethod
    def _single_episode_cleanup_text(cls, target_episodes, paths: list[str]) -> Optional[str]:
        """单集清理通知附带具体路径；多集或无路径时保持摘要通知。"""
        if len(cls._normalize_episode_numbers(target_episodes)) != 1:
            return None
        clean_paths = [path for path in paths if path]
        if not clean_paths:
            return None
        return "清理路径：\n" + "\n".join(clean_paths)

    @staticmethod
    def _mode_label(subscribe) -> str:
        """按订阅清理场景返回用户可见标签。"""
        media_type = resolve_subscribe_media_type(subscribe)
        return SubscriptionCleanup._cleanup_scene_label(
            SubscriptionCleanup._cleanup_scene(subscribe),
            media_type,
        )

    @staticmethod
    def _cleanup_scene(subscribe) -> str:
        """按订阅下载形态归类订阅清理场景。"""
        if is_full_best_version_subscribe(subscribe):
            return "best_version"
        if is_tv_episode_best_version_subscribe(subscribe):
            return "best_version_episode"
        return "normal"

    @staticmethod
    def _cleanup_scene_label(scene: str, media_type: Optional[MediaType] = None) -> str:
        """返回订阅清理场景的用户可见名称。"""
        if scene == "best_version":
            return "洗版"
        if scene == "best_version_episode":
            return "分集洗版"
        return {
            "normal": "普通订阅",
        }.get(scene, "订阅")

    def _cleanup_enabled_for(self, subscribe, media_type: MediaType) -> bool:
        """清理范围和场景同时命中时才允许执行破坏性订阅清理事务。"""
        if not self._type_matches(media_type, self._cleanup_history_type):
            return False
        return self._cleanup_scene(subscribe) in self._cleanup_history_scenes

    @classmethod
    def _task_key(cls, tmdbid, media_type: MediaType, season: Optional[str],
                  scene: str, target_episodes: Optional[list[int]]) -> str:
        """生成订阅清理事务键；同一 TMDB 的不同场景和集范围必须互不覆盖。"""
        media_value = media_type.value if isinstance(media_type, MediaType) else str(media_type or "")
        episodes = ",".join(str(episode) for episode in cls._normalize_episode_numbers(target_episodes))
        return "|".join([
            str(tmdbid or ""),
            media_value,
            season or "",
            scene or "",
            episodes or "all",
        ])

    @staticmethod
    def _type_matches(media_type: MediaType, type_setting) -> bool:
        """判断媒体类型是否落在清理范围：no/all/movie/tv。"""
        if media_type == MediaType.UNKNOWN:
            return False
        if type_setting == "no":
            return False
        if type_setting == "all":
            return True
        if type_setting == "movie":
            return media_type == MediaType.MOVIE
        if type_setting == "tv":
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
