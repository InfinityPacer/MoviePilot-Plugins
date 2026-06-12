"""域 ⑥：删除后恢复统一流程。"""
from typing import Callable, Optional

from ..engine.types import PriorityManagerProtocol
from ..shared.log import detail
from ..shared.subscribe import format_subscribe


class TorrentCleanup:
    """种子删除后的统一编排：归档删除指纹 → 删下载器种子 → 回滚优先级 → 清任务 → 延迟补搜。

    外部副作用通过注入回调执行，避免清理流程直接绑定下载器、搜索或文件系统实现。
    """

    def __init__(self, priority_manager: PriorityManagerProtocol,
                 clear_download_pending_fn: Callable,
                 task_data_update: Callable,
                 task_data_read: Optional[Callable] = None,
                 deletes_store=None,
                 delete_torrent_fn: Optional[Callable] = None,
                 search_fn: Optional[Callable] = None,
                 notify_fn: Optional[Callable] = None):
        """注入删种善后依赖；通知回调用于告知用户删除原因与补搜安排。"""
        self._priority = priority_manager
        self._clear_pending = clear_download_pending_fn
        self._update = task_data_update
        self._read = task_data_read
        self._deletes = deletes_store
        self._delete_torrent = delete_torrent_fn
        self._search = search_fn
        self._notify = notify_fn

    def handle_torrent_deleted(self, subscribe, torrent_hash: str,
                                reason: str = "download_timeout",
                                downloader: Optional[str] = None,
                                delete_from_downloader: bool = True):
        """种子删除后的统一处理，步骤顺序固定，避免中途失败留下半清理态。

        delete_from_downloader：仅下载器主动删种（timeout/tracker）为 True；手动删除时种子已不在，
        传 False 跳过删种。删除指纹负责防止同一坏种被立即重选，订阅继续保持可搜索状态。
        """
        sid = subscribe.id
        detail(f"删种善后：{format_subscribe(subscribe)} 种子 {torrent_hash} 开始善后（reason={reason}，删下载器={delete_from_downloader}）")

        # 1. 先归档删除指纹（须在清 torrents 任务前读取 enclosure/page_url），供资源选择阶段防重选
        torrent_task = self._read_torrent_task(torrent_hash)
        if self._deletes and torrent_task:
            detail(f"删种善后：种子 {torrent_hash} 归档删除指纹，避免后续被重新选中")
            self._deletes.save(torrent_task, reason=reason)

        # 2. 真正从下载器删种（delete_file=True）；手动删除时种子已不存在，跳过删种
        if delete_from_downloader and self._delete_torrent and downloader and torrent_hash:
            self._delete_torrent(downloader, torrent_hash)

        # 3. 洗版订阅按集归属回滚优先级：按种子 enclosure 归属回滚，隔离并行洗版；
        #    无 enclosure（旧数据/非洗版下载）时退回整体回滚
        if subscribe.best_version:
            enclosure = (torrent_task or {}).get("enclosure")
            rollback_torrent = getattr(self._priority, "rollback_torrent", None)
            if enclosure and callable(rollback_torrent):
                detail(f"删种善后：{format_subscribe(subscribe)} 洗版按种子 enclosure 归属回滚优先级")
                rollback_torrent(subscribe, enclosure)
            else:
                detail(f"删种善后：{format_subscribe(subscribe)} 洗版整体回滚优先级（无 enclosure 归属）")
                self._priority.rollback(subscribe, baseline=None)

        # 4. 清种子任务 + 下载待定标记
        self._clean_torrent_task(torrent_hash)
        self._clear_pending(sid, torrent_hash)

        # 5. 延迟补充搜索（注入；删后重新触发该订阅搜索，避免长期缺集）
        self._notify_deleted(subscribe, torrent_task, reason)
        if self._search and subscribe:
            self._search(subscribe)

    def _read_torrent_task(self, torrent_hash: str) -> Optional[dict]:
        """删除前读取种子任务（用于归档删除指纹）；无读回调或 hash 时返回 None。"""
        if not self._read or not torrent_hash:
            return None
        return (self._read("torrents") or {}).get(torrent_hash)

    def _clean_torrent_task(self, torrent_hash: str):
        """清理种子任务数据。"""
        def updater(data: dict) -> dict:
            data.pop(torrent_hash, None)
            return data
        self._update("torrents", updater)

    def _notify_deleted(self, subscribe, torrent_task: Optional[dict], reason: str):
        """发送删种善后通知，标题包含订阅、删除原因和最终动作。"""
        if not self._notify:
            return
        reason_text = {
            "timeout": "超时无进度",
            "delete_tracker": "Tracker 关键字命中",
            "manual": "订阅种子手动删除",
            "download_timeout": "超时无进度",
        }.get(reason, reason)
        msg_parts = []
        if torrent_task:
            if torrent_task.get("title"):
                msg_parts.append(f"标题：{torrent_task.get('title')}")
            if torrent_task.get("description"):
                msg_parts.append(f"内容：{torrent_task.get('description')}")
        if self._search:
            msg_parts.append("补全：将在 300 秒后触发搜索")
        self._notify(
            f"{format_subscribe(subscribe)} {reason_text}，已删除",
            "\n".join(msg_parts) if msg_parts else None,
        )
