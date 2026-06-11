"""删除指纹存储：记录已删除（超时/Tracker 命中）的种子，供资源选择阶段防止刚删的资源被立即重选。

匹配语义：仅按 enclosure / page_url 做部分匹配（任一命中即视为同一资源），不纳入站点/标题，
避免误杀同站同名的不同资源。
"""
import time
from typing import Callable, Optional


class DeletesStore:
    """已删除种子指纹的读写与匹配。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable):
        self._read = task_data_read
        self._update = task_data_update

    def save(self, torrent_task: dict, reason: str = "timeout"):
        """归档一条删除指纹（保留 enclosure/page_url/title 等），按 hash 存档。"""
        if not torrent_task:
            return
        torrent_hash = torrent_task.get("hash")
        if not torrent_hash:
            return

        def updater(data: dict) -> dict:
            entry = dict(torrent_task)
            entry["delete_time"] = time.time()
            entry["delete_type"] = reason
            data[torrent_hash] = entry
            return data

        self._update("deletes", updater)

    def match(self, enclosure: Optional[str] = None, page_url: Optional[str] = None,
              partial: bool = True) -> bool:
        """判断给定资源是否命中已删除指纹：enclosure 或 page_url 任一匹配即命中。"""

        def is_match(field1, field2) -> bool:
            if partial:
                # 双向子串匹配：兼容种子 URL 带/不带 passkey 等细微差异
                return bool(field1 and field2 and (field1 in field2 or field2 in field1))
            return field1 == field2

        deletes = self._read("deletes") or {}
        for entry in deletes.values():
            if is_match(enclosure, entry.get("enclosure")):
                return True
            if is_match(page_url, entry.get("page_url")):
                return True
        return False

    def cleanup_expired(self, retention_hours: int = 24, now: Optional[float] = None) -> int:
        """清理超过保留期的删除指纹，返回移除条数。

        指纹只增不减会长期挡住同源资源的重选；按 delete_time 老化，保留期内的保留、过期的移除。
        now 可注入便于测试；缺 delete_time 的旧条目保守保留（不老化）。
        """
        now = time.time() if now is None else now
        cutoff = now - retention_hours * 3600
        removed = 0

        def updater(data: dict) -> dict:
            nonlocal removed
            kept = {}
            for key, entry in (data or {}).items():
                delete_time = entry.get("delete_time", 0)
                if delete_time and delete_time < cutoff:
                    removed += 1
                    continue
                kept[key] = entry
            return kept

        self._update("deletes", updater)
        return removed
