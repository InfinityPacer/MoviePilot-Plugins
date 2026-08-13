"""L：订阅目标覆盖信号。"""
from dataclasses import dataclass
from typing import Optional

from ..shared.media import episode_field, target_episode_range
from ..shared.subscribe import build_subscribe_meta, is_tv_episode_best_version_subscribe
from .signals import scope_future_episodes
from .types import CompletionSignal, SeasonScope


@dataclass
class LocalSignalResult:
    """L 信号计算结果与失败诊断，供完成守卫输出可操作日志。"""
    signal: Optional[CompletionSignal] = None
    blocked_reason: str = "未命中 L"


def check_l_signal(subscribe, scope: SeasonScope, mediainfo, meta=None,
                   resolve_missing_fn=None) -> Optional[CompletionSignal]:
    """按主程序订阅目标缺集口径生成低置信 L 信号。"""
    return check_l_signal_detail(
        subscribe,
        scope,
        mediainfo=mediainfo,
        meta=meta,
        resolve_missing_fn=resolve_missing_fn,
    ).signal


def check_l_signal_detail(subscribe, scope: SeasonScope, mediainfo, meta=None,
                          resolve_missing_fn=None) -> LocalSignalResult:
    """按主程序订阅目标缺集口径生成 L 信号，并保留失败原因。"""
    start_episode = subscribe.start_episode or 1
    total_episode = subscribe.total_episode or 0
    if total_episode < start_episode:
        return LocalSignalResult(blocked_reason="目标范围无效，未命中 L")
    if resolve_missing_fn is None:
        return LocalSignalResult(blocked_reason="缺少主程序缺集查询入口，未命中 L")
    if meta is None:
        meta = build_subscribe_meta(subscribe, failure_context="L 信号缺集查询失败")
        if meta is None:
            return LocalSignalResult(blocked_reason="缺少主程序缺集查询 meta，未命中 L")
    satisfied, _ = resolve_missing_fn(
        subscribe=subscribe,
        meta=meta,
        mediainfo=mediainfo,
        best_version_accept_downloaded=is_tv_episode_best_version_subscribe(subscribe),
    )
    if not satisfied:
        return LocalSignalResult(blocked_reason="主程序缺集口径未满足，未命中 L")
    return LocalSignalResult(
        signal=CompletionSignal(
            completed=True,
            confidence="low",
            stable=True,
            signals=["L:target_satisfied"],
            reason="订阅目标范围已无待下载集",
            scope_total=scope.total or subscribe.total_episode,
            scope_high_risk=scope.high_risk,
        ),
        blocked_reason="",
    )


def format_future_episode(episode) -> str:
    """把后续集排期格式化为简短日志片段。"""
    if isinstance(episode, dict):
        number = episode.get("episode_number")
        air_date = episode.get("air_date")
    else:
        number = getattr(episode, "episode_number", None)
        air_date = getattr(episode, "air_date", None)
    episode_label = f"E{number}" if number is not None else "未知集号"
    return f"{episode_label}，播出日期：{air_date or '未知'}"


def format_future_blocked_reason(episode) -> str:
    """说明 TMDB 已存在当前订阅目标外的后续集。"""
    return f"TMDB 已存在目标范围外的后续集（{format_future_episode(episode)}）"


def _future_episode_number(episode) -> int | None:
    """解析 TMDB 分集集号；无法确认归属目标范围时按未知处理。"""
    number = episode_field(episode, "episode_number", None)
    try:
        return int(number)
    except (TypeError, ValueError):
        return None


def first_blocking_future_episode(subscribe, scope: SeasonScope, as_of=None):
    """返回当前订阅目标范围外的最早后续集。"""
    target_episodes = set(target_episode_range(subscribe))
    for episode in scope_future_episodes(scope, as_of=as_of):
        number = _future_episode_number(episode)
        if number is None or not target_episodes or number not in target_episodes:
            return episode
    return None
