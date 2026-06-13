"""完结信号引擎：按 M → F → E → I(±high_risk) → G 顺序裁决 SeasonScope。"""
from datetime import date
from typing import Optional, Callable

from .types import CompletionSignal, SeasonScope
from .scope import build_scope
from .signals import (
    check_m_signal, check_e_signal, check_i_signal,
    has_future_next_episode,
)
from .cadence import check_cadence_expired
from .volatility import VolatilityTracker
from ..shared.config import PluginConfig
from ..shared.log import detail
from ..shared.subscribe import format_subscribe_label


def evaluate(subscribe, mediainfo,
             tmdb_episodes_fn: Callable,
             volatility_tracker: VolatilityTracker,
             config: PluginConfig,
             as_of: Optional[date] = None) -> CompletionSignal:
    """信号引擎入口：构建 SeasonScope 后按优先级逐层判断当前目标范围是否完结。"""
    today = as_of or date.today()
    subscribe_id = subscribe.id
    subscribe_label = format_subscribe_label(subscribe)

    scope = build_scope(subscribe, mediainfo, tmdb_episodes_fn)

    # 1. 元数据硬否决（M）：mid_season 表示当前范围仍处于季中。
    m_sig = check_m_signal(scope, as_of=today)
    if m_sig is not None:
        detail(f"信号引擎[元数据硬否决（M）]：{subscribe_label} 否决完结，原因：{m_sig.reason}")
        return _attach_scope_total(m_sig, scope)

    # 2. 集数稳定性（F）：total_episode 仍在变化时拒绝提前完结。
    if config.volatility_enabled and subscribe_id is not None:
        if not volatility_tracker.is_stable(subscribe=subscribe):
            detail(
                f"信号引擎[集数稳定性（F）]：{subscribe_label} 否决完结，"
                f"原因：total_episode 近 {config.volatility_window_days} 天内变动"
            )
            return _attach_scope_total(CompletionSignal(
                completed=False, stable=False,
                signals=["F:unstable"],
                reason=f"total_episode 近 {config.volatility_window_days} 天内变动",
            ), scope)

    # 3. 剧级完结（E）：剧级状态或 finale 可提供强完结信号。
    e_sig = check_e_signal(mediainfo, scope, as_of=today)
    if e_sig is not None:
        detail(
            f"信号引擎[剧级完结（E）]：{subscribe_label} 判定完结，"
            f"原因：{e_sig.reason}，置信度：{_confidence_label(e_sig.confidence)}"
        )
        return _attach_scope_total(e_sig, scope)

    # 4. 季级完结（I）：high_risk SeasonScope 使用更保守的分支。
    i_sig = check_i_signal(mediainfo, scope,
                           cooldown_days=config.season_cooldown_days,
                           high_risk=scope.high_risk,
                           as_of=today)
    if i_sig is not None:
        detail(
            f"信号引擎[季级完结（I）]：{subscribe_label} 判定完结，"
            f"原因：{i_sig.reason}，置信度：{_confidence_label(i_sig.confidence)}"
        )
        return _attach_scope_total(i_sig, scope)

    # 5. 播出节奏（G）：只辅助待定释放，不单独确认完结。
    cadence_expired = False
    if scope.high_risk:
        from ..shared.media import all_aired as _all_aired
        tmdb_info = mediainfo.tmdb_info
        has_next = has_future_next_episode(
            tmdb_info, scope.season, as_of=today
        )
        if _all_aired(scope.episodes, as_of=today) and not has_next:
            cadence_expired = True
    elif config.cadence_enabled:
        cadence_expired = check_cadence_expired(
            scope.episodes,
            multiplier=config.cadence_multiplier,
            min_window_days=config.cadence_min_window_days,
            min_episodes=config.cadence_min_episodes,
            as_of=today,
        )
    detail(
        f"信号引擎[播出节奏（G）]：{subscribe_label} "
        f"{'播出窗口已到期' if cadence_expired else '尚无完结确认'}，作为待定释放辅助信号"
    )

    # 6. 兜底：没有任何信号确认完结时，按未完结处理。
    return _attach_scope_total(CompletionSignal(
        completed=False, stable=True, cadence_expired=cadence_expired,
        signals=["none"],
        reason="无信号确认当前目标范围已播完",
    ), scope)


def _confidence_label(confidence: str) -> str:
    """把置信度档位转成日志中的中文说明。"""
    return {
        "high": "高",
        "medium": "中",
        "low": "低",
        "none": "无",
    }.get(confidence, confidence)


def _attach_scope_total(signal: CompletionSignal, scope) -> CompletionSignal:
    """把本轮 TMDB 目标范围总数写入信号，供后续观察期判断增集。"""
    signal.scope_total = scope.total
    signal.scope_high_risk = scope.high_risk
    return signal
