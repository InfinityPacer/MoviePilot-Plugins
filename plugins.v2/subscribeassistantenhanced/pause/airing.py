"""域 ④：播出暂停——完结信号前置过滤后按间隔判断。"""
from datetime import date, timedelta
from typing import Callable, Optional

from app.schemas.types import MediaType

from ..engine.types import CompletionSignal, PauseRecord
from ..shared.media import (
    episode_field,
    get_tv_season_air_date,
    parse_date,
    resolve_airing_next_episode,
)
from ..shared.subscribe import resolve_subscribe_media_type


class AiringPauseChecker:
    """播出暂停判定：完结信号确认后不暂停，否则按间隔判断。"""

    def __init__(self, pause_days: int, evaluate_fn: Callable,
                 movie_air_days: int = 0, tv_air_days: int = 0):
        """保存播出间隔与上映前暂停阈值。"""
        self._pause_days = pause_days
        self._evaluate = evaluate_fn
        self._movie_air_days = movie_air_days
        self._tv_air_days = tv_air_days

    def check_pre_air(self, subscribe, mediainfo,
                      as_of: Optional[date] = None) -> Optional[PauseRecord]:
        """检查电影上映或电视剧开播前是否应暂停。"""
        today = as_of or date.today()
        media_type = resolve_subscribe_media_type(subscribe)

        if media_type == MediaType.MOVIE:
            if not self._movie_air_days:
                return None
            release_date = parse_date(mediainfo.release_date)
            if release_date is None:
                # 上映日期无法解析时默认暂停，避免在不明窗口期下载
                return PauseRecord(
                    reason="pre_air",
                    since=0.0,
                    detail="上映日期未知，暂停等待",
                )
            if today < release_date - timedelta(days=self._movie_air_days):
                return PauseRecord(
                    reason="pre_air",
                    since=0.0,
                    detail=f"电影 {release_date} 上映，暂未到订阅窗口",
                )
            return None

        if media_type != MediaType.TV:
            return None

        if not self._tv_air_days:
            return None
        air_date = get_tv_season_air_date(
            mediainfo,
            subscribe.season,
        ) or mediainfo.first_air_date
        air_date = parse_date(air_date)
        if air_date is None:
            # 开播日期无法解析时默认暂停，避免在不明窗口期下载
            return PauseRecord(
                reason="pre_air",
                since=0.0,
                detail="开播日期未知，暂停等待",
            )
        if today < air_date - timedelta(days=self._tv_air_days):
            return PauseRecord(
                reason="pre_air",
                since=0.0,
                detail=f"电视剧 {air_date} 开播，暂未到订阅窗口",
            )
        return None

    def check(self, subscribe, mediainfo, next_episode, latest_episode,
              episodes: Optional[list] = None,
              as_of: Optional[date] = None) -> Optional[PauseRecord]:
        """按聚合字段、SeasonScope 和 note 首待下载集检查是否应播出暂停。"""
        today = as_of or date.today()

        signal: CompletionSignal = self._evaluate(subscribe, mediainfo)
        if signal.completed:
            return None

        resolved_next = resolve_airing_next_episode(
            subscribe,
            next_episode,
            episodes or [],
            as_of=today,
        )
        if resolved_next:
            next_air_date = episode_field(resolved_next, "air_date")
            air = parse_date(next_air_date)
            if air:
                days_until = (air - today).days
                if days_until > self._pause_days:
                    return PauseRecord(
                        reason="airing_gap",
                        since=0.0,
                        detail=f"下一集 {next_air_date}，距今 {days_until} 天",
                    )
                return None

        return None
