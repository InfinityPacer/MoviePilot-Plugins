"""postcheck/timeout.py J 超时释放单测。"""
import time
from types import SimpleNamespace

from subscribeassistantenhanced.postcheck.timeout import PendingTimeoutManager
from subscribeassistantenhanced.engine.types import (
    CompletionEvidence,
    CompletionSignal,
    PendingTimeoutManagerProtocol,
)


def _store_mgr(store=None):
    store = store if store is not None else {}
    return (
        lambda key: store.get(key, {}),
        lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
        store,
    )


def _sub(tmdbid, sid=1, season=1, episode_group=None):
    """构造带完整媒体身份的订阅。"""
    return SimpleNamespace(
        id=sid, tmdbid=tmdbid, season=season, episode_group=episode_group
    )


class TestRecordObservation:

    def test_records_observation(self):
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        mgr.record_observation(1)
        assert "1" in store.get("blocks", {})

    def test_records_l_plus_s_as_medium_target_complete(self):
        """L+S medium 信号按 target_complete 观察类别记录。"""
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        signal = CompletionSignal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "S:site_complete_total"],
            scope_total=12,
        )

        mgr.record_observation(1, signal=signal, total_episode=12)

        assert store["blocks"]["1"]["observation_kind"] == "medium_target_complete"

    def test_does_not_overwrite_existing(self):
        """已有观察记录不覆盖。"""
        old_ts = time.time() - 86400
        store = {"blocks": {"1": {"blocked_at": old_ts, "reason": "guard_veto"}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        mgr.record_observation(1)
        assert store["blocks"]["1"]["blocked_at"] == old_ts

    def test_reused_id_replaces_mismatched_observation_identity(self):
        """新媒体复用 ID 时不能继承旧媒体的观察起点。"""
        old = _sub(100)
        new = _sub(200)
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update)

        mgr.record_observation(old)
        old_time = store["blocks"]["1"]["blocked_at"]
        time.sleep(0.001)
        mgr.record_observation(new)

        assert store["blocks"]["1"]["identity"]["tmdbid"] == 200
        assert store["blocks"]["1"]["blocked_at"] > old_time


class TestClearObservation:

    def test_clears(self):
        store = {"blocks": {"1": {"blocked_at": time.time()}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        mgr.clear_observation(1)
        assert "1" not in store.get("blocks", {})


class TestProtocolConformance:
    """真实超时管理器必须满足完成守卫依赖的运行时协议。"""

    def test_timeout_manager_satisfies_protocol(self):
        read, update, _ = _store_mgr()
        mgr = PendingTimeoutManager(read, update)

        assert isinstance(mgr, PendingTimeoutManagerProtocol)

    def test_clear_release_token_public_api_removes_token(self):
        store = {"releases": {"1": {"signals": ["I:all_aired"]}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)

        mgr.clear_release_token(1)

        assert "1" not in store.get("releases", {})

    def test_check_observation_holds_same_l_low_before_timeout(self):
        store = {"blocks": {"1": {
            "blocked_at": time.time(),
            "signals": ["L:target_satisfied"],
            "confidence": "low",
            "total_episode": 12,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=7)
        low_l = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_l,
            local_signal=low_l,
            scope_total=12,
            observation_kind="low_l",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "hold"
        assert decision.exit_pending is False


class TestCheckObservation:

    def test_without_existing_observation_low_starts_observation_without_release_token(self):
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update, timeout_days=7)
        low_l = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_l,
            local_signal=low_l,
            scope_total=12,
            observation_kind="low_l",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "hold"
        assert store["blocks"]["1"]["signals"] == ["L:target_satisfied"]
        assert store.get("releases", {}) == {}

    def test_l_to_i_low_replaces_observation_without_release(self, monkeypatch):
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.postcheck.timeout.detail", messages.append)
        store = {
            "blocks": {"1": {
                "blocked_at": time.time(),
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        low_i = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_i,
            i_low_signal=low_i,
            scope_total=12,
            observation_kind="low_i",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "hold"
        assert store["blocks"]["1"]["signals"] == ["I:all_aired"]
        assert "1" not in store.get("releases", {})
        assert any("低置信观察来源切换" in message for message in messages)
        assert not any("观察信号已变化" in message for message in messages)

    def test_i_family_switch_does_not_reset_timer(self):
        old_ts = time.time() - 3 * 86400
        store = {"blocks": {"1": {
            "blocked_at": old_ts,
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 12,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        low_i = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["I:cooldown"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_i,
            i_low_signal=low_i,
            scope_total=12,
            observation_kind="low_i",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "hold"
        assert store["blocks"]["1"]["blocked_at"] == old_ts
        assert store["blocks"]["1"]["signals"] == ["I:cooldown"]

    def test_l_plus_i_medium_allows_complete_and_clears_release(self, monkeypatch):
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.postcheck.timeout.detail", messages.append)
        store = {
            "blocks": {"1": {
                "blocked_at": time.time(),
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        medium = CompletionSignal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=medium,
            target_complete_signal=medium,
            scope_total=12,
            observation_kind="medium_target_complete",
        )

        decision = mgr.check_observation(1, evidence, mode="balanced")

        assert decision.action == "allow_complete"
        assert "1" not in store.get("releases", {})
        assert any("L:target_satisfied + I:all_aired" in message for message in messages)

    def test_l_plus_i_medium_overrides_ordinary_unstable(self):
        """普通 F 波动遇到当前目标完成证据时，balanced 仍可结束观察。"""
        store = {
            "blocks": {"1": {
                "blocked_at": time.time(),
                "signals": ["F:unstable"],
                "confidence": "",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        unstable = CompletionSignal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            volatility_direction="up",
            scope_total=12,
        )
        medium = CompletionSignal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=medium,
            unstable_signal=unstable,
            target_complete_signal=medium,
            scope_total=12,
            observation_kind="medium_target_complete",
        )

        decision = mgr.check_observation(1, evidence, mode="balanced")

        assert decision.action == "allow_complete"
        assert "1" not in store.get("blocks", {})
        assert "1" not in store.get("releases", {})

    def test_high_completion_overrides_ordinary_unstable_context(self):
        """流水线主结论为高置信完成时，普通 F 波动上下文不应继续阻塞观察。"""
        store = {
            "blocks": {"1": {
                "blocked_at": time.time(),
                "signals": ["F:unstable"],
                "confidence": "",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        unstable = CompletionSignal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            volatility_direction="up",
            scope_total=12,
        )
        ended = CompletionSignal(
            completed=True,
            confidence="high",
            signals=["E:ended"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=ended,
            high_completion=ended,
            unstable_signal=unstable,
            scope_total=12,
            observation_kind="high_completion",
        )

        decision = mgr.check_observation(1, evidence, mode="balanced")

        assert decision.action == "allow_complete"
        assert "1" not in store.get("blocks", {})
        assert "1" not in store.get("releases", {})

    def test_unstable_observation_uses_f_signal_even_with_high_context(self):
        """F 仍需观察时，持久观察身份应使用 F，不被旁路保留的 E high 覆盖。"""
        store = {"blocks": {"1": {
            "blocked_at": time.time(),
            "signals": ["F:unstable"],
            "confidence": "",
            "total_episode": 12,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        unstable = CompletionSignal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            reason="目标总集数最近发生变化",
            volatility_direction="up",
            scope_total=12,
        )
        ended = CompletionSignal(
            completed=True,
            confidence="high",
            signals=["E:ended"],
            reason="TMDB 状态为 Ended",
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=unstable,
            high_completion=ended,
            unstable_signal=unstable,
            scope_total=12,
            observation_kind="unstable",
        )

        decision = mgr.check_observation(1, evidence, mode="balanced")

        assert decision.action == "hold"
        assert store["blocks"]["1"]["signals"] == ["F:unstable"]
        assert store["blocks"]["1"]["reason"] == "目标总集数最近发生变化"
        assert "1" not in store.get("releases", {})

    def test_strict_target_complete_medium_keeps_observation(self):
        """strict 模式下 target_complete medium 仍按完成前观察处理。"""
        old_ts = time.time()
        store = {
            "blocks": {"1": {
                "blocked_at": old_ts,
                "signals": ["L:target_satisfied", "I:all_aired"],
                "confidence": "medium",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=7)
        medium = CompletionSignal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=medium,
            target_complete_signal=medium,
            scope_total=12,
            observation_kind="medium_target_complete",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "hold"
        assert store["blocks"]["1"]["blocked_at"] == old_ts
        assert "1" not in store.get("releases", {})

    def test_hard_veto_replaces_low_and_resets_timer(self, monkeypatch):
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.postcheck.timeout.detail", messages.append)
        old_ts = time.time() - 3 * 86400
        store = {
            "blocks": {"1": {
                "blocked_at": old_ts,
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        hard = CompletionSignal(
            completed=False,
            signals=["M:mid_season"],
            reason="季中间隔未完结",
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=hard,
            hard_veto=hard,
            scope_total=12,
            observation_kind="hard_veto",
        )

        decision = mgr.check_observation(1, evidence, mode="balanced")

        assert decision.action == "hold"
        assert store["blocks"]["1"]["blocked_at"] > old_ts
        assert store["blocks"]["1"]["signals"] == ["M:mid_season"]
        assert "1" not in store.get("releases", {})
        assert any("切换为 hard_veto 观察" in message for message in messages)
        assert any("季中间隔未完结" in message for message in messages)

    def test_hard_veto_overrides_target_complete_in_observation(self):
        """不可覆盖的 hard veto 与目标完成证据并存时，状态机保持完成前观察。"""
        old_ts = time.time() - 3 * 86400
        store = {
            "blocks": {"1": {
                "blocked_at": old_ts,
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        hard = CompletionSignal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            volatility_direction="down",
            scope_total=12,
        )
        medium = CompletionSignal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=hard,
            hard_veto=hard,
            target_complete_signal=medium,
            scope_total=12,
            observation_kind="hard_veto",
        )

        decision = mgr.check_observation(1, evidence, mode="balanced")

        assert decision.action == "hold"
        assert decision.exit_pending is False
        assert store["blocks"]["1"]["signals"] == ["F:unstable"]
        assert store["blocks"]["1"]["observation_kind"] == "hard_veto"
        assert store["blocks"]["1"]["blocked_at"] > old_ts
        assert "1" not in store.get("releases", {})

    def test_ordinary_unstable_hold_clears_stale_release_token(self):
        store = {
            "blocks": {"1": {
                "blocked_at": time.time(),
                "signals": ["I:all_aired"],
                "confidence": "low",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["I:all_aired"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        unstable = CompletionSignal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            volatility_direction="up",
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=unstable,
            unstable_signal=unstable,
            scope_total=12,
            observation_kind="unstable",
        )

        decision = mgr.check_observation(1, evidence, mode="balanced")

        assert decision.action == "hold"
        assert "1" not in store.get("releases", {})

    def test_low_l_timeout_returns_release_with_token_and_writes_token(self):
        store = {"blocks": {"1": {
            "blocked_at": time.time() - 8 * 86400,
            "signals": ["L:target_satisfied"],
            "confidence": "low",
            "total_episode": 12,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=7)
        low_l = CompletionSignal(
            completed=True,
            confidence="low",
            stable=True,
            signals=["L:target_satisfied"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_l,
            local_signal=low_l,
            scope_total=12,
            observation_kind="low_l",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "release_with_token"
        assert store["releases"]["1"]["signals"] == ["L:target_satisfied"]
        assert store["releases"]["1"]["total_episode"] == 12

    def test_cadence_acceleration_halves_low_timeout_without_joining_identity(self, monkeypatch):
        """G 只缩短观察超时，不写入完成证据身份。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.postcheck.timeout.detail", messages.append)
        store = {"blocks": {"1": {
            "blocked_at": time.time() - 12 * 86400,
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 12,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21, cadence_acceleration=True)
        low_i = CompletionSignal(
            completed=True,
            confidence="low",
            stable=True,
            cadence_expired=True,
            signals=["I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_i,
            i_low_signal=low_i,
            scope_total=12,
            cadence_expired=True,
            observation_kind="low_i",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "release_with_token"
        assert store["releases"]["1"]["signals"] == ["I:all_aired"]
        assert any("节奏已到期" in message for message in messages)

    def test_cadence_no_acceleration_when_disabled(self):
        store = {"blocks": {"1": {
            "blocked_at": time.time() - 12 * 86400,
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 12,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21, cadence_acceleration=False)
        low_i = CompletionSignal(
            completed=True,
            confidence="low",
            stable=True,
            cadence_expired=True,
            signals=["I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_i,
            i_low_signal=low_i,
            scope_total=12,
            cadence_expired=True,
            observation_kind="low_i",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "hold"
        assert store.get("releases", {}) == {}

    def test_total_growth_resets_observation_without_release_token(self, monkeypatch):
        """观察期间 TMDB 增集属于明确不放行，释放本轮 guard 但不写放行令牌。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.postcheck.timeout.detail", messages.append)
        store = {"blocks": {"1": {
            "blocked_at": time.time() - 25 * 86400,
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 2,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        none = CompletionSignal(completed=False, confidence="none", stable=True, signals=["none"], scope_total=3)
        evidence = CompletionEvidence(primary_signal=none, scope_total=3, observation_kind="none")

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "release_guard"

        assert "1" not in store.get("blocks", {})
        assert "1" not in store.get("releases", {})
        assert any("观察期间总集数增长 2→3" in message for message in messages)

    def test_total_growth_precedes_medium_or_high_completion(self):
        """观察期间增集先释放本轮守卫，不借当前 medium/high 完成证据直接放行。"""
        for signal, evidence_kwargs in (
            (
                CompletionSignal(
                    completed=True,
                    confidence="medium",
                    signals=["L:target_satisfied", "I:all_aired"],
                    scope_total=3,
                ),
                {"target_complete_signal": "self", "observation_kind": "medium_target_complete"},
            ),
            (
                CompletionSignal(
                    completed=True,
                    confidence="high",
                    signals=["E:ended"],
                    scope_total=3,
                ),
                {"high_completion": "self", "observation_kind": "high_completion"},
            ),
        ):
            store = {
                "blocks": {"1": {
                    "blocked_at": time.time() - 25 * 86400,
                    "signals": ["I:all_aired"],
                    "confidence": "low",
                    "total_episode": 2,
                }},
                "releases": {"1": {
                    "signals": ["I:all_aired"],
                    "confidence": "low",
                    "total_episode": 2,
                }},
            }
            read, update, _ = _store_mgr(store)
            mgr = PendingTimeoutManager(read, update, timeout_days=21)
            kwargs = {
                key: signal if value == "self" else value
                for key, value in evidence_kwargs.items()
            }
            evidence = CompletionEvidence(
                primary_signal=signal,
                scope_total=3,
                **kwargs,
            )

            decision = mgr.check_observation(1, evidence, mode="balanced")

            assert decision.action == "release_guard"
            assert "1" not in store.get("blocks", {})
            assert "1" not in store.get("releases", {})

    def test_no_completion_evidence_timeout_releases_guard_without_token(self, monkeypatch):
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.postcheck.timeout.detail", messages.append)
        store = {
            "blocks": {"1": {
                "blocked_at": time.time() - 8 * 86400,
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["L:target_satisfied"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=7)
        none = CompletionSignal(completed=False, signals=["none"], scope_total=12)
        evidence = CompletionEvidence(primary_signal=none, scope_total=12, observation_kind="none")

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "release_guard"
        assert "1" not in store.get("blocks", {})
        assert "1" not in store.get("releases", {})
        assert any("当前无完成证据且观察到期" in message for message in messages)
        assert not any("观察信号已变化" in message for message in messages)

    def test_off_mode_releases_guard_and_clears_tokens(self, monkeypatch):
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.postcheck.timeout.detail", messages.append)
        store = {
            "blocks": {"1": {
                "blocked_at": time.time(),
                "signals": ["I:all_aired"],
                "confidence": "low",
                "total_episode": 12,
            }},
            "releases": {"1": {
                "signals": ["I:all_aired"],
                "confidence": "low",
                "total_episode": 12,
            }},
        }
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        evidence = CompletionEvidence(primary_signal=CompletionSignal(signals=["none"]), scope_total=12)

        decision = mgr.check_observation(1, evidence, mode="off")

        assert decision.action == "release_guard"
        assert "1" not in store.get("blocks", {})
        assert "1" not in store.get("releases", {})
        assert any("守卫已关闭，清理既有观察状态" in message for message in messages)

    def test_persisted_observation_without_kind_is_parsed_for_low_observation(self):
        store = {"blocks": {"1": {
            "blocked_at": time.time(),
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 12,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        low_i = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_i,
            i_low_signal=low_i,
            scope_total=12,
            observation_kind="low_i",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "hold"

    def test_unparseable_persisted_observation_restarts_without_borrowing_timer(self):
        old_ts = time.time() - 30 * 86400
        store = {"blocks": {"1": {"blocked_at": old_ts, "reason": "guard_veto"}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=7)
        low_i = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["I:all_aired"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_i,
            i_low_signal=low_i,
            scope_total=12,
            observation_kind="low_i",
        )

        decision = mgr.check_observation(1, evidence, mode="strict")

        assert decision.action == "hold"
        assert store["blocks"]["1"]["blocked_at"] > old_ts
        assert store.get("releases", {}) == {}

    def test_hold_and_release_guard_do_not_write_release_token(self):
        store = {"blocks": {"1": {
            "blocked_at": time.time(),
            "signals": ["L:target_satisfied"],
            "confidence": "low",
            "total_episode": 12,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=7)
        low_l = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            scope_total=12,
        )
        hold = CompletionEvidence(
            primary_signal=low_l,
            local_signal=low_l,
            scope_total=12,
            observation_kind="low_l",
        )

        assert mgr.check_observation(1, hold, mode="strict").action == "hold"

        assert store.get("releases", {}) == {}

    def test_mismatched_release_token_is_discarded(self):
        """一次性放行令牌不匹配当前信号时立即失效。"""
        store = {"releases": {"1": {
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 2,
            "released_at": time.time(),
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(completed=False, confidence="none", stable=True, signals=["none"])

        assert mgr.consume_release_token(1, sig, total_episode=3) is False

        assert "1" not in store.get("releases", {})

    def test_persisted_matching_release_token_is_consumed(self):
        store = {"releases": {"1": {
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 12,
            "released_at": time.time(),
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        sig = CompletionSignal(
            completed=True,
            confidence="low",
            stable=True,
            signals=["I:all_aired"],
            scope_total=12,
        )

        assert mgr.consume_release_token(1, sig, total_episode=12) is True

    def test_reused_id_cannot_consume_stale_media_release_token(self):
        """一次性放行令牌必须匹配当前媒体身份。"""
        old = _sub(100)
        new = _sub(200)
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update)
        signal = CompletionSignal(
            completed=True, confidence="low", stable=True,
            signals=["I:all_aired"], scope_total=2,
        )
        mgr.record_release_token(old, signal, total_episode=2)

        assert mgr.consume_release_token(new, signal, total_episode=2) is False
        assert "1" not in store.get("releases", {})
