"""域 ④：无下载处理策略——上映后超期且无下载时按配置暂停、完成或删除订阅。"""
from datetime import date, timedelta
from typing import Optional

from ..shared.log import detail
from ..shared.media import get_tv_season_air_date, parse_date
from ..shared.subscribe import format_subscribe


class NoDownloadPolicy:
    """无下载处理策略：按媒体类型在上映后超期且无下载时给出动作。"""

    def __init__(self, movie_days: int = 0, tv_days: int = 0,
                 actions: Optional[list] = None):
        """保存电影、剧集的超期天数与启用动作。"""
        self._movie_days = movie_days
        self._tv_days = tv_days
        self._actions_ordered = list(actions or [])

    def evaluate(self, subscribe, mediainfo, last_download_date=None,
                 as_of: Optional[date] = None) -> Optional[str]:
        """返回应执行的动作 pause/complete/delete，或 None。

        截止日取上映或开播日、订阅创建日、订阅最后更新日、最近下载日中的最大值，
        再加对应类型的无下载天数。今天超过截止日才处理；
        动作按配置顺序取该媒体类型的第一个。
        """
        is_movie = subscribe.type == "电影"
        days = self._movie_days if is_movie else self._tv_days
        if not days:
            return None

        suffix = "movie" if is_movie else "tv"
        relevant = [action for action in self._actions_ordered if action.endswith(f"_{suffix}")]
        if not relevant:
            return None
        action = relevant[0].split("_")[0]
        if action not in {"pause", "complete", "delete"}:
            return None

        if is_movie:
            air_date = parse_date(mediainfo.release_date)
        else:
            air_date = parse_date(
                get_tv_season_air_date(mediainfo, subscribe.season)
                or mediainfo.first_air_date
            )
        if not air_date:
            return None

        subscribe_date = parse_date(
            subscribe.date,
            fmt="%Y-%m-%d %H:%M:%S",
        )
        last_update_date = parse_date(
            subscribe.last_update,
            fmt="%Y-%m-%d %H:%M:%S",
        )
        dates = [value for value in (air_date, subscribe_date, last_update_date, last_download_date) if value]
        if not dates:
            return None

        today = as_of or date.today()
        deadline = max(dates) + timedelta(days=days)
        if today > deadline:
            detail(f"无下载策略：{format_subscribe(subscribe)} 超过无下载截止日 {deadline}（阈值 {days} 天），建议动作={action}")
            return action
        return None
