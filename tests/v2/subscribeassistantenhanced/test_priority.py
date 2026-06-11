"""best_version/priority.py PriorityManager 单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.best_version.priority import PriorityManager


def _sub(sid=1, ep_priority=None, current_priority=0):
    return SimpleNamespace(
        id=sid, episode_priority=ep_priority or {}, current_priority=current_priority,
    )


def _mgr(store=None):
    store = store if store is not None else {}
    oper = MagicMock()
    m = PriorityManager(
        task_data_read=lambda key: store.get(key, {}),
        task_data_update=lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
        subscribe_oper=oper,
    )
    m._store = store
    m._oper = oper
    return m


class TestCaptureBaseline:

    def test_captures_current_state(self):
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 50, "2": 30}, current_priority=50)
        baseline = mgr.capture_baseline(sub, torrent_priority=60)
        assert baseline["episode_priority"] == {"1": 50, "2": 30}
        assert baseline["current_priority"] == 50
        assert baseline["torrent_priority"] == 60

    def test_baseline_persisted(self):
        store = {}
        mgr = _mgr(store)
        mgr.capture_baseline(_sub(), torrent_priority=60)
        assert "priority_baseline" in store.get("subscribes", {}).get("1", {})


class TestUpdateOnDownload:

    def test_updates_episode_priority(self):
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 0, "2": 0})
        mgr.update_on_download(sub, episodes=[1, 2], new_priority=80)
        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["episode_priority"]["1"] == 80
        assert call_payload["episode_priority"]["2"] == 80

    def test_does_not_downgrade(self):
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 100, "2": 50})
        mgr.update_on_download(sub, episodes=[1, 2], new_priority=80)
        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["episode_priority"]["1"] == 100
        assert call_payload["episode_priority"]["2"] == 80

    def test_updates_current_priority(self):
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 0}, current_priority=0)
        mgr.update_on_download(sub, episodes=[1], new_priority=80)
        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["current_priority"] == 80

    def test_empty_episodes_no_op(self):
        mgr = _mgr()
        mgr.update_on_download(_sub(), episodes=[], new_priority=80)
        mgr._oper.update.assert_not_called()


class TestRollback:

    def test_rollback_restores_baseline(self):
        mgr = _mgr()
        baseline = {"episode_priority": {"1": 30}, "current_priority": 30}
        mgr.rollback(_sub(), baseline=baseline)
        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["episode_priority"] == {"1": 30}
        assert call_payload["current_priority"] == 30

    def test_rollback_from_stored_baseline(self):
        store = {"subscribes": {"1": {"priority_baseline": {"episode_priority": {"1": 20}, "current_priority": 20}}}}
        mgr = _mgr(store)
        mgr.rollback(_sub())
        assert mgr._oper.update.called

    def test_rollback_no_baseline_no_op(self):
        mgr = _mgr()
        mgr.rollback(_sub())
        mgr._oper.update.assert_not_called()


class TestTorrentBaselineRollback:
    """按种子隔离的优先级基线与归属回滚（分级洗版不串号）。"""

    def test_rollback_preserves_other_torrents_episodes(self):
        """种子 A(ep1) 回滚不影响种子 B(ep2) 已升级的集。"""
        mgr = _mgr({})
        mgr.capture_torrent_baseline(_sub(ep_priority={"1": 0, "2": 0}), "A",
                                     episodes=[1], contributed_priority=80)
        mgr.capture_torrent_baseline(_sub(ep_priority={"1": 80, "2": 0}), "B",
                                     episodes=[2], contributed_priority=90)
        current = _sub(ep_priority={"1": 80, "2": 90}, current_priority=90)
        mgr.rollback_torrent(current, "A")
        payload = mgr._oper.update.call_args[0][1]
        assert payload["episode_priority"]["1"] == 0    # A 拥有 → 回滚
        assert payload["episode_priority"]["2"] == 90   # B 拥有 → 保留，不串改

    def test_rollback_skips_episode_upgraded_by_other(self):
        """本种子贡献的集已被更高档位覆盖 → 跳过不回滚。"""
        mgr = _mgr({})
        mgr.capture_torrent_baseline(_sub(ep_priority={"1": 0}), "A",
                                     episodes=[1], contributed_priority=80)
        mgr.rollback_torrent(_sub(ep_priority={"1": 95}), "A")
        payload = mgr._oper.update.call_args[0][1]
        assert payload["episode_priority"]["1"] == 95

    def test_empty_episodes_uses_target_range(self):
        """整季包 episodes 为空 → 回退到目标集范围记录基线。"""
        store = {}
        mgr = _mgr(store)
        mgr.capture_torrent_baseline(_sub(ep_priority={"1": 0, "2": 0}), "A",
                                     episodes=[], contributed_priority=80, target_episodes=[1, 2])
        baseline = store["subscribes"]["1"]["priority_baselines"]["A"]
        assert set(baseline["episode_priority_baseline"].keys()) == {"1", "2"}


class TestBackfillExisting:

    def test_backfill_sets_100(self):
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 0, "2": 0, "3": 0})
        mgr.backfill_existing(sub, existing_episodes=[1, 3])
        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["episode_priority"]["1"] == 100
        assert call_payload["episode_priority"]["3"] == 100

    def test_backfill_empty_no_op(self):
        mgr = _mgr()
        mgr.backfill_existing(_sub(), existing_episodes=[])
        mgr._oper.update.assert_not_called()


class TestIsComplete:

    def test_all_100_is_complete(self):
        mgr = _mgr()
        assert mgr.is_complete(_sub(ep_priority={"1": 100, "2": 100})) is True

    def test_mixed_not_complete(self):
        mgr = _mgr()
        assert mgr.is_complete(_sub(ep_priority={"1": 100, "2": 50})) is False

    def test_empty_not_complete(self):
        mgr = _mgr()
        assert mgr.is_complete(_sub(ep_priority={})) is False


class TestMarkComplete:

    def test_mark_sets_all_100(self):
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 50, "2": 80})
        mgr.mark_complete(sub)
        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["episode_priority"]["1"] == 100
        assert call_payload["episode_priority"]["2"] == 100
        assert call_payload["current_priority"] == 100
