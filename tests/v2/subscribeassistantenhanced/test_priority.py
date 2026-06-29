"""best_version/priority.py PriorityManager 单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType

from subscribeassistantenhanced.best_version.priority import PriorityManager


def _sub(sid=1, ep_priority=None, current_priority=0, start_episode=1, total_episode=2, best_version=1,
         best_version_full=0, media_type="电视剧", name="测试剧", season=1):
    return SimpleNamespace(
        id=sid,
        name=name,
        season=season,
        type=media_type,
        best_version=best_version,
        episode_priority=ep_priority or {},
        current_priority=current_priority,
        start_episode=start_episode,
        total_episode=total_episode,
        best_version_full=best_version_full,
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

    def test_tv_download_facts_are_owned_by_main_chain(self):
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 0, "2": 0})
        mgr.update_on_download(sub, episodes=[1, 2], new_priority=80)
        mgr._oper.update.assert_not_called()

    def test_empty_episodes_no_op(self):
        mgr = _mgr()
        mgr.update_on_download(_sub(), episodes=[], new_priority=80)
        mgr._oper.update.assert_not_called()


class TestRollback:

    def test_rollback_restores_baseline(self):
        mgr = _mgr()
        baseline = {"episode_priority": {"1": 30}, "current_priority": 30}
        with patch("subscribeassistantenhanced.best_version.priority.SubscribeChain") as chain_cls:
            mgr.rollback(_sub(), baseline=baseline)
        chain_cls.return_value.refresh_subscribe_progress.assert_called_once()
        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["episode_priority"] == {"1": 30}
        assert "current_priority" not in call_payload

    def test_rollback_from_stored_baseline(self):
        store = {"subscribes": {"1": {"priority_baseline": {"episode_priority": {"1": 20}, "current_priority": 20}}}}
        mgr = _mgr(store)
        with patch("subscribeassistantenhanced.best_version.priority.SubscribeChain") as chain_cls:
            mgr.rollback(_sub())
        chain_cls.return_value.refresh_subscribe_progress.assert_called_once()
        assert mgr._oper.update.called

    def test_movie_rollback_restores_current_priority(self):
        mgr = _mgr()
        baseline = {"episode_priority": {}, "current_priority": 30}
        mgr.rollback(_sub(media_type=MediaType.MOVIE), baseline=baseline)
        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["current_priority"] == 30

    def test_rollback_no_baseline_no_op(self):
        mgr = _mgr()
        mgr.rollback(_sub())
        mgr._oper.update.assert_not_called()


class TestTorrentBaselineRollback:
    """按种子隔离的优先级基线与归属回滚（分级洗版不串号）。"""

    def test_empty_torrent_id_skips_baseline_and_rollback(self):
        """缺少种子 ID 时不能写入或清理按种子基线。"""
        store = {}
        mgr = _mgr(store)

        mgr.capture_torrent_baseline(_sub(), "", episodes=[1], contributed_priority=80)
        mgr.rollback_torrent(_sub(ep_priority={"1": 80}), "")

        assert store == {}
        mgr._oper.update.assert_not_called()

    def test_missing_torrent_baseline_no_op(self):
        """找不到种子基线时不应回滚当前洗版优先级。"""
        mgr = _mgr({"subscribes": {"1": {"priority_baselines": {}}}})

        mgr.rollback_torrent(_sub(ep_priority={"1": 80}), "missing")

        mgr._oper.update.assert_not_called()

    def test_rollback_preserves_other_torrents_episodes(self):
        """种子 A(ep1) 回滚不影响种子 B(ep2) 已升级的集。"""
        mgr = _mgr({})
        mgr.capture_torrent_baseline(_sub(ep_priority={"1": 0, "2": 0}), "A",
                                     episodes=[1], contributed_priority=80)
        mgr.capture_torrent_baseline(_sub(ep_priority={"1": 80, "2": 0}), "B",
                                     episodes=[2], contributed_priority=90)
        current = _sub(ep_priority={"1": 80, "2": 90}, current_priority=90)
        with patch(
                "subscribeassistantenhanced.best_version.priority.SubscribeChain.refresh_subscribe_progress",
                create=True,
        ) as refresh_progress:
            mgr.rollback_torrent(current, "A")
        refresh_progress.assert_called_once()
        payload = mgr._oper.update.call_args[0][1]
        assert payload["episode_priority"]["1"] == 0    # A 拥有 → 回滚
        assert payload["episode_priority"]["2"] == 90   # B 拥有 → 保留，不串改
        assert "current_priority" not in payload

    def test_rollback_skips_episode_upgraded_by_other(self):
        """本种子贡献的集已被更高档位覆盖 → 跳过不回滚。"""
        mgr = _mgr({})
        mgr.capture_torrent_baseline(_sub(ep_priority={"1": 0}), "A",
                                     episodes=[1], contributed_priority=80)
        with patch(
                "subscribeassistantenhanced.best_version.priority.SubscribeChain.refresh_subscribe_progress",
                create=True,
        ) as refresh_progress:
            mgr.rollback_torrent(_sub(ep_priority={"1": 95}), "A")
        refresh_progress.assert_called_once()
        payload = mgr._oper.update.call_args[0][1]
        assert payload["episode_priority"]["1"] == 95

    def test_movie_rollback_by_torrent_restores_current_priority(self):
        """电影洗版仍以 current_priority 作为整体质量事实。"""
        store = {}
        mgr = _mgr(store)
        sub = _sub(media_type=MediaType.MOVIE, current_priority=30)
        mgr.capture_torrent_baseline(sub, "A", episodes=[], contributed_priority=80)

        mgr.rollback_torrent(_sub(media_type=MediaType.MOVIE, current_priority=80), "A")

        payload = mgr._oper.update.call_args[0][1]
        assert payload["current_priority"] == 30

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
        sub = _sub(ep_priority={"2": 0})
        with patch("subscribeassistantenhanced.best_version.priority.SubscribeChain") as chain_cls:
            chain_cls.return_value.backfill_existing_episodes.return_value = {"updated": True}
            assert mgr.backfill_existing(sub, existing_episodes=[1, 3]) is True
        chain_cls.return_value.backfill_existing_episodes.assert_called_once_with(
            sub,
            [1, 3],
            priority=100,
            scene="plugin_backfill<订阅助手（增强版）>",
        )

    def test_can_backfill_only_episode_best_version_tv(self):
        """回填仅适用于剧集分集洗版。"""
        mgr = _mgr()

        assert mgr.can_backfill(_sub()) is True
        assert mgr.can_backfill(_sub(media_type=MediaType.TV)) is True
        assert mgr.can_backfill(_sub(best_version=0)) is False
        assert mgr.can_backfill(_sub(best_version_full=1)) is False
        assert mgr.can_backfill(_sub(media_type="电影")) is False

    def test_full_best_version_does_not_backfill(self):
        """全集洗版必须等待整季资源，不使用媒体库已有集回填优先级。"""
        mgr = _mgr()

        with patch("subscribeassistantenhanced.best_version.priority.SubscribeChain") as chain_cls:
            mgr.backfill_existing(_sub(best_version_full=1), existing_episodes=[1, 2])

        mgr._oper.update.assert_not_called()
        chain_cls.return_value.backfill_existing_episodes.assert_not_called()

    def test_backfill_empty_no_op(self):
        mgr = _mgr()
        with patch("subscribeassistantenhanced.best_version.priority.SubscribeChain") as chain_cls:
            mgr.backfill_existing(_sub(), existing_episodes=[])
        mgr._oper.update.assert_not_called()
        chain_cls.return_value.backfill_existing_episodes.assert_not_called()


class TestIsComplete:

    def test_all_100_is_complete(self):
        mgr = _mgr()
        assert mgr.is_complete(_sub(ep_priority={"1": 100, "2": 100})) is True

    def test_invalid_target_range_not_complete(self):
        """目标集范围不可解析时不能按已有 priority 键误判洗版完成。"""
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 100}, start_episode="bad", total_episode=2)

        assert mgr.is_complete(sub) is False

    def test_missing_target_episodes_not_complete(self):
        """目标范围未全部达标时不能只因已有 priority 都是 100 就判洗版完成。"""
        mgr = _mgr()
        assert mgr.is_complete(_sub(ep_priority={"1": 100, "2": 100}, total_episode=9999)) is False

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
        with patch("subscribeassistantenhanced.best_version.priority.SubscribeChain") as chain_cls:
            mgr.mark_complete(sub)
        chain_cls.return_value.backfill_existing_episodes.assert_called_once_with(
            sub,
            [1, 2],
            priority=100,
            scene="plugin_complete<订阅助手（增强版）>",
        )
        mgr._oper.update.assert_not_called()

    def test_mark_complete_fills_target_range(self):
        """分集洗版完成标记应覆盖完整目标范围。"""
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 100}, total_episode=3, best_version_full=0)

        with patch("subscribeassistantenhanced.best_version.priority.SubscribeChain") as chain_cls:
            mgr.mark_complete(sub)

        chain_cls.return_value.backfill_existing_episodes.assert_called_once_with(
            sub,
            [1, 2, 3],
            priority=100,
            scene="plugin_complete<订阅助手（增强版）>",
        )

    def test_mark_complete_without_target_range_noops_for_tv(self):
        """目标范围不可用时不按已有 priority 键猜测 TV 完成范围。"""
        mgr = _mgr()
        sub = _sub(ep_priority={"1": 50, "2": 80}, start_episode="bad", total_episode=2)

        with patch("subscribeassistantenhanced.best_version.priority.SubscribeChain") as chain_cls:
            mgr.mark_complete(sub)

        chain_cls.return_value.backfill_existing_episodes.assert_not_called()
        mgr._oper.update.assert_not_called()

    def test_movie_mark_complete_updates_current_priority(self):
        """电影洗版没有按集事实，完成标记仍写整体优先级。"""
        mgr = _mgr()

        mgr.mark_complete(_sub(media_type=MediaType.MOVIE))

        call_payload = mgr._oper.update.call_args[0][1]
        assert call_payload["current_priority"] == 100
