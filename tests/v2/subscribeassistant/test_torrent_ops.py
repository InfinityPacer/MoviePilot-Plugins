"""
SubscribeAssistant 种子操作、整理/删除历史、锁包装器单测。

覆盖业务域：
- 种子查询/删除：__get_torrents / __delete_torrents / __get_torrent_tags / __get_delete_excluded_tags
- 种子信息提取：__get_torrent_info (QB + TR) / __get_torrent_completion_status / __get_torrent_progress_percent
- 下载器服务：__get_downloader_service
- 整理/历史清理：__handle_resource_download_history_clear / __clear_transfer_src_histories /
  __handle_transfer_intercept_history_clear / __clear_transfer_dest_histories /
  __handle_transfer_complete_remove_torrent
- 锁包装器：__with_lock_and_update_subscribe_tasks / __with_lock_and_update_torrent_tasks /
  __with_lock_and_update_delete_tasks
- 辅助：__update_or_add_delete_tasks / __clean_invalid_torrents / __get_torrent_desc
"""
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType, NotificationType

from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def make_plugin(**overrides) -> SubscribeAssistant:
    """构造绕过 __init__ 的插件实例，按需设置测试属性。"""
    plugin = object.__new__(SubscribeAssistant)
    plugin.downloader_helper = MagicMock()
    plugin.subscribe_oper = MagicMock()
    plugin.downloadhistory_oper = MagicMock()
    plugin.transferhistory_oper = MagicMock()
    plugin.tmdb_chain = MagicMock()
    plugin._notify = False
    plugin._delete_exclude_tags = ""
    plugin._auto_best_clear_history_types = set()
    plugin._auto_download_delete = False
    plugin._manual_delete_listen = False
    plugin._tracker_response_listen = False
    plugin._auto_download_pending = False
    plugin._timeout_history_cleanup = None
    plugin._auto_search_when_delete = False
    plugin._download_timeout = 3
    plugin._download_timeout_progress_threshold = 5
    plugin._download_timeout_retry_limit = 3
    plugin._download_timeout_ignore_hours = 48
    plugin.get_data = MagicMock(return_value={})
    plugin.save_data = MagicMock()
    plugin.post_message = MagicMock()
    plugin.update_config = MagicMock()
    for k, v in overrides.items():
        setattr(plugin, k, v)
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    """构造订阅替身。"""
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, imdbid=None, tvdbid=None, doubanid=None, bangumiid=None,
        best_version=0, best_version_full=0, start_episode=1, total_episode=12,
        lack_episode=0, state="R", manual_total_episode=0,
        note=[], current_priority=0, episode_priority={},
        backdrop="http://img/original/bg.jpg", poster="http://img/original/poster.jpg",
        date="2024-01-01 00:00:00", last_update="2024-06-01 00:00:00",
        username="admin",
    )
    base.update(kwargs)
    ns = SimpleNamespace(**base)
    if not hasattr(ns, "to_dict"):
        ns.to_dict = lambda: {k: getattr(ns, k) for k in base}
    return ns


# ===========================================================================
# __get_torrents
# ===========================================================================

class TestGetTorrents:

    def _call(self, downloader, torrent_hashes=None):
        return SubscribeAssistant._SubscribeAssistant__get_torrents(downloader, torrent_hashes)

    def test_none_downloader(self):
        assert self._call(None) is None

    def test_error_returns_none(self):
        dl = MagicMock()
        dl.get_torrents.return_value = (None, True)
        assert self._call(dl, "hash1") is None

    def test_single_hash_string(self):
        """传入单个字符串 hash，返回单个种子。"""
        dl = MagicMock()
        t = {"hash": "h1", "name": "test"}
        dl.get_torrents.return_value = ([t], None)
        result = self._call(dl, "h1")
        assert result == t
        dl.get_torrents.assert_called_once_with(ids=["h1"])

    def test_single_hash_empty_list(self):
        """传入单个字符串 hash，但返回空列表。"""
        dl = MagicMock()
        dl.get_torrents.return_value = ([], None)
        result = self._call(dl, "h1")
        assert result is None

    def test_multiple_hashes(self):
        dl = MagicMock()
        torrents = [{"hash": "h1"}, {"hash": "h2"}]
        dl.get_torrents.return_value = (torrents, None)
        result = self._call(dl, ["h1", "h2"])
        assert result == torrents

    def test_no_hashes(self):
        dl = MagicMock()
        torrents = [{"hash": "h1"}]
        dl.get_torrents.return_value = (torrents, None)
        result = self._call(dl)
        assert result == torrents


# ===========================================================================
# __delete_torrents
# ===========================================================================

class TestDeleteTorrents:

    def _call(self, downloader, torrent_hashes=None):
        return SubscribeAssistant._SubscribeAssistant__delete_torrents(downloader, torrent_hashes)

    def test_none_downloader(self):
        assert self._call(None) is False

    def test_delete_fails(self):
        dl = MagicMock()
        dl.delete_torrents.return_value = False
        assert self._call(dl, "h1") is False

    def test_delete_success_single_hash(self):
        dl = MagicMock()
        dl.delete_torrents.return_value = True
        assert self._call(dl, "h1") is True
        dl.delete_torrents.assert_called_once_with(delete_file=True, ids=["h1"])

    def test_delete_success_list_hashes(self):
        dl = MagicMock()
        dl.delete_torrents.return_value = True
        assert self._call(dl, ["h1", "h2"]) is True
        dl.delete_torrents.assert_called_once_with(delete_file=True, ids=["h1", "h2"])


# ===========================================================================
# __get_torrent_tags
# ===========================================================================

class TestGetTorrentTags:

    def _call(self, torrent, dl_type):
        return SubscribeAssistant._SubscribeAssistant__get_torrent_tags(torrent, dl_type)

    def test_qb_tags(self):
        torrent = {"tags": "tag1, tag2, tag3"}
        result = self._call(torrent, "qbittorrent")
        assert set(result) == {"tag1", "tag2", "tag3"}

    def test_qb_empty_tags(self):
        torrent = {"tags": ""}
        result = self._call(torrent, "qbittorrent")
        assert result == []

    def test_tr_tags(self):
        torrent = SimpleNamespace(labels=["a", "b"])
        result = self._call(torrent, "transmission")
        assert set(result) == {"a", "b"}

    def test_tr_no_labels(self):
        torrent = SimpleNamespace(labels=[])
        result = self._call(torrent, "transmission")
        assert result == []

    def test_exception_returns_empty(self):
        result = self._call(None, "qbittorrent")
        assert result == []


# ===========================================================================
# __get_delete_excluded_tags
# ===========================================================================

class TestGetDeleteExcludedTags:

    def test_no_config(self):
        plugin = make_plugin(_delete_exclude_tags="")
        result = plugin._SubscribeAssistant__get_delete_excluded_tags({"tags": "H&R"}, "qbittorrent")
        assert result == set()

    def test_no_matching_tags(self):
        plugin = make_plugin(_delete_exclude_tags="H&R, VIP")
        torrent = {"tags": "free, upload"}
        result = plugin._SubscribeAssistant__get_delete_excluded_tags(torrent, "qbittorrent")
        assert result == set()

    def test_matching_tags(self):
        plugin = make_plugin(_delete_exclude_tags="H&R, VIP")
        torrent = {"tags": "H&R, download"}
        result = plugin._SubscribeAssistant__get_delete_excluded_tags(torrent, "qbittorrent")
        assert result == {"H&R"}

    def test_torrent_no_tags(self):
        plugin = make_plugin(_delete_exclude_tags="H&R")
        torrent = {"tags": ""}
        result = plugin._SubscribeAssistant__get_delete_excluded_tags(torrent, "qbittorrent")
        assert result == set()


class TestCompareTorrentInfoAndTask:
    """种子信息与任务记录匹配规则。"""

    def test_compare_torrent_info_and_task_matches_exact_identity_fields(self):
        torrent_info = SimpleNamespace(enclosure="magnet:?xt=1", page_url="http://page",
                                       site=1, site_name="站点", title="标题", description="副标题")
        assert SubscribeAssistant._SubscribeAssistant__compare_torrent_info_and_task(
            torrent_info, {"enclosure": "magnet:?xt=1"})
        assert SubscribeAssistant._SubscribeAssistant__compare_torrent_info_and_task(
            torrent_info, {"page_url": "http://page"})

    def test_compare_torrent_info_and_task_supports_partial_title_match(self):
        torrent_info = SimpleNamespace(enclosure="https://example.com/torrent/abc?passkey=1", page_url="", site=1, site_name="站点",
                                       title="标题 S01E01", description="副标题")
        assert SubscribeAssistant._SubscribeAssistant__compare_torrent_info_and_task(
            torrent_info, {"enclosure": "https://example.com/torrent/abc"}, partial_match=True)

    def test_compare_torrent_info_and_task_returns_false_for_missing_or_different_values(self):
        torrent_info = SimpleNamespace(enclosure="", page_url="", site=1, site_name="站点",
                                       title="标题", description="副标题")
        assert not SubscribeAssistant._SubscribeAssistant__compare_torrent_info_and_task(None, {})
        assert not SubscribeAssistant._SubscribeAssistant__compare_torrent_info_and_task(torrent_info, {})
        assert not SubscribeAssistant._SubscribeAssistant__compare_torrent_info_and_task(
            torrent_info, {"site_id": 2, "title": "其他", "description": "其他"})


class TestHistoryClearWarning:
    """洗版清理保护告警和通知。"""

    def test_warn_history_clear_skipped_logs_only_when_notify_disabled(self):
        plugin = make_plugin(_notify=False)
        context = SimpleNamespace(torrent_info=SimpleNamespace(title="种子标题"))
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_target_episodes", return_value=[1, 2]), \
                patch.object(plugin, "_SubscribeAssistant__get_download_resource_episodes",
                             return_value=([1], "标题")), \
                patch.object(plugin, "_SubscribeAssistant__format_subscribe", return_value="测试剧 S01"), \
                patch.object(plugin, "_SubscribeAssistant__format_subscribe_desc",
                             return_value="测试剧 S01"), \
                patch.object(plugin, "_SubscribeAssistant__get_subscribe_image", return_value="img"):
            plugin._SubscribeAssistant__warn_history_clear_skipped(
                subscribe=make_subscribe(), context=context, episodes=[1], reason="范围不足")
        plugin.post_message.assert_not_called()

    def test_warn_history_clear_skipped_sends_notification_when_enabled(self):
        plugin = make_plugin(_notify=True)
        context = SimpleNamespace(torrent_info=SimpleNamespace(title="种子标题"))
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_target_episodes", return_value=[1, 2]), \
                patch.object(plugin, "_SubscribeAssistant__get_download_resource_episodes",
                             return_value=([1], "标题")), \
                patch.object(plugin, "_SubscribeAssistant__format_subscribe", return_value="测试剧 S01"), \
                patch.object(plugin, "_SubscribeAssistant__format_subscribe_desc",
                             return_value="测试剧 S01"), \
                patch.object(plugin, "_SubscribeAssistant__get_subscribe_image", return_value="img"):
            plugin._SubscribeAssistant__warn_history_clear_skipped(
                subscribe=make_subscribe(), context=context, episodes=[1], reason="范围不足")
        kwargs = plugin.post_message.call_args.kwargs
        assert "未覆盖目标范围" in kwargs["title"]
        assert "目标集数" in kwargs["text"]
        assert "种子标题" in kwargs["text"]


# ===========================================================================
# __get_torrent_info (QB)
# ===========================================================================

class TestGetTorrentInfoQB:

    def _call(self, torrent):
        return SubscribeAssistant._SubscribeAssistant__get_torrent_info(torrent, "qbittorrent")

    def _make_qb_torrent(self, **overrides):
        now = int(time.time())
        base = {
            "hash": "abc123",
            "name": "Test.Torrent",
            "added_on": now - 7200,
            "completion_on": now - 3600,
            "ratio": 1.5,
            "uploaded": 1024000,
            "last_activity": now - 600,
            "downloaded": 2048000,
            "total_size": 2048000,
            "size": 2048000,
            "tags": "test",
            "tracker": "https://tracker.example.com",
            "state": "stalledUP",
        }
        base.update(overrides)
        # trackers 属性
        tracker_obj = SimpleNamespace(tier=0, msg="OK")
        torrent = SimpleNamespace(**base, trackers=[tracker_obj])
        torrent.get = base.get
        return torrent

    def test_basic_fields(self):
        t = self._make_qb_torrent()
        info = self._call(t)
        assert info["hash"] == "abc123"
        assert info["title"] == "Test.Torrent"
        assert info["ratio"] == 1.5
        assert info["tags"] == "test"
        assert info["state"] == "stalledUP"
        assert info["tracker"] == "https://tracker.example.com"

    def test_negative_added_on(self):
        t = self._make_qb_torrent(added_on=-1)
        info = self._call(t)
        assert info["dltime"] == 0

    def test_no_added_on(self):
        t = self._make_qb_torrent(added_on=0)
        info = self._call(t)
        assert info["dltime"] == 0

    def test_negative_completion_on(self):
        t = self._make_qb_torrent(completion_on=-1)
        info = self._call(t)
        assert info["seeding_time"] == 0

    def test_negative_last_activity(self):
        t = self._make_qb_torrent(last_activity=-1)
        info = self._call(t)
        assert info["iatime"] == 0

    def test_tracker_responses(self):
        tracker1 = SimpleNamespace(tier=0, msg="OK")
        tracker2 = SimpleNamespace(tier=-1, msg="skip")
        tracker3 = SimpleNamespace(tier=1, msg="")
        t = self._make_qb_torrent()
        t.trackers = [tracker1, tracker2, tracker3]
        info = self._call(t)
        assert info["tracker_responses"] == ["OK"]

    def test_no_trackers(self):
        t = self._make_qb_torrent()
        t.trackers = None
        info = self._call(t)
        assert info["tracker_responses"] == []

    def test_avg_upspeed_no_dltime(self):
        """dltime=0 时 avg_upspeed 等于 uploaded。"""
        t = self._make_qb_torrent(added_on=0, uploaded=5000)
        info = self._call(t)
        assert info["avg_upspeed"] == 5000


# ===========================================================================
# __get_torrent_info (TR)
# ===========================================================================

class TestGetTorrentInfoTR:

    def _call(self, torrent):
        return SubscribeAssistant._SubscribeAssistant__get_torrent_info(torrent, "transmission")

    def _make_tr_torrent(self, **overrides):
        now = datetime.now()
        base = dict(
            hashString="tr_hash_1",
            name="TR.Test",
            date_done=now,
            date_added=now,
            date_active=now,
            total_size=4096000,
            progress=100,
            ratio=2.0,
            status="seeding",
            labels=["tag1"],
            tracker_stats=[],
            fields={"size_when_done": 4096000},
        )
        base.update(overrides)
        ns = SimpleNamespace(**base)
        ns.get = lambda key, default=None: getattr(ns, key, default)
        ns.size_when_done = base["fields"].get("size_when_done", base["total_size"])
        return ns

    def test_basic_fields(self):
        t = self._make_tr_torrent()
        info = self._call(t)
        assert info["hash"] == "tr_hash_1"
        assert info["title"] == "TR.Test"
        assert info["ratio"] == 2.0
        assert info["state"] == "seeding"

    def test_no_date_done(self):
        t = self._make_tr_torrent(date_done=None)
        info = self._call(t)
        assert info["seeding_time"] == 0

    def test_date_done_timestamp_lt_1(self):
        epoch = datetime(1970, 1, 1, 0, 0, 1)
        t = self._make_tr_torrent(date_done=epoch)
        info = self._call(t)
        assert info["seeding_time"] == 0

    def test_no_date_added(self):
        t = self._make_tr_torrent(date_added=None)
        info = self._call(t)
        assert info["dltime"] == 0

    def test_no_date_active(self):
        t = self._make_tr_torrent(date_active=None)
        info = self._call(t)
        assert info["iatime"] == 0

    def test_tracker_stats(self):
        stat = SimpleNamespace(tier=0, last_announce_result="OK")
        t = self._make_tr_torrent(tracker_stats=[stat])
        info = self._call(t)
        assert info["tracker_responses"] == ["OK"]

    def test_tracker_stats_none(self):
        t = self._make_tr_torrent(tracker_stats=None)
        info = self._call(t)
        assert info["tracker_responses"] == []

    def test_size_when_done_missing(self):
        """fields 不包含 size_when_done 时回退到 total_size。"""
        t = self._make_tr_torrent(fields={})
        t.size_when_done = t.total_size
        info = self._call(t)
        assert info["target_size"] == info["total_size"]

    def test_avg_upspeed_no_dltime(self):
        t = self._make_tr_torrent(date_added=None)
        info = self._call(t)
        assert info["avg_upspeed"] == info["uploaded"]


# ===========================================================================
# __get_torrent_completion_status
# ===========================================================================

class TestGetTorrentCompletionStatus:

    def _call(self, torrent_info):
        return SubscribeAssistant._SubscribeAssistant__get_torrent_completion_status(torrent_info)

    def test_none_input(self):
        assert self._call(None) == (False, -1)

    def test_empty_dict(self):
        assert self._call({}) == (False, -1)

    def test_seeding_state(self):
        assert self._call({"state": "seeding"}) == (True, 0)

    def test_seed_pending_state(self):
        assert self._call({"state": "seed_pending"}) == (True, 0)

    def test_has_seeding_time(self):
        assert self._call({"state": "downloading", "seeding_time": 100}) == (True, 0)

    def test_downloaded_gte_target(self):
        info = {"state": "downloading", "seeding_time": 0, "downloaded": 1000, "target_size": 1000}
        assert self._call(info) == (True, 0)

    def test_not_completed(self):
        info = {"state": "downloading", "seeding_time": 0, "downloaded": 500, "target_size": 1000, "dltime": 3600}
        assert self._call(info) == (False, 3600)


# ===========================================================================
# __get_torrent_progress_percent
# ===========================================================================

class TestGetTorrentProgressPercent:

    def _call(self, torrent_info):
        return SubscribeAssistant._SubscribeAssistant__get_torrent_progress_percent(torrent_info)

    def test_none_input(self):
        assert self._call(None) == 0

    def test_empty_dict(self):
        assert self._call({}) == 0

    def test_zero_target_size(self):
        assert self._call({"downloaded": 100, "target_size": 0}) == 0

    def test_normal_progress(self):
        result = self._call({"downloaded": 500, "target_size": 1000})
        assert result == 50.0

    def test_progress_capped_at_100(self):
        result = self._call({"downloaded": 2000, "target_size": 1000})
        assert result == 100.0

    def test_negative_target_size(self):
        result = self._call({"downloaded": 100, "target_size": -100})
        assert result == 0

    def test_type_error_in_values(self):
        result = self._call({"downloaded": "abc", "target_size": 1000})
        assert result == 0

    def test_fallback_to_total_size(self):
        result = self._call({"downloaded": 250, "total_size": 1000})
        assert result == 25.0


# ===========================================================================
# __get_downloader_service
# ===========================================================================

class TestGetDownloaderService:

    def test_service_found(self):
        plugin = make_plugin()
        service = SimpleNamespace(name="qb1", type="qbittorrent", instance=MagicMock())
        plugin.downloader_helper.get_service.return_value = service
        result = plugin._SubscribeAssistant__get_downloader_service("qb1")
        assert result is service

    def test_service_not_found(self):
        plugin = make_plugin()
        plugin.downloader_helper.get_service.return_value = None
        result = plugin._SubscribeAssistant__get_downloader_service("qb_missing")
        assert result is None


# ===========================================================================
# __handle_transfer_complete_remove_torrent
# ===========================================================================

class TestHandleTransferCompleteRemoveTorrent:

    def test_no_transfer_info(self):
        plugin = make_plugin()
        plugin._SubscribeAssistant__handle_transfer_complete_remove_torrent(None, "qb", "h1")
        plugin.save_data.assert_not_called()

    def test_non_move_transfer(self):
        plugin = make_plugin()
        info = SimpleNamespace(transfer_type="copy")
        plugin._SubscribeAssistant__handle_transfer_complete_remove_torrent(info, "qb", "h1")
        plugin.save_data.assert_not_called()

    def test_no_downloader(self):
        plugin = make_plugin()
        info = SimpleNamespace(transfer_type="move")
        plugin._SubscribeAssistant__handle_transfer_complete_remove_torrent(info, "", "h1")
        plugin.save_data.assert_not_called()

    def test_hash_not_in_tasks(self):
        plugin = make_plugin()
        plugin.get_data = MagicMock(side_effect=lambda key: {"subscribes": {}, "torrents": {}}.get(key, {}))
        info = SimpleNamespace(transfer_type="move")
        plugin._SubscribeAssistant__handle_transfer_complete_remove_torrent(info, "qb", "missing_hash")
        plugin.save_data.assert_not_called()

    def test_hash_cleaned(self):
        plugin = make_plugin()
        torrent_tasks = {
            "h1": {"subscribe_id": 1, "title": "T1", "description": "D1"}
        }
        subscribe_tasks = {
            "1": {"id": 1, "name": "测试", "torrent_tasks": [{"hash": "h1"}]}
        }
        plugin.get_data = MagicMock(side_effect=lambda key: {
            "subscribes": subscribe_tasks,
            "torrents": torrent_tasks,
        }.get(key, {}))
        info = SimpleNamespace(transfer_type="move")
        plugin._SubscribeAssistant__handle_transfer_complete_remove_torrent(info, "qb", "h1")
        assert "h1" not in torrent_tasks


# ===========================================================================
# __handle_transfer_intercept_history_clear
# ===========================================================================

class TestHandleTransferInterceptHistoryClear:

    def test_no_mediainfo(self):
        plugin = make_plugin()
        plugin._SubscribeAssistant__handle_transfer_intercept_history_clear(None, Path("/target"))
        plugin.save_data.assert_not_called()

    def test_no_tmdb_id(self):
        plugin = make_plugin()
        mediainfo = SimpleNamespace(tmdb_id=None)
        plugin.get_data = MagicMock(return_value={})
        plugin._SubscribeAssistant__handle_transfer_intercept_history_clear(mediainfo, Path("/target"))
        plugin.save_data.assert_not_called()

    def test_no_matching_task(self):
        plugin = make_plugin()
        mediainfo = SimpleNamespace(tmdb_id=100)
        plugin.get_data = MagicMock(return_value={})
        plugin._SubscribeAssistant__handle_transfer_intercept_history_clear(mediainfo, Path("/target"))
        plugin.save_data.assert_not_called()


# ===========================================================================
# __clear_transfer_dest_histories
# ===========================================================================

class TestClearTransferDestHistories:

    def test_empty_task(self):
        plugin = make_plugin()
        assert plugin._SubscribeAssistant__clear_transfer_dest_histories(
            None, SimpleNamespace(tmdb_id=100), Path("/t")) is False

    def test_no_histories(self):
        plugin = make_plugin()
        task = {"histories": None}
        assert plugin._SubscribeAssistant__clear_transfer_dest_histories(
            task, SimpleNamespace(tmdb_id=100), Path("/t")) is True

    def test_empty_histories_list(self):
        plugin = make_plugin()
        task = {"histories": []}
        assert plugin._SubscribeAssistant__clear_transfer_dest_histories(
            task, SimpleNamespace(tmdb_id=100), Path("/t")) is True

    @patch("subscribeassistant.StorageChain")
    def test_with_histories(self, mock_chain_cls):
        plugin = make_plugin(_notify=True)
        mock_chain = MagicMock()
        mock_chain.delete_media_file.return_value = True
        mock_chain_cls.return_value = mock_chain
        task = {
            "histories": [
                {"dest": "/path/a.mkv", "dest_fileitem": {"path": "/path/a.mkv", "type": "file", "storage": "local"}},
            ],
            "subscribe_desc": "测试",
            "subscribe_image": "img",
        }
        result = plugin._SubscribeAssistant__clear_transfer_dest_histories(
            task, SimpleNamespace(tmdb_id=100), Path("/t"))
        assert result is True
        plugin.post_message.assert_called_once()


# ===========================================================================
# __update_or_add_delete_tasks
# ===========================================================================

class TestUpdateOrAddDeleteTasks:

    def _call(self, delete_tasks, torrent_task, reason_type="timeout"):
        return SubscribeAssistant._SubscribeAssistant__update_or_add_delete_tasks(
            delete_tasks, torrent_task, reason_type)

    def test_none_torrent_task(self):
        tasks = {}
        self._call(tasks, None)
        assert tasks == {}

    def test_adds_task(self):
        tasks = {}
        torrent_task = {"hash": "h1", "title": "T1"}
        self._call(tasks, torrent_task, "tracker")
        assert "h1" in tasks
        assert tasks["h1"]["delete_type"] == "tracker"
        assert "delete_time" in tasks["h1"]


# ===========================================================================
# __clean_invalid_torrents
# ===========================================================================

class TestCleanInvalidTorrents:

    def test_removes_from_both(self):
        plugin = make_plugin()
        torrent_tasks = {
            "h1": {"subscribe_id": 1, "title": "T1", "description": "D1"},
            "h2": {"subscribe_id": 2, "title": "T2", "description": "D2"},
        }
        subscribe_tasks = {
            "1": {"torrent_tasks": [{"hash": "h1"}, {"hash": "h3"}]},
            "2": {"torrent_tasks": [{"hash": "h2"}]},
        }
        plugin._SubscribeAssistant__clean_invalid_torrents(["h1"], subscribe_tasks, torrent_tasks)
        assert "h1" not in torrent_tasks
        assert "h2" in torrent_tasks
        assert len(subscribe_tasks["1"]["torrent_tasks"]) == 1
        assert subscribe_tasks["1"]["torrent_tasks"][0]["hash"] == "h3"

    def test_hash_not_in_torrent_tasks(self):
        plugin = make_plugin()
        torrent_tasks = {}
        subscribe_tasks = {"1": {"torrent_tasks": []}}
        plugin._SubscribeAssistant__clean_invalid_torrents(["h_missing"], subscribe_tasks, torrent_tasks)
        assert torrent_tasks == {}


# ===========================================================================
# __with_lock_and_update_subscribe_tasks
# ===========================================================================

class TestWithLockAndUpdateSubscribeTasks:

    def test_calls_method_and_saves(self):
        plugin = make_plugin()
        data = {"1": {"id": 1}}
        plugin.get_data = MagicMock(return_value=data)

        method = MagicMock()
        plugin._SubscribeAssistant__with_lock_and_update_subscribe_tasks(method, "extra_arg", key="val")
        method.assert_called_once_with(data, "extra_arg", key="val")
        plugin.save_data.assert_called_once_with(key="subscribes", value=data)

    def test_exception_caught(self):
        plugin = make_plugin()
        plugin.get_data = MagicMock(return_value={})
        method = MagicMock(side_effect=RuntimeError("boom"))
        method.__name__ = "test_method"
        with patch("subscribeassistant.logger.error") as error:
            plugin._SubscribeAssistant__with_lock_and_update_subscribe_tasks(method)
        method.assert_called_once_with({})
        plugin.save_data.assert_not_called()
        error.assert_called_once()


# ===========================================================================
# __with_lock_and_update_torrent_tasks
# ===========================================================================

class TestWithLockAndUpdateTorrentTasks:

    def test_calls_method_and_saves(self):
        plugin = make_plugin()
        data = {"h1": {"title": "T"}}
        plugin.get_data = MagicMock(return_value=data)
        method = MagicMock()
        plugin._SubscribeAssistant__with_lock_and_update_torrent_tasks(method)
        method.assert_called_once_with(data)
        plugin.save_data.assert_called_once_with(key="torrents", value=data)

    def test_exception_caught(self):
        plugin = make_plugin()
        plugin.get_data = MagicMock(return_value={})
        method = MagicMock(side_effect=ValueError("bad"))
        method.__name__ = "bad_method"
        with patch("subscribeassistant.logger.error") as error:
            plugin._SubscribeAssistant__with_lock_and_update_torrent_tasks(method)
        method.assert_called_once_with({})
        plugin.save_data.assert_not_called()
        error.assert_called_once()


# ===========================================================================
# __with_lock_and_update_delete_tasks
# ===========================================================================

class TestWithLockAndUpdateDeleteTasks:

    def test_calls_method_and_saves(self):
        plugin = make_plugin()
        data = {}
        plugin.get_data = MagicMock(return_value=data)
        method = MagicMock()
        plugin._SubscribeAssistant__with_lock_and_update_delete_tasks(method, torrent_task={"hash": "h1"})
        method.assert_called_once_with(data, torrent_task={"hash": "h1"})
        plugin.save_data.assert_called_once_with(key="deletes", value=data)

    def test_exception_caught(self):
        plugin = make_plugin()
        plugin.get_data = MagicMock(return_value={})
        method = MagicMock(side_effect=RuntimeError("boom"))
        method.__name__ = "delete_method"
        plugin._SubscribeAssistant__with_lock_and_update_delete_tasks(method)
        plugin.save_data.assert_not_called()


# ===========================================================================
# __get_torrent_desc
# ===========================================================================

class TestGetTorrentDesc:

    def test_normal(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__get_torrent_desc(
            "abc123", {"title": "Test.Torrent.S01E01", "description": "subtitle"})
        assert "abc123" in result
        assert "Test.Torrent" in result


# ===========================================================================
# __handle_resource_download_history_clear
# ===========================================================================

class TestHandleResourceDownloadHistoryClear:

    def test_not_best_version(self):
        """非洗版订阅跳过。"""
        plugin = make_plugin()
        sub = make_subscribe(best_version=0)
        plugin._SubscribeAssistant__handle_resource_download_history_clear(sub)
        plugin.transferhistory_oper.get_by.assert_not_called()

    def test_unknown_type_skips(self):
        plugin = make_plugin(_auto_best_clear_history_types={MediaType.TV})
        sub = make_subscribe(best_version=1, type="invalid")
        plugin._SubscribeAssistant__handle_resource_download_history_clear(sub)
        plugin.transferhistory_oper.get_by.assert_not_called()

    def test_type_not_in_clear_types(self):
        plugin = make_plugin(_auto_best_clear_history_types={MediaType.MOVIE})
        sub = make_subscribe(best_version=1, type=TV)
        plugin._SubscribeAssistant__handle_resource_download_history_clear(sub)
        plugin.transferhistory_oper.get_by.assert_not_called()

    def test_episode_best_version_skips(self):
        """分集洗版跳过整季清理。"""
        plugin = make_plugin(_auto_best_clear_history_types={MediaType.TV})
        sub = make_subscribe(best_version=1, best_version_full=0, type=TV)
        plugin._SubscribeAssistant__handle_resource_download_history_clear(sub)
        plugin.transferhistory_oper.get_by.assert_not_called()

    def test_full_tv_best_version_warns_and_skips_when_resource_does_not_cover_range(self):
        plugin = make_plugin(_auto_best_clear_history_types={MediaType.TV})
        sub = make_subscribe(best_version=1, best_version_full=1, type=TV)
        context = SimpleNamespace(torrent_info=SimpleNamespace(title="S01E01"))
        with patch.object(plugin, "_SubscribeAssistant__is_download_resource_cover_subscribe_range",
                          return_value=False), \
                patch.object(plugin, "_SubscribeAssistant__warn_history_clear_skipped") as warn:
            plugin._SubscribeAssistant__handle_resource_download_history_clear(sub, context=context, episodes=[1])
        warn.assert_called_once_with(subscribe=sub, context=context, episodes=[1],
                                     reason="当前洗版资源未覆盖订阅剧集范围")
        plugin.transferhistory_oper.get_by.assert_not_called()

    def test_full_tv_best_version_records_matching_histories_for_cleanup(self):
        plugin = make_plugin(_auto_best_clear_history_types={MediaType.TV})
        sub = make_subscribe(best_version=1, best_version_full=1, type=TV)
        history = SimpleNamespace(id=1)
        plugin.transferhistory_oper.get_by.return_value = [history]
        tasks = {}
        with patch.object(plugin, "_SubscribeAssistant__is_download_resource_cover_subscribe_range",
                          return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__get_subscribe_meta",
                             return_value=SimpleNamespace(season=1)), \
                patch.object(plugin, "_SubscribeAssistant__get_data", return_value=tasks) as get_data, \
                patch.object(plugin, "_SubscribeAssistant__clear_transfer_src_histories") as clear_histories, \
                patch.object(plugin, "_SubscribeAssistant__save_data") as save_data, \
                patch("subscribeassistant.time.sleep"):
            plugin._SubscribeAssistant__handle_resource_download_history_clear(
                sub, context=SimpleNamespace(torrent_info=SimpleNamespace(title="全集")), episodes=[1, 2])
        plugin.transferhistory_oper.get_by.assert_called_once_with(tmdbid=100, mtype=TV, season=1)
        get_data.assert_called_once_with(key="best_version_clear_histories")
        clear_histories.assert_called_once_with(tasks=tasks, subscribe=sub, histories=[history])
        save_data.assert_called_once_with(key="best_version_clear_histories", value=tasks)

    def test_movie_best_version_records_matching_histories_for_cleanup(self):
        plugin = make_plugin(_auto_best_clear_history_types={MediaType.MOVIE})
        sub = make_subscribe(best_version=1, type=MOVIE)
        history = SimpleNamespace(id=1)
        plugin.transferhistory_oper.get_by.return_value = [history]
        with patch.object(plugin, "_SubscribeAssistant__get_data", return_value={}), \
                patch.object(plugin, "_SubscribeAssistant__clear_transfer_src_histories") as clear_histories, \
                patch.object(plugin, "_SubscribeAssistant__save_data"), \
                patch("subscribeassistant.time.sleep"):
            plugin._SubscribeAssistant__handle_resource_download_history_clear(sub)
        plugin.transferhistory_oper.get_by.assert_called_once_with(tmdbid=100, mtype=MOVIE)
        clear_histories.assert_called_once()


# ===========================================================================
# __clear_transfer_src_histories
# ===========================================================================

class TestClearTransferSrcHistories:

    def test_no_tmdbid(self):
        plugin = make_plugin()
        sub = make_subscribe(tmdbid=None)
        tasks = {}
        plugin._SubscribeAssistant__clear_transfer_src_histories(tasks, sub, [])
        assert tasks == {}

    def test_no_histories(self):
        plugin = make_plugin()
        sub = make_subscribe(tmdbid=100)
        tasks = {}
        plugin._SubscribeAssistant__clear_transfer_src_histories(tasks, sub, [])
        assert tasks == {}

    @patch("subscribeassistant.StorageChain")
    @patch("subscribeassistant.eventmanager")
    def test_with_histories(self, mock_em, mock_chain_cls):
        plugin = make_plugin(_notify=True)
        mock_chain = MagicMock()
        mock_chain.delete_media_file.return_value = True
        mock_chain_cls.return_value = mock_chain

        history = SimpleNamespace(
            id=10, src="/src/file.mkv", download_hash="dl_h1",
            src_fileitem={"path": "/src/file.mkv", "type": "file", "storage": "local"},
            to_dict=lambda: {"src": "/src/file.mkv"},
        )
        plugin.transferhistory_oper.delete = MagicMock()

        tasks = {}
        sub = make_subscribe(tmdbid=100)
        plugin._SubscribeAssistant__clear_transfer_src_histories(tasks, sub, [history])

        assert 100 in tasks
        plugin.transferhistory_oper.delete.assert_called_once_with(10)
        plugin.post_message.assert_called_once()
