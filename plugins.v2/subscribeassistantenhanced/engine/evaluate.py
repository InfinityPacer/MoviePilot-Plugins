"""信号引擎合并逻辑：M → F → E → I(±high_risk) → G → 兜底。"""
from datetime import date
from typing import Optional, Callable

from .types import CompletionSignal, SeasonScope
from .scope import build_scope
from .signals import check_m_signal, check_e_signal, check_i_signal, _field
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
    """信号引擎入口——构建 scope 后按优先级逐层检查。"""
    today = as_of or date.today()
    subscribe_id = subscribe.id
    subscribe_label = format_subscribe_label(subscribe)

    scope = build_scope(subscribe, mediainfo, tmdb_episodes_fn)

    # 1. M：mid_season 硬否决
    m_sig = check_m_signal(scope, as_of=today)
    if m_sig is not None:
        detail(f"信号引擎：{subscribe_label} M 否决完结 — {m_sig.reason}")
        return m_sig

    # 2. F：变更速率否决
    if config.volatility_enabled and subscribe_id is not None:
        if not volatility_tracker.is_stable(subscribe_id):
            detail(f"信号引擎：{subscribe_label} F 否决完结 — total_episode 近 {config.volatility_window_days} 天内变动")
            return CompletionSignal(
                completed=False, stable=False,
                signals=["F:unstable"],
                reason=f"total_episode 近 {config.volatility_window_days} 天内变动",
            )

    # 3. E：基线信号
    e_sig = check_e_signal(mediainfo, scope)
    if e_sig is not None:
        detail(f"信号引擎：{subscribe_label} E 信号判定完结 — {e_sig.reason}（confidence={e_sig.confidence}）")
        return e_sig

    # 4. I：季级信号
    i_sig = check_i_signal(mediainfo, scope,
                           cooldown_days=config.season_cooldown_days,
                           high_risk=scope.high_risk,
                           as_of=today)
    if i_sig is not None:
        detail(f"信号引擎：{subscribe_label} I 信号判定完结 — {i_sig.reason}（confidence={i_sig.confidence}）")
        return i_sig

    # 5. G：播出节奏（辅助信号）
    cadence_expired = False
    if scope.high_risk:
        from ..shared.media import all_aired as _all_aired
        tmdb_info = mediainfo.tmdb_info
        next_ep = _field(tmdb_info, "next_episode_to_air", None) if tmdb_info else None
        has_next = next_ep is not None and _field(next_ep, "season_number", 0) == scope.season
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

    # 6. 兜底
    return CompletionSignal(
        completed=False, stable=True, cadence_expired=cadence_expired,
        signals=["none"],
        reason="无信号确认当前 scope 已播完",
    )
