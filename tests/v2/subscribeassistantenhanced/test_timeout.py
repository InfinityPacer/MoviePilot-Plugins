"""postcheck/timeout.py J 超时释放单测。"""
import time
from types import SimpleNamespace

from subscribeassistantenhanced.postcheck.timeout import PendingTimeoutManager
from subscribeassistantenhanced.engine.types import CompletionSignal


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


class TestRecordBlock:

    def test_records_block(self):
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        mgr.record_block(1)
        assert "1" in store.get("blocks", {})

    def test_does_not_overwrite_existing(self):
        """已有 block 不覆盖。"""
        old_ts = time.time() - 86400
        store = {"blocks": {"1": {"blocked_at": old_ts, "reason": "guard_veto"}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        mgr.record_block(1)
        assert store["blocks"]["1"]["blocked_at"] == old_ts

    def test_reused_id_replaces_mismatched_block_identity(self):
        """新媒体复用 ID 时不能继承旧媒体的观察起点。"""
        old = _sub(100)
        new = _sub(200)
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update)

        mgr.record_block(old)
        old_time = store["blocks"]["1"]["blocked_at"]
        time.sleep(0.001)
        mgr.record_block(new)

        assert store["blocks"]["1"]["identity"]["tmdbid"] == 200
        assert store["blocks"]["1"]["blocked_at"] > old_time


class TestClearBlock:

    def test_clears(self):
        store = {"blocks": {"1": {"blocked_at": time.time()}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update)
        mgr.clear_block(1)
        assert "1" not in store.get("blocks", {})


class TestCheckRelease:

    def test_no_block_returns_false(self):
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(stable=True, cadence_expired=False)
        assert mgr.check_release(1, sig) is False

    def test_within_timeout_returns_false(self):
        store = {"blocks": {"1": {"blocked_at": time.time() - 5 * 86400}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(stable=True, cadence_expired=False)
        assert mgr.check_release(1, sig) is False

    def test_past_timeout_returns_true(self):
        store = {"blocks": {"1": {"blocked_at": time.time() - 25 * 86400}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(stable=True, cadence_expired=False)
        assert mgr.check_release(1, sig) is True

    def test_cadence_acceleration_halves_timeout(self):
        """G 过期时超时减半：21/2=10.5 天。"""
        store = {"blocks": {"1": {"blocked_at": time.time() - 12 * 86400}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21, cadence_acceleration=True)
        sig = CompletionSignal(stable=True, cadence_expired=True)
        assert mgr.check_release(1, sig) is True

    def test_cadence_no_acceleration_when_disabled(self):
        store = {"blocks": {"1": {"blocked_at": time.time() - 12 * 86400}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21, cadence_acceleration=False)
        sig = CompletionSignal(stable=True, cadence_expired=True)
        assert mgr.check_release(1, sig) is False

    def test_unstable_resets_timer(self):
        """F 不稳定 → 重置计时器。"""
        old_ts = time.time() - 25 * 86400
        store = {"blocks": {"1": {"blocked_at": old_ts}}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(stable=False)
        assert mgr.check_release(1, sig) is False
        assert store["blocks"]["1"]["blocked_at"] > old_ts

    def test_low_confidence_timeout_records_release_token(self):
        """低置信观察超时后记录一次性放行标记。"""
        store = {"blocks": {"1": {
            "blocked_at": time.time() - 25 * 86400,
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 2,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(completed=True, confidence="low", stable=True, signals=["I:all_aired"])

        assert mgr.check_release(1, sig, total_episode=2) is True

        assert store["releases"]["1"]["signals"] == ["I:all_aired"]
        assert store["releases"]["1"]["total_episode"] == 2

    def test_guard_block_does_not_grant_low_confidence_release_token(self):
        """guard_veto 计时不能借给低置信完成观察。"""
        store = {"blocks": {"1": {
            "blocked_at": time.time() - 25 * 86400,
            "reason": "guard_veto",
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(completed=True, confidence="low", stable=True, signals=["I:all_aired"])

        assert mgr.check_release(1, sig, total_episode=2) is False

        assert store["blocks"]["1"]["signals"] == ["I:all_aired"]
        assert store["blocks"]["1"]["confidence"] == "low"
        assert store["blocks"]["1"]["total_episode"] == 2
        assert store.get("releases", {}) == {}

    def test_total_growth_resets_observation_without_release_token(self):
        """观察期间 TMDB 增集属于明确不放行，释放本轮 guard 但不写放行标记。"""
        store = {"blocks": {"1": {
            "blocked_at": time.time() - 25 * 86400,
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 2,
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(completed=False, confidence="none", stable=True, signals=["none"])

        assert mgr.check_release(1, sig, total_episode=3) is True

        assert "1" not in store.get("releases", {})

    def test_mismatched_release_token_is_discarded(self):
        """一次性放行标记不匹配当前信号时立即失效。"""
        store = {"releases": {"1": {
            "signals": ["I:all_aired"],
            "confidence": "low",
            "total_episode": 2,
            "released_at": time.time(),
        }}}
        read, update, _ = _store_mgr(store)
        mgr = PendingTimeoutManager(read, update, timeout_days=21)
        sig = CompletionSignal(completed=False, confidence="none", stable=True, signals=["none"])

        assert mgr.consume_release(1, sig, total_episode=3) is False

        assert "1" not in store.get("releases", {})

    def test_reused_id_cannot_consume_old_media_release_token(self):
        """一次性放行令牌必须匹配当前媒体身份。"""
        old = _sub(100)
        new = _sub(200)
        read, update, store = _store_mgr()
        mgr = PendingTimeoutManager(read, update)
        signal = CompletionSignal(
            completed=True, confidence="low", stable=True,
            signals=["I:all_aired"], scope_total=2,
        )
        mgr.record_release(old, signal, total_episode=2)

        assert mgr.consume_release(new, signal, total_episode=2) is False
        assert "1" not in store.get("releases", {})
