"""
SubscribeAssistant P1 下载管理单测。

覆盖下载任务巡检入口、超时判定、删除记录清理、种子信息辅助函数和删除后状态回写。
"""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType
from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


def make_plugin(**overrides) -> SubscribeAssistant:
    """构造下载管理方法所需的插件实例。"""
    plugin = object.__new__(SubscribeAssistant)
    plugin.subscribe_oper = MagicMock()
    plugin.post_message = MagicMock()
    plugin._auto_download_delete = True
    plugin._manual_delete_listen = True
    plugin._tracker_response_listen = True
    plugin._auto_download_pending = True
    plugin._tracker_responses = []
    plugin._download_timeout = 1
    plugin._download_timeout_progress_threshold = 5
    plugin._download_timeout_retry_limit = 3
    plugin._download_timeout_ignore_hours = 48
    plugin._timeout_history_cleanup = 24
    plugin._delete_exclude_tags = ""
    plugin._notify = False
    plugin._auto_search_when_delete = False
    plugin._download_pending_hash_grace_seconds = 600
    for key, value in overrides.items():
        setattr(plugin, key, value)
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    """构造下载任务关联订阅。"""
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, imdbid=None, tvdbid=None, doubanid=None, bangumiid=None,
        note=[1, 2], total_episode=3, start_episode=1, state="R",
        best_version=0, episode_priority={}, current_priority=0,
        backdrop=None, poster=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def make_task(**kwargs) -> dict:
    """构造全局种子任务记录。"""
    base = dict(
        hash="h1", subscribe_id=1, subscribe_info={"id": 1}, username="u",
        downloader="qb", site_id=1, site_name="站点", title="标题", description="副标题",
        enclosure="http://e/1.torrent", page_url="http://e/page",
        pending_check=True, timeout_check=True, manual_check=True,
        time=time.time() - 7200, last_progress_percent=10,
        last_progress_check_time=time.time() - 7200, episodes=[1],
    )
    base.update(kwargs)
    return base


def make_service(inactive=False) -> SimpleNamespace:
    """构造下载器服务信息。"""
    instance = MagicMock()
    instance.is_inactive.return_value = inactive
    return SimpleNamespace(name="qb", type="qbittorrent", instance=instance)


class DownloadManagementTest:
    """下载巡检、超时处理和种子辅助逻辑。"""

    def setup_method(self):
        self.plugin = make_plugin()

    def test_process_download_task_returns_when_all_features_disabled(self):
        plugin = make_plugin(_auto_download_delete=False, _manual_delete_listen=False,
                             _tracker_response_listen=False, _auto_download_pending=False)
        plugin.get_data = MagicMock()
        plugin.process_download_task()
        plugin.get_data.assert_not_called()

    def test_process_download_task_loads_processes_resets_and_saves(self):
        plugin = make_plugin()
        plugin.get_data = MagicMock(side_effect=[{"1": {}}, {"h1": {}}])
        plugin.save_data = MagicMock()
        with patch.object(plugin, "_SubscribeAssistant__process_download_task") as process, \
                patch.object(plugin, "_SubscribeAssistant__reset_subscribe_task_pending") as reset:
            plugin.process_download_task()
        process.assert_called_once_with(subscribe_tasks={"1": {}}, torrent_tasks={"h1": {}})
        reset.assert_called_once_with(subscribe_tasks={"1": {}})
        assert plugin.save_data.call_count == 2

    def test_process_delete_task_removes_records_without_delete_time(self):
        tasks = {"h1": {"hash": "h1"}, "h2": {"hash": "h2", "delete_time": time.time()}}
        self.plugin._SubscribeAssistant__process_delete_task(tasks)
        assert "h1" not in tasks
        assert "h2" in tasks

    def test_process_delete_task_keeps_recent_and_removes_expired(self):
        tasks = {
            "recent": {"delete_time": time.time() - 60},
            "old": {"delete_time": time.time() - 25 * 3600},
        }
        self.plugin._SubscribeAssistant__process_delete_task(tasks)
        assert "recent" in tasks
        assert "old" not in tasks

    def test_check_download_timeout_action_waits_when_disabled_for_task(self):
        action, reason = self.plugin._SubscribeAssistant__check_download_timeout_action(
            make_subscribe(), {}, {"timeout_check": False}, {"downloaded": 1, "target_size": 10}, 3600)
        assert (action, reason) == ("wait", None)

    def test_check_download_timeout_action_initializes_missing_baseline(self):
        torrent_task = make_task(last_progress_percent=None, last_progress_check_time=None)
        action, reason = self.plugin._SubscribeAssistant__check_download_timeout_action(
            make_subscribe(), {}, torrent_task, {"downloaded": 5, "target_size": 10}, 3600)
        assert (action, reason) == ("wait", None)
        assert torrent_task["last_progress_percent"] == 50

    def test_check_download_timeout_action_waits_before_timeout_window(self):
        torrent_task = make_task(last_progress_percent=10, last_progress_check_time=time.time())
        action, reason = self.plugin._SubscribeAssistant__check_download_timeout_action(
            make_subscribe(), {}, torrent_task, {"downloaded": 11, "target_size": 100}, 3600)
        assert (action, reason) == ("wait", None)

    def test_check_download_timeout_action_refreshes_when_progress_delta_enough(self):
        subscribe_task = {"timeout_states": {"tv:1:1": {"fail_count": 1}}}
        torrent_task = make_task(last_progress_percent=10, last_progress_check_time=time.time() - 7200)
        action, reason = self.plugin._SubscribeAssistant__check_download_timeout_action(
            make_subscribe(), subscribe_task, torrent_task, {"downloaded": 20, "target_size": 100}, 7200)
        assert (action, reason) == ("wait", None)
        assert torrent_task["last_progress_percent"] == 20
        assert subscribe_task.get("timeout_states") == {}

    def test_check_download_timeout_action_deletes_on_low_progress(self):
        torrent_task = make_task(last_progress_percent=10, last_progress_check_time=time.time() - 7200)
        action, reason = self.plugin._SubscribeAssistant__check_download_timeout_action(
            make_subscribe(), {}, torrent_task, {"downloaded": 12, "target_size": 100}, 7200)
        assert action == "delete"
        assert "连续 1/3 次" in reason

    def test_check_download_timeout_action_manual_review_at_retry_limit(self):
        plugin = make_plugin(_download_timeout_retry_limit=1)
        torrent_task = make_task(last_progress_percent=10, last_progress_check_time=time.time() - 7200)
        subscribe_task = {}
        action, reason = plugin._SubscribeAssistant__check_download_timeout_action(
            make_subscribe(), subscribe_task, torrent_task, {"downloaded": 11, "target_size": 100}, 7200)
        assert action == "manual_review"
        state = subscribe_task["timeout_states"]["tv:1:1"]
        assert state["ignore_until"] > time.time()

    def test_check_download_timeout_action_ignores_during_protection_window(self):
        subscribe_task = {"timeout_states": {"tv:1:1": {
            "last_torrent_hash": "h1", "ignore_until": time.time() + 3600,
        }}}
        action, reason = self.plugin._SubscribeAssistant__check_download_timeout_action(
            make_subscribe(), subscribe_task, make_task(), {"downloaded": 0, "target_size": 100}, 7200)
        assert (action, reason) == ("ignore", None)

    def test_download_timeout_threshold_and_retry_limit_are_clamped(self):
        plugin = make_plugin(_download_timeout_progress_threshold="200", _download_timeout_retry_limit="0")
        assert plugin._SubscribeAssistant__get_download_timeout_progress_threshold() == 100
        assert plugin._SubscribeAssistant__get_download_timeout_retry_limit() == 1
        plugin._download_timeout_progress_threshold = "bad"
        assert plugin._SubscribeAssistant__get_download_timeout_progress_threshold() == 5

    def test_timeout_scope_key_uses_tv_season_and_episodes_or_movie(self):
        assert self.plugin._SubscribeAssistant__get_timeout_scope_key(
            make_subscribe(), {"episodes": [2, 1]}) == "tv:1:1,2"
        assert self.plugin._SubscribeAssistant__get_timeout_scope_key(
            make_subscribe(type=MOVIE), {"episodes": [1]}) == "movie"

    def test_torrent_completion_status_detects_completed_states_and_sizes(self):
        assert SubscribeAssistant._SubscribeAssistant__get_torrent_completion_status(
            {"state": "seeding", "dltime": 10}) == (True, 0)
        assert SubscribeAssistant._SubscribeAssistant__get_torrent_completion_status(
            {"state": "downloading", "seeding_time": 0, "downloaded": 100, "target_size": 100,
             "dltime": 10}) == (True, 0)
        assert SubscribeAssistant._SubscribeAssistant__get_torrent_completion_status(
            {"state": "downloading", "seeding_time": 0, "downloaded": 50, "target_size": 100,
             "dltime": 10}) == (False, 10)

    def test_torrent_progress_percent_handles_invalid_and_clamps(self):
        assert SubscribeAssistant._SubscribeAssistant__get_torrent_progress_percent({}) == 0
        assert SubscribeAssistant._SubscribeAssistant__get_torrent_progress_percent(
            {"downloaded": 150, "target_size": 100}) == 100
        assert SubscribeAssistant._SubscribeAssistant__get_torrent_progress_percent(
            {"downloaded": "bad", "target_size": 100}) == 0

    def test_clean_invalid_torrents_removes_global_and_subscribe_tasks(self):
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}, {"hash": "h2"}]}}
        torrent_tasks = {"h1": make_task(hash="h1"), "h2": make_task(hash="h2")}
        self.plugin._SubscribeAssistant__clean_invalid_torrents(["h1"], subscribe_tasks, torrent_tasks)
        assert "h1" not in torrent_tasks
        assert subscribe_tasks["1"]["torrent_tasks"] == [{"hash": "h2"}]

    def test_clean_torrent_task_by_hash_records_delete_and_delegates_followup(self):
        subscribe_task = {"torrent_tasks": [{"hash": "h1", "current_priority_baseline": 10}]}
        torrent_tasks = {"h1": make_task(hash="h1")}
        with patch.object(self.plugin, "_SubscribeAssistant__with_lock_and_update_delete_tasks") as delete_lock, \
                patch.object(self.plugin, "_SubscribeAssistant__handle_timeout_seed_deletion") as followup:
            self.plugin._SubscribeAssistant__clean_torrent_task_by_hash(
                make_subscribe(), subscribe_task, subscribe_task["torrent_tasks"], set(),
                "h1", torrent_tasks["h1"], torrent_tasks, "原因", "timeout")
        assert torrent_tasks == {}
        assert subscribe_task["torrent_tasks"] == []
        delete_lock.assert_called_once()
        followup.assert_called_once()

    def test_reset_subscribe_task_pending_restores_state_when_no_pending(self):
        subscribe = make_subscribe(state="P")
        self.plugin.subscribe_oper.get.return_value = subscribe
        subscribe_tasks = {"1": {"id": 1, "name": "测试剧", "tmdbid": 100, "season": 1,
                                 "episode_group": None, "torrent_tasks": [], "tv_pending": False}}
        self.plugin._SubscribeAssistant__reset_subscribe_task_pending(subscribe_tasks)
        self.plugin.subscribe_oper.update.assert_called_once_with(1, {"state": "R"})

    def test_process_download_task_marks_missing_subscribe_task_invalid(self):
        torrent_tasks = {"h1": make_task(hash="h1")}
        with patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task({}, torrent_tasks)
        clean_invalid.assert_called_once_with(["h1"], {}, torrent_tasks)

    def test_process_download_task_marks_missing_database_subscribe_invalid(self):
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        self.plugin.subscribe_oper.get.return_value = None
        with patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        clean_invalid.assert_called_once_with(["h1"], subscribe_tasks, torrent_tasks)

    def test_process_download_task_marks_mismatched_subscribe_invalid(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=False), \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        clean_invalid.assert_called_once_with(["h1"], subscribe_tasks, torrent_tasks)

    def test_process_download_task_skips_when_subscribe_status_not_active(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=False), \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        clean_invalid.assert_called_once_with([], subscribe_tasks, torrent_tasks)

    def test_process_download_task_marks_missing_subscribe_torrent_task_invalid(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "other"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        clean_invalid.assert_called_once_with(["h1"], subscribe_tasks, torrent_tasks)

    def test_process_download_task_marks_missing_downloader_service_invalid(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_downloader_service", return_value=None), \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        clean_invalid.assert_called_once_with(["h1"], subscribe_tasks, torrent_tasks)

    def test_process_download_task_keeps_task_when_downloader_inactive(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_downloader_service",
                             return_value=make_service(inactive=True)), \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        clean_invalid.assert_called_once_with([], subscribe_tasks, torrent_tasks)

    def test_process_download_task_cleans_manual_deleted_torrent_when_listen_enabled(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1", manual_check=True)}
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_downloader_service",
                             return_value=make_service()), \
                patch.object(self.plugin, "_SubscribeAssistant__get_torrents", return_value=None), \
                patch.object(self.plugin, "_SubscribeAssistant__clean_torrent_task_by_hash") as clean_by_hash, \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        clean_by_hash.assert_called_once()
        assert clean_by_hash.call_args.kwargs["reason_type"] == "manual"
        clean_invalid.assert_called_once_with([], subscribe_tasks, torrent_tasks)

    def test_process_download_task_marks_missing_torrent_info_invalid(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_downloader_service",
                             return_value=make_service()), \
                patch.object(self.plugin, "_SubscribeAssistant__get_torrents", return_value=object()), \
                patch.object(self.plugin, "_SubscribeAssistant__get_torrent_info", return_value=None), \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        clean_invalid.assert_called_once_with(["h1"], subscribe_tasks, torrent_tasks)

    def test_process_download_task_removes_completed_torrent_task(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}, {"hash": "h2"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_downloader_service",
                             return_value=make_service()), \
                patch.object(self.plugin, "_SubscribeAssistant__get_torrents", return_value=object()), \
                patch.object(self.plugin, "_SubscribeAssistant__get_torrent_info",
                             return_value={"state": "seeding", "dltime": 100}), \
                patch.object(self.plugin, "_SubscribeAssistant__clear_download_timeout_state") as clear_state, \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents") as clean_invalid:
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        assert torrent_tasks == {}
        assert subscribe_tasks["1"]["torrent_tasks"] == [{"hash": "h2"}]
        clear_state.assert_called_once()
        clean_invalid.assert_called_once_with([], subscribe_tasks, torrent_tasks)

    def test_process_download_task_deletes_tracker_matched_torrent(self):
        plugin = make_plugin(_tracker_response_listen=True, _tracker_responses=["banned"])
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        plugin.subscribe_oper.get.return_value = subscribe
        service = make_service()
        with patch.object(plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__get_downloader_service", return_value=service), \
                patch.object(plugin, "_SubscribeAssistant__get_torrents", return_value=object()), \
                patch.object(plugin, "_SubscribeAssistant__get_torrent_info",
                             return_value={"state": "downloading", "dltime": 7200,
                                           "downloaded": 1, "target_size": 100,
                                           "tracker_responses": ["Torrent BANNED"]}), \
                patch.object(plugin, "_SubscribeAssistant__get_delete_excluded_tags", return_value=[]), \
                patch.object(plugin, "_SubscribeAssistant__delete_torrents") as delete_torrents, \
                patch.object(plugin, "_SubscribeAssistant__clean_torrent_task_by_hash") as clean_by_hash, \
                patch.object(plugin, "_SubscribeAssistant__clean_invalid_torrents"):
            plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        delete_torrents.assert_called_once_with(downloader=service.instance, torrent_hashes="h1")
        assert clean_by_hash.call_args.kwargs["reason_type"] == "tracker"

    def test_process_download_task_skips_tracker_delete_when_excluded_tag_matches(self):
        plugin = make_plugin(_tracker_response_listen=True, _tracker_responses=["banned"])
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "h1"}]}}
        torrent_tasks = {"h1": make_task(hash="h1")}
        plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__get_downloader_service",
                             return_value=make_service()), \
                patch.object(plugin, "_SubscribeAssistant__get_torrents", return_value=object()), \
                patch.object(plugin, "_SubscribeAssistant__get_torrent_info",
                             return_value={"state": "downloading", "dltime": 7200,
                                           "downloaded": 1, "target_size": 100,
                                           "tracker_responses": ["banned"]}), \
                patch.object(plugin, "_SubscribeAssistant__get_delete_excluded_tags", return_value=["H&R"]), \
                patch.object(plugin, "_SubscribeAssistant__delete_torrents") as delete_torrents, \
                patch.object(plugin, "_SubscribeAssistant__clean_invalid_torrents"):
            plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        delete_torrents.assert_not_called()

    def test_process_download_task_routes_timeout_actions(self):
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {"torrent_tasks": [{"hash": "manual"}, {"hash": "ignore"}, {"hash": "delete"}]}}
        torrent_tasks = {
            "manual": make_task(hash="manual"),
            "ignore": make_task(hash="ignore"),
            "delete": make_task(hash="delete"),
        }
        self.plugin.subscribe_oper.get.return_value = subscribe
        service = make_service()
        timeout_results = [("manual_review", "人工确认"), ("ignore", None), ("delete", "超时删除")]
        with patch.object(self.plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_downloader_service", return_value=service), \
                patch.object(self.plugin, "_SubscribeAssistant__get_torrents", return_value=object()), \
                patch.object(self.plugin, "_SubscribeAssistant__get_torrent_info",
                             return_value={"state": "downloading", "dltime": 7200,
                                           "downloaded": 1, "target_size": 100,
                                           "tracker_responses": []}), \
                patch.object(self.plugin, "_SubscribeAssistant__get_delete_excluded_tags", return_value=[]), \
                patch.object(self.plugin, "_SubscribeAssistant__check_download_timeout_action",
                             side_effect=timeout_results), \
                patch.object(self.plugin, "_SubscribeAssistant__handle_download_timeout_manual_review") as review, \
                patch.object(self.plugin, "_SubscribeAssistant__delete_torrents") as delete_torrents, \
                patch.object(self.plugin, "_SubscribeAssistant__clean_torrent_task_by_hash") as clean_by_hash, \
                patch.object(self.plugin, "_SubscribeAssistant__clean_invalid_torrents"):
            self.plugin._SubscribeAssistant__process_download_task(subscribe_tasks, torrent_tasks)
        review.assert_called_once()
        delete_torrents.assert_called_once_with(downloader=service.instance, torrent_hashes="delete")
        assert clean_by_hash.call_args.kwargs["reason_type"] == "timeout"
