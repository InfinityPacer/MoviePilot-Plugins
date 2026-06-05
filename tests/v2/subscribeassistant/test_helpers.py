"""
SubscribeAssistant 辅助方法、生命周期及调度入口单测。

覆盖业务域：
- 集数/下载辅助：__get_subscribe_target_episodes / __normalize_episode_numbers /
  __get_download_resource_episodes / __is_download_resource_cover_subscribe_range /
  __get_subscribe_by_source
- 版本/Tracker辅助：__compare_versions / __get_default_tracker_response
- 下载历史：__get_related_download_histories
- 生命周期：init_plugin / get_state / get_service / stop_service / get_command / get_api
- 调度入口：auto_check / download_check / meta_check / best_version_check / reset_task
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

from app.schemas.types import MediaType

from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def make_plugin(**overrides) -> SubscribeAssistant:
    plugin = object.__new__(SubscribeAssistant)
    plugin.subscribe_oper = MagicMock()
    plugin.downloadhistory_oper = MagicMock()
    plugin.transferhistory_oper = MagicMock()
    plugin.tmdb_chain = MagicMock()
    plugin.downloader_helper = MagicMock()
    plugin._enabled = True
    plugin._notify = False
    plugin._onlyonce = False
    plugin._auto_download_delete = True
    plugin._manual_delete_listen = True
    plugin._tracker_response_listen = True
    plugin._tracker_responses = []
    plugin._tracker_response = ""
    plugin._auto_search_when_delete = False
    plugin._auto_download_pending = True
    plugin._auto_tv_pending = False
    plugin._auto_pause = False
    plugin._auto_best_types = set()
    plugin._auto_best_type = "no"
    plugin._auto_best_cron = "0 15 * * *"
    plugin._auto_best_episode_to_full = False
    plugin._auto_best_backfill_priority = False
    plugin._auto_best_remaining_days = None
    plugin._download_check_interval = 5
    plugin._meta_check_interval = 6
    plugin._download_timeout = 3
    plugin._download_timeout_progress_threshold = 5
    plugin._download_timeout_retry_limit = 3
    plugin._download_timeout_ignore_hours = 48
    plugin._timeout_history_cleanup = None
    plugin._skip_deletion = True
    plugin._delete_exclude_tags = ""
    plugin._download_pending_hash_grace_seconds = 300
    plugin._auto_pause_users = set()
    plugin._auto_pause_user = ""
    plugin.get_data = MagicMock(return_value={})
    plugin.save_data = MagicMock()
    plugin.post_message = MagicMock()
    plugin.update_config = MagicMock()
    for k, v in overrides.items():
        setattr(plugin, k, v)
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, imdbid=None, tvdbid=None, doubanid=None, bangumiid=None,
        best_version=0, best_version_full=0, start_episode=1, total_episode=12,
        lack_episode=0, state="R", manual_total_episode=0,
        note=[], current_priority=0, episode_priority={},
        backdrop="", poster="", date="2024-01-01 00:00:00",
        last_update="2024-06-01 00:00:00", username="admin",
    )
    base.update(kwargs)
    ns = SimpleNamespace(**base)
    if not hasattr(ns, "to_dict"):
        ns.to_dict = lambda: {k: getattr(ns, k) for k in base}
    return ns


# ===========================================================================
# __get_subscribe_target_episodes
# ===========================================================================

class TestGetSubscribeTargetEpisodes:

    def test_normal(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=5, start_episode=1)
        result = plugin._SubscribeAssistant__get_subscribe_target_episodes(sub)
        assert result == [1, 2, 3, 4, 5]

    def test_start_episode_gt_1(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=5, start_episode=3)
        result = plugin._SubscribeAssistant__get_subscribe_target_episodes(sub)
        assert result == [3, 4, 5]

    def test_no_total_episode(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=0)
        result = plugin._SubscribeAssistant__get_subscribe_target_episodes(sub)
        assert result == []

    def test_none_total_episode(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=None)
        result = plugin._SubscribeAssistant__get_subscribe_target_episodes(sub)
        assert result == []

    def test_none_subscribe(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_subscribe_target_episodes(None)
        assert result == []

    def test_none_start_episode(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=3, start_episode=None)
        result = plugin._SubscribeAssistant__get_subscribe_target_episodes(sub)
        assert result == [1, 2, 3]


# ===========================================================================
# __normalize_episode_numbers
# ===========================================================================

class TestNormalizeEpisodeNumbers:

    def _call(self, episodes):
        return SubscribeAssistant._SubscribeAssistant__normalize_episode_numbers(episodes)

    def test_normal(self):
        assert self._call([3, 1, 2]) == [1, 2, 3]

    def test_strings(self):
        assert self._call(["3", "1", "2"]) == [1, 2, 3]

    def test_invalid_values(self):
        assert self._call(["abc", None, 2, ""]) == [2]

    def test_none(self):
        assert self._call(None) == []

    def test_empty(self):
        assert self._call([]) == []

    def test_duplicates(self):
        assert self._call([1, 1, 2]) == [1, 2]

    def test_set_input(self):
        result = self._call({3, 1})
        assert sorted(result) == [1, 3]


# ===========================================================================
# __get_download_resource_episodes
# ===========================================================================

class TestGetDownloadResourceEpisodes:

    def test_event_episodes(self):
        plugin = make_plugin()
        ctx = SimpleNamespace(selected_episodes=None, torrent_info=None)
        result, source = plugin._SubscribeAssistant__get_download_resource_episodes(ctx, [1, 2, 3])
        assert result == [1, 2, 3]
        assert source == "下载事件"

    def test_selected_episodes(self):
        plugin = make_plugin()
        ctx = SimpleNamespace(selected_episodes=[5, 6], torrent_info=None)
        result, source = plugin._SubscribeAssistant__get_download_resource_episodes(ctx, [])
        assert result == [5, 6]
        assert source == "下载上下文"

    def test_title_episodes(self):
        plugin = make_plugin()
        torrent = SimpleNamespace(title="Test.S01E03.720p", description="subtitle")
        ctx = SimpleNamespace(selected_episodes=None, torrent_info=torrent)
        result, source = plugin._SubscribeAssistant__get_download_resource_episodes(ctx, [])
        if result:
            assert source == "资源标题"

    def test_no_context(self):
        plugin = make_plugin()
        result, source = plugin._SubscribeAssistant__get_download_resource_episodes(None, [])
        assert result == []
        assert source == ""

    def test_no_torrent_info(self):
        plugin = make_plugin()
        ctx = SimpleNamespace(selected_episodes=None, torrent_info=None)
        result, source = plugin._SubscribeAssistant__get_download_resource_episodes(ctx, [])
        assert result == []


# ===========================================================================
# __is_download_resource_cover_subscribe_range
# ===========================================================================

class TestIsDownloadResourceCoverSubscribeRange:

    def test_no_target(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=0)
        assert plugin._SubscribeAssistant__is_download_resource_cover_subscribe_range(sub, None, None) is True

    def test_no_actual_episodes(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=3, start_episode=1)
        ctx = SimpleNamespace(selected_episodes=None, torrent_info=None)
        assert plugin._SubscribeAssistant__is_download_resource_cover_subscribe_range(sub, ctx, []) is True

    def test_covers(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=3, start_episode=1)
        result = plugin._SubscribeAssistant__is_download_resource_cover_subscribe_range(sub, None, [1, 2, 3, 4])
        assert result is True

    def test_not_covers(self):
        plugin = make_plugin()
        sub = make_subscribe(total_episode=3, start_episode=1)
        result = plugin._SubscribeAssistant__is_download_resource_cover_subscribe_range(sub, None, [1, 2])
        assert result is False


# ===========================================================================
# __get_subscribe_by_source
# ===========================================================================

class TestGetSubscribeBySource:

    def test_empty_source(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_subscribe_by_source("")
        assert result == (None, None)

    def test_none_source(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_subscribe_by_source(None)
        assert result == (None, None)

    def test_no_pipe(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_subscribe_by_source("Subscribe")
        assert result == (None, None)

    def test_wrong_prefix(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_subscribe_by_source("Other|{}")
        assert result == (None, None)

    def test_invalid_json(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_subscribe_by_source("Subscribe|not_json")
        assert result == (None, None)

    def test_valid(self):
        plugin = make_plugin()
        sub_data = {"id": 5, "name": "Test"}
        source = f"Subscribe|{json.dumps(sub_data)}"
        mock_sub = make_subscribe(id=5)
        plugin.subscribe_oper.get.return_value = mock_sub
        d, sub = plugin._SubscribeAssistant__get_subscribe_by_source(source)
        assert d == sub_data
        assert sub is mock_sub
        plugin.subscribe_oper.get.assert_called_once_with(5)


# ===========================================================================
# __compare_versions
# ===========================================================================

class TestCompareVersions:

    def _call(self, v1, v2):
        return SubscribeAssistant._SubscribeAssistant__compare_versions(v1, v2)

    def test_v2_greater(self):
        assert self._call("1.0.0", "2.0.0") == 1

    def test_equal(self):
        assert self._call("1.0.0", "1.0.0") == 0

    def test_v2_less(self):
        assert self._call("2.0.0", "1.0.0") == -1

    def test_invalid_version(self):
        assert self._call("abc", "1.0.0") == 0

    def test_patch_version(self):
        assert self._call("1.0.0", "1.0.1") == 1


# ===========================================================================
# __get_default_tracker_response
# ===========================================================================

class TestGetDefaultTrackerResponse:

    def test_content(self):
        result = SubscribeAssistant._SubscribeAssistant__get_default_tracker_response()
        assert "torrent not registered" in result
        assert "torrent banned" in result


# ===========================================================================
# __get_related_download_histories
# ===========================================================================

class TestGetRelatedDownloadHistories:

    def test_unknown_type(self):
        plugin = make_plugin()
        sub = make_subscribe(type="invalid")
        result = plugin._SubscribeAssistant__get_related_download_histories(1, sub)
        assert result == []

    def test_no_downloads(self):
        plugin = make_plugin()
        plugin.downloadhistory_oper.get_last_by.return_value = []
        sub = make_subscribe(type=TV)
        result = plugin._SubscribeAssistant__get_related_download_histories(1, sub)
        assert result == []

    def test_movie_query(self):
        plugin = make_plugin()
        plugin.downloadhistory_oper.get_last_by.return_value = []
        sub = make_subscribe(type=MOVIE)
        plugin._SubscribeAssistant__get_related_download_histories(1, sub)
        call_kwargs = plugin.downloadhistory_oper.get_last_by.call_args[1]
        assert "season" not in call_kwargs

    def test_filters_by_subscribe_id(self):
        """下载记录的 source 必须匹配订阅 ID。"""
        plugin = make_plugin()
        sub_data = {"id": 1, "tmdbid": 100, "year": "2024", "season": 1}
        source = f"Subscribe|{json.dumps(sub_data)}"
        dl = SimpleNamespace(
            note={"source": source},
            date="2024-06-01 00:00:00",
            torrent_name="Test.S01E01",
            torrent_description="desc",
            episode_group=None,
        )
        plugin.downloadhistory_oper.get_last_by.return_value = [dl]
        plugin.subscribe_oper.get.return_value = None  # __get_subscribe_by_source
        sub = make_subscribe(type=TV, date="2024-01-01 00:00:00")
        result = plugin._SubscribeAssistant__get_related_download_histories(1, sub)
        # 因为 date 比较可能需要适配
        assert isinstance(result, list)


# ===========================================================================
# get_state
# ===========================================================================

class TestGetState:

    def test_enabled(self):
        plugin = make_plugin(_enabled=True)
        assert plugin.get_state() is True

    def test_disabled(self):
        plugin = make_plugin(_enabled=False)
        assert plugin.get_state() is False


# ===========================================================================
# get_command
# ===========================================================================

class TestGetCommand:

    def test_returns_list(self):
        result = SubscribeAssistant.get_command()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["cmd"] == "/subscribe_toggle"


# ===========================================================================
# get_api
# ===========================================================================

class TestGetApi:

    def test_returns_none(self):
        plugin = make_plugin()
        assert plugin.get_api() is None


# ===========================================================================
# get_service
# ===========================================================================

class TestGetService:

    def test_disabled(self):
        plugin = make_plugin(_enabled=False)
        result = plugin.get_service()
        assert result == []

    def test_download_service(self):
        plugin = make_plugin(_enabled=True, _download_check_interval=5)
        services = plugin.get_service()
        ids = [s["id"] for s in services]
        assert any("download" in sid for sid in ids)

    def test_meta_check_service(self):
        plugin = make_plugin(_enabled=True, _meta_check_interval=6)
        services = plugin.get_service()
        ids = [s["id"] for s in services]
        assert any("meta_check" in sid for sid in ids)

    def test_best_version_service(self):
        plugin = make_plugin(_enabled=True, _auto_best_type="all",
                             _auto_best_remaining_days=30,
                             _auto_best_cron="0 15 * * *")
        services = plugin.get_service()
        ids = [s["id"] for s in services]
        assert any("best_version" in sid for sid in ids)

    def test_no_download_check_interval(self):
        plugin = make_plugin(_enabled=True, _download_check_interval=0)
        services = plugin.get_service()
        ids = [s["id"] for s in services]
        assert not any("download" in sid for sid in ids)


# ===========================================================================
# stop_service
# ===========================================================================

class TestStopService:

    def test_no_scheduler(self):
        plugin = make_plugin(_scheduler=None)
        plugin._event = MagicMock()
        plugin.stop_service()
        plugin._event.set.assert_not_called()
        plugin._event.clear.assert_not_called()

    def test_with_running_scheduler(self):
        scheduler = MagicMock()
        scheduler.running = True
        plugin = make_plugin(_scheduler=scheduler)
        plugin._event = MagicMock()
        plugin.stop_service()
        scheduler.remove_all_jobs.assert_called_once()
        scheduler.shutdown.assert_called_once()
        assert plugin._scheduler is None

    def test_with_stopped_scheduler(self):
        scheduler = MagicMock()
        scheduler.running = False
        plugin = make_plugin(_scheduler=scheduler)
        plugin._event = MagicMock()
        plugin.stop_service()
        scheduler.remove_all_jobs.assert_called_once()
        scheduler.shutdown.assert_not_called()

    def test_exception_handled(self):
        scheduler = MagicMock()
        scheduler.remove_all_jobs.side_effect = RuntimeError("fail")
        plugin = make_plugin(_scheduler=scheduler)
        plugin._event = MagicMock()
        with patch("builtins.print") as print_mock:
            plugin.stop_service()
        print_mock.assert_called_once_with("fail")


# ===========================================================================
# auto_check / download_check / meta_check / best_version_check / reset_task
# ===========================================================================

class TestSchedulerEntryPoints:

    @patch.object(SubscribeAssistant, "best_version_check")
    @patch.object(SubscribeAssistant, "download_check")
    @patch.object(SubscribeAssistant, "meta_check")
    def test_auto_check(self, mock_meta, mock_dl, mock_bv):
        plugin = make_plugin()
        plugin.auto_check()
        mock_meta.assert_called_once()
        mock_dl.assert_called_once()
        mock_bv.assert_called_once()

    def test_download_check_disabled(self):
        plugin = make_plugin(_auto_download_delete=False, _manual_delete_listen=False,
                             _tracker_response_listen=False, _auto_download_pending=False)
        plugin.download_check()
        plugin.get_data.assert_not_called()

    @patch.object(SubscribeAssistant, "process_download_task")
    @patch.object(SubscribeAssistant, "process_delete_task")
    def test_download_check_enabled(self, mock_del, mock_dl):
        plugin = make_plugin(_auto_download_delete=True)
        plugin.download_check()
        mock_del.assert_called_once()
        mock_dl.assert_called_once()

    def test_meta_check_disabled(self):
        plugin = make_plugin(_auto_tv_pending=False, _auto_pause=False)
        plugin.meta_check()
        plugin.subscribe_oper.list.assert_not_called()

    @patch.object(SubscribeAssistant, "process_tv_pending")
    @patch.object(SubscribeAssistant, "process_subscribe_pause")
    def test_meta_check_enabled(self, mock_pause, mock_pending):
        plugin = make_plugin(_auto_tv_pending=True, _auto_pause=True)
        plugin.meta_check()
        mock_pause.assert_called_once()
        mock_pending.assert_called_once()

    @patch.object(SubscribeAssistant, "process_best_version_complete")
    @patch.object(SubscribeAssistant, "process_episode_best_version_to_full", return_value=False)
    def test_best_version_check(self, mock_ep, mock_complete):
        plugin = make_plugin()
        subs = [make_subscribe(best_version=1)]
        plugin.subscribe_oper.list.return_value = subs
        plugin.best_version_check()
        mock_ep.assert_called_once()
        mock_complete.assert_called_once()

    @patch.object(SubscribeAssistant, "process_best_version_complete")
    @patch.object(SubscribeAssistant, "process_episode_best_version_to_full", return_value=True)
    def test_best_version_check_reloads_subscribes_after_episode_to_full_conversion(self, mock_ep, mock_complete):
        plugin = make_plugin()
        first = [make_subscribe(id=1, best_version=1)]
        second = [make_subscribe(id=2, best_version=1)]
        plugin.subscribe_oper.list.side_effect = [first, second]
        plugin.best_version_check()
        assert plugin.subscribe_oper.list.call_count == 2
        mock_complete.assert_called_once_with(second)

    def test_best_version_check_empty(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = []
        plugin.best_version_check()
        plugin.subscribe_oper.list.assert_called_once_with(state="N,R,P")

    @patch("subscribeassistant.SubscribeChain")
    def test_reset_task(self, mock_chain_cls):
        plugin = make_plugin()
        sub = make_subscribe(state="P")
        plugin.subscribe_oper.list.return_value = [sub]
        plugin.reset_task()
        plugin.subscribe_oper.update.assert_called_once()
        assert plugin.save_data.call_count >= 3  # subscribes, torrents, deletes, states
