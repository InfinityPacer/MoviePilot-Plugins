"""
SubscribeAssistant P2 任务管理状态机单测。

覆盖插件持久化包装、订阅匹配、任务清理、种子任务维护与待定状态判断。
"""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType
from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


def make_plugin(**overrides) -> SubscribeAssistant:
    """构造绕过 __init__ 的插件实例。"""
    plugin = object.__new__(SubscribeAssistant)
    plugin.get_data = MagicMock(return_value=None)
    plugin.save_data = MagicMock(return_value=True)
    plugin.subscribe_oper = MagicMock()
    plugin._download_pending_hash_grace_seconds = 600
    for key, value in overrides.items():
        setattr(plugin, key, value)
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    """构造订阅任务匹配所需的最小对象。"""
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, imdbid=None, tvdbid=None, doubanid=None, bangumiid=None,
        best_version=0, backdrop=None, poster=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def make_torrent_info(**kwargs) -> SimpleNamespace:
    """构造种子信息替身。"""
    base = dict(site=1, site_name="站点", title="标题", description="副标题",
                enclosure="http://e/1.torrent", page_url="http://e/page", pri_order=80)
    base.update(kwargs)
    return SimpleNamespace(**base)


class TaskManagementTest:
    """插件任务字典的初始化、匹配和更新。"""

    def setup_method(self):
        self.plugin = make_plugin()

    def test_get_data_returns_empty_dict_when_storage_missing(self):
        assert self.plugin._SubscribeAssistant__get_data("subscribes") == {}
        self.plugin.get_data.assert_called_once_with(key="subscribes")

    def test_get_data_returns_existing_dict(self):
        self.plugin.get_data.return_value = {"1": {"id": 1}}
        assert self.plugin._SubscribeAssistant__get_data("subscribes") == {"1": {"id": 1}}

    def test_save_data_delegates_to_plugin_storage(self):
        assert self.plugin._SubscribeAssistant__save_data("subscribes", {"1": {}})
        self.plugin.save_data.assert_called_once_with(key="subscribes", value={"1": {}})

    def test_match_subscribe_returns_true_for_same_identity(self):
        subscribe = make_subscribe()
        task = {"id": 1, "name": "测试剧", "tmdbid": 100, "season": 1, "episode_group": None}
        assert SubscribeAssistant._SubscribeAssistant__match_subscribe(subscribe, task)

    def test_match_subscribe_rejects_id_name_tmdb_and_episode_group_mismatch(self):
        subscribe = make_subscribe()
        assert not SubscribeAssistant._SubscribeAssistant__match_subscribe(subscribe, {})
        assert not SubscribeAssistant._SubscribeAssistant__match_subscribe(subscribe, {"id": 2, "name": "测试剧"})
        assert not SubscribeAssistant._SubscribeAssistant__match_subscribe(
            subscribe, {"id": 1, "name": "测试剧", "tmdbid": 101, "season": 1, "episode_group": None})
        assert not SubscribeAssistant._SubscribeAssistant__match_subscribe(
            make_subscribe(tmdbid=None, doubanid="db-1"),
            {"id": 1, "name": "测试剧", "doubanid": "db-2", "season": 1, "episode_group": None})
        assert not SubscribeAssistant._SubscribeAssistant__match_subscribe(
            subscribe, {"id": 1, "name": "测试剧", "tmdbid": 100, "season": 2, "episode_group": None})
        assert not SubscribeAssistant._SubscribeAssistant__match_subscribe(
            make_subscribe(episode_group="a"),
            {"id": 1, "name": "测试剧", "tmdbid": 100, "season": 1, "episode_group": "b"})

    def test_clear_subscribe_tasks_removes_key(self):
        tasks = {"1": {"id": 1}, "2": {"id": 2}}
        SubscribeAssistant._SubscribeAssistant__clear_subscribe_tasks(tasks, 1)
        assert tasks == {"2": {"id": 2}}

    def test_clear_torrent_tasks_removes_matching_subscribe_id(self):
        tasks = {"h1": {"subscribe_id": 1}, "h2": {"subscribe_id": 2}}
        SubscribeAssistant._SubscribeAssistant__clear_torrent_tasks(tasks, 1)
        assert tasks == {"h2": {"subscribe_id": 2}}

    def test_clear_tasks_dispatches_both_locked_updates(self):
        calls = []

        def subscribe_lock(method, **kwargs):
            calls.append(("subscribes", method.__name__, kwargs))

        def torrent_lock(method, **kwargs):
            calls.append(("torrents", method.__name__, kwargs))

        with patch.object(self.plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks",
                          side_effect=subscribe_lock), \
                patch.object(self.plugin, "_SubscribeAssistant__with_lock_and_update_torrent_tasks",
                             side_effect=torrent_lock):
            self.plugin.clear_tasks(1, {"id": 1})
        assert calls[0][0] == "subscribes"
        assert calls[1][0] == "torrents"

    def test_update_or_add_delete_tasks_records_delete_time_and_type(self):
        tasks = {}
        torrent_task = {"hash": "h1", "title": "标题"}
        SubscribeAssistant._SubscribeAssistant__update_or_add_delete_tasks(tasks, torrent_task, "manual")
        assert tasks["h1"]["delete_type"] == "manual"
        assert tasks["h1"]["delete_time"] > 0

    def test_initialize_subscribe_task_creates_full_task(self):
        tasks = {}
        task, exists = self.plugin._SubscribeAssistant__initialize_subscribe_task(make_subscribe(), tasks)
        assert not exists
        assert task["id"] == 1
        assert task["torrent_tasks"] == []
        assert "1" in tasks

    def test_initialize_subscribe_task_reuses_matching_existing_task(self):
        tasks = {"1": {"id": 1, "name": "测试剧", "tmdbid": 100, "season": 1,
                       "episode_group": None, "torrent_tasks": [{"hash": "h"}]}}
        task, exists = self.plugin._SubscribeAssistant__initialize_subscribe_task(make_subscribe(), tasks)
        assert exists
        assert task["torrent_tasks"] == [{"hash": "h"}]

    def test_initialize_subscribe_task_replaces_mismatched_existing_task(self):
        tasks = {"1": {"id": 1, "name": "旧剧", "tmdbid": 100, "season": 1,
                       "episode_group": None, "torrent_tasks": [{"hash": "old"}]}}
        task, exists = self.plugin._SubscribeAssistant__initialize_subscribe_task(make_subscribe(), tasks)
        assert not exists
        assert task["name"] == "测试剧"
        assert task["torrent_tasks"] == []

    def test_update_or_add_subscribe_torrent_task_adds_new_task(self):
        subscribe_task = {"torrent_tasks": []}
        added = self.plugin._SubscribeAssistant__update_or_add_subscribe_torrent_task(
            subscribe_task, "h1", make_torrent_info(), [1], "qb", True)
        assert added
        assert subscribe_task["torrent_tasks"][0]["hash"] == "h1"
        assert subscribe_task["torrent_tasks"][0]["pending"]

    def test_update_or_add_subscribe_torrent_task_updates_hashless_match(self):
        torrent_info = make_torrent_info()
        subscribe_task = {"torrent_tasks": [{
            "hash": None, "enclosure": torrent_info.enclosure, "page_url": torrent_info.page_url,
            "pending": False,
        }]}
        updated = self.plugin._SubscribeAssistant__update_or_add_subscribe_torrent_task(
            subscribe_task, "h1", torrent_info, [2], "qb", True)
        assert updated
        task = subscribe_task["torrent_tasks"][0]
        assert task["hash"] == "h1"
        assert task["episodes"] == [2]
        assert task["pending"]

    def test_update_or_add_subscribe_torrent_task_deduplicates_existing_hash(self):
        subscribe_task = {"torrent_tasks": [{"hash": "h1", "pending": True}]}
        changed = self.plugin._SubscribeAssistant__update_or_add_subscribe_torrent_task(
            subscribe_task, "h1", make_torrent_info(), [1], "qb", True)
        assert not changed
        assert len(subscribe_task["torrent_tasks"]) == 1

    def test_update_or_add_subscribe_torrent_task_marks_existing_hash_pending_when_needed(self):
        subscribe_task = {"torrent_tasks": [{"hash": "h1", "pending": False}]}
        changed = self.plugin._SubscribeAssistant__update_or_add_subscribe_torrent_task(
            subscribe_task, "h1", make_torrent_info(), [1], "qb", True)
        assert changed
        task = subscribe_task["torrent_tasks"][0]
        assert task["pending"]
        assert task["episodes"] == [1]
        assert task["downloader"] == "qb"

    def test_update_or_add_subscribe_torrent_task_rejects_empty_task_or_missing_torrent_info(self):
        assert not self.plugin._SubscribeAssistant__update_or_add_subscribe_torrent_task(
            {}, "h1", make_torrent_info(), [1], "qb", True)
        subscribe_task = {"torrent_tasks": []}
        assert not self.plugin._SubscribeAssistant__update_or_add_subscribe_torrent_task(
            subscribe_task, None, None, [1], "qb", False)

    def test_update_subscribe_torrent_task_rejects_empty_subscribe_or_task_store(self):
        assert self.plugin._SubscribeAssistant__update_subscribe_torrent_task({}, None) is None
        assert self.plugin._SubscribeAssistant__update_subscribe_torrent_task(None, make_subscribe()) is None

    def test_update_subscribe_tv_pending_task_sets_and_clears_state(self):
        task = {}
        assert self.plugin._SubscribeAssistant__update_subscribe_tv_pending_task(
            make_subscribe(), task, True)
        assert task["tv_pending"]
        assert self.plugin._SubscribeAssistant__update_subscribe_tv_pending_task(
            make_subscribe(), task, False)
        assert not task["tv_pending"]
        assert task["tv_pending_time"] is None

    def test_update_subscribe_tv_pending_task_rejects_empty_or_unchanged_state(self):
        assert not self.plugin._SubscribeAssistant__update_subscribe_tv_pending_task(None, {}, True)
        assert not self.plugin._SubscribeAssistant__update_subscribe_tv_pending_task(make_subscribe(), None, True)
        task = {"tv_pending": True, "tv_pending_time": 123}
        assert not self.plugin._SubscribeAssistant__update_subscribe_tv_pending_task(make_subscribe(), task, True)
        assert task["tv_pending_time"] == 123

    def test_get_subscribe_task_download_pending_respects_hashless_grace(self):
        now = time.time()
        task = {"torrent_tasks": [
            {"pending": True, "hash": None, "pending_time": now - 100},
            {"pending": True, "hash": None, "pending_time": now - 1000},
        ]}
        assert self.plugin._SubscribeAssistant__get_subscribe_task_download_pending(task)

    def test_get_subscribe_task_pending_rejects_empty_task_and_delegates_download_pending(self):
        assert not self.plugin._SubscribeAssistant__get_subscribe_task_pending({})
        assert not self.plugin._SubscribeAssistant__get_subscribe_task_download_pending({})

    def test_is_download_pending_task_alive_rejects_invalid_hashless_pending_time(self):
        alive = self.plugin._SubscribeAssistant__is_download_pending_task_alive
        assert not alive({"pending": True, "hash": None, "pending_time": "bad"}, current_time=1000)
        assert not alive({"pending": True, "hash": None, "pending_time": 0}, current_time=1000)
        assert not alive({"pending": True, "hash": None, "pending_time": 100}, current_time=1000)
        assert alive({"pending": True, "hash": None, "pending_time": 900}, current_time=1000)

    def test_drop_expired_hashless_pending_tasks_removes_only_expired(self):
        now = time.time()
        subscribe_task = {"torrent_tasks": [
            {"hash": "h1", "pending": True},
            {"hash": None, "pending": True, "pending_time": now - 1000, "title": "old"},
            {"hash": None, "pending": True, "pending_time": now, "title": "new"},
        ]}
        changed = self.plugin._SubscribeAssistant__drop_expired_hashless_pending_tasks(
            make_subscribe(), subscribe_task)
        assert changed
        assert [task.get("title") for task in subscribe_task["torrent_tasks"]] == [None, "new"]

    def test_drop_expired_hashless_pending_tasks_removes_expired_baseline_but_keeps_plain_hashless_task(self):
        now = time.time()
        subscribe_task = {"torrent_tasks": [
            {"hash": None, "pending": False, "time": now - 1000,
             "current_priority_baseline": 10, "title": "old-baseline"},
            {"hash": None, "pending": False, "time": now, "episode_priority_baseline": {"1": 80},
             "title": "new-baseline"},
            {"hash": None, "pending": False, "time": now - 1000, "title": "plain"},
        ]}
        changed = self.plugin._SubscribeAssistant__drop_expired_hashless_pending_tasks(
            make_subscribe(), subscribe_task)
        assert changed
        assert [task.get("title") for task in subscribe_task["torrent_tasks"]] == ["new-baseline", "plain"]

    def test_get_subscribe_image_prefers_backdrop_then_poster(self):
        assert SubscribeAssistant._SubscribeAssistant__get_subscribe_image(
            make_subscribe(backdrop="http://img/original/a.jpg",
                           poster="http://img/original/p.jpg")) == "http://img/w500/a.jpg"
        assert SubscribeAssistant._SubscribeAssistant__get_subscribe_image(
            make_subscribe(backdrop=None,
                           poster="http://img/original/p.jpg")) == "http://img/w500/p.jpg"
