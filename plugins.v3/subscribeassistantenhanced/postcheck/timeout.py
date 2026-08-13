"""完成前观察状态机：管理守卫待定与一次性低置信放行令牌。"""
import time
from typing import Callable, Optional

from ..engine.types import CompletionEvidence, CompletionObservationDecision, CompletionSignal
from ..shared.log import detail
from ..shared.subscribe import (
    format_subscribe_label, identity_matches, subscribe_identity,
)


class PendingTimeoutManager:
    """完成前观察状态机与一次性低置信放行令牌管理。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 timeout_days: int = 7,
                 cadence_acceleration: bool = True,
                 subscribe_get_fn: Optional[Callable] = None):
        self._read = task_data_read
        self._update = task_data_update
        self._timeout_seconds = timeout_days * 86400
        self._cadence_acceleration = cadence_acceleration
        self._subscribe_get = subscribe_get_fn

    def record_observation(self, subscribe_or_id, signal: Optional[CompletionSignal] = None,
                           total_episode: Optional[int] = None):
        """CompletionCheck 否决时开始计时，并记录本轮完成前观察上下文。"""
        subscribe, subscribe_id = self._resolve_subscribe(subscribe_or_id)
        sid = str(subscribe_id)
        snapshot = self._snapshot_from_signal(signal, total_episode)

        def updater(data: dict) -> dict:
            current = data.get(sid)
            if current is None or (
                subscribe is not None
                and self._identity_mismatched(current, subscribe)
            ):
                data[sid] = self._observation_record_payload(
                    snapshot, subscribe, reset_timer=True
                )
                if subscribe is not None:
                    data[sid]["identity"] = subscribe_identity(subscribe)
            return data

        self._update("blocks", updater)

    def clear_observation(self, subscribe_id: int):
        """清除订阅的完成前观察记录。"""
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            data.pop(sid, None)
            return data

        self._update("blocks", updater)

    def record_release_token(self, subscribe_or_id, signal: CompletionSignal,
                             total_episode: Optional[int] = None):
        """记录一次性低置信放行令牌，供下一次 CompletionCheck 消费。"""
        subscribe, subscribe_id = self._resolve_subscribe(subscribe_or_id)
        sid = str(subscribe_id)
        token = {
            "signals": list(signal.signals),
            "confidence": signal.confidence,
            "total_episode": total_episode,
            "released_at": time.time(),
        }
        if subscribe is not None:
            token["identity"] = subscribe_identity(subscribe)

        def updater(data: dict) -> dict:
            data[sid] = token
            return data

        self._update("releases", updater)

    def consume_release_token(self, subscribe_or_id, signal: CompletionSignal,
                              total_episode: Optional[int] = None) -> bool:
        """消费匹配当前低置信信号的一次性放行令牌。"""
        subscribe, subscribe_id = self._resolve_subscribe(subscribe_or_id)
        sid = str(subscribe_id)
        total_episode = self._resolve_total(signal, total_episode)
        releases = self._read("releases")
        token = releases.get(sid)
        if not token:
            return False
        if subscribe is not None and self._identity_mismatched(token, subscribe):
            self._clear_release_token(sid)
            return False

        if not self._matches_token(token, signal, total_episode):
            self._clear_release_token(sid)
            return False

        self._clear_release_token(sid)
        return True

    def clear_release_token(self, subscribe_or_id):
        """清理一次性完成放行令牌，供完成守卫直接放行时清除残留令牌。"""
        _, subscribe_id = self._resolve_subscribe(subscribe_or_id)
        self._clear_release_token(str(subscribe_id))

    def check_observation(self, subscribe_or_id, evidence: CompletionEvidence,
                          mode: str) -> CompletionObservationDecision:
        """按完成证据状态机生成完成前观察裁决并维护持久观察数据。"""
        subscribe, subscribe_id = self._resolve_subscribe(subscribe_or_id)
        sid = str(subscribe_id)
        label = self._format_subscribe_label(subscribe_id)
        signal = self._signal_from_evidence(evidence)
        snapshot = self._snapshot_from_evidence(evidence)
        total_episode = snapshot.get("total_episode")

        if mode == "off":
            detail(f"完成前观察：{label} 守卫已关闭，清理既有观察状态")
            self.clear_observation(subscribe_id)
            self._clear_release_token(sid)
            return CompletionObservationDecision.release_guard("完成守卫已关闭")

        data = self._read("blocks") or {}
        observation_record = data.get(sid)
        if (
            observation_record
            and subscribe is not None
            and self._identity_mismatched(observation_record, subscribe)
        ):
            detail(f"完成前观察：{label} 观察记录媒体身份不匹配，重新建立观察状态")
            self.clear_observation(subscribe_id)
            self._clear_release_token(sid)
            observation_record = None

        record_snapshot = (
            self._snapshot_from_observation_record(observation_record)
            if observation_record else {}
        )
        record_parseable = self._is_parseable_snapshot(record_snapshot)

        kind = snapshot.get("observation_kind") or "none"
        record_total = record_snapshot.get("total_episode")
        if record_parseable and record_total and total_episode and total_episode > record_total:
            detail(
                f"完成前观察：{label} 观察期间总集数增长 "
                f"{record_total}→{total_episode}，释放本轮观察并等待重新判定"
            )
            self.clear_observation(subscribe_id)
            self._clear_release_token(sid)
            return CompletionObservationDecision.release_guard("观察期间目标总集数增长")

        if kind in ("hard_veto", "unstable"):
            reset = not record_parseable or not self._same_observation_family(record_snapshot, snapshot)
            self._write_observation(sid, subscribe, snapshot, reset_timer=reset)
            self._clear_release_token(sid)
            if reset:
                detail(
                    f"完成前观察：{label} 切换为 {kind} 观察，"
                    f"原因={snapshot.get('reason') or 'guard_veto'}，重新计时"
                )
            return CompletionObservationDecision.hold("继续观察")

        if self._is_allowed_completion(evidence, signal, mode):
            detail(
                f"完成前观察：{label} 当前证据已允许完成，"
                f"信号={self._signal_tags(signal)}，清理观察状态"
            )
            self.clear_observation(subscribe_id)
            self._clear_release_token(sid)
            return CompletionObservationDecision.allow_complete("信号确认完结")

        if kind == "medium_target_complete":
            reset = not record_parseable or not self._same_observation_family(record_snapshot, snapshot)
            self._write_observation(sid, subscribe, snapshot, reset_timer=reset)
            self._clear_release_token(sid)
            observation_record = self._read("blocks").get(sid, {})
            record_snapshot = self._snapshot_from_observation_record(observation_record)
            if reset:
                detail(f"完成前观察：{label} 切换为 target_complete 观察，重新计时")
            effective_timeout = self._effective_timeout(evidence, signal, label)
            elapsed = time.time() - record_snapshot.get("blocked_at", time.time())
            if elapsed <= effective_timeout:
                return CompletionObservationDecision.hold("继续观察")
            self.clear_observation(subscribe_id)
            return CompletionObservationDecision.release_guard("完成前观察到期")

        if self._is_low_observation(snapshot, signal):
            if not observation_record or not record_parseable:
                detail(f"完成前观察：{label} 开始低置信完成前观察")
                self._write_observation(sid, subscribe, snapshot, reset_timer=True)
                observation_record = self._read("blocks").get(sid, {})
                record_snapshot = self._snapshot_from_observation_record(observation_record)
            elif self._same_low_identity(record_snapshot, snapshot):
                self._write_observation(sid, subscribe, snapshot, reset_timer=False)
            elif self._same_i_family(record_snapshot, snapshot):
                detail(f"完成前观察：{label} I 族低置信信号切换，沿用观察计时")
                self._write_observation(sid, subscribe, snapshot, reset_timer=False)
            else:
                detail(f"完成前观察：{label} 低置信观察来源切换，重新计时")
                self._write_observation(sid, subscribe, snapshot, reset_timer=True)
                observation_record = self._read("blocks").get(sid, {})
                record_snapshot = self._snapshot_from_observation_record(observation_record)
            self._clear_release_token(sid)

            effective_timeout = self._effective_timeout(evidence, signal, label)
            elapsed = time.time() - record_snapshot.get("blocked_at", time.time())
            if elapsed <= effective_timeout:
                return CompletionObservationDecision.hold("继续观察")

            self.record_release_token(
                subscribe or subscribe_id, signal, total_episode=total_episode
            )
            self.clear_observation(subscribe_id)
            return CompletionObservationDecision.release_with_token("完成前观察到期")

        if not observation_record:
            self._clear_release_token(sid)
            return CompletionObservationDecision.release_guard("完成前观察记录缺失")

        if not record_parseable:
            detail(f"完成前观察：{label} 旧观察记录无法解析，重新建立无完成证据观察")
            self._write_observation(sid, subscribe, snapshot, reset_timer=True)
            self._clear_release_token(sid)
            return CompletionObservationDecision.hold("继续观察")

        self._clear_release_token(sid)
        effective_timeout = self._effective_timeout(evidence, signal, label)
        elapsed = time.time() - record_snapshot.get("blocked_at", time.time())
        if elapsed <= effective_timeout:
            return CompletionObservationDecision.hold("继续观察")

        detail(f"完成前观察：{label} 当前无完成证据且观察到期，释放本轮守卫")
        self.clear_observation(subscribe_id)
        return CompletionObservationDecision.release_guard("完成前观察到期")

    @staticmethod
    def _resolve_subscribe(subscribe_or_id):
        """同时支持订阅对象和订阅 ID；对象路径可校验媒体身份。"""
        if hasattr(subscribe_or_id, "id"):
            return subscribe_or_id, subscribe_or_id.id
        return None, subscribe_or_id

    def _format_subscribe_label(self, subscribe_id: int) -> str:
        """按订阅 ID 生成超时诊断标签；查库失败时仍保留 ID。"""
        subscribe = self._subscribe_get(subscribe_id) if self._subscribe_get else None
        return format_subscribe_label(subscribe, subscribe_id)

    def _write_observation(self, sid: str, subscribe, snapshot: dict,
                           reset_timer: bool):
        """写入当前观察快照；同源切换可保留原计时。"""
        def updater(data: dict) -> dict:
            current = data.get(sid, {})
            payload = self._observation_record_payload(
                snapshot,
                subscribe,
                reset_timer=reset_timer,
                current=current,
            )
            data[sid] = payload
            return data
        self._update("blocks", updater)

    def _clear_release_token(self, sid: str):
        """清理订阅的一次性完成放行令牌。"""
        def updater(data: dict) -> dict:
            data.pop(sid, None)
            return data
        self._update("releases", updater)

    def _resolve_total(self, signal: CompletionSignal,
                       total_episode: Optional[int]) -> Optional[int]:
        """优先使用信号携带的 TMDB scope 总数，缺失时回退调用方传入值。"""
        return signal.scope_total or total_episode

    def _matches_token(self, token: dict, signal: CompletionSignal,
                       total_episode: Optional[int]) -> bool:
        """判断一次性放行令牌是否仍匹配当前低置信信号。"""
        return (
            token.get("confidence") == signal.confidence
            and token.get("signals") == list(signal.signals)
            and token.get("total_episode") in (None, total_episode)
        )

    @staticmethod
    def _identity_mismatched(record: dict, subscribe) -> bool:
        """只有带持久化身份的记录才参与 ID 复用保护；旧记录按信号兼容解析。"""
        identity = record.get("identity") if record else None
        return bool(identity) and not identity_matches(identity, subscribe)

    def _snapshot_from_signal(self, signal: Optional[CompletionSignal],
                              total_episode: Optional[int]) -> dict:
        """把单一完成信号转换为可持久化的观察快照。"""
        if signal is None:
            return {
                "observation_kind": "none",
                "signals": [],
                "confidence": "",
                "total_episode": total_episode,
                "reason": "guard_veto",
            }
        total_episode = self._resolve_total(signal, total_episode)
        signals = list(signal.signals)
        return {
            "observation_kind": self._observation_kind_from_signal(signal),
            "signals": signals,
            "confidence": signal.confidence,
            "total_episode": total_episode,
            "reason": signal.reason or "guard_veto",
        }

    def _snapshot_from_evidence(self, evidence: CompletionEvidence) -> dict:
        """把流水线证据压缩成完成前观察可持久化的身份。"""
        signal = self._signal_from_evidence(evidence)
        total_episode = evidence.scope_total or (signal.scope_total if signal else None)
        snapshot = self._snapshot_from_signal(signal, total_episode)
        if evidence.hard_veto is not None:
            snapshot["observation_kind"] = "hard_veto"
            snapshot["signals"] = list(evidence.hard_veto.signals)
            snapshot["confidence"] = evidence.hard_veto.confidence
            snapshot["reason"] = evidence.hard_veto.reason or snapshot.get("reason") or "guard_veto"
            snapshot["total_episode"] = total_episode
            return snapshot
        snapshot["observation_kind"] = (
            evidence.observation_kind
            or snapshot.get("observation_kind")
            or "none"
        )
        snapshot["total_episode"] = total_episode
        return snapshot

    def _snapshot_from_observation_record(self, record: Optional[dict]) -> dict:
        """解析当前和旧格式观察记录；缺少必要信号字段时标记为无法复用计时。"""
        if not record:
            return {}
        signals = record.get("signals") or []
        confidence = record.get("confidence") or ""
        return {
            "observation_kind": record.get("observation_kind")
                                or self._observation_kind_from_observation_record(record),
            "signals": list(signals),
            "confidence": confidence,
            "total_episode": record.get("total_episode"),
            "reason": record.get("reason") or "",
            "blocked_at": record.get("blocked_at"),
        }

    @staticmethod
    def _signal_from_evidence(evidence: CompletionEvidence) -> CompletionSignal:
        """选择代表当前观察身份的信号；G 只留在 evidence，不进入身份。"""
        kind = evidence.observation_kind
        if kind == "hard_veto" and evidence.hard_veto is not None:
            return evidence.hard_veto
        if kind == "unstable" and evidence.unstable_signal is not None:
            return evidence.unstable_signal
        if kind == "medium_target_complete" and evidence.target_complete_signal is not None:
            return evidence.target_complete_signal
        if kind == "high_completion" and evidence.high_completion is not None:
            return evidence.high_completion
        if kind == "low_l" and evidence.local_signal is not None:
            return evidence.local_signal
        if kind == "low_i" and evidence.i_low_signal is not None:
            return evidence.i_low_signal
        if kind == "i_medium" and evidence.i_signal is not None:
            return evidence.i_signal
        return (
            evidence.hard_veto
            or evidence.high_completion
            or evidence.target_complete_signal
            or evidence.unstable_signal
            or evidence.local_signal
            or evidence.i_low_signal
            or evidence.i_signal
            or evidence.primary_signal
            or CompletionSignal(signals=["none"])
        )

    @staticmethod
    def _signal_tags(signal: CompletionSignal) -> str:
        """把完成信号来源压缩成日志可读的组合标签。"""
        return " + ".join(signal.signals or ["none"]) if signal else "none"

    @staticmethod
    def _observation_kind_from_signal(signal: CompletionSignal) -> str:
        """按当前完成信号推导观察类别。"""
        signals = list(signal.signals)
        if signal.confidence == "low" and signals == ["L:target_satisfied"]:
            return "low_l"
        if signal.confidence == "low" and signals in (["I:all_aired"], ["I:cooldown"]):
            return "low_i"
        if signal.confidence == "medium" and "L:target_satisfied" in signals:
            return "medium_target_complete"
        if signal.confidence == "medium":
            return "i_medium"
        if signal.confidence == "high":
            return "high_completion"
        if "M:mid_season" in signals or (
            "F:unstable" in signals and signal.volatility_direction == "down"
        ):
            return "hard_veto"
        if "F:unstable" in signals or not signal.stable:
            return "unstable"
        return "none"

    def _observation_kind_from_observation_record(self, record: dict) -> str:
        """从旧格式观察记录的 signals/confidence 恢复当前观察类别。"""
        signals = list(record.get("signals") or [])
        confidence = record.get("confidence") or ""
        if not signals and not confidence and record.get("total_episode") is None:
            return ""
        if confidence == "low" and signals == ["L:target_satisfied"]:
            return "low_l"
        if confidence == "low" and signals in (["I:all_aired"], ["I:cooldown"]):
            return "low_i"
        if confidence == "medium" and "L:target_satisfied" in signals:
            return "medium_target_complete"
        if confidence == "medium":
            return "i_medium"
        if confidence == "high":
            return "high_completion"
        if "M:mid_season" in signals:
            return "hard_veto"
        if "F:unstable" in signals:
            return "unstable"
        if signals == ["none"]:
            return "none"
        return ""

    @staticmethod
    def _is_parseable_snapshot(snapshot: dict) -> bool:
        """判断旧格式观察记录是否足以参与当前状态机；否则必须重新建档。"""
        return bool(snapshot and snapshot.get("observation_kind"))

    @staticmethod
    def _is_allowed_completion(evidence: CompletionEvidence,
                               signal: CompletionSignal,
                               mode: str) -> bool:
        """高置信、独立 medium I、宽松策略下的 target_complete 可结束观察。"""
        if signal and signal.completed and signal.confidence == "high":
            return True
        if not signal or not signal.completed or signal.confidence != "medium":
            return False
        if (
            evidence.target_complete_signal is signal
            or evidence.observation_kind == "medium_target_complete"
            or "L:target_satisfied" in list(signal.signals or [])
        ):
            return mode in ("balanced", "loose")
        return bool(
            evidence.observation_kind == "i_medium"
            or evidence.i_signal is signal
        )

    @staticmethod
    def _is_low_observation(snapshot: dict, signal: CompletionSignal) -> bool:
        """低置信 L/I 才能生成一次性放行令牌。"""
        return bool(
            signal
            and signal.completed
            and signal.confidence == "low"
            and snapshot.get("observation_kind") in ("low_l", "low_i")
        )

    @staticmethod
    def _same_low_identity(left: dict, right: dict) -> bool:
        """同一低置信观察身份可以沿用计时。"""
        return (
            left.get("observation_kind") == right.get("observation_kind")
            and left.get("signals") == right.get("signals")
            and left.get("confidence") == right.get("confidence")
            and left.get("total_episode") in (None, right.get("total_episode"))
        )

    @staticmethod
    def _same_i_family(left: dict, right: dict) -> bool:
        """I:all_aired 与 I:cooldown 属于同源 I 族，切换不重置计时。"""
        i_signals = (["I:all_aired"], ["I:cooldown"])
        return (
            left.get("observation_kind") == "low_i"
            and right.get("observation_kind") == "low_i"
            and left.get("signals") in i_signals
            and right.get("signals") in i_signals
            and left.get("total_episode") in (None, right.get("total_episode"))
        )

    @staticmethod
    def _same_observation_family(left: dict, right: dict) -> bool:
        """hard veto 或 F 观察同类保持计时，跨类重新计时。"""
        return (
            left.get("observation_kind") == right.get("observation_kind")
            and left.get("signals") == right.get("signals")
            and left.get("total_episode") in (None, right.get("total_episode"))
        )

    def _effective_timeout(self, evidence: CompletionEvidence,
                           signal: CompletionSignal,
                           label: str) -> float:
        """G 只影响观察超时阈值，不改变观察身份。"""
        if self._cadence_acceleration and (
            evidence.cadence_expired or getattr(signal, "cadence_expired", False)
        ):
            detail(f"完成前观察：{label} 节奏已到期，观察阈值减半加速释放")
            return self._timeout_seconds / 2
        return self._timeout_seconds

    @staticmethod
    def _observation_record_payload(
        snapshot: dict,
        subscribe=None,
        reset_timer: bool = True,
        current: Optional[dict] = None,
    ) -> dict:
        """按观察快照生成持久化观察记录，保留同源切换的既有计时。"""
        current = current or {}
        payload = {
            "blocked_at": time.time() if reset_timer else current.get("blocked_at", time.time()),
            "reason": snapshot.get("reason") or "guard_veto",
            "observation_kind": snapshot.get("observation_kind") or "none",
            "signals": list(snapshot.get("signals") or []),
            "confidence": snapshot.get("confidence") or "",
            "total_episode": snapshot.get("total_episode"),
        }
        if subscribe is not None:
            payload["identity"] = subscribe_identity(subscribe)
        elif current.get("identity"):
            payload["identity"] = current["identity"]
        return payload
