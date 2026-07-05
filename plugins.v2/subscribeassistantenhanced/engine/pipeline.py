"""完成证据流水线：汇总当前订阅目标的完成、阻断与观察证据。"""
from datetime import date, datetime, timezone
from typing import Callable, Optional

from .cadence import check_cadence_expired
from .local import (
    LocalSignalResult,
    check_l_signal_detail,
    first_blocking_future_episode,
    format_future_blocked_reason,
)
from .scope import build_scope
from .site import _eligible_site_evidence_subscribe
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
from ..shared.log import detail
from ..shared.subscribe import format_subscribe


class CompletionEvidencePipeline:
    """完成证据流水线，按固定阶段汇总当前订阅目标的完成证据。"""

    def __init__(self, tmdb_episodes_fn: Callable,
                 volatility_tracker: VolatilityTracker,
                 config: PluginConfig,
                 site_evidence_provider: Optional[Callable] = None,
                 now_fn: Optional[Callable[[], datetime]] = None):
        self._tmdb_episodes_fn = tmdb_episodes_fn
        self._volatility_tracker = volatility_tracker
        self._config = config
        self._site_evidence_provider = site_evidence_provider
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def evaluate(self, subscribe, mediainfo, as_of: Optional[date] = None,
                 resolve_missing_fn: Optional[Callable] = None,
                 meta=None,
                 consume_site_evidence: bool = False) -> CompletionEvidence:
        """构建 SeasonScope 后返回所有完成证据与当前主信号。"""
        now = _evaluation_now(as_of, self._now_fn)
        today = now.date() if isinstance(as_of, datetime) else (as_of or now.date())
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
            if consume_site_evidence:
                self._record_site_e_diagnostic(subscribe, scope, evidence, e_sig, today, now)
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

        site_action = None
        if consume_site_evidence:
            site_action = self._apply_site_signal(
                subscribe, scope, evidence, e_sig, today, now
            )
        if site_action == "hard_veto":
            return evidence
        if site_action == "target_complete":
            return _with_cadence(evidence, self._cadence_expired(scope, today))

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

    def _apply_site_signal(self, subscribe, scope: SeasonScope,
                           evidence: CompletionEvidence,
                           e_sig: Optional[CompletionSignal],
                           today: date,
                           now: datetime) -> Optional[str]:
        """把站点证据归一到现有完成证据槽位，不让 S 独立完成订阅。"""
        if not self._site_evidence_provider:
            return None
        site_evidence = self._site_evidence_provider(subscribe)
        if not site_evidence or site_evidence.is_expired(now):
            return None

        kind = getattr(site_evidence, "kind", "")
        if kind in ("no_evidence", ""):
            return None
        if not _eligible_site_evidence_subscribe(subscribe):
            evidence.site_conflict = _site_conflict_signal(site_evidence, scope)
            detail(
                f"信号引擎(S)：{format_subscribe(subscribe)} 当前订阅不在站点证据适用范围，"
                f"只记录诊断，信号={evidence.site_conflict.signals[0]} 原因={evidence.site_conflict.reason}"
            )
            return None

        live_total = max(
            _safe_int(getattr(subscribe, "total_episode", None)) or 0,
            scope.total or 0,
        )

        if kind == "site_complete_pack":
            return self._apply_site_completion(
                subscribe=subscribe,
                evidence=evidence,
                site_evidence=site_evidence,
                scope=scope,
                signal_name="S:site_complete_pack",
                reason="站点标题包含完结提示",
            )

        site_total = _safe_int(getattr(site_evidence, "site_candidate_total", None)) or 0
        if kind == "site_conflict" or not site_total:
            evidence.site_conflict = _site_conflict_signal(site_evidence, scope)
            detail(
                f"信号引擎(S)：{format_subscribe(subscribe)} 站点证据只记录诊断，"
                f"信号={evidence.site_conflict.signals[0]} 原因={evidence.site_conflict.reason}"
            )
            return None

        if site_total > live_total:
            if (
                e_sig is not None
                or not getattr(self._config, "site_total_probe_enabled", False)
            ):
                evidence.site_conflict = _site_conflict_signal(site_evidence, scope)
                detail(
                    f"信号引擎(S)：{format_subscribe(subscribe)} 站点证据只记录诊断，"
                    f"站点总集数={site_total} 当前目标={live_total} 原因={evidence.site_conflict.reason}"
                )
                return None
            signal = _attach_scope(
                CompletionSignal(
                    completed=False,
                    stable=True,
                    signals=["S:site_total_ahead"],
                    reason=(
                        f"站点证据显示目标总集数 {site_total} 高于当前目标 {live_total}，"
                        "等待扩展订阅目标"
                    ),
                ),
                scope,
            )
            evidence.hard_veto = signal
            evidence.site_total_ahead_veto = signal
            evidence.primary_signal = signal
            evidence.observation_kind = "hard_veto"
            detail(
                f"信号引擎(S)：{format_subscribe(subscribe)} 站点证据显示当前目标偏小，"
                f"站点总集数={site_total} 当前目标={live_total}，否决完成"
            )
            return "hard_veto"

        if site_total < live_total:
            evidence.site_conflict = _site_conflict_signal(site_evidence, scope)
            detail(
                f"信号引擎(S)：{format_subscribe(subscribe)} 站点证据低于当前目标，只记录诊断，"
                f"站点总集数={site_total} 当前目标={live_total}"
            )
            return None

        if not (_safe_int(getattr(site_evidence, "site_total", None)) or getattr(site_evidence, "complete_hint", False)):
            evidence.site_conflict = _site_conflict_signal(site_evidence, scope)
            detail(
                f"信号引擎(S)：{format_subscribe(subscribe)} 站点证据仅证明目标集存在，"
                "缺少可靠总集数或完结标题，只记录诊断"
            )
            return None

        return self._apply_site_completion(
            subscribe=subscribe,
            evidence=evidence,
            site_evidence=site_evidence,
            scope=scope,
            signal_name="S:site_complete_total",
            reason=f"站点证据确认目标总集数 {live_total}",
        )

    def _apply_site_completion(self, *, subscribe,
                               evidence: CompletionEvidence,
                               site_evidence,
                               scope: SeasonScope,
                               signal_name: str,
                               reason: str) -> Optional[str]:
        """S 完结证据必须与 L 目标满足合成 medium，不能单独放行完成。"""
        if not getattr(self._config, "site_completion_evidence_enabled", False):
            return None
        if (
            evidence.local_signal is None
            or evidence.local_signal.signals != ["L:target_satisfied"]
        ):
            evidence.site_conflict = _site_conflict_signal(site_evidence, scope)
            detail(
                f"信号引擎(S)：{format_subscribe(subscribe)} 站点完结信号缺少 L 目标满足佐证，"
                f"只记录诊断，原因={evidence.site_conflict.reason}"
            )
            return None

        signal = _attach_scope(
            CompletionSignal(
                completed=True,
                confidence="medium",
                stable=True,
                signals=["L:target_satisfied", signal_name],
                reason=f"{evidence.local_signal.reason}，{reason}",
            ),
            scope,
        )
        evidence.site_signal = signal
        evidence.target_complete_signal = signal
        evidence.primary_signal = signal
        evidence.observation_kind = "medium_target_complete"
        detail(
            f"信号引擎(L+S)：{format_subscribe(subscribe)} 命中当前目标完成证据，"
            f"信号={_signal_tags(signal)} 原因={signal.reason}"
        )
        return "target_complete"

    def _record_site_e_diagnostic(self, subscribe, scope: SeasonScope,
                                  evidence: CompletionEvidence,
                                  e_sig: CompletionSignal,
                                  today: date,
                                  now: datetime) -> None:
        """事件携带的 TMDB 高置信完结信号成立时，S ahead 只保留诊断，不影响 E 放行。"""
        if not self._site_evidence_provider:
            return
        site_evidence = self._site_evidence_provider(subscribe)
        if not site_evidence or site_evidence.is_expired(now):
            return
        site_total = _safe_int(getattr(site_evidence, "site_candidate_total", None)) or 0
        live_total = max(
            _safe_int(getattr(subscribe, "total_episode", None)) or 0,
            scope.total or 0,
        )
        if getattr(site_evidence, "kind", "") == "site_total_ahead" and site_total > live_total:
            evidence.site_conflict = _site_conflict_signal(site_evidence, scope)
            detail(
                f"信号引擎(S)：{format_subscribe(subscribe)} 事件携带的 TMDB 完结信号 "
                f"{_signal_tags(e_sig)} 已成立，站点 ahead 只记录诊断"
            )


def _e_can_bypass_unstable(e_sig: CompletionSignal, scope: SeasonScope,
                           today: date,
                           unstable_signal: Optional[CompletionSignal]) -> bool:
    """高置信 E 在目标范围仍有后续集时不能跳过活跃 F 观察。"""
    if unstable_signal is None:
        return True
    return not has_scope_future_episode(scope, as_of=today)


def _site_conflict_signal(site_evidence, scope: SeasonScope) -> CompletionSignal:
    """生成只用于诊断的 S 冲突信号，不参与完成放行。"""
    kind = getattr(site_evidence, "kind", "") or "site_conflict"
    reason = getattr(site_evidence, "reason", "") or "站点证据与当前订阅目标不一致"
    return _attach_scope(
        CompletionSignal(
            completed=False,
            confidence="none",
            stable=True,
            signals=["S:site_conflict"],
            reason=f"{kind}: {reason}",
        ),
        scope,
    )


def _evaluation_now(as_of: Optional[date],
                    now_fn: Callable[[], datetime]) -> datetime:
    """返回 TTL 判断使用的真实时点；日期型 as_of 只影响播出日历判断。"""
    if isinstance(as_of, datetime):
        return _ensure_aware(as_of)
    return _ensure_aware(now_fn())


def _ensure_aware(value: datetime) -> datetime:
    """站点证据过期时间按 timezone-aware datetime 比较，缺省时区视为 UTC。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _safe_int(value) -> Optional[int]:
    """解析可选整数，失败时返回 None。"""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _signal_tags(signal: CompletionSignal) -> str:
    """把完成信号来源压缩成日志可读的组合标签。"""
    return " + ".join(signal.signals or ["none"]) if signal else "none"


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
