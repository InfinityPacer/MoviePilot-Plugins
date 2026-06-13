"""L：媒体库覆盖信号。"""
from typing import Callable, Optional

from .types import CompletionSignal, SeasonScope


def check_l_signal(subscribe, scope: SeasonScope,
                   detect_missing_episodes_fn: Optional[Callable]) -> Optional[CompletionSignal]:
    """目标范围无缺集时生成低置信 L 信号；无法检测时不产生信号。"""
    if not detect_missing_episodes_fn:
        return None
    missing = detect_missing_episodes_fn(subscribe)
    if missing != []:
        return None
    return CompletionSignal(
        completed=True,
        confidence="low",
        stable=True,
        signals=["L:library_covered"],
        reason="媒体库已覆盖当前订阅目标范围",
        scope_total=scope.total or subscribe.total_episode,
        scope_high_risk=scope.high_risk,
    )
