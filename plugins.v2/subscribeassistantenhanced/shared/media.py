"""季信息/集信息/播出日期工具函数。"""
from datetime import datetime, date
from typing import Optional

from .subscribe import pending_subscription_episodes


def relative_day_text(target_date: date, as_of: Optional[date] = None) -> str:
    """把日期转成面向用户的相对天数描述。"""
    today = as_of or date.today()
    days = (target_date - today).days
    if days > 0:
        return f"距今 {days} 天"
    if days < 0:
        return f"已过 {-days} 天"
    return "今天"


def date_context(label: str, target_date: date, as_of: Optional[date] = None) -> str:
    """生成带日期和相对天数的通知上下文。"""
    return f"{label}：{target_date.isoformat()}，{relative_day_text(target_date, as_of=as_of)}"


def parse_date(date_str: Optional[str], fmt: str = "%Y-%m-%d") -> Optional[date]:
    """解析日期字符串，失败返回 None。"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, fmt).date()
    except (ValueError, TypeError):
        return None


def episode_field(episode, name: str, default=None):
    """读取 TMDB 集信息字段，兼容 API 原始 dict 与仓内 TmdbEpisode 对象。"""
    if isinstance(episode, dict):
        return episode.get(name, default)
    return getattr(episode, name, default)


def _same_optional_season(season_number, subscribe_season) -> bool:
    """按显式季号比较分集归属；S0 是合法季号，不能按空值处理。"""
    return season_number is None or subscribe_season is None or season_number == subscribe_season


def target_episode_range(subscribe) -> list[int]:
    """返回订阅目标集范围，按主程序 start_episode/total_episode 契约解释。"""
    start_episode = subscribe.start_episode or 1
    total_episode = subscribe.total_episode or 0
    if total_episode < start_episode:
        return []
    return list(range(start_episode, total_episode + 1))


def resolve_airing_next_episode(subscribe, aggregate_episode, episodes: list,
                                as_of: Optional[date] = None):
    """解析播出暂停使用的下一集，并限定为订阅范围内首个待下载集。

    聚合字段只有在属于当前季、明确晚于当天且集号匹配首待下载集时才可信；
    否则从当前 SeasonScope 分集表中寻找同一首待下载集，避免聚合字段为空或
    仍停留在当天已播集时漏掉已经公开的后续排期。
    """
    today = as_of or date.today()
    pending_episodes = pending_subscription_episodes(subscribe)
    if not pending_episodes:
        return None
    first_pending = pending_episodes[0]

    def valid_candidate(episode) -> bool:
        """判断候选集是否满足季、日期和首待下载集约束。"""
        if not episode:
            return False
        season_number = episode_field(episode, "season_number")
        subscribe_season = subscribe.season
        if not _same_optional_season(season_number, subscribe_season):
            return False
        air_date = parse_date(episode_field(episode, "air_date"))
        if air_date is None or air_date <= today:
            return False
        episode_number = episode_field(episode, "episode_number")
        if episode_number is None:
            return not episodes
        if episode_number != first_pending:
            return False
        return True

    if valid_candidate(aggregate_episode):
        return aggregate_episode

    candidates = [episode for episode in (episodes or []) if valid_candidate(episode)]
    if not candidates:
        candidates = resolve_inventory_next_episodes(subscribe, episodes, as_of=today)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda episode: (
            parse_date(episode_field(episode, "air_date")),
            episode_field(episode, "episode_number", 0),
        ),
    )


def future_episode_candidates(subscribe, episodes: list, as_of: Optional[date] = None) -> list:
    """返回当前季订阅目标范围内播出日期晚于当前日期的候选集。"""
    today = as_of or date.today()
    return episode_candidates_after(subscribe, episodes, today)


def unknown_tail_episode_count(subscribe, episodes: list) -> int:
    """统计订阅尾部超出 TMDB 当前分集表的目标集数量。"""
    target_episodes = target_episode_range(subscribe)
    if not target_episodes:
        return 0
    known_numbers = []
    for episode in (episodes or []):
        season_number = episode_field(episode, "season_number")
        if not _same_optional_season(season_number, subscribe.season):
            continue
        episode_number = episode_field(episode, "episode_number")
        if episode_number is not None:
            known_numbers.append(episode_number)
    if not known_numbers:
        return 0
    max_known = max(known_numbers)
    return sum(1 for episode_number in target_episodes if episode_number > max_known)


def episode_candidates_after(subscribe, episodes: list, cutoff: date) -> list:
    """返回当前季订阅目标范围内晚于指定日期的集候选。"""
    target_episodes = set(target_episode_range(subscribe))
    candidates = []
    for episode in (episodes or []):
        season_number = episode_field(episode, "season_number")
        if not _same_optional_season(season_number, subscribe.season):
            continue
        episode_number = episode_field(episode, "episode_number")
        if episode_number is None or (target_episodes and episode_number not in target_episodes):
            continue
        air = parse_date(episode_field(episode, "air_date"))
        if air and air > cutoff:
            candidates.append(episode)
    return candidates


def resolve_inventory_next_episodes(subscribe, episodes: list,
                                    as_of: Optional[date] = None) -> list:
    """按媒体库实缺数量判断追更已到当前已播最新时，返回后续播出候选集。

    ``note`` 只记录订阅链路下载历史，手动下载后整理入库不会补写；播出暂停需要判断
    真实库存是否已经追到当前已播最新，因此以主程序维护的 ``lack_episode`` 与未播集数量对齐为准。
    """
    futures = future_episode_candidates(subscribe, episodes, as_of=as_of)
    if not futures:
        return []
    lack_episode = subscribe.lack_episode
    if lack_episode is None:
        return []
    try:
        lack_count = int(lack_episode)
    except (TypeError, ValueError):
        return []
    if lack_count < 0:
        return []
    future_count = len(futures) + unknown_tail_episode_count(subscribe, episodes)
    if lack_count == future_count:
        return futures
    return []


def is_same_season(season_info: dict, season: int) -> bool:
    """判断主季或剧集组 season_info 是否属于指定季。"""
    return season_info.get("season_number") == season or season_info.get("order") == season


def get_tv_season_info(mediainfo, season: int) -> Optional[dict]:
    """从 mediainfo.season_info 中获取指定季的信息。"""
    for info in mediainfo.season_info or []:
        if is_same_season(info, season):
            return info
    return None


def get_tv_season_episode_count(mediainfo, season: int, episodes: list | None = None) -> Optional[int]:
    """解析当前季总集数；未知时返回 None，不把空查询当 0 集。"""
    info = get_tv_season_info(mediainfo, season)
    if info:
        episode_count = info.get("episode_count")
        if episode_count is not None:
            try:
                return int(episode_count)
            except (TypeError, ValueError):
                pass
        raw_episodes = info.get("episodes")
        if raw_episodes:
            return len(raw_episodes)
    if episodes:
        return len([
            ep for ep in episodes
            if episode_field(ep, "episode_number") is not None
        ])
    return None


def get_tv_season_air_date(mediainfo, season: int) -> Optional[str]:
    """获取指定季的开播日期。"""
    info = get_tv_season_info(mediainfo, season)
    if info:
        return info.get("air_date")
    return None


def first_scope_episode_air_date(subscribe, episodes: list) -> Optional[date]:
    """返回当前季分集表 E01 的播出日期；分集表由调用方按剧集组范围取得。"""
    candidates = []
    for episode in episodes or []:
        if not subscribe.episode_group:
            season_number = episode_field(episode, "season_number")
            if not _same_optional_season(season_number, subscribe.season):
                continue
        if episode_field(episode, "episode_number") != 1:
            continue
        air = parse_date(episode_field(episode, "air_date"))
        if air:
            candidates.append(air)
    if not candidates:
        return None
    return min(candidates)


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
