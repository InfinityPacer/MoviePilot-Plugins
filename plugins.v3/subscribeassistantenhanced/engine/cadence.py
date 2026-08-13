"""G：播出节奏推算，基于已知 air_date 预测窗口是否过期。"""
import statistics
from datetime import date, timedelta
from typing import Optional

from ..shared.media import episode_field, parse_date


def check_cadence_expired(episodes: list, multiplier: float = 2.5,
                           min_window_days: int = 7, min_episodes: int = 3,
                           as_of: Optional[date] = None) -> bool:
    """检查播出节奏预测窗口是否已过期。不足 min_episodes 已播集时返回 False。"""
    today = as_of or date.today()

    aired = []
    for ep in episodes:
        d = parse_date(episode_field(ep, "air_date"))
        if d and d <= today:
            aired.append(d)

    if len(aired) < min_episodes:
        return False

    aired.sort()
    intervals = [(aired[i + 1] - aired[i]).days for i in range(len(aired) - 1)]
    intervals = [iv for iv in intervals if iv > 0]
    if not intervals:
        return False

    median_interval = statistics.median(intervals)
    window_days = max(median_interval * multiplier, min_window_days)
    last_aired = aired[-1]
    deadline = last_aired + timedelta(days=window_days)

    return today > deadline
