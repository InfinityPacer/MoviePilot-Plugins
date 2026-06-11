"""域 ⑥：下载超时检测 + 进度监控 + tracker 关键字删种 + 人工保护期。"""
import time
from typing import Callable, Optional

from app.log import logger

from .torrent import TorrentInfo
from ..shared.log import detail


class DownloadMonitor:
    """下载生命周期状态机：DOWNLOADING → TIMEOUT_CHECK → DELETED/MANUAL_REVIEW/IGNORED。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 timeout_minutes: int = 180,
                 progress_threshold: int = 5,
                 retry_limit: int = 3,
                 tracker_keywords: Optional[list] = None,
                 exclude_tags: Optional[list] = None,
                 subscribe_oper=None,
                 fetch_fn: Optional[Callable] = None,
                 present_fn: Optional[Callable] = None,
                 manual_miss_threshold: int = 2,
                 pending_download_enabled: bool = True):
        """保存下载监控参数；pending_download_enabled 只控制下载中待定标记，不影响删种监控。"""
        self._read = task_data_read
        self._update = task_data_update
        self._timeout_seconds = timeout_minutes * 60
        self._progress_threshold = progress_threshold
        self._retry_limit = retry_limit
        self._tracker_keywords = tracker_keywords or []
        self._exclude_tags = exclude_tags or []
        self._subscribe_oper = subscribe_oper
        # 连下载器取实时种子状态的回调 fetch_fn(downloader, hash)->TorrentInfo；
        # 未注入时超时巡检为安全空操作（无实时数据则不判定、不删种）
        self._fetch_fn = fetch_fn
        # present_fn(downloader, hash)->Optional[bool]：True=在；False=下载器可达但不存在；None=不可判定。
        # 仅用于手动删除监听，把"用户删种"与"下载器瞬断"分开；未注入时不做手动删除检测。
        self._present_fn = present_fn
        # 连续确认"可达且不存在" miss 达到该阈值才判手动删除，去抖避免单次抖动误判。
        self._manual_miss_threshold = manual_miss_threshold
        self._pending_download_enabled = pending_download_enabled

    def mark_download_pending(self, subscribe_id: int, torrent_hash: str):
        """标记任务数据中的下载待定（不写 subscribe.state）。"""
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            pending = task.get("download_pending", {})
            pending[torrent_hash] = {"started_at": time.time()}
            task["download_pending"] = pending
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def clear_download_pending(self, subscribe_id: int, torrent_hash: str):
        """清除下载待定标记。"""
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            pending = task.get("download_pending", {})
            pending.pop(torrent_hash, None)
            if not pending:
                task.pop("download_pending", None)
            else:
                task["download_pending"] = pending
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def has_active_downloads(self, subscribe_id: int) -> bool:
        """检查是否存在进行中的下载。"""
        sid = str(subscribe_id)
        data = self._read("subscribes")
        task = data.get(sid, {})
        return bool(task.get("download_pending"))

    def on_download(self, subscribe_id, torrent_hash: str, episodes=None,
                    downloader: Optional[str] = None, progress: float = 0.0,
                    enclosure: Optional[str] = None, page_url: Optional[str] = None,
                    title: Optional[str] = None):
        """DownloadAdded 登记种子监控条目：按 hash 记归属订阅/集数/下载器/进度基线/重试计数，
        并记 enclosure/page_url/title——删除时据 enclosure 做洗版优先级按集归属回滚、
        据 enclosure/page_url 归档删除指纹防重选。

        超时巡检的输入即来自这里——hash 在 DownloadAdded 阶段才确定（ResourceDownload 阶段还没有），
        故监控登记必须放在本事件。开启下载中待定时同步写标记，供守门 has_active_downloads 判定。
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
                "baseline_progress": progress,
                "baseline_at": now,
                "retry_count": 0,
                "manual_review_count": 0,
                "time": now,
            }
            return data

        self._update("torrents", updater)
        if subscribe_id and self._pending_download_enabled:
            self.mark_download_pending(subscribe_id, torrent_hash)

    def run_timeout_check(self, cleanup=None):
        """定时巡检监控中的种子：取实时状态判定，超时/Tracker 命中则交 cleanup 删种善后。

        实时状态经注入的 fetch_fn(downloader, hash)->TorrentInfo 获取；未注入 fetch_fn 时直接跳过，
        保证未接入下载器实时数据时巡检为安全空操作（不会误删）。subscribe 经 subscribe_oper 解析。
        """
        if not self._fetch_fn:
            return
        torrents = self._read("torrents") or {}
        for torrent_hash, task in list(torrents.items()):
            downloader = task.get("downloader")
            info = self._fetch_fn(downloader, torrent_hash)
            if info:
                self._reset_missing(torrent_hash)
                action = self.check_torrent(info, task.get("subscribe_id"))
                if action in ("timeout", "delete_tracker") and cleanup:
                    subscribe = self._resolve_subscribe(task.get("subscribe_id"))
                    if subscribe is not None:
                        reason_text = "Tracker 关键字命中" if action == "delete_tracker" else "超时无进度"
                        logger.info(f"下载监控：种子 {torrent_hash} 判定删种（{reason_text}），交清理流程善后")
                        cleanup.handle_torrent_deleted(
                            subscribe, torrent_hash, reason=action,
                            downloader=downloader, delete_from_downloader=True)
                continue
            # 拿不到实时状态：仅当下载器可达且明确"不存在"且连续 miss 达阈值才算手动删除，否则按瞬断跳过
            present = self._present_fn(downloader, torrent_hash) if self._present_fn else None
            if present is not False:
                continue
            if self._bump_missing(torrent_hash) < self._manual_miss_threshold:
                continue
            subscribe = self._resolve_subscribe(task.get("subscribe_id"))
            if subscribe is not None and cleanup:
                logger.info(f"下载监控：种子 {torrent_hash} 在下载器中连续 {self._manual_miss_threshold} 次确认消失（疑似手动删除），触发善后")
                cleanup.handle_torrent_deleted(
                    subscribe, torrent_hash, reason="manual",
                    downloader=downloader, delete_from_downloader=False)
            self._reset_missing(torrent_hash)

    def _resolve_subscribe(self, subscribe_id):
        """按 subscribe_id 解析订阅对象，供删种善后、删除指纹归档和洗版优先级回滚使用。"""
        if self._subscribe_oper and subscribe_id:
            return self._subscribe_oper.get(subscribe_id)
        return None

    def _bump_missing(self, torrent_hash: str) -> int:
        """累加并返回该种子连续 miss 次数（下载器可达但探测不到）；与 retry_count 同存 torrents 任务。"""
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
        """种子恢复可见或已善后：清零 miss 计数。"""
        def updater(data: dict) -> dict:
            task = data.get(torrent_hash)
            if task and "missing_count" in task:
                task.pop("missing_count", None)
                data[torrent_hash] = task
            return data

        self._update("torrents", updater)

    def check_torrent(self, torrent_info: TorrentInfo, subscribe_id: int) -> str:
        """检查种子状态，返回动作：'ok'/'timeout'/'delete_tracker'/'manual_review'/'ignored'。"""
        if self._should_exclude(torrent_info):
            return "ignored"

        if self._matches_tracker_keywords(torrent_info):
            detail(f"下载监控：种子 {torrent_info.hash} 命中 Tracker 关键字 {self._tracker_keywords}")
            return "delete_tracker"

        torrent_task = self._get_torrent_task(torrent_info.hash)

        if torrent_info.completed:
            return "ok"

        if not torrent_task:
            self._init_torrent_task(torrent_info)
            return "ok"

        if self._has_progress(torrent_info, torrent_task):
            self._refresh_baseline(torrent_info)
            return "ok"

        elapsed = time.time() - torrent_task.get("baseline_at", time.time())
        if elapsed < self._timeout_seconds:
            return "ok"

        retry_count = torrent_task.get("retry_count", 0)
        if retry_count >= self._retry_limit:
            manual_count = torrent_task.get("manual_review_count", 0)
            if manual_count > 0:
                detail(f"下载监控：种子 {torrent_info.hash} 二次超时，转人工复核（不再自动删种）")
                return "manual_review"
            detail(f"下载监控：种子 {torrent_info.hash} 重试耗尽({retry_count}/{self._retry_limit})仍无进度，首次判定超时")
            self._mark_manual_review(torrent_info.hash)
            return "timeout"

        detail(f"下载监控：种子 {torrent_info.hash} 无进度，重试 {retry_count + 1}/{self._retry_limit}，刷新基线后继续观察")
        self._increment_retry(torrent_info.hash, retry_count)
        self._refresh_baseline(torrent_info)
        return "ok"

    def _should_exclude(self, info: TorrentInfo) -> bool:
        if not self._exclude_tags:
            return False
        return any(tag in self._exclude_tags for tag in info.tags)

    def _matches_tracker_keywords(self, info: TorrentInfo) -> bool:
        if not self._tracker_keywords:
            return False
        for response in info.tracker_responses:
            for kw in self._tracker_keywords:
                if kw.lower() in response.lower():
                    return True
        return False

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
        """首次 timeout 后标记 manual_review_count=1，下次再 timeout 进入 MANUAL_REVIEW。"""
        def updater(data: dict) -> dict:
            task = data.get(torrent_hash, {})
            task["manual_review_count"] = task.get("manual_review_count", 0) + 1
            data[torrent_hash] = task
            return data
        self._update("torrents", updater)
