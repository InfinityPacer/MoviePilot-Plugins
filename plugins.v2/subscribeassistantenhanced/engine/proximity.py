"""完成阶段接近度判断，供 F 信号和待定入口共享。"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from ..shared.media import episode_field, parse_date


@dataclass
class CompletionProximity:
    """目标范围是否已进入完成前风险区。"""
    near_completion: bool
    aired_ratio: float = 0.0
    remaining_count: Optional[int] = None
    reasons: list[str] = field(default_factory=list)


def assess_completion_proximity(
        episodes: Iterable,
        total: int,
        missing_episodes: Optional[list[int]] = None,
        as_of: Optional[date] = None,
        completion_check: bool = False,
) -> CompletionProximity:
    """组合已播比例、末集日期、剩余目标和完成检查上下文判断是否接近完结。"""
    today = as_of or date.today()
    episode_list = list(episodes or [])
    total_count = total or len(episode_list)
    air_dates = [
        parsed
        for parsed in (
            parse_date(episode_field(episode, "air_date"))
            for episode in episode_list
        )
        if parsed is not None
    ]
    aired_count = sum(1 for air_date in air_dates if air_date <= today)
    aired_ratio = (aired_count / total_count) if total_count else 0.0
    remaining_count = None if missing_episodes is None else len(missing_episodes)

    reasons = []
    if total_count >= 3 and aired_ratio >= 0.8:
        reasons.append("aired_ratio")
    if air_dates and today >= max(air_dates) - timedelta(days=3):
        reasons.append("last_air_date")
    if remaining_count is not None and total_count >= 3 and remaining_count <= 2:
        reasons.append("few_remaining")
    if completion_check:
        reasons.append("completion_check")

    return CompletionProximity(
        near_completion=bool(reasons),
        aired_ratio=aired_ratio,
        remaining_count=remaining_count,
        reasons=reasons,
    )
