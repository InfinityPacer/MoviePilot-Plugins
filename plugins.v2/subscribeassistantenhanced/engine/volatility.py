"""F：变更速率追踪，检测 total_episode 是否在窗口期内变动过。"""
import time
from typing import Optional

from ..shared.task import TaskDataManager
from ..shared.subscribe import identity_matches, subscribe_identity

VOLATILITY_KEY = "volatility"
MAX_BUFFER_SIZE = 20


class VolatilityTracker:
    """记录 TMDB 原始 total_episode 值，检测数据稳定性。"""

    def __init__(self, task_manager: TaskDataManager, window_days: int = 7):
        self._task = task_manager
        self._window_seconds = window_days * 86400

    def record(self, total: int, subscribe_id: Optional[int] = None,
               subscribe=None):
        """记录 total_episode；提供订阅对象时同时校验媒体身份。"""
        if subscribe is not None:
            subscribe_id = subscribe.id
        if subscribe_id is None:
            return
        sid = str(subscribe_id)
        now = time.time()

        def updater(data: dict) -> dict:
            entry = data.get(sid)
            if subscribe is not None:
                if not isinstance(entry, dict) or not identity_matches(
                    entry.get("identity"), subscribe
                ):
                    entry = {
                        "identity": subscribe_identity(subscribe),
                        "records": [],
                    }
                buf = entry.get("records", [])
            else:
                buf = entry if isinstance(entry, list) else []
            buf.append({"total": total, "ts": now})
            if len(buf) > MAX_BUFFER_SIZE:
                buf = buf[-MAX_BUFFER_SIZE:]
            if subscribe is not None:
                entry["records"] = buf
                data[sid] = entry
            else:
                data[sid] = buf
            return data

        self._task.update(VOLATILITY_KEY, updater)

    def is_stable(self, subscribe_id: Optional[int] = None, subscribe=None) -> bool:
        """检查窗口期内 total 是否无变动；身份不符按新订阅处理。"""
        if subscribe is not None:
            subscribe_id = subscribe.id
        if subscribe_id is None:
            return True
        sid = str(subscribe_id)
        data = self._task.read(VOLATILITY_KEY)
        entry = data.get(sid)
        if subscribe is not None:
            if not isinstance(entry, dict) or not identity_matches(
                entry.get("identity"), subscribe
            ):
                self._task.update(
                    VOLATILITY_KEY,
                    lambda current: _drop_key(current, sid),
                )
                return True
            buf = entry.get("records", [])
        else:
            buf = entry if isinstance(entry, list) else []
        if len(buf) <= 1:
            return True
        cutoff = time.time() - self._window_seconds
        recent = [r for r in buf if r["ts"] >= cutoff]
        if len(recent) <= 1:
            return True
        totals = {r["total"] for r in recent}
        return len(totals) == 1


def _drop_key(data: dict, sid: str) -> dict:
    """删除失配订阅 ID 的旧记录。"""
    data.pop(sid, None)
    return data
