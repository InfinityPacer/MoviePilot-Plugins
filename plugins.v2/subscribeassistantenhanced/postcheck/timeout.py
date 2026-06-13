"""域 ⑦J：P 状态超时释放——防止永久卡住。"""
import time
from typing import Callable, Optional

from ..engine.types import CompletionSignal
from ..shared.log import detail
from ..shared.subscribe import (
    format_subscribe_label, identity_matches, subscribe_identity,
)


class PendingTimeoutManager:
    """P 状态超时释放，实现 PendingTimeoutManagerProtocol。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 timeout_days: int = 7,
                 cadence_acceleration: bool = True,
                 subscribe_get_fn: Optional[Callable] = None):
        self._read = task_data_read
        self._update = task_data_update
        self._timeout_seconds = timeout_days * 86400
        self._cadence_acceleration = cadence_acceleration
        self._subscribe_get = subscribe_get_fn

    def record_block(self, subscribe_id, signal: Optional[CompletionSignal] = None,
                     total_episode: Optional[int] = None):
        """CompletionCheck 否决时开始计时，并记录本轮观察的信号上下文。"""
        subscribe, subscribe_id = self._resolve_subscribe(subscribe_id)
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            current = data.get(sid)
            if current is None or (
                subscribe is not None
                and not identity_matches(current.get("identity"), subscribe)
            ):
                data[sid] = {
                    "blocked_at": time.time(),
                    "reason": "guard_veto",
                    "signals": list(signal.signals) if signal else [],
                    "confidence": signal.confidence if signal else "",
                    "total_episode": total_episode,
                }
                if subscribe is not None:
                    data[sid]["identity"] = subscribe_identity(subscribe)
            return data

        self._update("blocks", updater)

    def clear_block(self, subscribe_id: int):
        """退出待定时清除计时器。"""
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            data.pop(sid, None)
            return data

        self._update("blocks", updater)

    def record_release(self, subscribe_id, signal: CompletionSignal,
                       total_episode: Optional[int] = None):
        """记录一次性低置信放行标记，供下一次 CompletionCheck 消费。"""
        subscribe, subscribe_id = self._resolve_subscribe(subscribe_id)
        sid = str(subscribe_id)
        token = {
            "signals": list(signal.signals),
            "confidence": signal.confidence,
            "total_episode": total_episode,
            "released_at": time.time(),
        }
        if subscribe is not None:
            token["identity"] = subscribe_identity(subscribe)

        def updater(data: dict) -> dict:
            data[sid] = token
            return data

        self._update("releases", updater)

    def consume_release(self, subscribe_id, signal: CompletionSignal,
                        total_episode: Optional[int] = None) -> bool:
        """消费匹配当前低置信信号的一次性放行标记。"""
        subscribe, subscribe_id = self._resolve_subscribe(subscribe_id)
        sid = str(subscribe_id)
        total_episode = self._resolve_total(signal, total_episode)
        releases = self._read("releases")
        token = releases.get(sid)
        if not token:
            return False
        if subscribe is not None and not identity_matches(
            token.get("identity"), subscribe
        ):
            self._clear_release(sid)
            return False

        if not self._matches_token(token, signal, total_episode):
            self._clear_release(sid)
            return False

        self._clear_release(sid)
        return True

    def check_release(self, subscribe_id,
                      signal: CompletionSignal,
                      total_episode: Optional[int] = None) -> bool:
        """检查是否应释放 P 状态。

        F 不稳定时重置计时并不释放——数据仍在变动的时间不计入超时额度；
        观察期间若总集数增长或低置信信号消失，释放当前 guard 来源但不写放行标记；
        开启 cadence_acceleration 且节奏已到期时，超时阈值减半以加速释放。
        """
        subscribe, subscribe_id = self._resolve_subscribe(subscribe_id)
        sid = str(subscribe_id)
        total_episode = self._resolve_total(signal, total_episode)
        data = self._read("blocks")
        block = data.get(sid)
        if not block:
            return False
        if subscribe is not None and not identity_matches(
            block.get("identity"), subscribe
        ):
            self.clear_block(subscribe_id)
            self._clear_release(sid)
            return False
        label = self._format_subscribe_label(subscribe_id)

        if not signal.stable:
            detail(f"待定超时：{label} 信号不稳定，重置超时计时（数据变动期不计入超时额度）")
            self._reset_timer(sid)
            return False

        block_total = block.get("total_episode")
        if block_total and total_episode and total_episode > block_total:
            detail(f"待定超时：{label} 观察期间总集数增长 {block_total}→{total_episode}，释放本轮观察并等待重新判定")
            return True

        block_signals = block.get("signals") or []
        if block.get("confidence") == "low" and block_signals and block_signals != list(signal.signals):
            detail(f"待定超时：{label} 观察信号已变化，释放本轮观察并等待重新判定")
            self._clear_release(sid)
            return True

        if signal.completed and signal.confidence == "low":
            if not self._matches_low_confidence_observation(block, signal, total_episode):
                detail(f"待定超时：{label} 开始低置信完成前观察")
                self._replace_observation(sid, signal, total_episode)
                self._clear_release(sid)
                return False

        effective_timeout = self._timeout_seconds
        if self._cadence_acceleration and signal.cadence_expired:
            detail(f"待定超时：{label} 节奏已到期，超时阈值减半加速释放")
            effective_timeout = self._timeout_seconds / 2

        elapsed = time.time() - block.get("blocked_at", time.time())
        if elapsed <= effective_timeout:
            return False

        if signal.completed and signal.confidence == "low":
            self.record_release(
                subscribe or subscribe_id, signal, total_episode=total_episode
            )
        return True

    @staticmethod
    def _resolve_subscribe(subscribe_or_id):
        """兼容旧整数调用，并在对象调用时返回完整订阅身份。"""
        if hasattr(subscribe_or_id, "id"):
            return subscribe_or_id, subscribe_or_id.id
        return None, subscribe_or_id

    def _format_subscribe_label(self, subscribe_id: int) -> str:
        """按订阅 ID 生成超时诊断标签；查库失败时仍保留 ID。"""
        subscribe = self._subscribe_get(subscribe_id) if self._subscribe_get else None
        return format_subscribe_label(subscribe, subscribe_id)

    def _reset_timer(self, sid: str):
        def updater(data: dict) -> dict:
            block = data.get(sid)
            if block:
                block["blocked_at"] = time.time()
                data[sid] = block
            return data
        self._update("blocks", updater)

    def _replace_observation(self, sid: str, signal: CompletionSignal,
                             total_episode: Optional[int]):
        """用当前低置信信号开启新的观察窗口。"""
        def updater(data: dict) -> dict:
            data[sid] = {
                "blocked_at": time.time(),
                "reason": "guard_veto",
                "signals": list(signal.signals),
                "confidence": signal.confidence,
                "total_episode": total_episode,
            }
            return data
        self._update("blocks", updater)

    def _clear_release(self, sid: str):
        """清理订阅的一次性完成放行标记。"""
        def updater(data: dict) -> dict:
            data.pop(sid, None)
            return data
        self._update("releases", updater)

    def _resolve_total(self, signal: CompletionSignal,
                       total_episode: Optional[int]) -> Optional[int]:
        """优先使用信号携带的 TMDB scope 总数，缺失时回退调用方传入值。"""
        return getattr(signal, "scope_total", 0) or total_episode

    def _matches_token(self, token: dict, signal: CompletionSignal,
                       total_episode: Optional[int]) -> bool:
        """判断一次性 release token 是否仍匹配当前低置信信号。"""
        return (
            token.get("confidence") == signal.confidence
            and token.get("signals") == list(signal.signals)
            and token.get("total_episode") in (None, total_episode)
        )

    def _matches_low_confidence_observation(self, block: dict,
                                            signal: CompletionSignal,
                                            total_episode: Optional[int]) -> bool:
        """低置信观察必须由同一信号和同一 TMDB 总集数启动，不能复用旧 guard 计时。"""
        return (
            block.get("confidence") == "low"
            and block.get("signals") == list(signal.signals)
            and block.get("total_episode") in (None, total_episode)
        )
