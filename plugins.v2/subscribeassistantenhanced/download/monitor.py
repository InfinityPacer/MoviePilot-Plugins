"""下载生命周期状态机、自动删种与下载待定管理。"""
import hashlib
import re
import time
from typing import Callable, Optional

from app.log import logger
from app.schemas.types import MediaType

from .torrent import TorrentInfo
from ..shared.log import detail, format_log_title_desc
from ..shared.subscribe import format_subscribe_label, resolve_subscribe_media_type

TIMEOUT_MANUAL_REVIEW_IGNORE_HOURS = 24


class DownloadMonitor:
    """下载状态机：DOWNLOADING → TIMEOUT_CHECK → DELETED/MANUAL_REVIEW/IGNORED。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 timeout_minutes: int = 180,
                 progress_threshold: int = 5,
                 retry_limit: int = 3,
                 tracker_keywords: Optional[list] = None,
                 exclude_tags: Optional[list] = None,
                 subscribe_oper=None,
                 fetch_fn: Optional[Callable] = None,
                 present_fn: Optional[Callable] = None,
                 manual_delete_enabled: bool = True,
                 manual_miss_threshold: int = 2,
                 pending_download_enabled: bool = True,
                 state_coordinator=None,
                 pending_hash_grace_seconds: int = 10 * 60):
        """保存下载检查参数；下载中待定开关不影响自动删种检查。"""
        self._read = task_data_read
        self._update = task_data_update
        self._timeout_seconds = timeout_minutes * 60
        self._progress_threshold = progress_threshold
        self._retry_limit = retry_limit
        self._tracker_keywords = tracker_keywords or []
        self._exclude_tags = exclude_tags or []
        self._subscribe_oper = subscribe_oper
        # fetch_fn(downloader, hash) -> TorrentInfo；未注入时不判定、不删种。
        self._fetch_fn = fetch_fn
        # present_fn(downloader, hash) -> Optional[bool]：True=存在，False=可达但不存在，None=不可判定。
        self._present_fn = present_fn
        # 关闭监听手动删除时，仍清理本地失效任务，但不触发删种善后。
        self._manual_delete_enabled = manual_delete_enabled
        # 连续 miss 达阈值才判手动删除，避免下载器瞬断触发误删善后。
        self._manual_miss_threshold = manual_miss_threshold
        self._pending_download_enabled = pending_download_enabled
        self._state = state_coordinator
        self._pending_hash_grace_seconds = pending_hash_grace_seconds

    def mark_download_pending(self, subscribe_id: int, torrent_hash: str):
        """记录订阅还有下载未整理完成。"""
        if not self._pending_download_enabled:
            return
        sid = str(subscribe_id)
        now = time.time()

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            pending = task.get("download_pending", {})
            pending[torrent_hash] = {"hash": torrent_hash, "started_at": now}
            task["download_pending"] = pending
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def mark_download_started(self, subscribe, episodes=None, downloader: Optional[str] = None,
                              enclosure: Optional[str] = None, page_url: Optional[str] = None,
                              title: Optional[str] = None, description: Optional[str] = None):
        """ResourceDownload 阶段登记无 hash 下载待定，覆盖 DownloadAdded 前的完成检查空窗。"""
        if not self._pending_download_enabled or not subscribe:
            return
        sid = str(subscribe.id)
        now = time.time()
        key = self._pending_key(enclosure=enclosure, page_url=page_url, title=title)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            pending = task.get("download_pending", {})
            pending[key] = {
                "hash": None,
                "started_at": now,
                "episodes": list(episodes or []),
                "downloader": downloader,
                "enclosure": enclosure,
                "page_url": page_url,
                "title": title,
                "description": description,
            }
            task["download_pending"] = pending
            data[sid] = task
            return data

        self._update("subscribes", updater)
        if self._state:
            self._state.mark_active(subscribe, source="download_pending", reason="下载已发起，等待下载器确认任务")

    def clear_download_pending(self, subscribe_id: int, torrent_hash: str):
        """清除指定下载任务对应的待定记录。"""
        sid = str(subscribe_id)
        result = {"had_pending": False, "active": False}

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            pending = task.get("download_pending", {})
            result["had_pending"] = torrent_hash in pending
            pending.pop(torrent_hash, None)
            if not pending:
                task.pop("download_pending", None)
            else:
                task["download_pending"] = pending
                result["active"] = True
            data[sid] = task
            return data

        self._update("subscribes", updater)
        if result["had_pending"] and not result["active"] and self._state:
            subscribe = self._resolve_subscribe(subscribe_id)
            if subscribe:
                self._state.clear_active(subscribe, source="download_pending", reason="下载待定已清除")

    def has_active_downloads(self, subscribe_id: int) -> bool:
        """检查订阅是否还有下载未整理完成。"""
        sid = str(subscribe_id)
        data = self._read("subscribes")
        task = data.get(sid, {})
        return self._drop_expired_hashless_pending(subscribe_id, task)

    def on_download(self, subscribe_id, torrent_hash: str, episodes=None,
                    downloader: Optional[str] = None, progress: float = 0.0,
                    enclosure: Optional[str] = None, page_url: Optional[str] = None,
                    title: Optional[str] = None, description: Optional[str] = None):
        """DownloadAdded 阶段按 hash 登记种子监控与归属信息。

        enclosure 用于洗版按集基线回滚，enclosure/page_url 用于删除指纹防重；
        此阶段 hash 已确定，同时补齐 ResourceDownload 建立的无 hash 待定。
        """
        if not torrent_hash:
            return
        now = time.time()

        def updater(data: dict) -> dict:
            data[torrent_hash] = {
                "hash": torrent_hash,
                "subscribe_id": subscribe_id,
                "episodes": list(episodes or []),
                "downloader": downloader,
                "enclosure": enclosure,
                "page_url": page_url,
                "title": title,
                "description": description,
                "baseline_progress": progress,
                "baseline_at": now,
                "retry_count": 0,
                "manual_review_count": 0,
                "time": now,
            }
            return data

        self._update("torrents", updater)
        if subscribe_id and self._pending_download_enabled:
            self._confirm_download_pending(
                subscribe_id,
                torrent_hash,
                episodes=episodes,
                downloader=downloader,
                enclosure=enclosure,
                page_url=page_url,
                title=title,
                description=description,
                now=now,
            )

    def run_timeout_check(self, cleanup=None):
        """定时巡检种子实时状态，将超时、Tracker 命中与手动删除交给 cleanup 善后。

        fetch_fn 未注入时安全空操作；完成或本地失效任务会释放下载待定。
        只有启用监听手动删除且 present_fn 明确返回 False，才进入删除善后。
        """
        torrents = self._read("torrents") or {}
        total = len(torrents)
        if total == 0:
            detail("下载监控：当前没有记录中的下载任务，跳过本轮检查")
            return
        if not self._fetch_fn:
            detail(f"下载监控：无法读取下载器状态，本轮不检查 {total} 个下载任务")
            return
        visible_count = 0
        skipped_count = 0
        missing_realtime_count = 0
        no_present_check_count = 0
        unknown_present_count = 0
        present_exists_count = 0
        pending_miss_count = 0
        cleanup_count = 0
        removed_count = 0
        triggered_subscribe_ids = set()
        for torrent_hash, task in list(torrents.items()):
            downloader = task.get("downloader")
            info = self._fetch_fn(downloader, torrent_hash)
            if info:
                visible_count += 1
                self._reset_missing(torrent_hash)
                if info.completed:
                    logger.info(
                        f"下载监控：种子 {self._format_torrent_desc(torrent_hash, task)} 已完成，"
                        f"{self._format_task_subscribe_label(task)}，"
                        f"关联集数={self._format_task_episodes(task)}，将从订阅下载任务中移除"
                    )
                    self._clean_local_torrent_task(task.get("subscribe_id"), torrent_hash)
                    removed_count += 1
                    continue
                action = self.check_torrent(info, task.get("subscribe_id"))
                if action in ("timeout", "delete_tracker") and cleanup:
                    subscribe = self._resolve_subscribe(task.get("subscribe_id"))
                    if subscribe is not None:
                        reason_text = "Tracker 返回内容包含删除关键字" if action == "delete_tracker" else "连续观察后仍无进度"
                        logger.info(
                            f"下载监控：种子 {self._format_torrent_desc(torrent_hash, task)} 需要删除，"
                            f"{self._format_task_subscribe_label(task)}，"
                            f"关联集数={self._format_task_episodes(task)}，原因：{reason_text}"
                        )
                        reason_detail = (
                            self.get_timeout_reason(task.get("subscribe_id"), task, info)
                            if action == "timeout" else None
                        )
                        self._handle_cleanup_once_per_subscribe(
                            cleanup, subscribe, triggered_subscribe_ids,
                            torrent_hash, reason=action,
                            reason_detail=reason_detail,
                            downloader=downloader, delete_from_downloader=True)
                        cleanup_count += 1
                elif action == "manual_review" and cleanup:
                    subscribe = self._resolve_subscribe(task.get("subscribe_id"))
                    if subscribe is not None:
                        cleanup.handle_timeout_manual_review(
                            subscribe,
                            torrent_hash,
                            self.get_timeout_reason(task.get("subscribe_id"), task, info),
                            ignore_hours=TIMEOUT_MANUAL_REVIEW_IGNORE_HOURS,
                        )
                continue
            # 拿不到实时状态时，只有下载器可达且连续确认种子不存在，才按用户手动删除处理。
            missing_realtime_count += 1
            if not self._present_fn:
                no_present_check_count += 1
                skipped_count += 1
                continue
            present = self._present_fn(downloader, torrent_hash) if self._present_fn else None
            if present is not False:
                if present is True:
                    present_exists_count += 1
                else:
                    unknown_present_count += 1
                skipped_count += 1
                continue
            if not self._manual_delete_enabled:
                logger.info(
                    f"下载监控：种子 {self._format_torrent_desc(torrent_hash, task)} 不在下载器中，"
                    f"{self._format_task_subscribe_label(task)}，"
                    f"关联集数={self._format_task_episodes(task)}，将按失效下载任务清理"
                )
                self._clean_local_torrent_task(task.get("subscribe_id"), torrent_hash)
                removed_count += 1
                self._reset_missing(torrent_hash)
                continue
            if self._bump_missing(torrent_hash) < self._manual_miss_threshold:
                pending_miss_count += 1
                skipped_count += 1
                continue
            subscribe = self._resolve_subscribe(task.get("subscribe_id"))
            if self._manual_delete_enabled and subscribe is not None and cleanup:
                logger.info(
                    f"下载监控：种子 {self._format_torrent_desc(torrent_hash, task)} "
                    f"连续 {self._manual_miss_threshold} 次不在下载器中，"
                    f"{self._format_task_subscribe_label(task)}，"
                    f"关联集数={self._format_task_episodes(task)}，按用户手动删除处理"
                )
                self._handle_cleanup_once_per_subscribe(
                    cleanup, subscribe, triggered_subscribe_ids,
                    torrent_hash, reason="manual",
                    downloader=downloader, delete_from_downloader=False)
                cleanup_count += 1
            else:
                logger.info(
                    f"下载监控：种子 {self._format_torrent_desc(torrent_hash, task)} 不在下载器中，"
                    f"{self._format_task_subscribe_label(task)}，"
                    f"关联集数={self._format_task_episodes(task)}，将按失效下载任务清理"
                )
                self._clean_local_torrent_task(task.get("subscribe_id"), torrent_hash)
                removed_count += 1
            self._reset_missing(torrent_hash)
        skip_detail = self._format_skip_summary(
            missing_realtime_count=missing_realtime_count,
            no_present_check_count=no_present_check_count,
            unknown_present_count=unknown_present_count,
            present_exists_count=present_exists_count,
            pending_miss_count=pending_miss_count,
            skipped_count=skipped_count,
        )
        detail(
            f"下载监控：本轮检查 {total} 个下载任务，下载器中仍存在 {visible_count} 个，"
            f"{skip_detail}，已处理删除 {cleanup_count} 个，从订阅下载任务移除 {removed_count} 个"
        )

    def _format_task_subscribe_label(self, task: dict) -> str:
        """下载任务日志中的订阅标签；优先展示订阅名、季号和订阅 ID。"""
        subscribe_id = (task or {}).get("subscribe_id")
        subscribe = self._resolve_subscribe(subscribe_id)
        return format_subscribe_label(subscribe, subscribe_id)

    @staticmethod
    def _format_task_episodes(task: dict) -> str:
        """格式化下载任务关联集数，未知集数保持可诊断。"""
        episodes = (task or {}).get("episodes") or []
        if not episodes:
            return "未知"
        return ",".join(str(episode) for episode in episodes)

    @staticmethod
    def _format_torrent_desc(torrent_hash: str, task: dict) -> str:
        """格式化种子标题和内容；hash 固定放在括号中，便于日志检索。"""
        title_desc = format_log_title_desc(
            title=(task or {}).get("title"),
            description=(task or {}).get("description"),
        )
        return f"{title_desc} ({torrent_hash})" if title_desc else f"({torrent_hash})"

    @staticmethod
    def _format_skip_summary(missing_realtime_count: int,
                             no_present_check_count: int,
                             unknown_present_count: int,
                             present_exists_count: int,
                             pending_miss_count: int,
                             skipped_count: int) -> str:
        """把保守跳过的下载任务拆成可诊断原因，便于区分连接失败和去抖保护。"""
        if skipped_count <= 0:
            return "暂不处理 0 个"
        parts = [f"暂不处理 {skipped_count} 个"]
        if missing_realtime_count:
            parts.append(f"未取到实时任务信息 {missing_realtime_count} 个")
        if no_present_check_count:
            parts.append(f"缺少任务存在性确认能力 {no_present_check_count} 个")
        if unknown_present_count:
            parts.append(f"无法确认任务是否仍存在 {unknown_present_count} 个")
        if present_exists_count:
            parts.append(f"存在性确认仍在下载器中 {present_exists_count} 个")
        if pending_miss_count:
            parts.append(f"连续缺失未达阈值 {pending_miss_count} 个")
        parts.append("建议检查下载器连接、下载器别名配置和本轮任务是否刚被客户端刷新")
        return "，".join(parts)

    def _resolve_subscribe(self, subscribe_id):
        """按 subscribe_id 解析订阅对象，供删种善后与优先级回滚使用。"""
        if self._subscribe_oper and subscribe_id:
            return self._subscribe_oper.get(subscribe_id)
        return None

    @staticmethod
    def _handle_cleanup_once_per_subscribe(cleanup, subscribe, triggered_subscribe_ids: set,
                                           torrent_hash: str, **kwargs):
        """同一轮同一订阅只允许首个删种善后触发补搜，其余种子仍完整清理。"""
        if subscribe.id in triggered_subscribe_ids:
            cleanup.handle_torrent_deleted(subscribe, torrent_hash, search_enabled=False, **kwargs)
            return
        triggered_subscribe_ids.add(subscribe.id)
        cleanup.handle_torrent_deleted(subscribe, torrent_hash, **kwargs)

    def _clean_local_torrent_task(self, subscribe_id: int, torrent_hash: str):
        """只清理本地下载任务和下载待定，不记录坏种、不回滚优先级、不触发补搜。"""
        self._remove_torrent_task(torrent_hash)
        if subscribe_id:
            self.clear_download_pending(subscribe_id, torrent_hash)
            self._remove_subscribe_torrent_task(subscribe_id, torrent_hash)

    def _remove_torrent_task(self, torrent_hash: str):
        """从下载任务表移除指定 hash。"""
        def updater(data: dict) -> dict:
            data.pop(torrent_hash, None)
            return data

        self._update("torrents", updater)

    def _remove_subscribe_torrent_task(self, subscribe_id: int, torrent_hash: str):
        """移除订阅内 subscribes.torrent_tasks 的同名种子任务。"""
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            torrent_tasks = task.get("torrent_tasks")
            if torrent_tasks:
                task["torrent_tasks"] = [
                    item for item in torrent_tasks
                    if item.get("hash") != torrent_hash
                ]
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def _confirm_download_pending(self, subscribe_id, torrent_hash: str, episodes=None,
                                  downloader: Optional[str] = None,
                                  enclosure: Optional[str] = None,
                                  page_url: Optional[str] = None,
                                  title: Optional[str] = None,
                                  description: Optional[str] = None,
                                  now: Optional[float] = None):
        """DownloadAdded 补齐下载待定 hash，优先复用 ResourceDownload 的无 hash 记录。"""
        sid = str(subscribe_id)
        now = now or time.time()

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            pending = task.get("download_pending", {})
            matched_key = self._find_hashless_pending_key(pending, enclosure=enclosure, page_url=page_url)
            base = pending.pop(matched_key, {}) if matched_key else {}
            pending[torrent_hash] = {
                "hash": torrent_hash,
                "started_at": base.get("started_at", now),
                "episodes": list(episodes if episodes is not None else base.get("episodes") or []),
                "downloader": downloader or base.get("downloader"),
                "enclosure": enclosure or base.get("enclosure"),
                "page_url": page_url or base.get("page_url"),
                "title": title or base.get("title"),
                "description": description or base.get("description"),
            }
            task["download_pending"] = pending
            data[sid] = task
            return data

        self._update("subscribes", updater)
        subscribe = self._resolve_subscribe(subscribe_id)
        if subscribe and self._state:
            self._state.mark_active(subscribe, source="download_pending", reason="下载器已创建任务，等待整理入库")

    def _drop_expired_hashless_pending(self, subscribe_id: int, task: dict) -> bool:
        """清理超过宽限期仍未补 hash 的下载待定，并返回是否仍有活跃下载。"""
        pending = (task or {}).get("download_pending") or {}
        if not pending:
            return False
        now = time.time()
        kept = {}
        changed = False
        for key, item in pending.items():
            if item.get("hash"):
                kept[key] = item
                continue
            try:
                started_at = float(item.get("started_at") or 0)
            except (TypeError, ValueError):
                started_at = 0
            if started_at > 0 and now - started_at <= self._pending_hash_grace_seconds:
                kept[key] = item
                continue
            changed = True
            detail(f"下载待定：订阅 {subscribe_id} 发起下载后超过 {self._pending_hash_grace_seconds} 秒仍未创建下载器任务，解除下载待定")
        if not changed:
            return True

        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            sub_task = data.get(sid, {})
            if kept:
                sub_task["download_pending"] = kept
            else:
                sub_task.pop("download_pending", None)
            data[sid] = sub_task
            return data

        self._update("subscribes", updater)
        if not kept and self._state:
            subscribe = self._resolve_subscribe(subscribe_id)
            if subscribe:
                self._state.clear_active(subscribe, source="download_pending", reason="下载器长时间未确认任务")
        return bool(kept)

    @staticmethod
    def _pending_key(enclosure: Optional[str] = None, page_url: Optional[str] = None,
                     title: Optional[str] = None) -> str:
        """生成无 hash 下载待定 key，优先使用 enclosure/page_url/title 指纹。"""
        raw = enclosure or page_url or title or str(time.time())
        return f"pending:{hashlib.sha1(raw.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _find_hashless_pending_key(pending: dict, enclosure: Optional[str] = None,
                                   page_url: Optional[str] = None) -> Optional[str]:
        """按 enclosure/page_url 匹配 ResourceDownload 写入的无 hash 待定。"""
        for key, item in pending.items():
            if item.get("hash"):
                continue
            if enclosure and item.get("enclosure") == enclosure:
                return key
            if page_url and item.get("page_url") == page_url:
                return key
        return None

    def _bump_missing(self, torrent_hash: str) -> int:
        """累加下载器可达但种子不存在的连续 miss 次数。"""
        result = {"count": 0}

        def updater(data: dict) -> dict:
            task = data.get(torrent_hash, {})
            task["missing_count"] = task.get("missing_count", 0) + 1
            result["count"] = task["missing_count"]
            data[torrent_hash] = task
            return data

        self._update("torrents", updater)
        return result["count"]

    def _reset_missing(self, torrent_hash: str):
        """种子恢复可见或已处理后，清零连续不存在次数。"""
        def updater(data: dict) -> dict:
            task = data.get(torrent_hash)
            if task and "missing_count" in task:
                task.pop("missing_count", None)
                data[torrent_hash] = task
            return data

        self._update("torrents", updater)

    def check_torrent(self, torrent_info: TorrentInfo, subscribe_id: int) -> str:
        """检查种子状态，返回 ok/timeout/delete_tracker/manual_review/ignored。"""
        if self._should_exclude(torrent_info):
            return "ignored"

        if self._matches_tracker_keywords(torrent_info):
            detail(f"下载监控：种子 {torrent_info.hash} 的 Tracker 返回内容包含删除关键字 {self._tracker_keywords}")
            return "delete_tracker"

        torrent_task = self._get_torrent_task(torrent_info.hash)

        if torrent_info.completed:
            return "ok"

        if not torrent_task:
            self._init_torrent_task(torrent_info)
            return "ok"

        if self._has_progress(torrent_info, torrent_task):
            self._refresh_baseline(torrent_info)
            self._clear_timeout_state(subscribe_id, torrent_task)
            return "ok"

        elapsed = time.time() - torrent_task.get("baseline_at", time.time())
        if elapsed < self._timeout_seconds:
            return "ok"

        if self._is_timeout_ignore_active(subscribe_id, torrent_info.hash, torrent_task):
            detail(f"下载监控：种子 {torrent_info.hash} 处于连续低进度保护期，本轮跳过")
            return "ignored"

        timeout_state = self._record_timeout_failure(subscribe_id, torrent_info.hash, torrent_task)
        retry_limit = max(int(self._retry_limit or 1), 1)
        if timeout_state.get("fail_count", 0) >= retry_limit:
            self._mark_timeout_manual_review(subscribe_id, torrent_task)
            detail(f"下载监控：种子 {torrent_info.hash} 已达到连续低进度保护上限，本轮保留种子并等待人工确认")
            return "manual_review"

        detail(
            f"下载监控：种子 {torrent_info.hash} 低进度超时"
            f"（低进度删除 {timeout_state.get('fail_count', 0)}/{retry_limit} 次），准备删除"
        )
        return "timeout"

    def _should_exclude(self, info: TorrentInfo) -> bool:
        if not self._exclude_tags:
            return False
        return any(tag in self._exclude_tags for tag in info.tags)

    def _matches_tracker_keywords(self, info: TorrentInfo) -> bool:
        if not self._tracker_keywords:
            return False
        for response in info.tracker_responses:
            for kw in self._tracker_keywords:
                if self._tracker_keyword_matches(kw, response):
                    return True
        return False

    @staticmethod
    def _tracker_keyword_matches(keyword: str, response: str) -> bool:
        """Tracker 关键字优先按正则匹配；表达式非法时退回大小写不敏感文本包含。"""
        try:
            return bool(re.search(keyword, response, flags=re.IGNORECASE))
        except re.error:
            return keyword.lower() in response.lower()

    def _get_torrent_task(self, torrent_hash: str) -> Optional[dict]:
        data = self._read("torrents")
        return data.get(torrent_hash)

    def _init_torrent_task(self, info: TorrentInfo):
        def updater(data: dict) -> dict:
            data[info.hash] = {
                "baseline_progress": info.progress,
                "baseline_at": time.time(),
                "retry_count": 0,
                "manual_review_count": 0,
            }
            return data
        self._update("torrents", updater)

    def _has_progress(self, info: TorrentInfo, task: dict) -> bool:
        baseline = task.get("baseline_progress", 0.0)
        diff = (info.progress - baseline) * 100
        return diff >= self._progress_threshold

    def _refresh_baseline(self, info: TorrentInfo):
        def updater(data: dict) -> dict:
            task = data.get(info.hash, {})
            task["baseline_progress"] = info.progress
            task["baseline_at"] = time.time()
            data[info.hash] = task
            return data
        self._update("torrents", updater)

    def _increment_retry(self, torrent_hash: str, current: int):
        def updater(data: dict) -> dict:
            task = data.get(torrent_hash, {})
            task["retry_count"] = current + 1
            data[torrent_hash] = task
            return data
        self._update("torrents", updater)

    def _mark_manual_review(self, torrent_hash: str):
        """首次 timeout 后写 manual_review_count，再次 timeout 转 MANUAL_REVIEW。"""
        def updater(data: dict) -> dict:
            task = data.get(torrent_hash, {})
            task["manual_review_count"] = task.get("manual_review_count", 0) + 1
            data[torrent_hash] = task
            return data
        self._update("torrents", updater)

    def _timeout_scope_key(self, subscribe_id: int, torrent_task: dict) -> str:
        """生成连续低进度统计范围；剧集按季和集数，其他订阅按 movie 兜底。"""
        subscribe = self._resolve_subscribe(subscribe_id)
        media_type = resolve_subscribe_media_type(subscribe)
        if media_type == MediaType.TV:
            episodes = torrent_task.get("episodes") or []
            if not isinstance(episodes, list):
                episodes = [episodes]
            episode_key = ",".join(sorted(str(ep) for ep in episodes if ep is not None)) or "unknown"
            season = subscribe.season if subscribe else None
            return f"tv:{season if season is not None else 'unknown'}:{episode_key}"
        return "movie"

    def _record_timeout_failure(self, subscribe_id: int, torrent_hash: str, torrent_task: dict) -> dict:
        """按订阅范围记录低进度超时次数，换种子后仍继承同一 scope 的保护计数。"""
        sid = str(subscribe_id)
        scope_key = self._timeout_scope_key(subscribe_id, torrent_task)
        now = time.time()
        result = {"state": {}}

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            states = task.get("timeout_states", {})
            state = states.get(scope_key, {})
            try:
                window_start = float(state.get("window_start") or now)
            except (TypeError, ValueError):
                window_start = now
            if self._timeout_retry_window_seconds() and now - window_start > self._timeout_retry_window_seconds():
                state = {}
                window_start = now
            state["fail_count"] = int(state.get("fail_count") or 0) + 1
            state["window_start"] = window_start
            state["last_fail_time"] = now
            state["last_torrent_hash"] = torrent_hash
            states[scope_key] = state
            task["timeout_states"] = states
            data[sid] = task
            result["state"] = state
            return data

        self._update("subscribes", updater)
        return result["state"]

    def get_timeout_reason(self, subscribe_id: int, torrent_task: dict, torrent_info: TorrentInfo) -> str:
        """描述下载时长、观察窗口、进度增长和连续超时次数。"""
        scope_key = self._timeout_scope_key(subscribe_id, torrent_task)
        subscribe_task = (self._read("subscribes") or {}).get(str(subscribe_id), {})
        timeout_state = (subscribe_task.get("timeout_states") or {}).get(scope_key, {})
        started_at = torrent_task.get("time") or torrent_task.get("baseline_at") or time.time()
        download_hours = max(time.time() - started_at, 0) / 3600
        progress_delta = (torrent_info.progress - torrent_task.get("baseline_progress", 0.0)) * 100
        timeout_hours = self._timeout_seconds / 3600
        retry_limit = max(int(self._retry_limit or 1), 1)
        return (
            f"订阅种子，下载时长 {download_hours:.2f} 小时，"
            f"超时窗口 {timeout_hours:g} 小时内进度增长 {progress_delta:.2f}%，"
            f"低于 {self._progress_threshold:g}%"
            f"（低进度删除 {timeout_state.get('fail_count', 0)}/{retry_limit} 次）"
        )

    def _timeout_retry_window_seconds(self) -> float:
        """连续低进度统计窗口：至少 24 小时，或超时窗口乘保护次数。"""
        return max(24 * 3600, self._timeout_seconds * max(int(self._retry_limit or 1), 1))

    def _is_timeout_ignore_active(self, subscribe_id: int, torrent_hash: str, torrent_task: dict) -> bool:
        """读取人工保护期：同一 hash 在 ignore_until 前不再重复计数或处理。"""
        sid = str(subscribe_id)
        scope_key = self._timeout_scope_key(subscribe_id, torrent_task)
        task = (self._read("subscribes") or {}).get(sid, {})
        state = (task.get("timeout_states") or {}).get(scope_key, {})
        try:
            ignore_until = float(state.get("ignore_until") or 0)
        except (TypeError, ValueError):
            ignore_until = 0
        return state.get("last_torrent_hash") == torrent_hash and ignore_until > time.time()

    def _mark_timeout_manual_review(self, subscribe_id: int, torrent_task: dict):
        """达到连续低进度保护上限后，给当前范围写入人工处理保护期。"""
        sid = str(subscribe_id)
        scope_key = self._timeout_scope_key(subscribe_id, torrent_task)
        ignore_until = time.time() + TIMEOUT_MANUAL_REVIEW_IGNORE_HOURS * 3600

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            states = task.get("timeout_states", {})
            state = states.get(scope_key, {})
            state["ignore_until"] = ignore_until
            states[scope_key] = state
            task["timeout_states"] = states
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def _clear_timeout_state(self, subscribe_id: int, torrent_task: dict):
        """进度恢复增长时清理同一订阅范围的连续低进度状态。"""
        sid = str(subscribe_id)
        scope_key = self._timeout_scope_key(subscribe_id, torrent_task)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            states = task.get("timeout_states")
            if states:
                states.pop(scope_key, None)
                task["timeout_states"] = states
                data[sid] = task
            return data

        self._update("subscribes", updater)
