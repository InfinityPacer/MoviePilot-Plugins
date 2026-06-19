"""域 ②：完成守卫——CompletionCheck 事件处理。"""
from typing import Callable

from app.chain.subscribe import SubscribeChain
from app.log import logger
from app.schemas.event import SubscribeCompletionCheckEventData
from app.schemas.types import MediaType

from .engine.scope import build_scope
from .engine.local import check_l_signal
from .engine.signals import has_future_episodes, has_future_next_episode
from .engine.types import CompletionSignal, PendingTimeoutManagerProtocol
from .shared.log import detail
from .shared.subscribe import format_subscribe, resolve_subscribe_media_type


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
        detail(f"完成守卫：收到完成检查 {format_subscribe(subscribe)}")

        if resolve_subscribe_media_type(subscribe) != MediaType.TV:
            return

        if self.pending_download_enabled and self.has_active_downloads_fn(subscribe):
            logger.info(f"完成守卫：{format_subscribe(subscribe)} 存在进行中的下载，否决完成（等待下载转移入库）")
            data.cancel = True
            data.source = "subscribeassistantenhanced"
            data.reason = "存在进行中的下载，等待下载完成并转移入库"
            return

        signal: CompletionSignal = self.evaluate_fn(subscribe, data.mediainfo)

        if subscribe.best_version:
            if not signal.stable:
                mode_label = "全集洗版" if subscribe.best_version_full else "分集洗版"
                logger.info(f"完成守卫：{format_subscribe(subscribe)} {mode_label}信号不稳定（{signal.reason}），否决完成")
                data.cancel = True
                data.source = "subscribeassistantenhanced"
                data.reason = signal.reason
                return
            return

        if not signal.stable:
            local_signal = self._local_signal(subscribe, data.mediainfo, data.meta)
            if local_signal is not None and self._allow_unstable_local_completion(local_signal, signal):
                detail(
                    f"完成守卫：{format_subscribe(subscribe)} F 不稳定但命中可信 L 目标满足信号，"
                    f"按 {self.mode} 模式放行"
                )
                return
            logger.info(f"完成守卫：{format_subscribe(subscribe)} 信号不稳定（{signal.reason}），否决完成并进入待定（P）")
            data.cancel = True
            data.source = "subscribeassistantenhanced"
            data.reason = signal.reason
            self.mark_pending_fn(subscribe, source="guard_veto", reason=signal.reason)
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

        local_signal = self._local_signal(subscribe, data.mediainfo, data.meta)
        if local_signal is not None:
            if self._allow_low_confidence(local_signal):
                detail(
                    f"完成守卫：{format_subscribe(subscribe)} 命中 L 目标满足信号，"
                    f"按 {self.mode} 模式放行"
                )
                return
            self._observe_low_confidence(data, subscribe, local_signal)
            return

        self._block_completion(data, subscribe, signal)

    def _local_signal(self, subscribe, mediainfo, meta=None):
        """计算 L 信号；明确存在未来集时不允许目标满足口径绕过排期。"""
        if not self.tmdb_episodes_fn:
            return None
        tmdb_info = mediainfo.tmdb_info if mediainfo else None
        if has_future_next_episode(tmdb_info, subscribe.season):
            return None
        scope = build_scope(subscribe, mediainfo, self.tmdb_episodes_fn)
        if has_future_episodes(scope.episodes):
            return None
        if meta is not None:
            resolve_missing = self.resolve_missing_fn
            if resolve_missing is None:
                resolve_missing = SubscribeChain().resolve_subscribe_missing
            satisfied, _ = resolve_missing(
                subscribe=subscribe,
                meta=meta,
                mediainfo=mediainfo,
                best_version_accept_downloaded=bool(
                    subscribe.best_version and not subscribe.best_version_full
                ),
            )
            if not satisfied:
                return None
            return CompletionSignal(
                completed=True,
                confidence="low",
                stable=True,
                signals=["L:target_satisfied"],
                reason="订阅目标范围已无待下载集",
                scope_total=scope.total or subscribe.total_episode,
                scope_high_risk=scope.high_risk,
            )
        return check_l_signal(subscribe, scope)

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
        if "L:target_satisfied" not in local_signal.signals:
            return False
        if unstable_signal.volatility_direction == "down":
            return False
        return self._allow_low_confidence(local_signal)

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

    def _block_completion(self, data, subscribe, signal: CompletionSignal):
        """记录普通完成否决并进入待定观察。"""
        logger.info(
            f"完成守卫：{format_subscribe(subscribe)} 未完结（{signal.reason}），"
            "否决完成、进入待定（P）并开始超时计时"
        )
        data.cancel = True
        data.source = "subscribeassistantenhanced"
        data.reason = signal.reason
        self.mark_pending_fn(subscribe, source="guard_veto", reason=signal.reason)
        self.timeout_manager.record_block(subscribe)
