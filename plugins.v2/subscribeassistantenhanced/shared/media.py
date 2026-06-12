"""季信息/集信息/播出日期工具函数。"""
from datetime import datetime, date
from typing import Optional


def parse_date(date_str: Optional[str], fmt: str = "%Y-%m-%d") -> Optional[date]:
    """解析日期字符串，失败返回 None。"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, fmt).date()
    except (ValueError, TypeError):
        return None


def is_same_season(season_info: dict, season: int) -> bool:
    """判断 season_info 是否属于指定季。"""
    return season_info.get("season_number") == season


def get_tv_season_info(mediainfo, season: int) -> Optional[dict]:
    """从 mediainfo.season_info 中获取指定季的信息。"""
    for info in mediainfo.season_info or []:
        if is_same_season(info, season):
            return info
    return None


def get_tv_season_episode_count(mediainfo, season: int,
                                 episode_group: Optional[str] = None) -> int:
    """获取指定季的集数。"""
    info = get_tv_season_info(mediainfo, season)
    if info:
        return info.get("episode_count", 0)
    return 0


def get_tv_season_air_date(mediainfo, season: int) -> Optional[str]:
    """获取指定季的开播日期。"""
    info = get_tv_season_info(mediainfo, season)
    if info:
        return info.get("air_date")
    return None


def count_aired_episodes(episodes: list, as_of: Optional[date] = None) -> int:
    """统计目标范围内已播出的集数。"""
    today = as_of or date.today()
    count = 0
    for ep in episodes:
        air = parse_date(ep.air_date)
        if air and air <= today:
            count += 1
    return count


def last_aired_episode(episodes: list, as_of: Optional[date] = None):
    """返回目标范围内最后一个已播出的集。"""
    today = as_of or date.today()
    aired = []
    for ep in episodes:
        air = parse_date(ep.air_date)
        if air and air <= today:
            aired.append((air, ep))
    if not aired:
        return None
    aired.sort(key=lambda x: x[0])
    return aired[-1][1]


def all_aired(episodes: list, as_of: Optional[date] = None) -> bool:
    """判断目标范围内所有集是否都已播出。"""
    if not episodes:
        return False
    today = as_of or date.today()
    for ep in episodes:
        air = parse_date(ep.air_date)
        if not air or air > today:
            return False
    return True
