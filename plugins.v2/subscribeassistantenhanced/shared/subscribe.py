"""订阅匹配/格式化工具函数。"""
import json
from typing import List, Optional, Tuple

from app.schemas.types import MediaType


def resolve_subscribe_media_type(subscribe) -> MediaType:
    """解析订阅媒体类型，非法或缺失时返回 UNKNOWN，供状态变更链路 fail-closed。"""
    if not subscribe:
        return MediaType.UNKNOWN
    media_type = getattr(subscribe, "type", None)
    if isinstance(media_type, MediaType):
        return media_type
    value = getattr(media_type, "value", media_type)
    if isinstance(value, str):
        value = value.strip()
    if not value:
        return MediaType.UNKNOWN
    try:
        return MediaType(value)
    except ValueError:
        return MediaType.UNKNOWN


def format_subscribe(subscribe) -> str:
    """格式化订阅为可读字符串。"""
    name = subscribe.name
    season = subscribe.season
    return f"{name} S{season}" if season else name


def format_subscribe_label(subscribe=None, subscribe_id=None) -> str:
    """格式化日志订阅标签；对象可用时输出名称、季号和 ID。"""
    if subscribe:
        try:
            sid = subscribe_id if subscribe_id is not None else subscribe.id
            return f"{format_subscribe(subscribe)}(id={sid})"
        except AttributeError:
            try:
                subscribe_id = subscribe.id
            except AttributeError:
                pass
    if subscribe_id is not None:
        return f"订阅 {subscribe_id}"
    return "未知订阅"


def format_subscribe_desc(subscribe) -> str:
    """格式化订阅描述信息。"""
    parts = [format_subscribe(subscribe)]
    total = subscribe.total_episode
    lack = subscribe.lack_episode
    if total:
        parts.append(f"({total - lack}/{total})")
    return " ".join(parts)


def pending_subscription_episodes(subscribe) -> List[int]:
    """返回目标范围内尚未下载到任何版本的集数。

    note 记录订阅下载历史；分集洗版还会把已取得版本的集写入
    episode_priority。正优先级表示该集已有可用版本，即使仍需继续洗版，
    也不属于从未下载的集。
    """
    start_episode = subscribe.start_episode or 1
    total_episode = subscribe.total_episode or 0
    if total_episode < start_episode:
        return []
    downloaded = {
        int(episode) for episode in (subscribe.note or [])
        if isinstance(episode, int) or (
            isinstance(episode, str) and episode.lstrip("-").isdigit()
        )
    }
    for episode, priority in (subscribe.episode_priority or {}).items():
        if not str(episode).isdigit():
            continue
        try:
            if float(priority) > 0:
                downloaded.add(int(episode))
        except (TypeError, ValueError):
            continue
    return [
        episode for episode in range(start_episode, total_episode + 1)
        if episode not in downloaded
    ]


def match_subscribe(subscribe, task: dict) -> bool:
    """判断任务数据是否匹配指定订阅。"""
    if not task:
        return False
    if task.get("id") != subscribe.id:
        return False
    if task.get("name") != subscribe.name:
        return False
    if task.get("tmdbid") != subscribe.tmdbid:
        return False
    if task.get("season") != subscribe.season:
        return False
    task_group = task.get("episode_group")
    sub_group = subscribe.episode_group
    if task_group != sub_group:
        return False
    return True


def subscribe_identity(subscribe) -> dict:
    """提取订阅实例的媒体身份，防止数据库 ID 复用时读取旧状态。"""
    return {
        "subscribe_id": subscribe.id,
        "tmdbid": subscribe.tmdbid,
        "season": subscribe.season,
        "episode_group": subscribe.episode_group,
    }


def identity_matches(identity: dict, subscribe) -> bool:
    """判断持久化身份是否仍属于当前订阅实例。"""
    return bool(identity) and identity == subscribe_identity(subscribe)


def subscribe_from_source(origin, subscribe_oper) -> Tuple[Optional[dict], Optional[object]]:
    """从事件 origin/source 解析订阅。

    origin 是主程序订阅来源约定 ``Subscribe|<json>``（json 内含订阅 id）。解析失败、前缀不符或
    缺 id 一律返回 ``(None, None)``，调用方据此跳过——避免把消息/手动等非订阅来源误当订阅处理。
    返回 ``(subscribe_dict, subscribe)``：前者为事件来源携带的订阅快照，后者为订阅表最新对象
    （订阅已删除时为 None）。
    """
    if not origin or "|" not in str(origin):
        return None, None
    prefix, json_data = str(origin).split("|", 1)
    if prefix != "Subscribe":
        return None, None
    try:
        subscribe_dict = json.loads(json_data)
    except (ValueError, TypeError):
        return None, None
    subscribe_id = subscribe_dict.get("id")
    subscribe = subscribe_oper.get(subscribe_id) if subscribe_oper and subscribe_id else None
    return subscribe_dict, subscribe
