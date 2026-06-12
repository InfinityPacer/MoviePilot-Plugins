"""postcheck/timeout.py J 超时释放单测。"""
import time

from subscribeassistantenhanced.postcheck.timeout import PendingTimeoutManager
from subscribeassistantenhanced.engine.types import CompletionSignal


def _store_mgr(store=None):
    store = store if store is not None else {}
    return (
        lambda key: store.get(key, {}),
        lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
        store,
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
