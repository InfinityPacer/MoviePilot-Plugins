"""种子删除后的统一善后编排。"""
from typing import Callable, Optional

from app.schemas.types import MediaType

from ..engine.types import PriorityManagerProtocol
from ..shared.log import detail
from ..shared.subscribe import format_subscribe, resolve_subscribe_media_type
from ..shared.update import update_subscribe


class TorrentCleanup:
    """种子删除统一编排：归档删除指纹 → 删种 → 回滚优先级 → 清任务 → 补搜。

    外部副作用通过注入回调执行，避免本模块直接绑定下载器、搜索或文件系统实现。
    """

    def __init__(self, priority_manager: PriorityManagerProtocol,
                 clear_download_pending_fn: Callable,
                 task_data_update: Callable,
                 task_data_read: Optional[Callable] = None,
                 deletes_store=None,
                 delete_torrent_fn: Optional[Callable] = None,
                 search_fn: Optional[Callable] = None,
                 notify_fn: Optional[Callable] = None,
                 get_subscribe_image_fn: Optional[Callable] = None,
                 subscribe_oper=None):
        """注入删种、任务清理、补搜和通知依赖。"""
        self._priority = priority_manager
        self._clear_pending = clear_download_pending_fn
        self._update = task_data_update
        self._read = task_data_read
        self._deletes = deletes_store
        self._delete_torrent = delete_torrent_fn
        self._search = search_fn
        self._notify = notify_fn
        self._get_subscribe_image = get_subscribe_image_fn
        self._subscribe_oper = subscribe_oper

    def handle_torrent_deleted(self, subscribe, torrent_hash: str,
                                reason: str = "download_timeout",
                                reason_detail: Optional[str] = None,
                                downloader: Optional[str] = None,
                                delete_from_downloader: bool = True,
                                search_enabled: bool = True):
        """种子删除后的统一处理，步骤顺序固定，避免中途失败留下不一致状态。

        delete_from_downloader：仅下载器主动删种（timeout/tracker）为 True；手动删除时种子已不在，
        传 False 跳过删种。删除指纹负责防止同一坏种被立即重选，订阅继续保持可搜索状态。
        """
        sid = subscribe.id
        detail(
            f"种子删除处理：{format_subscribe(subscribe)} 开始处理 hash={torrent_hash}"
            f"（reason={reason}, delete_from_downloader={delete_from_downloader}）"
        )

        # 1. 清 torrents 任务前归档删除指纹，供 ResourceSelection 防止坏种立即重选。
        torrent_task = self._read_torrent_task(torrent_hash)
        if self._deletes and torrent_task:
            detail(f"种子删除处理：已记录种子 {torrent_hash}，避免后续被重新选中")
            self._deletes.save(torrent_task, reason=reason)

        # 删种后需要把已记为完成的剧集重新标为缺失，补搜前先恢复订阅缺集状态。
        self._restore_subscribe_missing_state(subscribe, torrent_task)

        # 2. 下载器主动删除场景真正删种；用户手动删除场景种子已不存在。
        if delete_from_downloader and self._delete_torrent and downloader and torrent_hash:
            self._delete_torrent(downloader, torrent_hash)

        # 3. 洗版按 enclosure 归属回滚，隔离并行洗版；旧数据无归属时退回整体基线。
        if subscribe.best_version:
            enclosure = (torrent_task or {}).get("enclosure")
            rollback_torrent = getattr(self._priority, "rollback_torrent", None)
            if enclosure and callable(rollback_torrent):
                detail(f"种子删除处理：{format_subscribe(subscribe)} 恢复本次洗版下载对应集数的优先级")
                rollback_torrent(subscribe, enclosure)
            else:
                detail(f"种子删除处理：{format_subscribe(subscribe)} 无法确认对应集数，恢复整体洗版优先级")
                self._priority.rollback(subscribe, baseline=None)

        # 4. 清理种子任务与下载待定，避免订阅长期保持下载中。
        self._clean_torrent_task(torrent_hash)
        self._clean_subscribe_torrent_task(sid, torrent_hash)
        self._clear_pending(sid, torrent_hash)

        # 5. 按配置触发补搜，避免删种后长期缺集。
        search_delay_seconds = None
        if search_enabled and self._search and subscribe:
            search_delay_seconds = self._search(subscribe)
            if not isinstance(search_delay_seconds, (int, float)):
                search_delay_seconds = None
        self._notify_deleted(
            subscribe, torrent_task, reason,
            reason_detail=reason_detail,
            search_delay_seconds=search_delay_seconds,
        )

    def handle_timeout_manual_review(self, subscribe, torrent_hash: str,
                                     reason_detail: str, ignore_hours: int = 48):
        """连续低进度达到保护上限时保留种子，并通知用户人工判断。"""
        if not self._notify:
            return
        torrent_task = self._read_torrent_task(torrent_hash) or {}
        detail_parts = []
        if torrent_task.get("title"):
            detail_parts.append(f"标题：{torrent_task.get('title')}")
        if torrent_task.get("description"):
            detail_parts.append(f"内容：{torrent_task.get('description')}")
        action = f"已保留当前种子，{ignore_hours} 小时内不再自动删除"
        detail(f"种子删除处理：{format_subscribe(subscribe)} 原因={reason_detail}，处理={action}，后续=请手动判断")
        self._notify(
            f"{format_subscribe(subscribe)} {self._manual_review_title_reason(reason_detail)}，{action}",
            "\n".join(detail_parts) if detail_parts else None,
            image=self._subscribe_image(subscribe),
            follow_up="请手动判断",
            diagnostic=True,
        )

    @staticmethod
    def _manual_review_title_reason(reason_detail: str) -> str:
        """将低进度诊断改写为通知标题语序，保留下载时长与进度判断信息。"""
        prefix = "订阅种子，"
        if reason_detail.startswith(prefix):
            return f"{prefix}下载连续超时，{reason_detail[len(prefix):]}"
        return f"下载连续超时，{reason_detail}"

    def _read_torrent_task(self, torrent_hash: str) -> Optional[dict]:
        """删除前读取种子任务，供删除指纹归档与按集基线回滚。"""
        if not self._read or not torrent_hash:
            return None
        return (self._read("torrents") or {}).get(torrent_hash)

    def _restore_subscribe_missing_state(self, subscribe, torrent_task: Optional[dict]):
        """删种善后恢复订阅缺集状态，确保后续补搜能覆盖被删集。"""
        if not self._subscribe_oper or not subscribe or not torrent_task:
            return
        media_type = resolve_subscribe_media_type(subscribe)
        payload = {}
        if media_type == MediaType.TV:
            note = list(subscribe.note or [])
            episodes = torrent_task.get("episodes") or []
            episode_set = set(episodes if isinstance(episodes, list) else [episodes])
            kept_note = [episode for episode in note if episode not in episode_set]
            payload["note"] = kept_note
            total_episode = subscribe.total_episode
            if total_episode:
                start_episode = (subscribe.start_episode or 1) - 1
                payload["lack_episode"] = total_episode - start_episode - len(kept_note)
            else:
                payload["lack_episode"] = total_episode
        elif media_type == MediaType.MOVIE:
            payload["note"] = []
        if payload:
            update_subscribe(self._subscribe_oper, subscribe.id, payload)

    def _clean_torrent_task(self, torrent_hash: str):
        """清理种子任务数据。"""
        def updater(data: dict) -> dict:
            data.pop(torrent_hash, None)
            return data
        self._update("torrents", updater)

    def _clean_subscribe_torrent_task(self, subscribe_id: int, torrent_hash: str):
        """同步清理订阅内 torrent_tasks，兼容订阅级种子记录。"""
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

    def _notify_deleted(self, subscribe, torrent_task: Optional[dict], reason: str,
                        reason_detail: Optional[str] = None,
                        search_delay_seconds: Optional[float] = None):
        """发送种子删除通知，标题包含订阅、删除原因和最终动作。"""
        if not self._notify:
            return
        reason_text = {
            "timeout": "超时无进度",
            "delete_tracker": "Tracker 返回内容包含删除关键字",
            "manual": "订阅种子手动删除",
            "download_timeout": "超时无进度",
        }.get(reason, reason)
        detail_parts = []
        if torrent_task:
            if torrent_task.get("title"):
                detail_parts.append(f"标题：{torrent_task.get('title')}")
            if torrent_task.get("description"):
                detail_parts.append(f"内容：{torrent_task.get('description')}")
        follow_up = None
        if search_delay_seconds is not None:
            follow_up = f"将在 {search_delay_seconds / 60:.2f} 分钟后触发搜索补全"
        detail(
            f"种子删除处理：{format_subscribe(subscribe)} 原因={reason_detail or reason_text}，"
            f"处理=已删除，后续={follow_up or '无'}"
        )
        self._notify(
            f"{format_subscribe(subscribe)} {reason_detail or reason_text}，已删除",
            "\n".join(detail_parts) if detail_parts else None,
            image=self._subscribe_image(subscribe),
            follow_up=follow_up,
            diagnostic=True,
        )

    def _subscribe_image(self, subscribe):
        """读取订阅通知图片；未注入图片解析器时保持兼容。"""
        return self._get_subscribe_image(subscribe) if self._get_subscribe_image else None
