"""域 ②：完成守卫——CompletionCheck 事件处理。"""
from typing import Callable

from app.log import logger
from app.schemas.event import SubscribeCompletionCheckEventData
from app.schemas.types import MediaType

from .engine.scope import build_scope
from .engine.local import LocalSignalResult, check_l_signal_detail
from .engine.signals import scope_future_episodes
from .engine.types import CompletionSignal, PendingTimeoutManagerProtocol
from .shared.log import detail
from .shared.media import episode_field, target_episode_range
from .shared.subscribe import (
    format_subscribe,
    is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
    resolve_subscribe_media_type,
)


class CompletionGuard:
    """完成守卫：下载待定检查 + 完结信号引擎最终裁决。"""

    def __init__(self,
                 evaluate_fn: Callable,
                 has_active_downloads_fn: Callable,
                 mark_pending_fn: Callable,
                 timeout_manager: PendingTimeoutManagerProtocol,
                 tmdb_episodes_fn: Callable = None,
                 mode: str = "balanced",
                 pending_download_enabled: bool = True,
                 resolve_missing_fn: Callable = None):
        """保存完成守卫依赖与下载中待定开关。"""
        self.evaluate_fn = evaluate_fn
        self.has_active_downloads_fn = has_active_downloads_fn
        self.mark_pending_fn = mark_pending_fn
        self.timeout_manager = timeout_manager
        self.tmdb_episodes_fn = tmdb_episodes_fn
        self.mode = mode
        self.pending_download_enabled = pending_download_enabled
        self.resolve_missing_fn = resolve_missing_fn

    def handle(self, event):
        """CompletionCheck 链式事件处理入口：主程序只读取 event.event_data 上的输出字段。

        输入（subscribe/mediainfo）与输出（cancel/source/reason）一律操作 event.event_data；
        每个否决分支都写 source，避免主程序日志打出 [未知来源]。
        """
        data: SubscribeCompletionCheckEventData = event.event_data
        if data is None:
            return
        subscribe = data.subscribe

        media_type = resolve_subscribe_media_type(subscribe)
        if media_type == MediaType.UNKNOWN:
            return

        detail(f"完成守卫：收到完成检查 {format_subscribe(subscribe)}")

        if self.pending_download_enabled and self.has_active_downloads_fn(subscribe):
            logger.info(f"完成守卫：{format_subscribe(subscribe)} 存在进行中的下载，否决完成（等待下载转移入库）")
            data.cancel = True
            data.source = "subscribeassistantenhanced"
            data.reason = "存在进行中的下载，等待下载完成并转移入库"
            return

        if media_type != MediaType.TV or is_full_best_version_subscribe(subscribe):
            detail(f"完成守卫：{format_subscribe(subscribe)} 非普通/分集剧集订阅，跳过")
            return

        signal: CompletionSignal = self.evaluate_fn(subscribe, data.mediainfo)

        if not signal.stable:
            local_result = self._local_signal_result(subscribe, data.mediainfo, data.meta)
            local_signal = local_result.signal
            allowed, deny_reason = self._allow_unstable_local_completion_detail(local_signal, signal)
            if allowed:
                detail(
                    f"完成守卫：{format_subscribe(subscribe)} F 不稳定但命中可信 L 目标满足信号，"
                    f"按 {self.mode} 模式放行"
                )
                return
            reason = deny_reason or local_result.blocked_reason or "未命中 L"
            logger.info(
                f"完成守卫：{format_subscribe(subscribe)} F 不稳定，L 兜底未放行（{reason}），"
                f"原始原因：{signal.reason}"
            )
            logger.info(f"完成守卫：{format_subscribe(subscribe)} 信号不稳定（{signal.reason}），否决完成并进入待定（P）")
            data.cancel = True
            data.source = "subscribeassistantenhanced"
            data.reason = signal.reason
            self.mark_pending_fn(subscribe, source="guard_veto", reason=signal.reason)
            self.timeout_manager.record_block(
                subscribe,
                signal=signal,
                total_episode=signal.scope_total or subscribe.total_episode,
            )
            return

        if "M:mid_season" in signal.signals:
            self._block_completion(data, subscribe, signal)
            return

        if signal.completed:
            if signal.confidence == "low" and not self._allow_low_confidence(signal):
                self._observe_low_confidence(data, subscribe, signal)
                return
            detail(
                f"完成守卫：{format_subscribe(subscribe)} "
                f"{signal.confidence or '未知'}置信完结，按 {self.mode} 模式放行"
            )
            return

        local_result = self._local_signal_result(subscribe, data.mediainfo, data.meta)
        local_signal = local_result.signal
        if local_signal is not None:
            if self._allow_low_confidence(local_signal):
                detail(
                    f"完成守卫：{format_subscribe(subscribe)} 命中 L 目标满足信号，"
                    f"按 {self.mode} 模式放行"
                )
                return
            self._observe_low_confidence(data, subscribe, local_signal)
            return

        self._block_completion(
            data,
            subscribe,
            signal,
            reason=self._completion_block_reason(signal, local_result),
        )

    def _local_signal(self, subscribe, mediainfo, meta=None):
        """计算 L 信号；目标范围外后续集仍会阻断目标满足口径。"""
        return self._local_signal_result(subscribe, mediainfo, meta).signal

    def _local_signal_result(self, subscribe, mediainfo, meta=None) -> LocalSignalResult:
        """计算 L 信号并保留失败原因，便于完成守卫输出可诊断日志。"""
        if not self.tmdb_episodes_fn:
            return LocalSignalResult(blocked_reason="缺少 TMDB 分集数据入口，未命中 L")
        scope = build_scope(subscribe, mediainfo, self.tmdb_episodes_fn)
        future_episode = self._first_blocking_future_episode(subscribe, scope)
        if future_episode:
            return LocalSignalResult(
                blocked_reason=self._format_future_blocked_reason(future_episode)
            )
        return check_l_signal_detail(
            subscribe,
            scope,
            mediainfo=mediainfo,
            meta=meta,
            resolve_missing_fn=self.resolve_missing_fn,
        )

    @staticmethod
    def _best_version_mode_label(subscribe) -> str:
        """按订阅实际洗版形态返回完成守卫日志标签。"""
        if is_full_best_version_subscribe(subscribe):
            return "洗版"
        if is_tv_episode_best_version_subscribe(subscribe):
            return "分集洗版"
        return "洗版"

    @staticmethod
    def _format_future_episode(episode) -> str:
        """把后续集排期格式化为简短日志片段。"""
        if isinstance(episode, dict):
            number = episode.get("episode_number")
            air_date = episode.get("air_date")
        else:
            number = getattr(episode, "episode_number", None)
            air_date = getattr(episode, "air_date", None)
        episode_label = f"E{number}" if number is not None else "未知集号"
        return f"{episode_label}，播出日期：{air_date or '未知'}"

    @classmethod
    def _format_future_blocked_reason(cls, episode) -> str:
        """说明 TMDB 已存在当前订阅目标外的后续集。"""
        return f"TMDB 已存在目标范围外的后续集（{cls._format_future_episode(episode)}）"

    @staticmethod
    def _future_episode_number(episode) -> int | None:
        """解析 TMDB 分集集号；无法确认归属目标范围时按未知处理。"""
        number = episode_field(episode, "episode_number", None)
        try:
            return int(number)
        except (TypeError, ValueError):
            return None

    def _first_blocking_future_episode(self, subscribe, scope):
        """返回当前订阅目标范围外的最早后续集。"""
        target_episodes = set(target_episode_range(subscribe))
        for episode in scope_future_episodes(scope):
            number = self._future_episode_number(episode)
            if number is None or not target_episodes or number not in target_episodes:
                return episode
        return None

    @staticmethod
    def _completion_block_reason(signal: CompletionSignal, local_result: LocalSignalResult) -> str:
        """普通未完成否决优先使用 L 失败诊断，避免用户只看到泛化无信号。"""
        if (
            signal.signals == ["none"]
            and signal.reason == "无信号确认当前目标范围已播完"
            and local_result is not None
            and local_result.blocked_reason
            and local_result.blocked_reason != "未命中 L"
        ):
            return local_result.blocked_reason
        return signal.reason

    def _allow_low_confidence(self, signal: CompletionSignal) -> bool:
        """按守卫模式判断低置信 I/L 是否可立即完成。"""
        if "L:target_satisfied" in signal.signals and (
            signal.scope_total < 3 or signal.scope_high_risk
        ):
            return False
        if self.mode == "loose":
            return True
        if self.mode == "balanced":
            return signal.scope_total >= 3 and not signal.scope_high_risk
        return False

    def _allow_unstable_local_completion(self, local_signal: CompletionSignal,
                                         unstable_signal: CompletionSignal) -> bool:
        """F 不稳定时只允许可信 L 绕过普通波动，不绕过 total 缩小风险。"""
        allowed, _ = self._allow_unstable_local_completion_detail(local_signal, unstable_signal)
        return allowed

    def _allow_unstable_local_completion_detail(self, local_signal: CompletionSignal,
                                                unstable_signal: CompletionSignal) -> tuple[bool, str]:
        """F 不稳定时给出 L 是否可覆盖以及不可覆盖原因。"""
        if local_signal is None:
            return False, ""
        if "L:target_satisfied" not in local_signal.signals:
            return False, "未命中 L"
        if unstable_signal.volatility_direction == "down":
            return False, "F 缩小风险"
        if local_signal.scope_total < 3:
            return False, "短样本 L"
        if local_signal.scope_high_risk:
            return False, "高风险目标范围"
        if self.mode == "strict":
            return False, "strict 模式限制"
        if self.mode in ("balanced", "loose"):
            return True, ""
        return False, f"{self.mode} 模式限制"

    def _observe_low_confidence(self, data, subscribe, signal: CompletionSignal):
        """低置信信号未获策略直接放行时，消费令牌或进入完成前观察。"""
        total_episode = signal.scope_total or subscribe.total_episode
        if self.timeout_manager.consume_release(
            subscribe, signal, total_episode=total_episode
        ):
            detail(f"完成守卫：{format_subscribe(subscribe)} 低置信观察已释放，放行完成")
            return
        logger.info(
            f"完成守卫：{format_subscribe(subscribe)} 低置信完结（{signal.reason}），"
            "进入完成前观察"
        )
        data.cancel = True
        data.source = "subscribeassistantenhanced"
        data.reason = signal.reason
        self.mark_pending_fn(subscribe, source="guard_veto", reason=signal.reason)
        self.timeout_manager.record_block(
            subscribe, signal=signal, total_episode=total_episode
        )

    def _block_completion(self, data, subscribe, signal: CompletionSignal, reason: str = None):
        """记录普通完成否决并进入待定观察。"""
        block_reason = reason or signal.reason
        logger.info(
            f"完成守卫：{format_subscribe(subscribe)} 未完结（{block_reason}），"
            "否决完成、进入待定（P）并开始超时计时"
        )
        data.cancel = True
        data.source = "subscribeassistantenhanced"
        data.reason = block_reason
        self.mark_pending_fn(subscribe, source="guard_veto", reason=block_reason)
        self.timeout_manager.record_block(subscribe)
