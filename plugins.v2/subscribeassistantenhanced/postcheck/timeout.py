"""域 ⑦J：P 状态超时释放——防止永久卡住。"""
import time
from typing import Callable, Optional

from ..engine.types import CompletionSignal
from ..shared.log import detail


class PendingTimeoutManager:
    """P 状态超时释放，实现 PendingTimeoutManagerProtocol。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 timeout_days: int = 21,
                 cadence_acceleration: bool = True):
        self._read = task_data_read
        self._update = task_data_update
        self._timeout_seconds = timeout_days * 86400
        self._cadence_acceleration = cadence_acceleration

    def record_block(self, subscribe_id: int):
        """CompletionCheck 否决时开始计时。"""
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            if sid not in data:
                data[sid] = {
                    "blocked_at": time.time(),
                    "reason": "guard_veto",
                }
            return data

        self._update("blocks", updater)

    def clear_block(self, subscribe_id: int):
        """退出待定时清除计时器。"""
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            data.pop(sid, None)
            return data

        self._update("blocks", updater)

    def check_release(self, subscribe_id: int,
                       signal: CompletionSignal) -> bool:
        """检查是否应释放 P 状态。

        F 不稳定时重置计时并不释放——数据仍在变动的时间不计入超时额度；
        开启 cadence_acceleration 且节奏已到期时，超时阈值减半以加速释放。
        """
        sid = str(subscribe_id)
        data = self._read("blocks")
        block = data.get(sid)
        if not block:
            return False

        if not signal.stable:
            detail(f"待定超时：订阅 {sid} 信号不稳定，重置超时计时（数据变动期不计入超时额度）")
            self._reset_timer(sid)
            return False

        effective_timeout = self._timeout_seconds
        if self._cadence_acceleration and signal.cadence_expired:
            detail(f"待定超时：订阅 {sid} 节奏已到期，超时阈值减半加速释放")
            effective_timeout = self._timeout_seconds / 2

        elapsed = time.time() - block.get("blocked_at", time.time())
        return elapsed > effective_timeout

    def _reset_timer(self, sid: str):
        def updater(data: dict) -> dict:
            block = data.get(sid)
            if block:
                block["blocked_at"] = time.time()
                data[sid] = block
            return data
        self._update("blocks", updater)
