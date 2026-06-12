"""M + E + I 完结信号实现。"""
from datetime import date, timedelta
from typing import Optional

from .types import CompletionSignal, SeasonScope
from ..shared.media import last_aired_episode as _last_aired, all_aired as _all_aired, parse_date


def _field(data, name: str, default=None):
    """读取 TMDB 原始 dict 或对象字段，避免不同来源的数据形态吞掉信号。"""
    if isinstance(data, dict):
        return data.get(name, default)
    return getattr(data, name, default)


def check_m_signal(scope: SeasonScope, as_of: Optional[date] = None) -> Optional[CompletionSignal]:
    """M：mid_season 硬否决，SeasonScope 内最后已播集为阶段中场时判定未完结。"""
    last = _last_aired(scope.episodes, as_of=as_of)
    if not last:
        return None
    if last.episode_type == "mid_season":
        return CompletionSignal(
            completed=False, stable=True,
            signals=["M:mid_season"],
            reason="最后已播集为 mid_season，阶段中场",
        )
    return None


def check_e_signal(mediainfo, scope: SeasonScope) -> Optional[CompletionSignal]:
    """E：基线信号，按剧级状态或 SeasonScope 末集 finale 判断完结。"""
    status = _field(mediainfo.tmdb_info, "status", "")
    if status in ("Ended", "Canceled"):
        return CompletionSignal(
            completed=True, confidence="high",
            signals=[f"E:{status.lower()}"],
            reason=f"status={status}",
        )
    if has_scope_finale(scope):
        return CompletionSignal(
            completed=True, confidence="high",
            signals=["E:finale"],
            reason="目标范围末集有 finale 标记",
        )
    return None


def check_i_signal(mediainfo, scope: SeasonScope, cooldown_days: int = 14,
                   high_risk: bool = False,
                   as_of: Optional[date] = None) -> Optional[CompletionSignal]:
    """I：季级信号；I-3/I-4 在 high_risk 范围内不放行。"""
    today = as_of or date.today()
    tmdb_info = mediainfo.tmdb_info
    if not tmdb_info:
        return None

    # I-1：TMDB 有更晚的季
    seasons = _field(tmdb_info, "seasons", []) or []
    for s in seasons:
        season_number = _field(s, "season_number", 0)
        if season_number > scope.season:
            return CompletionSignal(
                completed=True, confidence="medium",
                signals=["I:next_season"],
                reason=f"TMDB 存在 S{season_number}",
            )

    # I-2：last_episode_to_air 季号 > 当前季
    last_ep = _field(tmdb_info, "last_episode_to_air", None)
    last_season = _field(last_ep, "season_number", 0) if last_ep else 0
    if last_ep and last_season > scope.season:
        return CompletionSignal(
            completed=True, confidence="medium",
            signals=["I:last_ep_beyond"],
            reason=f"last_episode_to_air 属于 S{last_season}",
        )

    # I-3 和 I-4 在 high_risk 范围内不放行，避免绝对季断档期间误判完结。
    if high_risk or scope.high_risk:
        return None

    # I-3：SeasonScope 内所有集已播，且 TMDB 没有同季 next_episode_to_air。
    next_ep = _field(tmdb_info, "next_episode_to_air", None)
    has_next_this_season = (
        next_ep is not None
        and _field(next_ep, "season_number", 0) == scope.season
    )

    if _all_aired(scope.episodes, as_of=today) and not has_next_this_season:
        return CompletionSignal(
            completed=True, confidence="low",
            signals=["I:all_aired"],
            reason="目标范围内所有集已播且无同季下一集",
        )

    # I-4：SeasonScope 内无未来集，且最后已播集超过冷却期。
    if not _has_future_episodes(scope.episodes, today):
        last_aired = _last_aired(scope.episodes, as_of=today)
        if last_aired:
            air = parse_date(last_aired.air_date)
            if air and (today - air).days > cooldown_days:
                if not has_next_this_season:
                    return CompletionSignal(
                        completed=True, confidence="low",
                        signals=["I:cooldown"],
                        reason=f"最后集播出超 {cooldown_days} 天，无本季新集",
                    )

    return None


def _has_future_episodes(episodes: list, today: date) -> bool:
    """判断 SeasonScope 内是否存在未来播出的集。"""
    for ep in episodes:
        air = parse_date(ep.air_date)
        if air and air > today:
            return True
    return False


def has_scope_finale(scope: SeasonScope) -> bool:
    """finale 必须是 SeasonScope 的最后目标集才放行。"""
    if not scope.episodes:
        return False
    last_ep = scope.episodes[-1]
    return last_ep.episode_type == "finale"


def last_aired_episode(episodes: list, as_of: Optional[date] = None):
    """返回 SeasonScope 内最后一个已播出的集。"""
    return _last_aired(episodes, as_of=as_of)
