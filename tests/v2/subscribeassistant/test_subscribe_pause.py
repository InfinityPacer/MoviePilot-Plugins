"""
SubscribeAssistant 订阅暂停逻辑单测。

覆盖业务域：
- 暂停入口：process_subscribe_pause / process_subscribe_pause_for_user
- 暂停处理：__process_subscribe_pause / __process_subscribe_pause_for_user
- 下载暂停：__process_subscribe_pause_for_download / __check_subscribe_action_for_download
- 播出暂停：__process_subscribe_pause_for_airing / __check_subscribe_pause_for_airing
"""
import time
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
    plugin._auto_pause = True
    plugin._auto_pause_users = set()
    plugin._auto_pause_user = ""
    plugin._auto_pause_movie_air_days = None
    plugin._auto_pause_tv_air_days = None
    plugin._auto_pause_tv_latest_days = None
    plugin._auto_pause_no_download_actions = []
    plugin._auto_pause_movie_no_download_days = None
    plugin._auto_pause_tv_no_download_days = None
    plugin._auto_tv_pending = False
    plugin._auto_tv_pending_days = None
    plugin._auto_tv_pending_episodes = None
    plugin._auto_update_tv_pending_episodes = None
    plugin._auto_download_pending = False
    plugin._download_pending_hash_grace_seconds = 300
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
        status="Returning Series",
    )
    base.update(kwargs)
    ns = SimpleNamespace(**base)
    ns.get_message_image = lambda: ""
    return ns


def _today_str(delta_days=0):
    return (datetime.now() + timedelta(days=delta_days)).strftime("%Y-%m-%d")


# ===========================================================================
# process_subscribe_pause
# ===========================================================================

class TestProcessSubscribePause:

    def test_disabled(self):
        plugin = make_plugin(_auto_pause=False)
        plugin.process_subscribe_pause()
        plugin.subscribe_oper.list.assert_not_called()

    def test_list_all(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = []
        plugin.process_subscribe_pause()
        plugin.subscribe_oper.list.assert_called_once()

    def test_specific_id(self):
        plugin = make_plugin()
        sub = make_subscribe()
        plugin.subscribe_oper.get.return_value = sub
        plugin.subscribe_oper.list.return_value = None
        plugin.process_subscribe_pause(subscribe_id=1)
        plugin.subscribe_oper.get.assert_called_once_with(sid=1)

    def test_empty_subscribes(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = []
        plugin.process_subscribe_pause()
        plugin.save_data.assert_not_called()


# ===========================================================================
# process_subscribe_pause_for_user
# ===========================================================================

class TestProcessSubscribePauseForUser:

    def test_disabled(self):
        plugin = make_plugin(_auto_pause=False)
        plugin.process_subscribe_pause_for_user(1)
        plugin.subscribe_oper.get.assert_not_called()

    def test_no_pause_users(self):
        plugin = make_plugin(_auto_pause_users=set())
        plugin.process_subscribe_pause_for_user(1)
        plugin.subscribe_oper.get.assert_not_called()

    def test_subscribe_not_found(self):
        plugin = make_plugin(_auto_pause_users={"admin"})
        plugin.subscribe_oper.get.return_value = None
        plugin.process_subscribe_pause_for_user(1)
        plugin.save_data.assert_not_called()

    def test_best_version_skipped(self):
        plugin = make_plugin(_auto_pause_users={"admin"})
        sub = make_subscribe(best_version=1, username="admin")
        plugin.subscribe_oper.get.return_value = sub
        plugin.process_subscribe_pause_for_user(1)
        plugin.save_data.assert_not_called()

    def test_user_not_in_list(self):
        plugin = make_plugin(_auto_pause_users={"admin"})
        sub = make_subscribe(username="other_user")
        plugin.subscribe_oper.get.return_value = sub
        plugin.process_subscribe_pause_for_user(1)
        plugin.save_data.assert_not_called()


# ===========================================================================
# __process_subscribe_pause_for_user
# ===========================================================================

class TestProcessSubscribePauseForUserInner:

    def test_sets_pause_and_state(self):
        plugin = make_plugin()
        sub = make_subscribe(state="R", username="admin")
        tasks = {}
        plugin._SubscribeAssistant__process_subscribe_pause_for_user(tasks, sub)
        plugin.subscribe_oper.update.assert_called_once_with(sub.id, {"state": "S"})
        task = tasks[str(sub.id)]
        assert task["pause_for_user"] is True
        assert task["pause_for_user_time"] is not None

    def test_notify(self):
        plugin = make_plugin(_notify=True)
        sub = make_subscribe(state="R", username="admin")
        tasks = {}
        plugin._SubscribeAssistant__process_subscribe_pause_for_user(tasks, sub)
        plugin.post_message.assert_called_once()

    def test_exception_handled(self):
        plugin = make_plugin()
        sub = make_subscribe(state="R", username="admin")
        plugin.subscribe_oper.update.side_effect = RuntimeError("db error")
        tasks = {}
        with patch("subscribeassistant.logger.error") as error:
            plugin._SubscribeAssistant__process_subscribe_pause_for_user(tasks, sub)
        assert tasks == {}
        error.assert_called_once()


# ===========================================================================
# __process_subscribe_pause
# ===========================================================================

class TestProcessSubscribePauseInner:

    def test_best_version_skipped(self):
        plugin = make_plugin()
        sub = make_subscribe(best_version=1)
        tasks = {}
        plugin._SubscribeAssistant__process_subscribe_pause(tasks, [sub])
        plugin.subscribe_oper.update.assert_not_called()

    def test_already_paused_by_user(self):
        plugin = make_plugin()
        sub = make_subscribe(state="S")
        tasks = {
            str(sub.id): {
                "id": sub.id, "name": sub.name, "year": sub.year, "type": sub.type,
                "season": sub.season, "episode_group": sub.episode_group,
                "tmdbid": sub.tmdbid, "doubanid": sub.doubanid,
                "imdbid": None, "tvdbid": None, "bangumiid": None,
                "best_version": 0, "pause_for_user": True,
                "pause_for_user_time": time.time(),
                "pause_for_download": False, "pause_for_download_time": None,
                "tv_pending": False, "tv_pending_time": None,
                "torrent_tasks": [],
            }
        }
        plugin._SubscribeAssistant__process_subscribe_pause(tasks, [sub])
        plugin.subscribe_oper.update.assert_not_called()

    def test_resets_pause_if_state_not_s(self):
        """订阅已被用户启用（state!=S），重置暂停标记。"""
        plugin = make_plugin()
        sub = make_subscribe(state="R")
        tasks = {
            str(sub.id): {
                "id": sub.id, "name": sub.name, "year": sub.year, "type": sub.type,
                "season": sub.season, "episode_group": sub.episode_group,
                "tmdbid": sub.tmdbid, "doubanid": sub.doubanid,
                "imdbid": None, "tvdbid": None, "bangumiid": None,
                "best_version": 0, "pause_for_user": True,
                "pause_for_user_time": time.time(),
                "pause_for_download": False, "pause_for_download_time": None,
                "tv_pending": False, "tv_pending_time": None,
                "torrent_tasks": [],
            }
        }
        # recognize_media returns None -> early return on missing mediainfo
        with patch.object(SubscribeAssistant, "_SubscribeAssistant__recognize_media", return_value=None):
            plugin._SubscribeAssistant__process_subscribe_pause(tasks, [sub])
        task = tasks[str(sub.id)]
        assert task["pause_for_user"] is False
        assert task["pause_for_download"] is False

    def test_tuple_input(self):
        """输入为 (subscribe, mediainfo) 元组。"""
        plugin = make_plugin()
        sub = make_subscribe(best_version=0)
        mi = make_mediainfo()
        with patch.object(plugin, "_SubscribeAssistant__recognize_media") as recognize, \
                patch.object(plugin, "_SubscribeAssistant__process_subscribe_pause_for_download",
                             return_value=True) as download:
            plugin._SubscribeAssistant__process_subscribe_pause({}, [(sub, mi)])
        recognize.assert_not_called()
        download.assert_called_once()

    def test_unknown_mediainfo_type_skips_pause_handlers(self):
        plugin = make_plugin()
        sub = make_subscribe()
        mi = make_mediainfo(type=MediaType.UNKNOWN)
        with patch.object(plugin, "_SubscribeAssistant__process_subscribe_pause_for_download") as download, \
                patch.object(plugin, "_SubscribeAssistant__process_subscribe_pause_for_airing") as airing:
            plugin._SubscribeAssistant__process_subscribe_pause({}, [(sub, mi)])
        download.assert_not_called()
        airing.assert_not_called()

    def test_download_handler_executed_skips_airing_handler(self):
        plugin = make_plugin()
        sub = make_subscribe()
        mi = make_mediainfo()
        with patch.object(plugin, "_SubscribeAssistant__process_subscribe_pause_for_download", return_value=True) \
                as download, \
                patch.object(plugin, "_SubscribeAssistant__process_subscribe_pause_for_airing") as airing:
            plugin._SubscribeAssistant__process_subscribe_pause({}, [(sub, mi)])
        download.assert_called_once()
        airing.assert_not_called()

    def test_airing_handler_runs_when_download_handler_not_executed(self):
        plugin = make_plugin()
        sub = make_subscribe()
        mi = make_mediainfo()
        with patch.object(plugin, "_SubscribeAssistant__process_subscribe_pause_for_download", return_value=False), \
                patch.object(plugin, "_SubscribeAssistant__process_subscribe_pause_for_airing") as airing:
            plugin._SubscribeAssistant__process_subscribe_pause({}, [(sub, mi)])
        airing.assert_called_once()

    def test_exception_handled(self):
        plugin = make_plugin()
        sub = make_subscribe()
        with patch.object(SubscribeAssistant, "_SubscribeAssistant__initialize_subscribe_task",
                          side_effect=RuntimeError("boom")), \
                patch("subscribeassistant.logger.error") as error:
            plugin._SubscribeAssistant__process_subscribe_pause({}, [sub])
        error.assert_called_once()


# ===========================================================================
# __process_subscribe_pause_for_download
# ===========================================================================

class TestProcessSubscribePauseForDownload:

    def test_no_mediainfo(self):
        plugin = make_plugin()
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download(
            {}, make_subscribe(), None)
        assert result is False

    def test_unknown_type(self):
        plugin = make_plugin()
        sub = make_subscribe(type="invalid")
        mi = make_mediainfo()
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download({}, sub, mi)
        assert result is False

    def test_tv_no_download_days_not_set(self):
        plugin = make_plugin(_auto_pause_tv_no_download_days=None)
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download({}, sub, mi)
        assert result is False

    def test_movie_no_download_days_not_set(self):
        plugin = make_plugin(_auto_pause_movie_no_download_days=None)
        sub = make_subscribe(type=MOVIE)
        mi = make_mediainfo(type=MediaType.MOVIE)
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download({}, sub, mi)
        assert result is False

    def test_no_relevant_actions(self):
        plugin = make_plugin(
            _auto_pause_tv_no_download_days=30,
            _auto_pause_no_download_actions=[]
        )
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download({}, sub, mi)
        assert result is False

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__check_subscribe_action_for_download",
                  return_value=(False, 30))
    def test_action_not_triggered(self, mock_check):
        plugin = make_plugin(
            _auto_pause_tv_no_download_days=30,
            _auto_pause_no_download_actions=["pause_tv"]
        )
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download({}, sub, mi)
        assert result is False

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__send_subscribe_status_msg")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__check_subscribe_action_for_download",
                  return_value=(True, 45))
    def test_pause_action(self, mock_check, mock_msg):
        plugin = make_plugin(
            _auto_pause_tv_no_download_days=30,
            _auto_pause_no_download_actions=["pause_tv"]
        )
        sub = make_subscribe(type=TV, state="R")
        mi = make_mediainfo(type=MediaType.TV)
        task = {
            "pause_for_download": False, "pause_for_download_time": None,
            "tv_pending": False,
        }
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download(task, sub, mi)
        assert result is True
        assert task["pause_for_download"] is True
        plugin.subscribe_oper.update.assert_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__send_subscribe_status_msg")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__check_subscribe_action_for_download",
                  return_value=(True, 45))
    def test_complete_action(self, mock_check, mock_msg):
        plugin = make_plugin(
            _auto_pause_movie_no_download_days=30,
            _auto_pause_no_download_actions=["complete_movie"]
        )
        sub = make_subscribe(type=MOVIE, state="R")
        mi = make_mediainfo(type=MediaType.MOVIE)
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download({}, sub, mi)
        assert result is True
        plugin.subscribe_oper.add_history.assert_called_once()
        plugin.subscribe_oper.delete.assert_called_once()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__send_subscribe_status_msg")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__check_subscribe_action_for_download",
                  return_value=(True, 45))
    def test_delete_action(self, mock_check, mock_msg):
        plugin = make_plugin(
            _auto_pause_movie_no_download_days=30,
            _auto_pause_no_download_actions=["delete_movie"]
        )
        sub = make_subscribe(type=MOVIE, state="R")
        mi = make_mediainfo(type=MediaType.MOVIE)
        result = plugin._SubscribeAssistant__process_subscribe_pause_for_download({}, sub, mi)
        assert result is True
        plugin.subscribe_oper.delete.assert_called_once_with(sid=sub.id)


# ===========================================================================
# __check_subscribe_action_for_download
# ===========================================================================

class TestCheckSubscribeActionForDownload:

    def test_unknown_type(self):
        plugin = make_plugin()
        mi = make_mediainfo(type=MediaType.UNKNOWN)
        result = plugin._SubscribeAssistant__check_subscribe_action_for_download(make_subscribe(), mi)
        assert result == (False, None)

    def test_no_download_days_none(self):
        plugin = make_plugin(_auto_pause_tv_no_download_days=None)
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        result = plugin._SubscribeAssistant__check_subscribe_action_for_download(sub, mi)
        assert result == (False, None)

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_tv_season_air_date",
                  return_value=(None, None))
    def test_no_air_date(self, mock_air):
        plugin = make_plugin(_auto_pause_tv_no_download_days=30)
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        result = plugin._SubscribeAssistant__check_subscribe_action_for_download(sub, mi)
        assert result[0] is False

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_related_download_histories",
                  return_value=[])
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_tv_season_air_date")
    def test_deadline_not_passed(self, mock_air, mock_dl):
        """截止日期尚未到来。"""
        plugin = make_plugin(_auto_pause_tv_no_download_days=30)
        future = datetime.now() + timedelta(days=10)
        mock_air.return_value = (future, future.strftime("%Y-%m-%d"))
        sub = make_subscribe(type=TV, date="2024-01-01 00:00:00")
        mi = make_mediainfo(type=MediaType.TV)
        result = plugin._SubscribeAssistant__check_subscribe_action_for_download(sub, mi)
        assert result[0] is False

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_related_download_histories",
                  return_value=[])
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_tv_season_air_date")
    def test_deadline_passed(self, mock_air, mock_dl):
        """截止日期已过。"""
        plugin = make_plugin(_auto_pause_tv_no_download_days=5)
        past = datetime.now() - timedelta(days=60)
        mock_air.return_value = (past, past.strftime("%Y-%m-%d"))
        sub = make_subscribe(type=TV, date="2024-01-01 00:00:00", last_update="2024-01-01 00:00:00")
        mi = make_mediainfo(type=MediaType.TV)
        result = plugin._SubscribeAssistant__check_subscribe_action_for_download(sub, mi)
        assert result[0] is True
        assert result[1] > 0


# ===========================================================================
# __process_subscribe_pause_for_airing
# ===========================================================================

class TestProcessSubscribePauseForAiring:

    def test_no_mediainfo(self):
        plugin = make_plugin()
        sub = make_subscribe()
        plugin._SubscribeAssistant__process_subscribe_pause_for_airing({}, sub, None)
        plugin.subscribe_oper.update.assert_not_called()

    def test_unknown_type(self):
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=3)
        sub = make_subscribe(type="invalid")
        mi = make_mediainfo()
        plugin._SubscribeAssistant__process_subscribe_pause_for_airing({}, sub, mi)
        plugin.subscribe_oper.update.assert_not_called()

    def test_tv_no_air_days(self):
        plugin = make_plugin(_auto_pause_tv_air_days=None, _auto_pause_tv_latest_days=None)
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        plugin._SubscribeAssistant__process_subscribe_pause_for_airing({}, sub, mi)
        plugin.subscribe_oper.update.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__send_subscribe_status_msg")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__check_subscribe_pause_for_airing",
                  return_value=(True, "2025-01-01", "上映日期"))
    def test_pause_from_r(self, mock_check, mock_msg):
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=3)
        sub = make_subscribe(type=TV, state="R")
        mi = make_mediainfo(type=MediaType.TV)
        plugin._SubscribeAssistant__process_subscribe_pause_for_airing({}, sub, mi)
        plugin.subscribe_oper.update.assert_called_once_with(sub.id, {"state": "S"})

    @patch("subscribeassistant.threading.Timer")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__send_subscribe_status_msg")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__check_subscribe_pause_for_airing",
                  return_value=(False, "2024-01-01", "上映日期"))
    def test_resume_from_s(self, mock_check, mock_msg, mock_timer):
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=3)
        sub = make_subscribe(type=TV, state="S")
        mi = make_mediainfo(type=MediaType.TV)
        plugin._SubscribeAssistant__process_subscribe_pause_for_airing({}, sub, mi)
        plugin.subscribe_oper.update.assert_called_once_with(sub.id, {"state": "R"})
        mock_timer.assert_called_once()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__check_subscribe_pause_for_airing",
                  return_value=(True, "2025-01-01", "上映日期"))
    def test_no_change_already_s(self, mock_check):
        """已经是暂停状态且条件仍暂停，不更新。"""
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=3)
        sub = make_subscribe(type=TV, state="S")
        mi = make_mediainfo(type=MediaType.TV)
        plugin._SubscribeAssistant__process_subscribe_pause_for_airing({}, sub, mi)
        plugin.subscribe_oper.update.assert_not_called()

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__check_subscribe_pause_for_airing",
                  return_value=(False, "2024-01-01", "上映日期"))
    def test_no_change_already_r(self, mock_check):
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=3)
        sub = make_subscribe(type=TV, state="R")
        mi = make_mediainfo(type=MediaType.TV)
        plugin._SubscribeAssistant__process_subscribe_pause_for_airing({}, sub, mi)
        plugin.subscribe_oper.update.assert_not_called()


# ===========================================================================
# __check_subscribe_pause_for_airing
# ===========================================================================

class TestCheckSubscribePauseForAiring:

    def test_unknown_media_type(self):
        plugin = make_plugin()
        sub = make_subscribe()
        mi = make_mediainfo(type=MediaType.UNKNOWN)
        result = plugin._SubscribeAssistant__check_subscribe_pause_for_airing(sub, mi)
        assert result == (False, None, None)

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_tv_season_air_date")
    def test_no_air_date_pauses(self, mock_air):
        """无法解析上映日期时默认暂停。"""
        mock_air.return_value = (None, None)
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=None)
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        pause, day, reason = plugin._SubscribeAssistant__check_subscribe_pause_for_airing(sub, mi)
        assert pause is True
        assert day == "未知"

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_tv_season_air_date")
    def test_future_air_date_pauses(self, mock_air):
        future = datetime.now() + timedelta(days=30)
        mock_air.return_value = (future, future.strftime("%Y-%m-%d"))
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=None)
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        pause, day, reason = plugin._SubscribeAssistant__check_subscribe_pause_for_airing(sub, mi)
        assert pause is True

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_tv_season_air_date")
    def test_past_air_date_no_pause(self, mock_air):
        past = datetime.now() - timedelta(days=30)
        mock_air.return_value = (past, past.strftime("%Y-%m-%d"))
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=None)
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        pause, day, reason = plugin._SubscribeAssistant__check_subscribe_pause_for_airing(sub, mi)
        assert pause is False

    def test_movie_air_date(self):
        plugin = make_plugin(_auto_pause_movie_air_days=7, _auto_pause_tv_latest_days=None)
        future = datetime.now() + timedelta(days=30)
        sub = make_subscribe(type=MOVIE)
        mi = make_mediainfo(type=MediaType.MOVIE, release_date=future.strftime("%Y-%m-%d"))
        pause, day, reason = plugin._SubscribeAssistant__check_subscribe_pause_for_airing(sub, mi)
        assert pause is True

    def test_no_auto_pause_days(self):
        plugin = make_plugin(_auto_pause_tv_air_days=None, _auto_pause_movie_air_days=None,
                             _auto_pause_tv_latest_days=None)
        sub = make_subscribe(type=TV)
        mi = make_mediainfo(type=MediaType.TV)
        pause, day, reason = plugin._SubscribeAssistant__check_subscribe_pause_for_airing(sub, mi)
        assert pause is False

    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_tv_season_air_date")
    @patch.object(SubscribeAssistant, "_SubscribeAssistant__get_tv_latest_episode")
    def test_latest_episode_pause_uses_first_missing_episode_from_note(self, mock_latest, mock_air):
        mock_air.return_value = (datetime.now() - timedelta(days=30), _today_str(-30))
        next_air = datetime.now() + timedelta(days=10)
        latest = SimpleNamespace(episode_number=2, air_date=_today_str(-1))
        next_ep = SimpleNamespace(episode_number=3, air_date=next_air.strftime("%Y-%m-%d"))
        mock_latest.return_value = (latest, next_ep)
        plugin = make_plugin(_auto_pause_tv_air_days=7, _auto_pause_tv_latest_days=3)
        sub = make_subscribe(type=TV, start_episode=1, total_episode=4, note=[1, "2"])
        mi = make_mediainfo(type=MediaType.TV)
        pause, day, reason = plugin._SubscribeAssistant__check_subscribe_pause_for_airing(sub, mi)
        assert pause is True
        assert day == next_air.strftime("%Y-%m-%d")
        assert reason == "即将播出日期"


class TestGetRelatedDownloadHistories:
    """下载历史关联筛选用于判断订阅是否长期无下载。"""

    def test_get_related_download_histories_filters_tv_source_identity_and_episode_group(self):
        plugin = make_plugin()
        sub = make_subscribe(id=7, type=TV, season=1, episode_group="group-a",
                             tmdbid=100, year="2024", date="2024-01-01 00:00:00")
        matching = SimpleNamespace(
            note={"source": "ok"}, date="2024-01-02 00:00:00",
            episode_group="group-a", torrent_name="测试剧 S01E01",
            torrent_description="第1集",
        )
        no_source = SimpleNamespace(note={}, date="2024-01-02 00:00:00", episode_group=None,
                                    torrent_name="x", torrent_description="")
        old = SimpleNamespace(note={"source": "old"}, date="2023-12-31 00:00:00", episode_group=None,
                              torrent_name="x", torrent_description="")
        wrong_group = SimpleNamespace(note={"source": "wrong-group"}, date="2024-01-02 00:00:00",
                                      episode_group="group-b", torrent_name="测试剧 S01E01",
                                      torrent_description="第1集")
        plugin.downloadhistory_oper.get_last_by.return_value = [matching, no_source, old, wrong_group]

        def source_lookup(source):
            if source == "ok":
                return {"id": 7, "tmdbid": 100, "year": "2024", "season": 1, "episode_group": "group-a"}, sub
            if source == "wrong-group":
                return {"id": 7, "tmdbid": 100, "year": "2024", "season": 1, "episode_group": "group-b"}, sub
            return None, None

        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source", side_effect=source_lookup):
            assert plugin._SubscribeAssistant__get_related_download_histories(7, sub) == [matching]

    def test_get_related_download_histories_filters_mismatched_source_fields_and_full_pack(self):
        plugin = make_plugin()
        sub = make_subscribe(id=7, type=TV, season=1, episode_group="group-a",
                             tmdbid=100, year="2024", total_episode=12,
                             date="2024-01-01 00:00:00")

        def download(source, **kwargs):
            base = dict(
                note={"source": source}, date="2024-01-02 00:00:00",
                episode_group=None, torrent_name="测试剧 S01E01",
                torrent_description="第1集",
            )
            base.update(kwargs)
            return SimpleNamespace(**base)

        missing_subscribe = download("missing")
        wrong_id = download("wrong-id")
        wrong_tmdb = download("wrong-tmdb")
        wrong_year = download("wrong-year")
        wrong_season = download("wrong-season")
        wrong_download_group = download("wrong-download-group", episode_group="group-b")
        full_pack = download("full-pack", torrent_name="测试剧 S01 Complete", torrent_description="全12集")
        plugin.downloadhistory_oper.get_last_by.return_value = [
            missing_subscribe, wrong_id, wrong_tmdb, wrong_year, wrong_season, wrong_download_group, full_pack,
        ]

        def source_lookup(source):
            mapping = {
                "missing": None,
                "wrong-id": {"id": 8, "tmdbid": 100, "year": "2024", "season": 1},
                "wrong-tmdb": {"id": 7, "tmdbid": 101, "year": "2024", "season": 1},
                "wrong-year": {"id": 7, "tmdbid": 100, "year": "2023", "season": 1},
                "wrong-season": {"id": 7, "tmdbid": 100, "year": "2024", "season": 2},
                "wrong-download-group": {"id": 7, "tmdbid": 100, "year": "2024", "season": 1},
                "full-pack": {"id": 7, "tmdbid": 100, "year": "2024", "season": 1, "episode_group": "group-a"},
            }
            subscribe_info = mapping[source]
            return subscribe_info, sub if subscribe_info else None

        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source", side_effect=source_lookup):
            assert plugin._SubscribeAssistant__get_related_download_histories(7, sub) == []

    def test_get_related_download_histories_matches_movie_without_season(self):
        plugin = make_plugin()
        sub = make_subscribe(id=8, type=MOVIE, season=None, tmdbid=200,
                             date="2024-01-01 00:00:00")
        matching = SimpleNamespace(note={"source": "movie"}, date="2024-01-02 00:00:00")
        plugin.downloadhistory_oper.get_last_by.return_value = [matching]
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 8, "tmdbid": 200, "year": "2024"}, sub)):
            assert plugin._SubscribeAssistant__get_related_download_histories(8, sub) == [matching]
