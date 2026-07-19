"""postcheck/verifier.py H 异步自验证单测。"""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.postcheck.verifier import CompletionVerifier
from subscribeassistantenhanced.engine.types import SeasonScope


def _sub(tmdbid=100, season=1, episode_group=None, total=12, best_version=0, best_version_full=0):
    return SimpleNamespace(
        id=1, tmdbid=tmdbid, season=season, episode_group=episode_group,
        total_episode=total, best_version=best_version, best_version_full=best_version_full,
        name="测试剧", type="电视剧", save_path="/media",
        sites="site1", filter="rule1", filter_groups=["group1"],
    )


def _verifier(store=None, tmdb_fn=None, retention_days=90, rebuild_fn=None,
              subscribe_image_fn=None):
    store = store if store is not None else {}
    oper = MagicMock()
    oper.list.return_value = []
    notify = MagicMock()
    v = CompletionVerifier(
        task_data_read=lambda key: store.get(key, {}),
        task_data_update=lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
        tmdb_episodes_fn=tmdb_fn,
        subscribe_oper=oper,
        retention_days=retention_days,
        notify_fn=notify,
        rebuild_subscribe_fn=rebuild_fn,
        get_subscribe_image_fn=subscribe_image_fn,
    )
    v._store = store
    v._oper = oper
    v._notify_mock = notify
    return v


class TestSnapshot:

    def test_saves_snapshot(self):
        store = {}
        v = _verifier(store)
        scope = SeasonScope(tmdbid=100, season=1, source="main_season")
        v.snapshot(_sub(best_version=1, best_version_full=1), None, scope)
        snaps = store.get("snapshots", {}).get("list", [])
        assert len(snaps) == 1
        assert snaps[0]["tmdbid"] == 100
        assert snaps[0]["total_at_completion"] == 12
        assert snaps[0]["subscribe_config"]["filter"] == "rule1"
        assert snaps[0]["subscribe_config"]["filter_groups"] == ["group1"]
        assert snaps[0]["subscribe_config"]["best_version"] == 1
        assert snaps[0]["subscribe_config"]["best_version_full"] == 1

    def test_saves_media_image_for_later_rebuild_notification(self):
        """完成快照保存媒体图片，供未来增集重建通知继续使用。"""
        store = {}
        v = _verifier(store)
        media = SimpleNamespace(get_message_image=lambda: "media.jpg")

        v.snapshot(_sub(), media, SeasonScope(source="main_season"))

        assert store["snapshots"]["list"][0]["subscribe_image"] == "media.jpg"

    def test_snapshot_falls_back_to_subscribe_image(self):
        """完成快照优先使用订阅记录图片。"""
        store = {}
        v = _verifier(store, subscribe_image_fn=lambda _subscribe: "subscribe.jpg")
        media = SimpleNamespace(get_message_image=lambda: "media.jpg")

        v.snapshot(_sub(), media, SeasonScope(source="main_season"))

        assert store["snapshots"]["list"][0]["subscribe_image"] == "subscribe.jpg"

    def test_dedup_by_key(self):
        """同 (tmdbid, season, episode_group_id) 幂等去重。"""
        store = {}
        v = _verifier(store)
        scope = SeasonScope(tmdbid=100, season=1, source="main_season")
        v.snapshot(_sub(total=12), None, scope)
        v.snapshot(_sub(total=15), None, scope)
        snaps = store["snapshots"]["list"]
        assert len(snaps) == 1
        assert snaps[0]["total_at_completion"] == 15

    def test_different_group_not_deduped(self):
        store = {}
        v = _verifier(store)
        v.snapshot(_sub(episode_group=None), None, SeasonScope(source="main_season"))
        v.snapshot(_sub(episode_group="eg-1"), None, SeasonScope(source="episode_group"))
        snaps = store["snapshots"]["list"]
        assert len(snaps) == 2

    def test_preserves_scope_source(self):
        store = {}
        v = _verifier(store)
        scope = SeasonScope(source="episode_group")
        v.snapshot(_sub(episode_group="eg-1"), None, scope)
        assert store["snapshots"]["list"][0]["scope_source"] == "episode_group"


class TestVerifyAll:

    def test_no_change_keeps_snapshot(self):
        """total 不变 → 保留快照。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_config": {},
        }]}}
        v = _verifier(store, tmdb_fn=lambda *a, **kw: [object()] * 12)
        v.verify_all()
        assert len(store["snapshots"]["list"]) == 1

    def test_increase_triggers_rebuild(self):
        """total 增加 → 重建 + 移除快照。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_image": "subscribe.jpg",
            "subscribe_config": {"name": "测试剧", "season": 1},
        }]}}
        rebuild = MagicMock(return_value=True)
        v = _verifier(store, tmdb_fn=lambda *a, **kw: [object()] * 15,
                      rebuild_fn=rebuild)
        v.verify_all()
        rebuild.assert_called_once()
        assert len(store["snapshots"]["list"]) == 0
        v._notify_mock.assert_called_once()
        assert v._notify_mock.call_args.args[0] == "测试剧 S1 检测到新增集数（12→15），已自动重建订阅"
        assert v._notify_mock.call_args.kwargs["image"] == "subscribe.jpg"
        assert "action" not in v._notify_mock.call_args.kwargs
        assert "reason" not in v._notify_mock.call_args.kwargs

    def test_rebuild_failure_keeps_snapshot_for_retry(self):
        """真实重建失败时必须保留快照，避免丢失后续补救机会。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_config": {"name": "测试"},
        }]}}
        rebuild = MagicMock(return_value=False)
        v = _verifier(store, tmdb_fn=lambda *a, **kw: [object()] * 15,
                      rebuild_fn=rebuild)

        v.verify_all()

        rebuild.assert_called_once()
        assert len(store["snapshots"]["list"]) == 1

    def test_expired_removed(self):
        """超过保留期 → 移除。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12,
            "completed_at": time.time() - 100 * 86400,
            "subscribe_config": {},
        }]}}
        v = _verifier(store, tmdb_fn=lambda *a, **kw: [object()] * 12, retention_days=90)
        v.verify_all()
        assert len(store["snapshots"]["list"]) == 0

    def test_cleanup_expired_uses_configured_retention_without_tmdb(self):
        """纯清理入口按用户保留期删除快照，不触发 TMDB 查询。"""
        now = time.time()
        store = {"snapshots": {"list": [
            {
                "tmdbid": 100, "season": 1, "episode_group_id": None,
                "total_at_completion": 12,
                "completed_at": now - 31 * 86400,
                "subscribe_config": {},
            },
            {
                "tmdbid": 101, "season": 1, "episode_group_id": None,
                "total_at_completion": 12,
                "completed_at": now - 29 * 86400,
                "subscribe_config": {},
            },
        ]}}
        tmdb_fn = MagicMock()
        v = _verifier(store, tmdb_fn=tmdb_fn, retention_days=30)

        assert v.cleanup_expired() == 1

        assert [snap["tmdbid"] for snap in store["snapshots"]["list"]] == [101]
        tmdb_fn.assert_not_called()

    def test_scope_aware_group_verification(self):
        """group scope 快照用 group 集数验证。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": "eg-1",
            "total_at_completion": 16, "completed_at": time.time(),
            "subscribe_config": {"name": "测试"},
        }]}}

        def tmdb_fn(tmdbid, season, episode_group=None):
            if episode_group == "eg-1":
                return [object()] * 20
            return [object()] * 85

        rebuild = MagicMock(return_value=True)
        v = _verifier(store, tmdb_fn=tmdb_fn, rebuild_fn=rebuild)
        v.verify_all()
        rebuild.assert_called_once()

    def test_rebuild_deletes_best_version(self):
        """重建时删除已有洗版订阅。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_config": {"name": "测试"},
        }]}}
        existing_bv = SimpleNamespace(
            id=99, tmdbid=100, season=1, episode_group=None,
            type="电视剧", best_version=1, best_version_full=1,
            total_episode=12,
            name="测试剧", save_path=None, sites=None, filter=None, filter_groups=[],
        )
        rebuild = MagicMock(return_value=True)
        v = _verifier(store, tmdb_fn=lambda *a, **kw: [object()] * 15,
                      rebuild_fn=rebuild)
        v._oper.list.return_value = [existing_bv]
        v.verify_all()
        v._oper.delete.assert_called_once_with(99)
        rebuild.assert_called_once()
        assert v._notify_mock.call_args.args[0] == "测试 S1 检测到新增集数（12→15），已移除旧洗版订阅并重建订阅"

    def test_rebuild_does_not_touch_different_episode_group(self):
        """同 TMDB 同季但不同剧集组不是同一目标范围。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": "eg-new",
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_config": {"name": "测试"},
        }]}}
        other_group = SimpleNamespace(
            id=99, tmdbid=100, season=1,
            episode_group="eg-old", type="电视剧", best_version=1, best_version_full=1,
            save_path=None, sites=None, filter=None, filter_groups=[],
        )
        rebuild = MagicMock(return_value=True)
        v = _verifier(
            store, tmdb_fn=lambda *a, **kw: [object()] * 15,
            rebuild_fn=rebuild,
        )
        v._oper.list.return_value = [other_group]

        v.verify_all()

        v._oper.delete.assert_not_called()
        rebuild.assert_called_once()

    def test_rebuild_sends_notification(self):
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_config": {"name": "测试剧"},
        }]}}
        v = _verifier(store, tmdb_fn=lambda *a, **kw: [object()] * 15,
                      rebuild_fn=MagicMock(return_value=True))
        v.verify_all()
        v._notify_mock.assert_called_once()
        msg = v._notify_mock.call_args[0][0]
        assert "测试剧" in msg
        assert "12" in msg and "15" in msg

    def test_covered_active_normal_subscribe_consumes_snapshot(self):
        """已有普通订阅覆盖最新 TMDB 总集数时，完成快照已完成交接。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_config": {"name": "测试"},
        }]}}
        existing = SimpleNamespace(
            id=50, tmdbid=100, season=1, episode_group=None,
            total_episode=15, best_version=0, best_version_full=0,
        )
        v = _verifier(store, tmdb_fn=lambda *a, **kw: [object()] * 15)
        v._oper.list.return_value = [existing]
        v.verify_all()
        v._oper.add.assert_not_called()
        assert store["snapshots"]["list"] == []

    def test_lagging_active_normal_subscribe_keeps_snapshot(self):
        """已有普通订阅未覆盖最新 TMDB 总集数时，不得误判纠错成功。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_config": {"name": "测试"},
        }]}}
        existing = SimpleNamespace(
            id=50, tmdbid=100, season=1, episode_group=None,
            total_episode=12, best_version=0, best_version_full=0,
        )
        rebuild = MagicMock(return_value=True)
        v = _verifier(
            store,
            tmdb_fn=lambda *a, **kw: [object()] * 15,
            rebuild_fn=rebuild,
        )
        v._oper.list.return_value = [existing]

        v.verify_all()

        rebuild.assert_not_called()
        v._oper.delete.assert_not_called()
        assert len(store["snapshots"]["list"]) == 1

    def test_covered_full_best_version_does_not_rebuild_again(self):
        """已有全集洗版订阅覆盖最新总集数时直接消费快照，不重复删除重建。"""
        store = {"snapshots": {"list": [{
            "tmdbid": 100, "season": 1, "episode_group_id": None,
            "total_at_completion": 12, "completed_at": time.time(),
            "subscribe_config": {"name": "测试"},
        }]}}
        existing = SimpleNamespace(
            id=50, tmdbid=100, season=1, episode_group=None,
            total_episode=15, best_version=1, best_version_full=1,
        )
        rebuild = MagicMock(return_value=True)
        v = _verifier(
            store,
            tmdb_fn=lambda *a, **kw: [object()] * 15,
            rebuild_fn=rebuild,
        )
        v._oper.list.return_value = [existing]

        v.verify_all()

        rebuild.assert_not_called()
        v._oper.delete.assert_not_called()
        assert store["snapshots"]["list"] == []
