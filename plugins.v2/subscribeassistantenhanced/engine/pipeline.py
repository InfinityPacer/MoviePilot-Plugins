"""完成证据流水线：汇总当前订阅目标的完成、阻断与观察证据。"""
from datetime import date
from typing import Callable, Optional

from .cadence import check_cadence_expired
from .local import (
    LocalSignalResult,
    check_l_signal_detail,
    first_blocking_future_episode,
    format_future_blocked_reason,
)
from .scope import build_scope
from .signals import (
    all_scope_episodes_aired,
    check_e_signal,
    check_i_signal,
    check_m_signal,
    has_scope_future_episode,
)
from .types import CompletionEvidence, CompletionSignal, SeasonScope
from .volatility import VolatilityTracker
from ..shared.config import PluginConfig


class CompletionEvidencePipeline:
    """完成证据流水线，按固定阶段汇总当前订阅目标的完成证据。"""

    def __init__(self, tmdb_episodes_fn: Callable,
                 volatility_tracker: VolatilityTracker,
                 config: PluginConfig):
        self._tmdb_episodes_fn = tmdb_episodes_fn
        self._volatility_tracker = volatility_tracker
        self._config = config

    def evaluate(self, subscribe, mediainfo, as_of: Optional[date] = None,
                 resolve_missing_fn: Optional[Callable] = None,
                 meta=None) -> CompletionEvidence:
        """构建 SeasonScope 后返回所有完成证据与当前主信号。"""
        today = as_of or date.today()
        scope = build_scope(subscribe, mediainfo, self._tmdb_episodes_fn)
        evidence = CompletionEvidence(
            scope_total=scope.total,
            scope_high_risk=scope.high_risk,
        )

        m_sig = _attach_scope(check_m_signal(scope, as_of=today), scope)
        if m_sig is not None:
            evidence.hard_veto = m_sig
            evidence.primary_signal = m_sig
            evidence.observation_kind = "hard_veto"
            return evidence

        e_sig = _attach_scope(check_e_signal(mediainfo, scope, as_of=today), scope)
        f_sig = self._unstable_signal(subscribe, scope)
        if f_sig is not None:
            if f_sig.volatility_direction == "down":
                evidence.hard_veto = f_sig
                evidence.primary_signal = f_sig
                evidence.observation_kind = "hard_veto"
                return evidence
            evidence.unstable_signal = f_sig

        if e_sig is not None:
            evidence.high_completion = e_sig
            if _e_can_bypass_unstable(e_sig, scope, today, f_sig):
                evidence.primary_signal = e_sig
                evidence.observation_kind = "high_completion"
                return _with_cadence(evidence, self._cadence_expired(scope, today))

        target_block = first_blocking_future_episode(subscribe, scope, as_of=today)
        target_blocked = target_block is not None
        if target_blocked:
            evidence.local_blocked_reason = format_future_blocked_reason(target_block)

        i_sig = _attach_scope(
            check_i_signal(
                mediainfo,
                scope,
                cooldown_days=self._config.season_cooldown_days,
                high_risk=scope.high_risk,
                as_of=today,
            ),
            scope,
        )
        if i_sig is not None:
            if i_sig.confidence == "low":
                if not target_blocked:
                    evidence.i_signal = i_sig
                    evidence.i_low_signal = i_sig
            else:
                evidence.i_signal = i_sig

        if not target_blocked:
            local_result = check_l_signal_detail(
                subscribe,
                scope,
                mediainfo=mediainfo,
                meta=meta,
                resolve_missing_fn=resolve_missing_fn,
            )
            evidence.local_signal = _attach_scope(local_result.signal, scope)
            evidence.local_blocked_reason = local_result.blocked_reason
        elif not evidence.local_blocked_reason:
            evidence.local_blocked_reason = LocalSignalResult().blocked_reason

        target_complete = _build_target_complete_signal(
            evidence.local_signal,
            evidence.i_low_signal,
            scope,
        )
        if target_complete is not None:
            evidence.target_complete_signal = target_complete
            evidence.primary_signal = target_complete
            evidence.observation_kind = "medium_target_complete"
            return _with_cadence(evidence, self._cadence_expired(scope, today))

        if evidence.unstable_signal is not None:
            evidence.primary_signal = evidence.unstable_signal
            evidence.observation_kind = "unstable"
            return _with_cadence(evidence, self._cadence_expired(scope, today))

        if evidence.high_completion is not None:
            evidence.primary_signal = evidence.high_completion
            evidence.observation_kind = "high_completion"
            return _with_cadence(evidence, self._cadence_expired(scope, today))

        if evidence.i_signal is not None:
            evidence.primary_signal = evidence.i_signal
            evidence.observation_kind = (
                "i_low" if evidence.i_signal.confidence == "low" else "i_medium"
            )
            return _with_cadence(evidence, self._cadence_expired(scope, today))

        if evidence.local_signal is not None:
            evidence.primary_signal = evidence.local_signal
            evidence.observation_kind = "low_l"
            return _with_cadence(evidence, self._cadence_expired(scope, today))

        cadence_expired = self._cadence_expired(scope, today)
        evidence.primary_signal = _attach_scope(
            CompletionSignal(
                completed=False,
                stable=True,
                cadence_expired=cadence_expired,
                signals=["none"],
                reason="无信号确认当前目标范围已播完",
            ),
            scope,
        )
        evidence.cadence_expired = cadence_expired
        evidence.observation_kind = "none"
        return evidence

    def _unstable_signal(self, subscribe, scope: SeasonScope) -> Optional[CompletionSignal]:
        """生成 F 观察信号；total 缩小由主流程提升为硬否决。"""
        subscribe_id = getattr(subscribe, "id", None)
        if not self._config.volatility_enabled or subscribe_id is None:
            return None
        if self._volatility_tracker.is_stable(subscribe=subscribe):
            return None

        volatility_detail = self._volatility_tracker.recent_change_detail(subscribe=subscribe)
        unstable_reason = f"目标总集数最近 {self._config.volatility_window_days} 天发生变化"
        if volatility_detail:
            unstable_reason = f"{unstable_reason}（{volatility_detail}）"
        return _attach_scope(
            CompletionSignal(
                completed=False,
                stable=False,
                signals=["F:unstable"],
                reason=unstable_reason,
                volatility_direction=self._volatility_tracker.recent_change_direction(
                    subscribe=subscribe
                ),
                volatility_detail=volatility_detail,
            ),
            scope,
        )

    def _cadence_expired(self, scope: SeasonScope, today: date) -> bool:
        """计算 G 辅助观察结果，不把 G 写入任何完成信号标识。"""
        if scope.high_risk:
            return (
                all_scope_episodes_aired(scope, as_of=today)
                and not has_scope_future_episode(scope, as_of=today)
            )
        if not self._config.cadence_enabled:
            return False
        return check_cadence_expired(
            scope.episodes,
            multiplier=self._config.cadence_multiplier,
            min_window_days=self._config.cadence_min_window_days,
            min_episodes=self._config.cadence_min_episodes,
            as_of=today,
        )


def _e_can_bypass_unstable(e_sig: CompletionSignal, scope: SeasonScope,
                           today: date,
                           unstable_signal: Optional[CompletionSignal]) -> bool:
    """高置信 E 在目标范围仍有后续集时不能跳过活跃 F 观察。"""
    if unstable_signal is None:
        return True
    return not has_scope_future_episode(scope, as_of=today)


def _build_target_complete_signal(local_signal: Optional[CompletionSignal],
                                  i_signal: Optional[CompletionSignal],
                                  scope: SeasonScope) -> Optional[CompletionSignal]:
    """仅 L 与 I:all_aired/I:cooldown 可合成当前订阅目标完成证据。"""
    if local_signal is None or i_signal is None:
        return None
    if local_signal.signals != ["L:target_satisfied"]:
        return None
    if i_signal.signals not in (["I:all_aired"], ["I:cooldown"]):
        return None
    return _attach_scope(
        CompletionSignal(
            completed=True,
            confidence="medium",
            stable=True,
            signals=["L:target_satisfied", i_signal.signals[0]],
            reason=f"{local_signal.reason}，{i_signal.reason}",
        ),
        scope,
    )


def _with_cadence(evidence: CompletionEvidence,
                  cadence_expired: bool) -> CompletionEvidence:
    """把 G 辅助结果同步到 evidence 与主信号的独立字段。"""
    evidence.cadence_expired = cadence_expired
    evidence.primary_signal.cadence_expired = cadence_expired
    return evidence


def _attach_scope(signal: Optional[CompletionSignal],
                  scope: SeasonScope) -> Optional[CompletionSignal]:
    """所有流水线产物都携带同一 SeasonScope 的总数与风险标记。"""
    if signal is None:
        return None
    signal.scope_total = scope.total
    signal.scope_high_risk = scope.high_risk
    return signal
