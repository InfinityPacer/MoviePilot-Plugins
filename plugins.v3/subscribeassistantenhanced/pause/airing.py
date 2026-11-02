"""播出暂停：完结信号前置过滤后按间隔判断是否暂停订阅。"""
import re
from datetime import date, timedelta
from typing import Callable, Optional

from app.schemas.types import MediaType

from ..engine.types import CompletionSignal, PauseRecord
from ..shared.log import detail
from ..shared.media import (
    episode_candidates_after,
    episode_field,
    date_context,
    first_available_scope_episode_air_date,
    get_tv_season_air_date,
    parse_date,
    resolve_airing_next_episode,
)
from ..shared.subscribe import format_subscribe, resolve_subscribe_media_type


class AiringPauseChecker:
    """播出暂停判定：完结信号确认后不暂停，否则按间隔判断。"""

    def __init__(self, pause_days: int, evidence_pipeline,
                 movie_air_days: int = 0, tv_air_days: int = 0,
                 pause_delay_days: int = 0,
                 last_download_date_fn: Optional[Callable[[object], Optional[date]]] = None):
        """保存播出间隔与上映前暂停阈值。

        :param pause_delay_days: 最近一次下载后 N 天内不新建播出间隔暂停，0 表示不延迟
        :param last_download_date_fn: 读取订阅最近一次下载日期，仅在命中播出间隔条件且启用延迟时调用
        """
        self._pause_days = pause_days
        self._evidence_pipeline = evidence_pipeline
        self._movie_air_days = movie_air_days
        self._tv_air_days = tv_air_days
        self._pause_delay_days = pause_delay_days
        self._last_download_date = last_download_date_fn

    def check_pre_air(self, subscribe, mediainfo,
                      as_of: Optional[date] = None,
                      episodes: Optional[list] = None) -> Optional[PauseRecord]:
        """检查电影上映或剧集开播前是否应暂停。"""
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
                    detail=f"{date_context('上映日期', release_date, as_of=today)}，暂未到订阅窗口",
                )
            return None

        if media_type != MediaType.TV:
            return None

        if not self._tv_air_days:
            return None
        air_date = parse_date(get_tv_season_air_date(
            mediainfo,
            subscribe.season,
        ))
        if air_date is None:
            air_date = first_available_scope_episode_air_date(subscribe, episodes or [])
        if air_date is None:
            # 剧集没有任何可用排期时保持暂停，避免未知开播窗口被集数待定提前接管。
            return PauseRecord(
                reason="pre_air",
                since=0.0,
                detail="开播日期未知",
            )
        if today < air_date - timedelta(days=self._tv_air_days):
            return PauseRecord(
                reason="pre_air",
                since=0.0,
                detail=f"{date_context('开播日期', air_date, as_of=today)}，暂未到订阅窗口",
            )
        return None

    def check(self, subscribe, mediainfo, next_episode, latest_episode,
              episodes: Optional[list] = None,
              as_of: Optional[date] = None) -> Optional[PauseRecord]:
        """按聚合字段、SeasonScope 和 note 首待下载集检查是否应播出暂停。"""
        if not self._pause_days:
            return None
        today = as_of or date.today()

        signal: CompletionSignal = self._evidence_pipeline.evaluate(
            subscribe,
            mediainfo,
        ).primary_signal
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
                    if self._within_pause_delay(subscribe, today):
                        return None
                    return PauseRecord(
                        reason="airing_gap",
                        since=0.0,
                        detail=f"{date_context('下一集日期', air, as_of=today)}",
                    )
                return None

        return None

    def should_resume_airing_gap(self, subscribe, mediainfo, next_episode,
                                 episodes: Optional[list] = None,
                                 current_record: Optional[PauseRecord] = None,
                                 as_of: Optional[date] = None) -> bool:
        """判断已有 airing_gap 暂停是否具备明确恢复证据。"""
        if not self._pause_days:
            # 播出间隔规则已关闭，遗留的 airing_gap 暂停不再有依据。
            return True
        today = as_of or date.today()

        signal: CompletionSignal = self._evidence_pipeline.evaluate(
            subscribe,
            mediainfo,
        ).primary_signal
        if signal.completed:
            return True

        paused_air_date = self._parse_pause_air_date(current_record)
        if paused_air_date and paused_air_date <= today:
            return True

        resolved_next = self._resolve_airing_resume_episode(
            subscribe,
            next_episode,
            episodes or [],
            as_of=today,
        )
        if not resolved_next:
            return False
        next_air_date = episode_field(resolved_next, "air_date")
        air = parse_date(next_air_date)
        if not air:
            return False
        return (air - today).days <= self._pause_days

    def _within_pause_delay(self, subscribe, today: date) -> bool:
        """最近一次下载仍在延迟期内时推迟播出间隔暂停，让刚更新的集继续搜索后续版本。

        只推迟新建暂停；延迟期满后由下一次巡检按原规则暂停，已暂停订阅的恢复不受影响。
        """
        if not self._pause_delay_days or not self._last_download_date:
            return False
        last_download = self._last_download_date(subscribe)
        if not last_download:
            return False
        elapsed = (today - last_download).days
        if elapsed >= self._pause_delay_days:
            return False
        detail(
            f"播出暂停：{format_subscribe(subscribe)} 最近下载于 {last_download}，"
            f"仍在 {self._pause_delay_days} 天延迟期内，暂不暂停"
        )
        return True

    def _resolve_airing_resume_episode(self, subscribe, aggregate_episode,
                                       episodes: list, as_of: date):
        """解析 airing_gap 恢复使用的窗口集，允许下一集已进入下载窗口。"""
        resolved_next = resolve_airing_next_episode(
            subscribe,
            aggregate_episode,
            episodes,
            as_of=as_of,
        )
        if resolved_next:
            return resolved_next
        window_start = as_of - timedelta(days=self._pause_days)
        candidates = [
            episode
            for episode in episode_candidates_after(subscribe, episodes, date.min)
            if parse_date(episode_field(episode, "air_date")) >= window_start
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda episode: (
                parse_date(episode_field(episode, "air_date")),
                episode_field(episode, "episode_number", 0),
            ),
        )

    @staticmethod
    def _parse_pause_air_date(record: Optional[PauseRecord]) -> Optional[date]:
        """从已保存的播出暂停说明中提取当时的下一集日期。"""
        if not record or record.reason != "airing_gap" or not record.detail:
            return None
        match = re.search(r"\d{4}-\d{2}-\d{2}", record.detail)
        if not match:
            return None
        return parse_date(match.group(0))
