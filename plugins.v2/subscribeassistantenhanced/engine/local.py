"""L：订阅目标覆盖信号。"""
from typing import Optional

from ..shared.subscribe import pending_subscription_episodes
from .types import CompletionSignal, SeasonScope


def check_l_signal(subscribe, scope: SeasonScope) -> Optional[CompletionSignal]:
    """订阅目标范围均已记入 note 时生成低置信 L 信号。"""
    start_episode = subscribe.start_episode or 1
    total_episode = subscribe.total_episode or 0
    if total_episode < start_episode:
        return None
    if pending_subscription_episodes(subscribe):
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
