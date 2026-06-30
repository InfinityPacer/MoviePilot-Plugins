"""engine/volatility.py F 变更速率追踪单测。"""
import time
from types import SimpleNamespace

from subscribeassistantenhanced.engine.volatility import (
    MAX_SAMPLE_HISTORY_SIZE,
    VolatilityTracker,
)


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

    def test_default_window_is_two_days(self):
        """无参构造也应使用插件默认的两天观察窗口。"""
        tracker = VolatilityTracker(self.task_mgr)

        tracker.record(total=10, subscribe_id=1)
        tracker.record(total=12, subscribe_id=1)

        entry = self.store["volatility"]["1"]
        assert entry["unstable_until"] - entry["last_total_changed_at"] == 2 * 86400

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

    def test_current_window_shortening_overrides_persisted_unstable_until(self):
        """缩短配置窗口后，旧 unstable_until 不能继续延长观察期。"""
        now = time.time()
        self.store["volatility"] = {
            "1": {
                "records": [
                    {"total": 1, "ts": now - 3 * 86400},
                    {"total": 12, "ts": now - 3 * 86400 + 1},
                ],
                "last_total": 12,
                "last_total_changed_at": now - 3 * 86400 + 1,
                "unstable_until": now + 4 * 86400,
                "last_total_before_change": 1,
                "last_total_after_change": 12,
                "last_total_change_direction": "up",
            }
        }
        tracker = VolatilityTracker(self.task_mgr, window_days=2)

        assert tracker.is_stable(subscribe_id=1) is True
        assert tracker.recent_change_detail(subscribe_id=1) is None
        assert tracker.recent_change_direction(subscribe_id=1) is None
        tracker.record(total=12, subscribe_id=1)
        entry = self.store["volatility"]["1"]
        assert entry["unstable_until"] == entry["last_total_changed_at"] + 2 * 86400

    def test_sample_history_is_capped_for_diagnostics(self):
        """诊断采样保留数量有上限，但不代表稳定判断窗口。"""
        for i in range(25):
            self.tracker.record(total=12, subscribe_id=1)
        entry = self.store.get("volatility", {}).get("1", {})
        assert len(entry["records"]) <= MAX_SAMPLE_HISTORY_SIZE

    def test_recent_total_change_survives_many_same_total_samples(self):
        """窗口内 total 变化不能被后续高频相同采样提前冲掉。"""
        self.tracker.record(total=36, subscribe_id=1)
        self.tracker.record(total=33, subscribe_id=1)
        for _ in range(25):
            self.tracker.record(total=33, subscribe_id=1)

        entry = self.store["volatility"]["1"]
        assert len(entry["records"]) <= MAX_SAMPLE_HISTORY_SIZE
        assert entry["last_total_changed_at"] is not None
        assert entry["unstable_until"] is not None
        assert self.tracker.is_stable(subscribe_id=1) is False
        assert self.tracker.recent_change_direction(subscribe_id=1) == "down"

    def test_recent_change_direction_reports_increase(self):
        """窗口内最近 total 增大时记录 up，供完成守卫区分普通补集与缩小风险。"""
        self.tracker.record(total=10, subscribe_id=1)
        self.tracker.record(total=12, subscribe_id=1)

        assert self.tracker.recent_change_direction(subscribe_id=1) == "up"

    def test_recent_change_detail_reports_old_and_new_total(self):
        """窗口内最近 total 变化明细应保留旧值和新值，供通知原因展示。"""
        self.tracker.record(total=10, subscribe_id=1)
        self.tracker.record(total=12, subscribe_id=1)

        assert self.tracker.recent_change_detail(subscribe_id=1) == "10 -> 12"

    def test_recent_change_detail_reads_existing_entry_without_after_field(self):
        """已持久化的 entry 没有 after 字段时，用 last_total 还原新值。"""
        now = time.time()
        self.store["volatility"] = {
            "1": {
                "records": [{"total": 10, "ts": now - 10}, {"total": 12, "ts": now - 5}],
                "last_total": 12,
                "last_total_changed_at": now - 5,
                "unstable_until": now + 86400,
                "last_total_before_change": 10,
                "last_total_change_direction": "up",
            }
        }

        assert self.tracker.recent_change_detail(subscribe_id=1) == "10 -> 12"

    def test_recent_change_detail_without_subscribe_id_returns_none(self):
        """缺少订阅 ID 时不能从共享记录里猜测变化明细。"""
        assert self.tracker.recent_change_detail(subscribe_id=None) is None

    def test_recent_change_detail_rejects_reused_subscribe_identity(self):
        """订阅 ID 被新媒体复用时，旧媒体的变化明细不能继续展示。"""
        now = time.time()
        old = SimpleNamespace(id=41, tmdbid=100, season=1, episode_group=None)
        new = SimpleNamespace(id=41, tmdbid=200, season=1, episode_group=None)
        self.tracker.record(total=10, subscribe=old)
        self.tracker.record(total=12, subscribe=old)
        self.store["volatility"]["41"]["last_total_changed_at"] = now

        assert self.tracker.recent_change_detail(subscribe=new) is None

    def test_recent_change_detail_reads_legacy_list_records(self):
        """旧 list 记录仍可展示窗口内最近 total 变化明细。"""
        now = time.time()
        self.store["volatility"] = {
            "1": [
                {"total": 9, "ts": now - 8 * 86400},
                {"total": 10, "ts": now - 3600},
                {"total": 12, "ts": now - 1800},
            ]
        }

        assert self.tracker.recent_change_detail(subscribe_id=1) == "10 -> 12"

    def test_recent_change_detail_falls_back_to_records_when_state_expired(self):
        """状态字段过期时，仍从窗口内采样回退读取最近变化明细。"""
        now = time.time()
        self.store["volatility"] = {
            "1": {
                "records": [
                    {"total": 10, "ts": now - 3600},
                    {"total": 12, "ts": now - 1800},
                ],
                "last_total": 12,
                "last_total_changed_at": now - 8 * 86400,
                "last_total_before_change": 8,
                "last_total_after_change": 9,
                "last_total_change_direction": "up",
            }
        }

        assert self.tracker.recent_change_detail(subscribe_id=1) == "10 -> 12"

    def test_recent_change_detail_ignores_invalid_entry(self):
        """损坏的变化记录不能生成用户可见的集数明细。"""
        self.store["volatility"] = {"1": "invalid"}

        assert self.tracker.recent_change_detail(subscribe_id=1) is None

    def test_record_recovers_malformed_records_field(self):
        """持久化 records 字段损坏时，后续写入应重建采样列表。"""
        self.store["volatility"] = {"1": {"records": {"total": 10, "ts": time.time()}}}

        self.tracker.record(total=12, subscribe_id=1)

        entry = self.store["volatility"]["1"]
        assert len(entry["records"]) == 1
        assert entry["records"][0]["total"] == 12
        assert isinstance(entry["records"][0]["ts"], float)
        assert entry["last_total"] == 12

    def test_record_preserves_last_total_when_records_field_is_malformed(self):
        """已有 last_total 仍应参与损坏记录恢复后的变化判断。"""
        self.store["volatility"] = {
            "1": {
                "records": {"bad": "shape"},
                "last_total": 10,
            }
        }

        self.tracker.record(total=12, subscribe_id=1)

        entry = self.store["volatility"]["1"]
        assert entry["last_total_change_direction"] == "up"
        assert entry["last_total_before_change"] == 10
        assert entry["last_total_after_change"] == 12

    def test_is_stable_ignores_malformed_records_field(self):
        """只读路径遇到损坏 records 字段时不能影响订阅刷新。"""
        self.store["volatility"] = {"1": {"records": {"bad": "shape"}}}

        assert self.tracker.is_stable(subscribe_id=1) is True

    def test_recent_change_detail_ignores_malformed_records_field(self):
        """明细读取遇到损坏 records 字段时不能抛错。"""
        self.store["volatility"] = {"1": {"records": {"bad": "shape"}}}

        assert self.tracker.recent_change_detail(subscribe_id=1) is None

    def test_legacy_recent_total_change_survives_after_next_sample(self):
        """旧 list 形态记录升级后也要保留窗口内变化状态。"""
        now = time.time()
        self.store["volatility"] = {
            "1": [
                {"total": 36, "ts": now - 3600},
                {"total": 33, "ts": now - 1800},
            ]
        }

        for _ in range(25):
            self.tracker.record(total=33, subscribe_id=1)

        assert self.tracker.is_stable(subscribe_id=1) is False

    def test_legacy_recent_total_change_survives_subscribe_object_migration(self):
        """带订阅对象写入旧 list 记录时，也要迁移并保留窗口内变化状态。"""
        now = time.time()
        subscribe = SimpleNamespace(id=41, tmdbid=100, season=1, episode_group=None)
        self.store["volatility"] = {
            "41": [
                {"total": 36, "ts": now - 3600},
                {"total": 33, "ts": now - 1800},
            ]
        }

        for _ in range(25):
            self.tracker.record(total=33, subscribe=subscribe)

        entry = self.store["volatility"]["41"]
        assert entry["identity"]["tmdbid"] == 100
        assert entry["last_total_changed_at"] is not None
        assert entry["unstable_until"] is not None
        assert self.tracker.is_stable(subscribe=subscribe) is False

    def test_legacy_recent_total_change_can_be_read_with_subscribe_object(self):
        """只读旧 list 记录时，订阅对象路径不能把旧窗口直接删除。"""
        now = time.time()
        subscribe = SimpleNamespace(id=41, tmdbid=100, season=1, episode_group=None)
        self.store["volatility"] = {
            "41": [
                {"total": 36, "ts": now - 3600},
                {"total": 33, "ts": now - 1800},
            ]
        }

        assert self.tracker.is_stable(subscribe=subscribe) is False
        assert "41" in self.store["volatility"]

    def test_multiple_subscribes_independent(self):
        """不同订阅的 buffer 独立。"""
        self.tracker.record(total=12, subscribe_id=1)
        self.tracker.record(total=13, subscribe_id=1)
        self.tracker.record(total=10, subscribe_id=2)
        assert self.tracker.is_stable(subscribe_id=1) is False
        assert self.tracker.is_stable(subscribe_id=2) is True

    def test_reused_id_with_different_media_starts_new_history(self):
        """同一数据库 ID 被新媒体复用时不得继承旧媒体的总集数变化。"""
        old = SimpleNamespace(id=41, tmdbid=100, season=1, episode_group=None)
        new = SimpleNamespace(id=41, tmdbid=200, season=2, episode_group=None)

        self.tracker.record(total=10, subscribe=old)
        self.tracker.record(total=15, subscribe=new)

        assert self.tracker.is_stable(subscribe=new) is True
        entry = self.store["volatility"]["41"]
        assert entry["identity"]["tmdbid"] == 200
        assert [record["total"] for record in entry["records"]] == [15]
