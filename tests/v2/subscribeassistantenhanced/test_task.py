"""shared/task.py TaskDataManager 单测。"""
import threading

from subscribeassistantenhanced.shared.task import TaskDataManager


class TaskDataManagerTest:
    """TaskDataManager 读写与锁隔离。"""

    def setup_method(self):
        self.store = {}

        def get_fn(key):
            return self.store.get(key)

        def save_fn(key, data):
            self.store[key] = data

        self.mgr = TaskDataManager(get_data_fn=get_fn, save_data_fn=save_fn)

    def test_read_returns_empty_dict_when_missing(self):
        assert self.mgr.read("unknown") == {}

    def test_write_and_read_roundtrip(self):
        self.mgr.write("subscribes", {"a": 1})
        assert self.mgr.read("subscribes") == {"a": 1}

    def test_update_applies_updater(self):
        self.mgr.write("counters", {"x": 0})
        result = self.mgr.update("counters", lambda d: {**d, "x": d["x"] + 1})
        assert result == {"x": 1}
        assert self.mgr.read("counters") == {"x": 1}

    def test_update_on_missing_key_starts_empty(self):
        result = self.mgr.update("new_key", lambda d: {**d, "added": True})
        assert result == {"added": True}

    def test_reset_clears_key(self):
        self.mgr.write("subscribes", {"a": 1, "b": 2})
        self.mgr.reset("subscribes")
        assert self.mgr.read("subscribes") == {}

    def test_reset_all_clears_multiple_keys(self):
        self.mgr.write("subscribes", {"a": 1})
        self.mgr.write("volatility", {"v": 2})
        self.mgr.reset_all(["subscribes", "volatility"])
        assert self.mgr.read("subscribes") == {}
        assert self.mgr.read("volatility") == {}

    def test_per_key_lock_isolation(self):
        """volatility 和 subscribes 使用独立的锁实例。"""
        lock_sub = self.mgr._lock_for("subscribes")
        lock_vol = self.mgr._lock_for("volatility")
        assert lock_sub is not lock_vol
        assert isinstance(lock_sub, type(threading.RLock()))
        assert isinstance(lock_vol, type(threading.RLock()))

    def test_same_key_returns_same_lock(self):
        lock1 = self.mgr._lock_for("subscribes")
        lock2 = self.mgr._lock_for("subscribes")
        assert lock1 is lock2

    def test_clear_tasks_removes_all_subscription_instance_state(self):
        """清理订阅实例数据，但保留按媒体或事务保存的长期数据。"""
        self.mgr.write("subscribes", {"9": {"x": 1}, "10": {"y": 2}})
        self.mgr.write("torrents", {"h1": {"subscribe_id": 9}, "h2": {"subscribe_id": 10}})
        self.mgr.write("volatility", {"9": [{"total": 2}], "10": [{"total": 3}]})
        self.mgr.write("blocks", {"9": {"blocked_at": 1}, "10": {"blocked_at": 2}})
        self.mgr.write("releases", {"9": {"signals": []}, "10": {"signals": []}})
        self.mgr.write("snapshots", {"list": [{"tmdbid": 100}]})
        self.mgr.write("deletes", {"hash": {"time": 1}})
        self.mgr.clear_tasks(9)
        assert self.mgr.read("subscribes") == {"10": {"y": 2}}
        assert self.mgr.read("torrents") == {"h2": {"subscribe_id": 10}}
        assert self.mgr.read("volatility") == {"10": [{"total": 3}]}
        assert self.mgr.read("blocks") == {"10": {"blocked_at": 2}}
        assert self.mgr.read("releases") == {"10": {"signals": []}}
        assert self.mgr.read("snapshots") == {"list": [{"tmdbid": 100}]}
        assert self.mgr.read("deletes") == {"hash": {"time": 1}}

    def test_clean_torrent_tasks_removes_by_hash(self):
        """按 hash 清理：从 torrents 移除，并从订阅 torrent_tasks 移除该 hash。"""
        self.mgr.write("torrents", {"h1": {"x": 1}, "h2": {"y": 2}})
        self.mgr.write("subscribes", {"1": {"torrent_tasks": [{"hash": "h1"}, {"hash": "h2"}]}})
        self.mgr.clean_torrent_tasks("h1")
        assert self.mgr.read("torrents") == {"h2": {"y": 2}}
        assert self.mgr.read("subscribes")["1"]["torrent_tasks"] == [{"hash": "h2"}]
