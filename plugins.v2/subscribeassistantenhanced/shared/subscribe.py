"""订阅匹配/格式化工具函数。"""
import json
from typing import Optional, Tuple


def format_subscribe(subscribe) -> str:
    """格式化订阅为可读字符串。"""
    name = subscribe.name
    season = subscribe.season
    return f"{name} S{season}" if season else name


def format_subscribe_desc(subscribe) -> str:
    """格式化订阅描述信息。"""
    parts = [format_subscribe(subscribe)]
    total = subscribe.total_episode
    lack = subscribe.lack_episode
    if total:
        parts.append(f"({total - lack}/{total})")
    return " ".join(parts)


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


def subscribe_from_source(origin, subscribe_oper) -> Tuple[Optional[dict], Optional[object]]:
    """从事件 origin/source 解析订阅。

    origin 是主程序订阅来源约定 ``Subscribe|<json>``（json 内含订阅 id）。解析失败、前缀不符或
    缺 id 一律返回 ``(None, None)``，调用方据此跳过——避免把消息/手动等非订阅来源误当订阅处理。
    返回 ``(subscribe_dict, subscribe)``：前者为来源内联快照，后者为库内最新对象（可能已被删而为 None）。
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
