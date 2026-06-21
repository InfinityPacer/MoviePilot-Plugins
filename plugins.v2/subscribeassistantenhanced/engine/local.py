"""L：订阅目标覆盖信号。"""
from typing import Optional

from ..shared.subscribe import build_subscribe_meta
from .types import CompletionSignal, SeasonScope


def check_l_signal(subscribe, scope: SeasonScope, mediainfo, meta=None,
                   resolve_missing_fn=None) -> Optional[CompletionSignal]:
    """按主程序订阅目标缺集口径生成低置信 L 信号。"""
    start_episode = subscribe.start_episode or 1
    total_episode = subscribe.total_episode or 0
    if total_episode < start_episode:
        return None
    if resolve_missing_fn is None:
        return None
    if meta is None:
        meta = build_subscribe_meta(subscribe, failure_context="L 信号缺集查询失败")
        if meta is None:
            return None
    satisfied, _ = resolve_missing_fn(
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
