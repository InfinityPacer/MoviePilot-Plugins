"""SeasonScope 构建与 high_risk 绝对季风险检测。"""
from typing import Callable, Optional

from .types import SeasonScope
from .signals import _field

PRODUCTION_GROUP_TYPE = 7  # TMDB 剧集组类型枚举值 7：按制作/拍摄顺序分组（绝对季常见来源）


def build_scope(subscribe, mediainfo, tmdb_episodes_fn: Callable) -> SeasonScope:
    """按订阅季与 episode_group 构建统一的 SeasonScope。"""
    tmdbid = subscribe.tmdbid
    season = subscribe.season
    episode_group = subscribe.episode_group

    if episode_group:
        episodes = tmdb_episodes_fn(tmdbid, season, episode_group=episode_group)
        source = "episode_group"
    else:
        episodes = tmdb_episodes_fn(tmdbid, season)
        source = "main_season"

    scope = SeasonScope(
        tmdbid=tmdbid,
        season=season,
        episode_group_id=episode_group,
        episodes=episodes or [],
        total=len(episodes) if episodes else 0,
        source=source,
    )
    scope.high_risk = detect_high_risk(scope, mediainfo)
    return scope


def detect_high_risk(scope: SeasonScope, mediainfo) -> bool:
    """检测 high_risk 范围：超长季、阶段标记或多个制作顺序剧集组。"""
    if len(scope.episodes) >= 40:
        return True

    for ep in scope.episodes[:-1]:
        if ep.episode_type in ("mid_season", "finale"):
            return True

    production_count = _count_production_groups(mediainfo)
    if production_count >= 2:
        return True

    return False


def _count_production_groups(mediainfo) -> int:
    """统计 production/story 类剧集组数量。"""
    tmdb_info = mediainfo.tmdb_info
    if not tmdb_info:
        return 0
    episode_groups = _field(tmdb_info, "episode_groups", None)
    if not episode_groups:
        return 0
    results = _field(episode_groups, "results", None)
    if not results:
        return 0
    return sum(1 for g in results if _field(g, "type", 0) == PRODUCTION_GROUP_TYPE)
