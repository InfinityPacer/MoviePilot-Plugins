"""插件持久化数据管理，封装 get_data/save_data + per-key RLock。"""
import threading
from typing import Any, Callable


class TaskDataManager:
    """线程安全的 JSON 数据读写，每个 key 独立 RLock。"""

    def __init__(self, get_data_fn: Callable, save_data_fn: Callable):
        self._get = get_data_fn
        self._save = save_data_fn
        self._locks: dict[str, threading.RLock] = {}
        self._meta_lock = threading.Lock()

    def _lock_for(self, key: str) -> threading.RLock:
        """获取或创建指定 key 的 RLock，创建过程由 _meta_lock 保护。"""
        with self._meta_lock:
            if key not in self._locks:
                self._locks[key] = threading.RLock()
            return self._locks[key]

    def read(self, key: str) -> Any:
        """线程安全读取，key 不存在时返回空 dict。"""
        with self._lock_for(key):
            return self._get(key) or {}

    def write(self, key: str, data: Any):
        """线程安全写入。"""
        with self._lock_for(key):
            self._save(key, data)

    def update(self, key: str, updater: Callable[[Any], Any]):
        """线程安全读-改-写。"""
        with self._lock_for(key):
            data = self._get(key) or {}
            updated = updater(data)
            self._save(key, updated)
            return updated

    def reset(self, key: str):
        """清空指定 key 的数据。"""
        with self._lock_for(key):
            self._save(key, {})

    def reset_all(self, keys: list[str]):
        """批量清空多个 key。"""
        for key in keys:
            self.reset(key)

    def clear_tasks(self, subscribe_id):
        """清理某订阅的全部任务数据：先清订阅任务、再清其名下种子任务。

        固定 subscribes→torrents 顺序，避免中途失败留下"订阅没了但种子任务还在"的半清理态。
        种子任务按 ``subscribe_id`` 归属匹配（统一 str 比较，兼容 JSON 落盘后 key 字符串化）。
        """
        sid = str(subscribe_id)

        def _clear_subscribe(data: dict) -> dict:
            data.pop(sid, None)
            return data

        def _clear_torrents(data: dict) -> dict:
            for torrent_hash in list(data.keys()):
                if str(data[torrent_hash].get("subscribe_id")) == sid:
                    del data[torrent_hash]
            return data

        self.update("subscribes", _clear_subscribe)
        self.update("torrents", _clear_torrents)
        for key in ("volatility", "blocks", "releases"):
            self.update(key, _clear_subscribe)

    def clean_torrent_tasks(self, torrent_hash):
        """按 hash 同步清理单个种子的任务记录：从 torrents 移除，并从各订阅的 torrent_tasks 移除。

        用于移动模式整理完成后作废残留下载任务。
        """
        if not torrent_hash:
            return

        def _clear_torrents(data: dict) -> dict:
            data.pop(torrent_hash, None)
            return data

        def _clear_from_subscribes(data: dict) -> dict:
            for sub_task in data.values():
                tasks = sub_task.get("torrent_tasks")
                if tasks:
                    sub_task["torrent_tasks"] = [t for t in tasks if t.get("hash") != torrent_hash]
            return data

        self.update("torrents", _clear_torrents)
        self.update("subscribes", _clear_from_subscribes)
