"""删除指纹存储，对用户表现为“近期删除资源”。

记录因超时、Tracker 命中或手动删除而移除的种子，供 ResourceSelection 防止立即重选。
匹配语义只使用 enclosure/page_url，不按站点或标题泛匹配，避免误挡同站同名的不同资源。
"""
import time
from typing import Callable, Optional


class DeletesStore:
    """已删除种子指纹的读写、匹配与老化。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable):
        self._read = task_data_read
        self._update = task_data_update

    def save(self, torrent_task: dict, reason: str = "timeout"):
        """按 hash 归档删除指纹，保留 enclosure/page_url/title 等诊断字段。"""
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
        """判断资源是否命中删除指纹，enclosure/page_url 任一匹配即命中。"""

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

        指纹只增不减会长期挡住同源资源重选；按 delete_time 老化，保留期内保留、过期移除。
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
