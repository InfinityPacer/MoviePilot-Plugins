"""
SubscribeAssistant 洗版编排单测。

覆盖业务域：
- 分集转全集：process_episode_best_version_to_full
- 洗版完成检查：process_best_version_complete
- 自动洗版：process_best_version
- 媒体库探测回填：__detect_existing_episodes_for_subscribe / __backfill_best_version_episode_priority /
  __backfill_all_existing_best_version
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    plugin._notify = False
    plugin._auto_best_types = set()
    plugin._auto_best_type = "no"
    plugin._auto_best_clear_history_types = set()
    plugin._auto_best_episode_to_full = False
    plugin._auto_best_backfill_priority = False
    plugin._auto_best_remaining_days = None
    plugin._auto_download_pending = False
    plugin._download_pending_hash_grace_seconds = 300
    plugin.plugin_name = "订阅助手"
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


def make_mediainfo(**kwargs) -> SimpleNamespace:
    base = dict(
        type=MediaType.TV, tmdb_id=100, title="测试剧", title_year="测试剧 (2024)",
        season_info=[], release_date="2024-06-01", vote_average=8.0,
        status="Returning Series", douban_id=None,
    )
    base.update(kwargs)
    ns = SimpleNamespace(**base)
    ns.get_message_image = lambda: ""
    ns.to_dict = lambda: base
    return ns


# ===========================================================================
# process_episode_best_version_to_full
# ===========================================================================

class TestProcessEpisodeBestVersionToFull:

    def test_disabled(self):
        plugin = make_plugin(_auto_best_episode_to_full=False)
        assert plugin.process_episode_best_version_to_full([make_subscribe()]) is False

    def test_empty_subscribes(self):
        plugin = make_plugin(_auto_best_episode_to_full=True)
        assert plugin.process_episode_best_version_to_full([]) is False

    def test_non_episode_best_version_skipped(self):
        """非分集洗版订阅跳过。"""
        plugin = make_plugin(_auto_best_episode_to_full=True)
        sub = make_subscribe(best_version=0)
        assert plugin.process_episode_best_version_to_full([sub]) is False

    def test_full_best_version_skipped(self):
        plugin = make_plugin(_auto_best_episode_to_full=True)
        sub = make_subscribe(best_version=1, best_version_full=1)
        assert plugin.process_episode_best_version_to_full([sub]) is False

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__is_episode_best_version_target_ready",
                  return_value=False)
    def test_target_not_ready(self, mock_ready):
        plugin = make_plugin(_auto_best_episode_to_full=True)
        sub = make_subscribe(best_version=1, best_version_full=0)
        assert plugin.process_episode_best_version_to_full([sub]) is False

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__convert_episode_best_version_to_full",
                  return_value=True)
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__is_episode_best_version_target_ready",
                  return_value=True)
    def test_conversion_triggered(self, mock_ready, mock_convert):
        plugin = make_plugin(_auto_best_episode_to_full=True)
        sub = make_subscribe(best_version=1, best_version_full=0)
        result = plugin.process_episode_best_version_to_full([sub])
        assert result is True
        mock_convert.assert_called_once()

    def test_convert_episode_best_version_returns_false_when_recognition_failed(self):
        plugin = make_plugin()
        sub = make_subscribe(best_version=1, best_version_full=0)
        with patch.object(plugin, "_SubscribeAssistant__recognize_media", return_value=None):
            assert not plugin._SubscribeAssistant__convert_episode_best_version_to_full(sub)

    def test_convert_episode_best_version_stops_when_original_delete_fails(self):
        plugin = make_plugin(_notify=True)
        plugin.subscribe_oper.add_history.side_effect = RuntimeError("delete failed")
        sub = make_subscribe(best_version=1, best_version_full=0)
        mediainfo = make_mediainfo()
        with patch.object(plugin, "_SubscribeAssistant__recognize_media", return_value=mediainfo), \
                patch.object(plugin, "_SubscribeAssistant__format_subscribe_desc", return_value="测试剧 S01"), \
                patch.object(plugin, "_SubscribeAssistant__build_best_version_payload", return_value={}), \
                patch.object(plugin, "clear_tasks") as clear_tasks:
            assert not plugin._SubscribeAssistant__convert_episode_best_version_to_full(sub)
        clear_tasks.assert_not_called()
        plugin.post_message.assert_called_once()

    def test_convert_episode_best_version_adds_full_subscribe_and_emits_event(self):
        plugin = make_plugin(_notify=True)
        plugin.subscribe_oper.add.return_value = (9, None)
        sub = make_subscribe(best_version=1, best_version_full=0)
        mediainfo = make_mediainfo()
        with patch.object(plugin, "_SubscribeAssistant__recognize_media", return_value=mediainfo), \
                patch.object(plugin, "_SubscribeAssistant__format_subscribe_desc", return_value="测试剧 S01"), \
                patch.object(plugin, "_SubscribeAssistant__build_best_version_payload",
                             return_value={"name": "测试剧"}), \
                patch.object(plugin, "clear_tasks") as clear_tasks, \
                patch("subscribeassistant.eventmanager.send_event") as send_event:
            assert plugin._SubscribeAssistant__convert_episode_best_version_to_full(sub)
        plugin.subscribe_oper.add_history.assert_called_once()
        plugin.subscribe_oper.delete.assert_called_once_with(sid=sub.id)
        clear_tasks.assert_called_once()
        plugin.subscribe_oper.add.assert_called_once()
        send_event.assert_called_once()
        plugin.post_message.assert_called_once()

    def test_convert_episode_best_version_restores_original_when_full_add_fails(self):
        plugin = make_plugin(_notify=True)
        plugin.subscribe_oper.add.return_value = (None, "add failed")
        sub = make_subscribe(best_version=1, best_version_full=0)
        mediainfo = make_mediainfo()
        with patch.object(plugin, "_SubscribeAssistant__recognize_media", return_value=mediainfo), \
                patch.object(plugin, "_SubscribeAssistant__format_subscribe_desc", return_value="测试剧 S01"), \
                patch.object(plugin, "_SubscribeAssistant__build_best_version_payload", return_value={}), \
                patch.object(plugin, "clear_tasks"), \
                patch.object(plugin, "_SubscribeAssistant__restore_episode_best_version_subscribe",
                             return_value=True) as restore:
            assert not plugin._SubscribeAssistant__convert_episode_best_version_to_full(sub)
        restore.assert_called_once()
        assert "已尝试恢复" in plugin.post_message.call_args.kwargs["text"]

    def test_restore_episode_best_version_subscribe_recreates_original_and_emits_event(self):
        plugin = make_plugin()
        plugin.subscribe_oper._db = object()
        plugin.subscribe_oper.get.return_value = make_subscribe(id=1)
        subscribe_dict = make_subscribe(best_version=1, best_version_full=0).to_dict()
        restored = MagicMock()
        with patch.object(plugin, "_SubscribeAssistant__build_restore_subscribe_payload",
                          return_value=subscribe_dict), \
                patch.object(plugin, "_SubscribeAssistant__format_subscribe_desc", return_value="测试剧 S01"), \
                patch("subscribeassistant.Subscribe", return_value=restored), \
                patch("subscribeassistant.eventmanager.send_event") as send_event:
            assert plugin._SubscribeAssistant__restore_episode_best_version_subscribe(
                subscribe_dict=subscribe_dict, mediainfo=make_mediainfo())
        restored.create.assert_called_once_with(plugin.subscribe_oper._db)
        send_event.assert_called_once()

    def test_restore_episode_best_version_subscribe_returns_false_when_readback_missing(self):
        plugin = make_plugin()
        plugin.subscribe_oper._db = object()
        plugin.subscribe_oper.get.return_value = None
        subscribe_dict = make_subscribe(best_version=1, best_version_full=0).to_dict()
        with patch.object(plugin, "_SubscribeAssistant__build_restore_subscribe_payload",
                          return_value=subscribe_dict), \
                patch("subscribeassistant.Subscribe", return_value=MagicMock()):
            assert not plugin._SubscribeAssistant__restore_episode_best_version_subscribe(
                subscribe_dict=subscribe_dict, mediainfo=make_mediainfo())

    def test_restore_episode_best_version_subscribe_returns_false_on_exception(self):
        plugin = make_plugin()
        subscribe_dict = make_subscribe(best_version=1, best_version_full=0).to_dict()
        with patch.object(plugin, "_SubscribeAssistant__build_restore_subscribe_payload",
                          side_effect=RuntimeError("boom")):
            assert not plugin._SubscribeAssistant__restore_episode_best_version_subscribe(
                subscribe_dict=subscribe_dict, mediainfo=make_mediainfo())

    def test_episode_best_version_target_ready_skips_when_pending(self):
        plugin = make_plugin()
        sub = make_subscribe(best_version=1, best_version_full=0)
        with patch.object(plugin, "_SubscribeAssistant__is_episode_best_version_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__has_pending_subscribe_task", return_value=True):
            assert not plugin._SubscribeAssistant__is_episode_best_version_target_ready(sub)

    def test_episode_best_version_target_ready_skips_when_recognition_failed(self):
        plugin = make_plugin()
        sub = make_subscribe(best_version=1, best_version_full=0)
        with patch.object(plugin, "_SubscribeAssistant__is_episode_best_version_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False), \
                patch.object(plugin, "_SubscribeAssistant__recognize_media", return_value=None):
            assert not plugin._SubscribeAssistant__is_episode_best_version_target_ready(sub)

    def test_episode_best_version_target_ready_skips_without_media_key(self):
        plugin = make_plugin()
        sub = make_subscribe(best_version=1, best_version_full=0, tmdbid=None, doubanid=None)
        mediainfo = make_mediainfo(tmdb_id=None, douban_id=None)
        with patch.object(plugin, "_SubscribeAssistant__is_episode_best_version_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False), \
                patch.object(plugin, "_SubscribeAssistant__recognize_media", return_value=mediainfo):
            assert not plugin._SubscribeAssistant__is_episode_best_version_target_ready(sub)

    def test_episode_best_version_target_ready_returns_true_when_media_server_reports_all_exist(self):
        plugin = make_plugin()
        sub = make_subscribe(best_version=1, best_version_full=0)
        chain = MagicMock()
        chain.get_no_exists_info.return_value = (True, {})
        with patch.object(plugin, "_SubscribeAssistant__is_episode_best_version_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False), \
                patch.object(plugin, "_SubscribeAssistant__recognize_media", return_value=make_mediainfo()), \
                patch.object(plugin, "_SubscribeAssistant__get_subscribe_meta", return_value=SimpleNamespace()), \
                patch.object(plugin, "_SubscribeAssistant__get_episode_best_version_state_episodes",
                             return_value=[]), \
                patch("subscribeassistant.DownloadChain", return_value=chain):
            assert plugin._SubscribeAssistant__is_episode_best_version_target_ready(sub)
        chain.get_no_exists_info.assert_called_once()

    def test_episode_best_version_target_ready_uses_lefts_and_state_episodes_when_not_all_exist(self):
        plugin = make_plugin()
        sub = make_subscribe(best_version=1, best_version_full=0)
        chain = MagicMock()
        chain.get_no_exists_info.return_value = (False, {100: {1: SimpleNamespace(episodes=[1])}})
        with patch.object(plugin, "_SubscribeAssistant__is_episode_best_version_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False), \
                patch.object(plugin, "_SubscribeAssistant__recognize_media", return_value=make_mediainfo()), \
                patch.object(plugin, "_SubscribeAssistant__get_subscribe_meta", return_value=SimpleNamespace()), \
                patch.object(plugin, "_SubscribeAssistant__get_episode_best_version_state_episodes",
                             return_value=[1]), \
                patch("subscribeassistant.DownloadChain", return_value=chain):
            assert plugin._SubscribeAssistant__is_episode_best_version_target_ready(sub)


# ===========================================================================
# process_best_version_complete
# ===========================================================================

class TestProcessBestVersionComplete:

    def test_empty_subscribes(self):
        plugin = make_plugin(_auto_best_remaining_days=30)
        with patch.object(plugin, "_SubscribeAssistant__mark_best_version_subscription_complete") as mark:
            plugin.process_best_version_complete([])
        mark.assert_not_called()

    def test_none_remaining_days(self):
        plugin = make_plugin(_auto_best_remaining_days=None)
        plugin.process_best_version_complete([make_subscribe(best_version=1)])
        plugin.subscribe_oper.update.assert_not_called()

    def test_zero_remaining_days(self):
        plugin = make_plugin(_auto_best_remaining_days=0)
        plugin.process_best_version_complete([make_subscribe(best_version=1)])
        plugin.subscribe_oper.update.assert_not_called()

    def test_negative_remaining_days(self):
        plugin = make_plugin(_auto_best_remaining_days=-1)
        plugin.process_best_version_complete([make_subscribe(best_version=1)])
        plugin.subscribe_oper.update.assert_not_called()

    def test_non_best_version_skipped(self):
        plugin = make_plugin(_auto_best_remaining_days=30)
        sub = make_subscribe(best_version=0)
        plugin.process_best_version_complete([sub])
        plugin.subscribe_oper.update.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__has_pending_subscribe_task", return_value=True)
    def test_pending_skipped(self, mock_pending):
        plugin = make_plugin(_auto_best_remaining_days=30)
        sub = make_subscribe(best_version=1)
        plugin.process_best_version_complete([sub])
        plugin.subscribe_oper.update.assert_not_called()

    @patch("subscribeassistant.SubscribeChain")
    def test_already_complete(self, mock_chain_cls):
        mock_chain_cls.is_best_version_complete.return_value = True
        plugin = make_plugin(_auto_best_remaining_days=30)
        sub = make_subscribe(best_version=1)
        plugin.process_best_version_complete([sub])
        plugin.subscribe_oper.update.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__is_episode_best_version_subscribe",
                  return_value=False)
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False)
    @patch("subscribeassistant.SubscribeChain")
    def test_no_date(self, mock_chain_cls, mock_pending, mock_ep):
        mock_chain_cls.is_best_version_complete.return_value = False
        plugin = make_plugin(_auto_best_remaining_days=30)
        sub = make_subscribe(best_version=1, last_update=None, date=None)
        plugin.process_best_version_complete([sub])
        plugin.subscribe_oper.update.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__is_episode_best_version_subscribe",
                  return_value=False)
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False)
    @patch("subscribeassistant.SubscribeChain")
    def test_invalid_date_format(self, mock_chain_cls, mock_pending, mock_ep):
        mock_chain_cls.is_best_version_complete.return_value = False
        plugin = make_plugin(_auto_best_remaining_days=30)
        sub = make_subscribe(best_version=1, last_update="bad-date")
        plugin.process_best_version_complete([sub])
        plugin.subscribe_oper.update.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__mark_best_version_subscription_complete")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__is_episode_best_version_subscribe",
                  return_value=False)
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False)
    @patch("subscribeassistant.SubscribeChain")
    def test_remaining_days_reached(self, mock_chain_cls, mock_pending, mock_ep, mock_mark):
        mock_chain_cls.is_best_version_complete.return_value = False
        plugin = make_plugin(_auto_best_remaining_days=5)
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        sub = make_subscribe(best_version=1, last_update=old_date)
        plugin.process_best_version_complete([sub])
        mock_mark.assert_called_once()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__mark_best_version_subscription_complete")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__is_episode_best_version_subscribe",
                  return_value=False)
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False)
    @patch("subscribeassistant.SubscribeChain")
    def test_remaining_days_not_reached(self, mock_chain_cls, mock_pending, mock_ep, mock_mark):
        mock_chain_cls.is_best_version_complete.return_value = False
        plugin = make_plugin(_auto_best_remaining_days=30)
        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
        sub = make_subscribe(best_version=1, last_update=recent_date)
        plugin.process_best_version_complete([sub])
        mock_mark.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__is_episode_best_version_target_ready",
                  return_value=False)
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__is_episode_best_version_subscribe",
                  return_value=True)
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__has_pending_subscribe_task", return_value=False)
    @patch("subscribeassistant.SubscribeChain")
    def test_episode_best_version_not_ready_skipped(self, mock_chain_cls, mock_pending, mock_ep, mock_ready):
        mock_chain_cls.is_best_version_complete.return_value = False
        plugin = make_plugin(_auto_best_remaining_days=30)
        old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
        sub = make_subscribe(best_version=1, last_update=old_date)
        plugin.process_best_version_complete([sub])
        plugin.subscribe_oper.update.assert_not_called()


# ===========================================================================
# process_best_version
# ===========================================================================

class TestProcessBestVersion:

    def test_empty_dict(self):
        plugin = make_plugin()
        plugin.process_best_version({}, make_mediainfo())
        plugin.subscribe_oper.add.assert_not_called()
        plugin.subscribe_oper.delete.assert_not_called()

    def test_already_best_version(self):
        plugin = make_plugin()
        sub_dict = make_subscribe(best_version=1).to_dict()
        plugin.process_best_version(sub_dict, make_mediainfo())
        plugin.subscribe_oper.add.assert_not_called()

    def test_type_not_in_auto_types(self):
        plugin = make_plugin(_auto_best_types=set())
        sub_dict = make_subscribe().to_dict()
        plugin.process_best_version(sub_dict, make_mediainfo())
        plugin.subscribe_oper.add.assert_not_called()

    def test_unknown_type(self):
        plugin = make_plugin(_auto_best_types={MediaType.TV})
        sub_dict = make_subscribe(type="invalid").to_dict()
        plugin.process_best_version(sub_dict, make_mediainfo())
        plugin.subscribe_oper.add.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__recognize_media")
    def test_no_mediainfo_recognized(self, mock_recognize):
        mock_recognize.return_value = None
        plugin = make_plugin(_auto_best_types={MediaType.TV})
        sub_dict = make_subscribe().to_dict()
        plugin.process_best_version(sub_dict, None)
        plugin.subscribe_oper.add.assert_not_called()

    @patch("subscribeassistant.eventmanager")
    def test_successful_add(self, mock_em):
        plugin = make_plugin(_auto_best_types={MediaType.MOVIE}, _notify=True)
        sub_dict = make_subscribe(type=MOVIE).to_dict()
        mi = make_mediainfo(type=MediaType.MOVIE)
        plugin.subscribe_oper.add.return_value = (99, None)
        plugin.process_best_version(sub_dict, mi)
        plugin.subscribe_oper.add.assert_called_once()
        plugin.post_message.assert_called_once()

    def test_failed_add(self):
        plugin = make_plugin(_auto_best_types={MediaType.MOVIE}, _notify=True)
        sub_dict = make_subscribe(type=MOVIE).to_dict()
        mi = make_mediainfo(type=MediaType.MOVIE)
        plugin.subscribe_oper.add.return_value = (None, "duplicate")
        plugin.process_best_version(sub_dict, mi)
        plugin.post_message.assert_called_once()
        call_kwargs = plugin.post_message.call_args[1]
        assert "失败" in call_kwargs["title"]

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_related_download_histories")
    def test_tv_episode_type_checks_downloads(self, mock_dl):
        plugin = make_plugin(
            _auto_best_types={MediaType.TV}, _auto_best_type="tv_episode")
        mock_dl.return_value = []
        sub_dict = make_subscribe(type=TV).to_dict()
        mi = make_mediainfo(type=MediaType.TV)
        plugin.process_best_version(sub_dict, mi)
        plugin.subscribe_oper.add.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_related_download_histories")
    def test_tv_episode_single_download_skipped(self, mock_dl):
        mock_dl.return_value = [SimpleNamespace()]
        plugin = make_plugin(
            _auto_best_types={MediaType.TV}, _auto_best_type="tv_episode")
        sub_dict = make_subscribe(type=TV).to_dict()
        mi = make_mediainfo(type=MediaType.TV)
        plugin.process_best_version(sub_dict, mi)
        plugin.subscribe_oper.add.assert_not_called()


# ===========================================================================
# __detect_existing_episodes_for_subscribe
# ===========================================================================

class TestDetectExistingEpisodesForSubscribe:

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__recognize_media", return_value=None)
    def test_no_mediainfo(self, mock_rec):
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1)
        ok, eps = plugin._SubscribeAssistant__detect_existing_episodes_for_subscribe(sub)
        assert ok is False
        assert eps == []

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__recognize_media")
    def test_no_mediakey(self, mock_rec):
        mi = make_mediainfo(tmdb_id=None)
        mock_rec.return_value = mi
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1, tmdbid=None, doubanid=None)
        ok, eps = plugin._SubscribeAssistant__detect_existing_episodes_for_subscribe(sub, mi)
        assert ok is False

    @patch("subscribeassistant.DownloadChain")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__recognize_media")
    def test_all_exist(self, mock_rec, mock_chain_cls):
        mi = make_mediainfo()
        mock_rec.return_value = mi
        mock_chain = MagicMock()
        mock_chain.get_no_exists_info.return_value = (True, {})
        mock_chain_cls.return_value = mock_chain
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1, start_episode=1, total_episode=3)
        ok, eps = plugin._SubscribeAssistant__detect_existing_episodes_for_subscribe(sub, mi)
        assert ok is True
        assert eps == [1, 2, 3]

    @patch("subscribeassistant.DownloadChain")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__recognize_media")
    def test_some_missing(self, mock_rec, mock_chain_cls):
        mi = make_mediainfo()
        mock_rec.return_value = mi
        missing_season = SimpleNamespace(episodes=[3])
        mock_chain = MagicMock()
        mock_chain.get_no_exists_info.return_value = (False, {100: {1: missing_season}})
        mock_chain_cls.return_value = mock_chain
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1, start_episode=1, total_episode=3)
        ok, eps = plugin._SubscribeAssistant__detect_existing_episodes_for_subscribe(sub, mi)
        assert ok is True
        assert eps == [1, 2]

    @patch("subscribeassistant.DownloadChain")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__recognize_media")
    def test_exception(self, mock_rec, mock_chain_cls):
        mi = make_mediainfo()
        mock_rec.return_value = mi
        mock_chain = MagicMock()
        mock_chain.get_no_exists_info.side_effect = RuntimeError("fail")
        mock_chain_cls.return_value = mock_chain
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1, start_episode=1, total_episode=3)
        ok, eps = plugin._SubscribeAssistant__detect_existing_episodes_for_subscribe(sub, mi)
        assert ok is False

    @patch("subscribeassistant.DownloadChain")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__recognize_media")
    def test_season_no_exist_none(self, mock_rec, mock_chain_cls):
        """缺失信息未确定，返回空。"""
        mi = make_mediainfo()
        mock_rec.return_value = mi
        mock_chain = MagicMock()
        mock_chain.get_no_exists_info.return_value = (False, {100: {}})
        mock_chain_cls.return_value = mock_chain
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1, start_episode=1, total_episode=3)
        ok, eps = plugin._SubscribeAssistant__detect_existing_episodes_for_subscribe(sub, mi)
        assert ok is True
        assert eps == []


# ===========================================================================
# __backfill_best_version_episode_priority
# ===========================================================================

class TestBackfillBestVersionEpisodePriority:

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__should_backfill_priority", return_value=False)
    def test_should_not_backfill(self, mock_should):
        plugin = make_plugin()
        sub = make_subscribe()
        ok, count = plugin._SubscribeAssistant__backfill_best_version_episode_priority(sub)
        assert ok is False

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__detect_existing_episodes_for_subscribe",
                  return_value=(False, []))
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__should_backfill_priority", return_value=True)
    def test_detection_fails(self, mock_should, mock_detect):
        plugin = make_plugin()
        sub = make_subscribe()
        ok, count = plugin._SubscribeAssistant__backfill_best_version_episode_priority(sub)
        assert ok is False

    @patch("subscribeassistant.SubscribeChain")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__detect_existing_episodes_for_subscribe",
                  return_value=(True, [1, 2, 3]))
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__should_backfill_priority", return_value=True)
    def test_backfills_missing(self, mock_should, mock_detect, mock_chain_cls):
        mock_chain = MagicMock()
        mock_chain.backfill_existing_episodes.return_value = {
            "updated": True,
            "accepted": [2, 3],
            "priority_updated": [],
        }
        mock_chain_cls.return_value = mock_chain
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1, episode_priority={"1": 80})
        ok, count = plugin._SubscribeAssistant__backfill_best_version_episode_priority(sub)
        assert ok is True
        assert count == 2  # episodes 2,3 new
        mock_chain.backfill_existing_episodes.assert_called_once_with(
            sub,
            [1, 2, 3],
            priority=100,
            scene="plugin_backfill<订阅助手>",
        )
        plugin.subscribe_oper.update.assert_not_called()

    @patch("subscribeassistant.SubscribeChain")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__detect_existing_episodes_for_subscribe",
                  return_value=(True, [1, 2]))
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__should_backfill_priority", return_value=True)
    def test_all_already_present(self, mock_should, mock_detect, mock_chain_cls):
        mock_chain_cls.return_value.backfill_existing_episodes.return_value = {
            "updated": False,
            "accepted": [],
            "priority_updated": [],
        }
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1, episode_priority={"1": 80, "2": 100})
        ok, count = plugin._SubscribeAssistant__backfill_best_version_episode_priority(sub)
        assert ok is False
        assert count == 0

    @patch("subscribeassistant.SubscribeChain")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__detect_existing_episodes_for_subscribe",
                  return_value=(True, [1]))
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__should_backfill_priority", return_value=True)
    def test_preserves_formatted_scene(self, mock_should, mock_detect, mock_chain_cls):
        mock_chain_cls.return_value.backfill_existing_episodes.return_value = {
            "updated": True,
            "accepted": [1],
            "priority_updated": [],
        }
        plugin = make_plugin()
        sub = make_subscribe(type=TV, best_version=1)
        ok, count = plugin._SubscribeAssistant__backfill_best_version_episode_priority(
            sub,
            scene="reset_backfill<订阅助手>",
        )
        assert ok is True
        assert count == 1
        mock_chain_cls.return_value.backfill_existing_episodes.assert_called_once_with(
            sub,
            [1],
            priority=100,
            scene="reset_backfill<订阅助手>",
        )


# ===========================================================================
# __backfill_all_existing_best_version
# ===========================================================================

class TestBackfillAllExistingBestVersion:

    def test_empty_list(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = []
        result = plugin._SubscribeAssistant__backfill_all_existing_best_version()
        assert result["scanned"] == 0

    def test_list_exception(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.side_effect = RuntimeError("db")
        result = plugin._SubscribeAssistant__backfill_all_existing_best_version()
        assert result["scanned"] == 0

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__backfill_best_version_episode_priority",
                  return_value=(True, 5))
    def test_scans_best_version_only(self, mock_bf):
        plugin = make_plugin(_notify=True)
        subs = [
            make_subscribe(id=1, best_version=1),
            make_subscribe(id=2, best_version=0),
            make_subscribe(id=3, best_version=1),
        ]
        plugin.subscribe_oper.list.return_value = subs
        result = plugin._SubscribeAssistant__backfill_all_existing_best_version()
        assert result["scanned"] == 2
        assert result["updated"] == 2
        assert result["filled_episodes"] == 10
        plugin.post_message.assert_called_once()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__backfill_best_version_episode_priority",
                  side_effect=RuntimeError("boom"))
    def test_exception_per_sub(self, mock_bf):
        plugin = make_plugin()
        subs = [make_subscribe(id=1, best_version=1)]
        plugin.subscribe_oper.list.return_value = subs
        result = plugin._SubscribeAssistant__backfill_all_existing_best_version()
        assert result["skipped"] == 1

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__backfill_best_version_episode_priority",
                  return_value=(False, 0))
    def test_skipped_when_no_update(self, mock_bf):
        plugin = make_plugin()
        subs = [make_subscribe(id=1, best_version=1)]
        plugin.subscribe_oper.list.return_value = subs
        result = plugin._SubscribeAssistant__backfill_all_existing_best_version()
        assert result["skipped"] == 1
        assert result["updated"] == 0

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__backfill_best_version_episode_priority",
                  return_value=(True, 1))
    def test_notification_exception_does_not_fail_scan(self, mock_bf):
        plugin = make_plugin(_notify=True)
        plugin.post_message.side_effect = RuntimeError("notify")
        plugin.subscribe_oper.list.return_value = [make_subscribe(id=1, best_version=1)]
        result = plugin._SubscribeAssistant__backfill_all_existing_best_version()
        assert result["updated"] == 1
        plugin.post_message.assert_called_once()
