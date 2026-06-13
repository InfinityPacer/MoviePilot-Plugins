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


def check_e_signal(mediainfo, scope: SeasonScope,
                   as_of: Optional[date] = None) -> Optional[CompletionSignal]:
    """E：基线信号，按剧级状态或 SeasonScope 末集 finale 判断完结。"""
    status = _field(mediainfo.tmdb_info, "status", "")
    if status in ("Ended", "Canceled"):
        return CompletionSignal(
            completed=True, confidence="high",
            signals=[f"E:{status.lower()}"],
            reason=f"status={status}",
        )
    if has_scope_finale(scope, as_of=as_of):
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
    has_next_this_season = has_future_next_episode(
        tmdb_info, scope.season, as_of=today
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


def has_future_next_episode(tmdb_info, season: int,
                            as_of: Optional[date] = None) -> bool:
    """判断 TMDB 下一集是否属于当前季且明确尚未到播出日期。

    TMDB 在播出当天仍可能保留 next_episode_to_air；日期等于当天时按已播处理。
    日期缺失或无法解析时保守视为未来集，避免未知排期被提前完成。
    """
    if not tmdb_info:
        return False
    next_ep = _field(tmdb_info, "next_episode_to_air", None)
    if next_ep is None or _field(next_ep, "season_number", 0) != season:
        return False
    air_date = parse_date(_field(next_ep, "air_date", None))
    if air_date is None:
        return True
    return air_date > (as_of or date.today())


def _has_future_episodes(episodes: list, today: date) -> bool:
    """判断 SeasonScope 内是否存在未来播出的集。"""
    for ep in episodes:
        air = parse_date(ep.air_date)
        if air and air > today:
            return True
    return False


def scope_finale_episode(scope: SeasonScope):
    """返回可信的目标范围 finale；多标记或非末集标记均视为 TMDB 数据异常。"""
    if not scope.episodes:
        return None
    finale_episodes = [ep for ep in scope.episodes if ep.episode_type == "finale"]
    if len(finale_episodes) != 1:
        return None
    if finale_episodes[0] is not scope.episodes[-1]:
        return None
    return finale_episodes[0]


def has_scope_finale(scope: SeasonScope, as_of: Optional[date] = None) -> bool:
    """finale 必须在 SeasonScope 内唯一、位于最后一集且已播出，才可确认当前范围完结。"""
    finale = scope_finale_episode(scope)
    if not finale:
        return False
    air = parse_date(finale.air_date)
    return bool(air and air <= (as_of or date.today()))


def last_aired_episode(episodes: list, as_of: Optional[date] = None):
    """返回 SeasonScope 内最后一个已播出的集。"""
    return _last_aired(episodes, as_of=as_of)
