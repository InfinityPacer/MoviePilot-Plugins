"""完成守卫：处理 CompletionCheck 事件并按证据流水线裁决是否完成。"""
from typing import Callable

from app.log import logger
from app.schemas.event import SubscribeCompletionCheckEventData
from app.schemas.types import MediaType

from .engine.types import CompletionEvidence, CompletionSignal, PendingTimeoutManagerProtocol
from .shared.log import detail
from .shared.subscribe import (
    format_subscribe,
    is_full_best_version_subscribe,
    resolve_subscribe_media_type,
)


class CompletionGuard:
    """完成守卫：下载待定检查与完成证据流水线裁决。"""

    def __init__(self,
                 evidence_pipeline,
                 has_active_downloads_fn: Callable,
                 mark_pending_fn: Callable,
                 timeout_manager: PendingTimeoutManagerProtocol,
                 mode: str = "balanced",
                 pending_download_enabled: bool = True,
                 resolve_missing_fn: Callable = None):
        """保存完成守卫依赖与下载中待定开关。"""
        self.evidence_pipeline = evidence_pipeline
        self.has_active_downloads_fn = has_active_downloads_fn
        self.mark_pending_fn = mark_pending_fn
        self.timeout_manager = timeout_manager
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

        evidence: CompletionEvidence = self.evidence_pipeline.evaluate(
            subscribe,
            data.mediainfo,
            resolve_missing_fn=self.resolve_missing_fn,
            meta=getattr(data, "meta", None),
        )

        if evidence.hard_veto is not None:
            self._record_observation(data, subscribe, evidence.hard_veto, evidence)
            return

        if self._is_active_high_completion(evidence):
            self.timeout_manager.clear_release_token(subscribe)
            detail(
                f"完成守卫：{format_subscribe(subscribe)} 高置信完结，"
                f"按 {self.mode} 模式放行"
            )
            return

        if (
            evidence.unstable_signal is not None
            and not self._allow_unstable_target_complete(evidence)
        ):
            self._record_observation(data, subscribe, evidence.unstable_signal, evidence)
            return

        if evidence.unstable_signal is not None:
            self.timeout_manager.clear_release_token(subscribe)
            detail(
                f"完成守卫：{format_subscribe(subscribe)} F 不稳定但命中当前目标完成证据，"
                f"信号={self._signal_tags(evidence.target_complete_signal)}，按 {self.mode} 模式放行"
            )
            return

        if evidence.target_complete_signal is not None:
            signal = evidence.target_complete_signal
            if self.mode in ("balanced", "loose"):
                self.timeout_manager.clear_release_token(subscribe)
                detail(
                    f"完成守卫：{format_subscribe(subscribe)} 命中当前目标完成证据，"
                    f"信号={self._signal_tags(signal)}，按 {self.mode} 模式放行"
                )
                return
            self._record_observation(data, subscribe, signal, evidence)
            return

        if self._is_medium_i_completion(evidence.i_signal):
            self.timeout_manager.clear_release_token(subscribe)
            detail(
                f"完成守卫：{format_subscribe(subscribe)} 中置信完结，"
                f"按 {self.mode} 模式放行"
            )
            return

        low_signal = self._low_signal(evidence)
        if low_signal is not None:
            if self._allow_low_confidence(low_signal):
                self.timeout_manager.clear_release_token(subscribe)
                detail(
                    f"完成守卫：{format_subscribe(subscribe)} 低置信完结，"
                    f"按 {self.mode} 模式放行"
                )
                return
            self._consume_or_observe(data, subscribe, low_signal, evidence)
            return

        self._block_completion(
            data,
            subscribe,
            evidence.primary_signal,
            reason=self._completion_block_reason(evidence),
        )

    @staticmethod
    def _completion_block_reason(evidence: CompletionEvidence) -> str:
        """普通未完成否决优先使用 L 失败诊断，避免用户只看到泛化无信号。"""
        signal = evidence.primary_signal
        if (
            signal.signals == ["none"]
            and signal.reason == "无信号确认当前目标范围已播完"
            and evidence.local_blocked_reason
            and evidence.local_blocked_reason != "未命中 L"
        ):
            return evidence.local_blocked_reason
        return signal.reason

    def _allow_unstable_target_complete(self, evidence: CompletionEvidence) -> bool:
        """F up/普通波动只允许由当前目标完成证据在宽松策略下覆盖。"""
        if evidence.target_complete_signal is None:
            return False
        if evidence.unstable_signal.volatility_direction == "down":
            return False
        return self.mode in ("balanced", "loose")

    @staticmethod
    def _is_active_high_completion(evidence: CompletionEvidence) -> bool:
        """只接受流水线已选为主结论的高置信完成证据。"""
        return (
            evidence.high_completion is not None
            and evidence.primary_signal == evidence.high_completion
        )

    @staticmethod
    def _is_medium_i_completion(signal: CompletionSignal) -> bool:
        """识别独立的 medium I 完成证据，不把它当作 target_complete 组合证据。"""
        return (
            signal is not None
            and signal.completed
            and signal.confidence == "medium"
        )

    @staticmethod
    def _low_signal(evidence: CompletionEvidence) -> CompletionSignal:
        """返回需要按低置信策略裁决的单一 I/L 完成信号。"""
        for signal in (
            evidence.i_low_signal,
            evidence.local_signal,
            evidence.primary_signal,
        ):
            if (
                signal is not None
                and signal.completed
                and signal.confidence == "low"
            ):
                return signal
        return None

    @staticmethod
    def _signal_tags(signal: CompletionSignal) -> str:
        """把完成信号来源压缩成日志可读的组合标签。"""
        return " + ".join(signal.signals or ["none"]) if signal else "none"

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

    def _consume_or_observe(self, data, subscribe, signal: CompletionSignal,
                            evidence: CompletionEvidence):
        """完成证据未获策略直接放行时，消费令牌或进入完成前观察。"""
        total_episode = self._signal_total(signal, evidence, subscribe)
        if self.timeout_manager.consume_release_token(
            subscribe, signal, total_episode=total_episode
        ):
            detail(f"完成守卫：{format_subscribe(subscribe)} 完成前观察已释放，放行完成")
            return
        self._record_observation(data, subscribe, signal, evidence, total_episode=total_episode)

    def _record_observation(self, data, subscribe, signal: CompletionSignal,
                            evidence: CompletionEvidence, total_episode: int = None):
        """写入 guard_veto 观察前清理旧释放令牌，避免过期令牌跨信号放行。"""
        total_episode = total_episode or self._signal_total(signal, evidence, subscribe)
        self.timeout_manager.clear_release_token(subscribe)
        logger.info(
            f"完成守卫：{format_subscribe(subscribe)} 完成证据需观察（{signal.reason}），"
            "进入完成前观察"
        )
        data.cancel = True
        data.source = "subscribeassistantenhanced"
        data.reason = signal.reason
        self.mark_pending_fn(subscribe, source="guard_veto", reason=signal.reason)
        self.timeout_manager.record_observation(
            subscribe, signal=signal, total_episode=total_episode
        )

    @staticmethod
    def _signal_total(signal: CompletionSignal, evidence: CompletionEvidence, subscribe) -> int:
        """观察期增集判断优先使用证据流水线的 SeasonScope 目标集数。"""
        return signal.scope_total or evidence.scope_total or subscribe.total_episode

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
        self.timeout_manager.record_observation(subscribe)
