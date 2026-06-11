"""F：变更速率追踪，检测 total_episode 是否在窗口期内变动过。"""
import time
from typing import Optional

from ..shared.task import TaskDataManager

VOLATILITY_KEY = "volatility"
MAX_BUFFER_SIZE = 20


class VolatilityTracker:
    """记录 TMDB 原始 total_episode 值，检测数据稳定性。"""

    def __init__(self, task_manager: TaskDataManager, window_days: int = 7):
        self._task = task_manager
        self._window_seconds = window_days * 86400

    def record(self, total: int, subscribe_id: Optional[int]):
        """记录一次 total_episode 值。subscribe_id=None 时跳过。"""
        if subscribe_id is None:
            return
        sid = str(subscribe_id)
        now = time.time()

        def updater(data: dict) -> dict:
            buf = data.get(sid, [])
            buf.append({"total": total, "ts": now})
            if len(buf) > MAX_BUFFER_SIZE:
                buf = buf[-MAX_BUFFER_SIZE:]
            data[sid] = buf
            return data

        self._task.update(VOLATILITY_KEY, updater)

    def is_stable(self, subscribe_id: Optional[int]) -> bool:
        """检查窗口期内 total 是否无变动。None 或从未记录视为稳定。"""
        if subscribe_id is None:
            return True
        sid = str(subscribe_id)
        data = self._task.read(VOLATILITY_KEY)
        buf = data.get(sid, [])
        if len(buf) <= 1:
            return True
        cutoff = time.time() - self._window_seconds
        recent = [r for r in buf if r["ts"] >= cutoff]
        if len(recent) <= 1:
            return True
        totals = {r["total"] for r in recent}
        return len(totals) == 1
