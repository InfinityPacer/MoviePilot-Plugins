"""域 ②：完成守卫——CompletionCheck 事件处理。"""
from typing import Callable

from app.log import logger
from app.schemas.event import SubscribeCompletionCheckEventData
from app.schemas.types import MediaType

from .engine.types import CompletionSignal, CompletionVerifierProtocol, PendingTimeoutManagerProtocol
from .shared.log import detail
from .shared.subscribe import format_subscribe, resolve_subscribe_media_type


class CompletionGuard:
    """完成守卫：下载待定检查 + 完结信号引擎最终裁决。"""

    def __init__(self,
                 evaluate_fn: Callable,
                 has_active_downloads_fn: Callable,
                 mark_pending_fn: Callable,
                 verifier: CompletionVerifierProtocol,
                 timeout_manager: PendingTimeoutManagerProtocol,
                 pending_download_enabled: bool = True):
        """保存完成守卫依赖与下载中待定开关。"""
        self.evaluate_fn = evaluate_fn
        self.has_active_downloads_fn = has_active_downloads_fn
        self.mark_pending_fn = mark_pending_fn
        self.verifier = verifier
        self.timeout_manager = timeout_manager
        self.pending_download_enabled = pending_download_enabled

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
                logger.info(f"完成守卫：{format_subscribe(subscribe)} 洗版订阅信号不稳定（{signal.reason}），否决完成")
                data.cancel = True
                data.source = "subscribeassistantenhanced"
                data.reason = signal.reason
            return

        if not signal.stable:
            logger.info(f"完成守卫：{format_subscribe(subscribe)} 信号不稳定（{signal.reason}），否决完成并进入待定（P）")
            data.cancel = True
            data.source = "subscribeassistantenhanced"
            data.reason = signal.reason
            self.mark_pending_fn(subscribe, source="guard_veto", reason=signal.reason)
            return

        if signal.completed:
            if signal.confidence == "low":
                if self.timeout_manager.consume_release(
                    subscribe.id,
                    signal,
                    total_episode=getattr(signal, "scope_total", 0) or subscribe.total_episode,
                ):
                    detail(f"完成守卫：{format_subscribe(subscribe)} 低置信观察已释放，放行完成并登记完成快照")
                    self.verifier.snapshot(subscribe, data.mediainfo, None)
                    return
                logger.info(f"完成守卫：{format_subscribe(subscribe)} 低置信完结（{signal.reason}），进入完成前观察")
                data.cancel = True
                data.source = "subscribeassistantenhanced"
                data.reason = signal.reason
                self.mark_pending_fn(subscribe, source="guard_veto", reason=signal.reason)
                self.timeout_manager.record_block(
                    subscribe.id,
                    signal=signal,
                    total_episode=getattr(signal, "scope_total", 0) or subscribe.total_episode,
                )
                return
            if signal.confidence != "high":
                detail(f"完成守卫：{format_subscribe(subscribe)} 已判定完结但置信度非高，放行完成并登记完成快照")
                self.verifier.snapshot(subscribe, data.mediainfo, None)
            else:
                detail(f"完成守卫：{format_subscribe(subscribe)} 高置信完结，放行完成")
            return

        logger.info(f"完成守卫：{format_subscribe(subscribe)} 未完结（{signal.reason}），否决完成、进入待定（P）并开始超时计时")
        data.cancel = True
        data.source = "subscribeassistantenhanced"
        data.reason = signal.reason
        self.mark_pending_fn(subscribe, source="guard_veto", reason=signal.reason)
        self.timeout_manager.record_block(subscribe.id)
