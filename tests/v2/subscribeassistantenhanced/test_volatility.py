"""engine/volatility.py F 变更速率追踪单测。"""
import time

from subscribeassistantenhanced.engine.volatility import VolatilityTracker


class TestVolatilityTracker:

    def setup_method(self):
        self.store = {}

        def get_fn(key):
            return self.store.get(key)

        def save_fn(key, data):
            self.store[key] = data

        from subscribeassistantenhanced.shared.task import TaskDataManager
        self.task_mgr = TaskDataManager(get_data_fn=get_fn, save_data_fn=save_fn)
        self.tracker = VolatilityTracker(self.task_mgr, window_days=7)

    def test_first_record_is_stable(self):
        """首次记录不算变动。"""
        self.tracker.record(total=12, subscribe_id=1)
        assert self.tracker.is_stable(subscribe_id=1) is True

    def test_same_value_is_stable(self):
        """相同值不算变动。"""
        self.tracker.record(total=12, subscribe_id=1)
        self.tracker.record(total=12, subscribe_id=1)
        assert self.tracker.is_stable(subscribe_id=1) is True

    def test_changed_value_is_unstable(self):
        """值变化 → 不稳定。"""
        self.tracker.record(total=12, subscribe_id=1)
        self.tracker.record(total=13, subscribe_id=1)
        assert self.tracker.is_stable(subscribe_id=1) is False

    def test_none_subscribe_id_skipped(self):
        """subscribe_id=None（创建场景）跳过记录，视为稳定。"""
        self.tracker.record(total=12, subscribe_id=None)
        assert self.tracker.is_stable(subscribe_id=None) is True

    def test_unknown_subscribe_id_stable(self):
        """从未记录过的 id 视为稳定。"""
        assert self.tracker.is_stable(subscribe_id=999) is True

    def test_old_change_expires(self):
        """超过窗口期的变动不再计入。"""
        old_ts = time.time() - 8 * 86400
        self.store["volatility"] = {
            "1": [
                {"total": 12, "ts": old_ts},
                {"total": 13, "ts": old_ts + 1},
            ]
        }
        assert self.tracker.is_stable(subscribe_id=1) is True

    def test_recent_change_within_window(self):
        """窗口期内的变动仍然不稳定。"""
        now = time.time()
        self.store["volatility"] = {
            "1": [
                {"total": 12, "ts": now - 3 * 86400},
                {"total": 13, "ts": now - 2 * 86400},
            ]
        }
        assert self.tracker.is_stable(subscribe_id=1) is False

    def test_ring_buffer_max_20(self):
        """超过 20 条丢弃最旧。"""
        for i in range(25):
            self.tracker.record(total=12, subscribe_id=1)
        buf = self.store.get("volatility", {}).get("1", [])
        assert len(buf) <= 20

    def test_multiple_subscribes_independent(self):
        """不同订阅的 buffer 独立。"""
        self.tracker.record(total=12, subscribe_id=1)
        self.tracker.record(total=13, subscribe_id=1)
        self.tracker.record(total=10, subscribe_id=2)
        assert self.tracker.is_stable(subscribe_id=1) is False
        assert self.tracker.is_stable(subscribe_id=2) is True
