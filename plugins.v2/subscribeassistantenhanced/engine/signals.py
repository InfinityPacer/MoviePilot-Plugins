"""M + E + I 完结信号实现。"""
from datetime import date
from typing import Optional

from .types import CompletionSignal, SeasonScope
from ..shared.media import parse_date


def _field(data, name: str, default=None):
    """读取 TMDB 原始 dict 或对象字段，避免不同来源的数据形态吞掉信号。"""
    if isinstance(data, dict):
        return data.get(name, default)
    return getattr(data, name, default)


def _episode_number(episode) -> Optional[int]:
    """返回可比较集号；缺失或不可解析时返回 None。"""
    number = _field(episode, "episode_number", None)
    try:
        return int(number)
    except (TypeError, ValueError):
        return None


def _episode_air_date(episode) -> Optional[date]:
    """返回集播出日期，兼容对象和 TMDB 原始 dict。"""
    return parse_date(_field(episode, "air_date", None))


def _scope_last_aired_episode(episodes: list, as_of: Optional[date] = None):
    """返回 scope 内最后一集已播分集，字段读取兼容对象和 TMDB 原始 dict。"""
    today = as_of or date.today()
    aired = []
    for episode in episodes or []:
        air = _episode_air_date(episode)
        if air and air <= today:
            aired.append((air, _episode_number(episode) or 0, episode))
    if not aired:
        return None
    return max(aired, key=lambda item: (item[0], item[1]))[2]


def all_scope_episodes_aired(scope: SeasonScope, as_of: Optional[date] = None) -> bool:
    """判断 SeasonScope 内所有分集是否都已播出，兼容对象和 TMDB 原始 dict。"""
    if not scope.episodes:
        return False
    today = as_of or date.today()
    for episode in scope.episodes:
        air = _episode_air_date(episode)
        if not air or air > today:
            return False
    return True


def check_m_signal(scope: SeasonScope, as_of: Optional[date] = None) -> Optional[CompletionSignal]:
    """M：mid_season 硬否决，SeasonScope 内最后已播集为阶段中场时判定未完结。"""
    last = _scope_last_aired_episode(scope.episodes, as_of=as_of)
    if not last:
        return None
    if _field(last, "episode_type") == "mid_season":
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
    if has_scope_finale(scope, as_of=as_of) and not has_scope_future_episode(scope, as_of=as_of):
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
    has_scope_future = has_scope_future_episode(scope, as_of=today)
    if has_scope_future:
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

    # I-3：SeasonScope 内所有集已播，且目标范围内没有后续集反证。
    if all_scope_episodes_aired(scope, as_of=today) and not has_scope_future:
        return CompletionSignal(
            completed=True, confidence="low",
            signals=["I:all_aired"],
            reason="目标范围内所有集已播且无后续集反证",
        )

    # I-4：SeasonScope 内无未来集，且最后已播集超过冷却期。
    if not has_scope_future:
        last_aired = _scope_last_aired_episode(scope.episodes, as_of=today)
        if last_aired:
            air = _episode_air_date(last_aired)
            if air and (today - air).days > cooldown_days:
                return CompletionSignal(
                    completed=True, confidence="low",
                    signals=["I:cooldown"],
                    reason=f"最后集播出超 {cooldown_days} 天，无后续集反证",
                )

    return None


def scope_future_episode(scope: SeasonScope, as_of: Optional[date] = None):
    """返回当前 SeasonScope 内证明目标范围尚未播完的分集。"""
    today = as_of or date.today()
    last_aired = _scope_last_aired_episode(scope.episodes, as_of=today)
    last_aired_number = _episode_number(last_aired) if last_aired else None
    candidates = []
    for episode in scope.episodes or []:
        number = _episode_number(episode)
        air = _episode_air_date(episode)
        if air and air > today:
            candidates.append(episode)
        elif (
            air is None
            and number is not None
            and last_aired_number is not None
            and number > last_aired_number
        ):
            candidates.append(episode)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda episode: (
            _episode_air_date(episode) or date.max,
            _episode_number(episode) or 0,
        ),
    )


def has_scope_future_episode(scope: SeasonScope, as_of: Optional[date] = None) -> bool:
    """判断当前 SeasonScope 是否存在后续集反证。"""
    return scope_future_episode(scope, as_of=as_of) is not None


def scope_finale_episode(scope: SeasonScope):
    """返回可信的目标范围 finale；多标记或非末集标记均视为 TMDB 数据异常。"""
    if not scope.episodes:
        return None
    finale_episodes = [ep for ep in scope.episodes if _field(ep, "episode_type") == "finale"]
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
    air = _episode_air_date(finale)
    return bool(air and air <= (as_of or date.today()))


def last_aired_episode(episodes: list, as_of: Optional[date] = None):
    """返回 SeasonScope 内最后一个已播出的集。"""
    return _scope_last_aired_episode(episodes, as_of=as_of)
