"""
SubscribeAssistant 完结探测与待定判定单测。

覆盖业务域：
- 完结探测：__check_tv_season_completed / __get_tv_latest_episode / __get_tv_season_air_date /
  __get_tv_season_episode_count / __get_tv_episodes / __get_tv_season_info / __is_same_season / __parse_date
- 待定判定：__check_tv_pending_by_mediainfo / __update_tv_pending_episodes
- 辅助：__check_subscribe_status / __resolve_subscribe_media_type
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

from app.schemas.tmdb import TmdbEpisode
from app.schemas.types import MediaType
from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def make_plugin(**overrides) -> SubscribeAssistant:
    """构造绕过 __init__ 的插件实例，按需设置逻辑方法依赖的属性。"""
    plugin = object.__new__(SubscribeAssistant)
    plugin.tmdb_chain = MagicMock()
    plugin.subscribe_oper = MagicMock()
    plugin._auto_tv_pending_days = None
    plugin._auto_tv_pending_episodes = None
    plugin._auto_update_tv_pending_episodes = None
    for k, v in overrides.items():
        setattr(plugin, k, v)
    return plugin


def make_mediainfo(*, status: str = "Returning Series", tmdb_id: int = 100,
                   season_info: Optional[list] = None, seasons: Optional[dict] = None,
                   title: str = "测试剧", title_year: str = "测试剧 (2024)",
                   type_: MediaType = MediaType.TV) -> SimpleNamespace:
    """构造 MediaInfo 最小替身。"""
    return SimpleNamespace(
        status=status, tmdb_id=tmdb_id, season_info=season_info or [],
        seasons=seasons or {}, title=title, title_year=title_year, type=type_,
    )


def make_episode(episode_number: int, *, air_date: Optional[str] = None,
                 episode_type: Optional[str] = None) -> TmdbEpisode:
    """构造 TmdbEpisode 实例。"""
    return TmdbEpisode(episode_number=episode_number, air_date=air_date,
                       episode_type=episode_type)


def make_subscribe(**kwargs) -> SimpleNamespace:
    """构造订阅替身，字段默认值对齐剧集订阅。"""
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, imdbid=None, tvdbid=None, doubanid=None, bangumiid=None,
        best_version=0, best_version_full=0, start_episode=1, total_episode=12,
        lack_episode=0, state="R", manual_total_episode=0,
        episode_priority={}, current_priority=0,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _today_str(delta_days=0):
    return (datetime.now() + timedelta(days=delta_days)).strftime("%Y-%m-%d")


# ===========================================================================
# process_tv_pending / __process_tv_pending
# ===========================================================================

class TestProcessTvPending:

    def setup_method(self):
        self.plugin = make_plugin(_auto_tv_pending=True, _auto_tv_pending_days=3,
                                  _auto_tv_pending_episodes=None,
                                  _auto_update_tv_pending_episodes=12)

    def test_process_tv_pending_returns_when_disabled(self):
        plugin = make_plugin(_auto_tv_pending=False, _auto_tv_pending_days=3,
                             _auto_tv_pending_episodes=None)
        plugin.subscribe_oper.list.return_value = [make_subscribe()]
        plugin._SubscribeAssistant__with_lock_and_update_subscribe_tasks = MagicMock()
        plugin.process_tv_pending()
        plugin._SubscribeAssistant__with_lock_and_update_subscribe_tasks.assert_not_called()

    def test_process_tv_pending_loads_all_active_states(self):
        subscribes = [make_subscribe()]
        self.plugin.subscribe_oper.list.return_value = subscribes
        with patch.object(self.plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as update:
            self.plugin.process_tv_pending()
        self.plugin.subscribe_oper.list.assert_called_once_with(state="N,R,P")
        update.assert_called_once_with(method=self.plugin._SubscribeAssistant__process_tv_pending,
                                       subscribes=subscribes)

    def test_process_tv_pending_loads_single_subscribe(self):
        subscribe = make_subscribe(id=9)
        self.plugin.subscribe_oper.get.return_value = subscribe
        with patch.object(self.plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as update:
            self.plugin.process_tv_pending(subscribe_id=9)
        self.plugin.subscribe_oper.get.assert_called_once_with(sid=9)
        update.assert_called_once_with(method=self.plugin._SubscribeAssistant__process_tv_pending,
                                       subscribes=[subscribe])

    def test_process_tv_pending_skips_ineligible_subscribes(self):
        subscribes = [
            make_subscribe(best_version=1),
            make_subscribe(state="S"),
            make_subscribe(type=MOVIE),
            make_subscribe(id=4),
            make_subscribe(id=5),
            make_subscribe(id=6),
        ]
        non_tv_media = make_mediainfo(type_=MediaType.MOVIE, season_info=[{"season_number": 1}])
        no_season_info = make_mediainfo(season_info=[])
        subscribe_tasks = {}
        with patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status",
                          side_effect=[False, True, True, True, True]), \
                patch.object(self.plugin, "_SubscribeAssistant__recognize_media",
                             side_effect=[None, non_tv_media, no_season_info]), \
                patch.object(self.plugin, "_SubscribeAssistant__initialize_subscribe_task") as initialize:
            self.plugin._SubscribeAssistant__process_tv_pending(subscribe_tasks, subscribes)
        initialize.assert_not_called()

    def test_process_tv_pending_sets_new_subscribe_to_pending_and_schedules_search(self):
        subscribe = make_subscribe(state="N")
        mediainfo = make_mediainfo(season_info=[{"season_number": 1, "episode_count": 12}])
        subscribe_task = {}
        timer = MagicMock()
        with patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_tv_pending_by_mediainfo",
                             return_value=(True, "2026-01-01")), \
                patch.object(self.plugin, "_SubscribeAssistant__initialize_subscribe_task",
                             return_value=(subscribe_task, False)), \
                patch.object(self.plugin, "_SubscribeAssistant__update_subscribe_tv_pending_task",
                             return_value=True) as update_task, \
                patch.object(self.plugin, "_SubscribeAssistant__get_subscribe_task_pending", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_subscribe_meta",
                             return_value=SimpleNamespace(season=1)), \
                patch.object(self.plugin, "_SubscribeAssistant__update_tv_pending_episodes",
                             return_value=12) as update_episodes, \
                patch.object(self.plugin, "_SubscribeAssistant__send_subscribe_status_msg") as send_msg, \
                patch("subscribeassistant.threading.Timer", return_value=timer):
            self.plugin._SubscribeAssistant__process_tv_pending({}, [(subscribe, mediainfo)])
        timer.start.assert_called_once()
        update_task.assert_called_once_with(subscribe=subscribe, subscribe_task=subscribe_task, pending=True)
        self.plugin.subscribe_oper.update.assert_called_once_with(subscribe.id, {"state": "P"})
        update_episodes.assert_called_once_with(subscribe=subscribe, mediainfo=mediainfo, tv_pending=True)
        assert "满足上映待定" in send_msg.call_args.kwargs["msg_title"]

    def test_process_tv_pending_restores_pending_subscribe_when_no_longer_pending(self):
        subscribe = make_subscribe(state="P")
        mediainfo = make_mediainfo(season_info=[{"season_number": 1, "episode_count": 12}])
        subscribe_task = {}
        with patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_tv_pending_by_mediainfo",
                             return_value=(False, "2024-01-01")), \
                patch.object(self.plugin, "_SubscribeAssistant__initialize_subscribe_task",
                             return_value=(subscribe_task, True)), \
                patch.object(self.plugin, "_SubscribeAssistant__update_subscribe_tv_pending_task",
                             return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_subscribe_task_pending", return_value=False), \
                patch.object(self.plugin, "_SubscribeAssistant__get_subscribe_meta",
                             return_value=SimpleNamespace(season=1)), \
                patch.object(self.plugin, "_SubscribeAssistant__update_tv_pending_episodes",
                             return_value=12) as update_episodes, \
                patch.object(self.plugin, "_SubscribeAssistant__send_subscribe_status_msg") as send_msg:
            self.plugin._SubscribeAssistant__process_tv_pending({}, [(subscribe, mediainfo)])
        self.plugin.subscribe_oper.update.assert_called_once_with(subscribe.id, {"state": "R"})
        update_episodes.assert_called_once_with(subscribe=subscribe, mediainfo=mediainfo, tv_pending=False)
        assert "不再满足上映待定" in send_msg.call_args.kwargs["msg_title"]

    def test_process_tv_pending_sends_message_when_task_changed_but_state_unchanged(self):
        subscribe = make_subscribe(state="R")
        mediainfo = make_mediainfo(season_info=[{"season_number": 1, "episode_count": 12}])
        with patch.object(self.plugin, "_SubscribeAssistant__check_subscribe_status", return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__check_tv_pending_by_mediainfo",
                             return_value=(False, "2024-01-01")), \
                patch.object(self.plugin, "_SubscribeAssistant__initialize_subscribe_task",
                             return_value=({}, True)), \
                patch.object(self.plugin, "_SubscribeAssistant__update_subscribe_tv_pending_task",
                             return_value=True), \
                patch.object(self.plugin, "_SubscribeAssistant__get_subscribe_task_pending", return_value=False), \
                patch.object(self.plugin, "_SubscribeAssistant__get_subscribe_meta",
                             return_value=SimpleNamespace(season=1)), \
                patch.object(self.plugin, "_SubscribeAssistant__update_tv_pending_episodes",
                             return_value=12), \
                patch.object(self.plugin, "_SubscribeAssistant__send_subscribe_status_msg") as send_msg:
            self.plugin._SubscribeAssistant__process_tv_pending({}, [(subscribe, mediainfo)])
        self.plugin.subscribe_oper.update.assert_not_called()
        send_msg.assert_called_once()


class TestSendSubscribeStatusMsg:

    def test_send_subscribe_status_msg_skips_when_notify_disabled(self):
        plugin = make_plugin(_notify=False)
        plugin.post_message = MagicMock()
        plugin._SubscribeAssistant__send_subscribe_status_msg(
            subscribe=make_subscribe(username="admin"),
            mediainfo=SimpleNamespace(type=MediaType.TV, vote_average=8.0,
                                      get_message_image=MagicMock(return_value="img")),
            msg_title="标题",
            air_day="上映日期：2024-01-01",
            episode_count=12,
        )
        plugin.post_message.assert_not_called()

    def test_send_subscribe_status_msg_builds_tv_notification_text(self):
        plugin = make_plugin(_notify=True)
        plugin.post_message = MagicMock()
        with patch("subscribeassistant.settings", SimpleNamespace(MP_DOMAIN=lambda path: path)):
            plugin._SubscribeAssistant__send_subscribe_status_msg(
                subscribe=make_subscribe(username="admin"),
                mediainfo=SimpleNamespace(type=MediaType.TV, vote_average=8.0,
                                          get_message_image=MagicMock(return_value="img")),
                msg_title="标题",
                air_day="上映日期：2024-01-01",
                episode_count=12,
            )
        kwargs = plugin.post_message.call_args.kwargs
        assert kwargs["title"] == "标题"
        assert "评分：8.0" in kwargs["text"]
        assert "来自用户：admin" in kwargs["text"]
        assert "集数更新为：12" in kwargs["text"]
        assert "subscribe/tv" in kwargs["link"]

    def test_send_subscribe_status_msg_uses_movie_link_for_movie_media(self):
        plugin = make_plugin(_notify=True)
        plugin.post_message = MagicMock()
        with patch("subscribeassistant.settings", SimpleNamespace(MP_DOMAIN=lambda path: path)):
            plugin._SubscribeAssistant__send_subscribe_status_msg(
                subscribe=make_subscribe(username=None),
                mediainfo=SimpleNamespace(type=MediaType.MOVIE, vote_average=None,
                                          get_message_image=MagicMock(return_value="img")),
                msg_title="电影标题",
            )
        kwargs = plugin.post_message.call_args.kwargs
        assert kwargs["text"] == ""
        assert "subscribe/movie" in kwargs["link"]


# ===========================================================================
# __parse_date
# ===========================================================================

class TestParseDate:

    def _call(self, day, f="%Y-%m-%d"):
        return SubscribeAssistant._SubscribeAssistant__parse_date(day, f)

    def test_valid_date(self):
        dt, day_str = self._call("2024-06-15")
        assert dt == datetime(2024, 6, 15)
        assert day_str == "2024-06-15"

    def test_empty_string(self):
        assert self._call("") == (None, None)

    def test_none_input(self):
        assert self._call(None) == (None, None)

    def test_invalid_format(self):
        dt, day_str = self._call("15/06/2024")
        assert dt is None
        assert day_str is None

    def test_custom_format(self):
        dt, day_str = self._call("15/06/2024", "%d/%m/%Y")
        assert dt == datetime(2024, 6, 15)


# ===========================================================================
# __is_same_season
# ===========================================================================

class TestIsSameSeason:

    def _call(self, season_value, season):
        return SubscribeAssistant._SubscribeAssistant__is_same_season(season_value, season)

    def test_int_match(self):
        assert self._call(1, 1)

    def test_int_mismatch(self):
        assert not self._call(1, 2)

    def test_str_vs_int(self):
        assert self._call("1", 1)

    def test_none_season_value(self):
        assert not self._call(None, 1)

    def test_none_season(self):
        assert not self._call(1, None)

    def test_both_none(self):
        assert not self._call(None, None)

    def test_non_numeric_string_match(self):
        assert self._call("abc", "abc")

    def test_non_numeric_string_mismatch(self):
        assert not self._call("abc", "def")


# ===========================================================================
# __get_tv_season_info
# ===========================================================================

class TestGetTvSeasonInfo:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, mediainfo, season):
        return self.plugin._SubscribeAssistant__get_tv_season_info(mediainfo, season)

    def test_match_by_season_number(self):
        info = {"season_number": 2, "episode_count": 12, "air_date": "2024-01-01"}
        mediainfo = make_mediainfo(season_info=[{"season_number": 1, "episode_count": 10}, info])
        assert self._call(mediainfo, 2) == info

    def test_match_by_order(self):
        info = {"order": 3, "episode_count": 8}
        mediainfo = make_mediainfo(season_info=[info])
        assert self._call(mediainfo, 3) == info

    def test_no_match(self):
        mediainfo = make_mediainfo(season_info=[{"season_number": 1}])
        assert self._call(mediainfo, 99) is None

    def test_empty_season_info(self):
        assert self._call(make_mediainfo(season_info=[]), 1) is None

    def test_none_mediainfo(self):
        assert self._call(None, 1) is None

    def test_zero_season(self):
        mediainfo = make_mediainfo(season_info=[{"season_number": 0}])
        assert self._call(mediainfo, 0) is None


# ===========================================================================
# __get_tv_episodes
# ===========================================================================

class TestGetTvEpisodes:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, mediainfo, season, episode_group=None):
        return self.plugin._SubscribeAssistant__get_tv_episodes(mediainfo, season, episode_group)

    def test_delegates_to_tmdb_chain(self):
        ep = make_episode(1, air_date="2024-01-01")
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [ep]
        result = self._call(make_mediainfo(), 1)
        assert result == [ep]
        self.plugin.tmdb_chain.tmdb_episodes.assert_called_once_with(
            tmdbid=100, season=1, episode_group=None)

    def test_with_episode_group(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = []
        self._call(make_mediainfo(), 1, episode_group="group-abc")
        self.plugin.tmdb_chain.tmdb_episodes.assert_called_once_with(
            tmdbid=100, season=1, episode_group="group-abc")

    def test_none_mediainfo_returns_empty(self):
        assert self._call(None, 1) == []

    def test_no_tmdb_id_returns_empty(self):
        assert self._call(make_mediainfo(tmdb_id=None), 1) == []

    def test_zero_season_returns_empty(self):
        assert self._call(make_mediainfo(), 0) == []


# ===========================================================================
# __get_tv_season_episode_count
# ===========================================================================

class TestGetTvSeasonEpisodeCount:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, mediainfo, season, episode_group=None):
        return self.plugin._SubscribeAssistant__get_tv_season_episode_count(
            mediainfo, season, episode_group)

    def test_from_season_info_episode_count(self):
        mediainfo = make_mediainfo(season_info=[{"season_number": 1, "episode_count": 24}])
        assert self._call(mediainfo, 1) == 24

    def test_from_season_info_episodes_list(self):
        mediainfo = make_mediainfo(season_info=[{
            "season_number": 1, "episode_count": None,
            "episodes": [{"episode_number": 1}, {"episode_number": 2}, {"episode_number": 3}]
        }])
        assert self._call(mediainfo, 1) == 3

    def test_fallback_to_tmdb_episodes(self):
        mediainfo = make_mediainfo(season_info=[])
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [make_episode(i) for i in range(1, 11)]
        assert self._call(mediainfo, 1) == 10

    def test_tmdb_episodes_filters_none_episode_number(self):
        mediainfo = make_mediainfo(season_info=[])
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(1), make_episode(None), make_episode(3)]
        assert self._call(mediainfo, 1) == 2

    def test_no_data_returns_none(self):
        mediainfo = make_mediainfo(season_info=[])
        self.plugin.tmdb_chain.tmdb_episodes.return_value = []
        assert self._call(mediainfo, 1) is None


# ===========================================================================
# __get_tv_season_air_date
# ===========================================================================

class TestGetTvSeasonAirDate:

    def setup_method(self):
        self.plugin = make_plugin()
        self.plugin.tmdb_chain.tmdb_episodes.return_value = []

    def _call(self, mediainfo, season, episode_group=None):
        return self.plugin._SubscribeAssistant__get_tv_season_air_date(
            mediainfo, season, episode_group)

    def test_from_season_info_air_date(self):
        mediainfo = make_mediainfo(season_info=[{"season_number": 1, "air_date": "2024-03-15"}])
        dt, day = self._call(mediainfo, 1)
        assert dt == datetime(2024, 3, 15)
        assert day == "2024-03-15"

    def test_from_season_info_episodes_air_date(self):
        mediainfo = make_mediainfo(season_info=[{
            "season_number": 1,
            "episodes": [
                {"episode_number": 2, "air_date": "2024-04-01"},
                {"episode_number": 1, "air_date": "2024-03-25"},
            ]
        }])
        _, day = self._call(mediainfo, 1)
        assert day == "2024-03-25"

    def test_episodes_without_episode_number_skipped(self):
        mediainfo = make_mediainfo(season_info=[{
            "season_number": 1,
            "episodes": [
                {"episode_number": None, "air_date": "2024-01-01"},
                {"episode_number": 1, "air_date": "2024-02-01"},
            ]
        }])
        _, day = self._call(mediainfo, 1)
        assert day == "2024-02-01"

    def test_fallback_to_tmdb_episodes(self):
        mediainfo = make_mediainfo(season_info=[])
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(2, air_date="2024-05-10"),
            make_episode(1, air_date="2024-05-03"),
        ]
        _, day = self._call(mediainfo, 1)
        assert day == "2024-05-03"

    def test_invalid_air_date_falls_back(self):
        mediainfo = make_mediainfo(season_info=[{"season_number": 1, "air_date": "not-a-date"}])
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [make_episode(1, air_date="2024-06-01")]
        _, day = self._call(mediainfo, 1)
        assert day == "2024-06-01"

    def test_no_data_returns_none_none(self):
        mediainfo = make_mediainfo(season_info=[])
        assert self._call(mediainfo, 1) == (None, None)

    def test_tmdb_episodes_without_air_date(self):
        mediainfo = make_mediainfo(season_info=[])
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [make_episode(1), make_episode(2)]
        assert self._call(mediainfo, 1) == (None, None)


# ===========================================================================
# __check_tv_season_completed
# ===========================================================================

class TestCheckTvSeasonCompleted:

    def setup_method(self):
        self.plugin = make_plugin()
        self.plugin.tmdb_chain.tmdb_episodes.return_value = []

    def _call(self, mediainfo, season, episode_group=None):
        return self.plugin._SubscribeAssistant__check_tv_season_completed(
            mediainfo, season, episode_group)

    def test_ended_status(self):
        assert self._call(make_mediainfo(status="Ended"), 1)

    def test_canceled_status(self):
        assert self._call(make_mediainfo(status="Canceled"), 1)

    def test_returning_with_finale(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(1, air_date="2024-01-01"),
            make_episode(12, air_date="2024-03-20", episode_type="finale"),
        ]
        assert self._call(make_mediainfo(status="Returning Series"), 1)

    def test_returning_without_finale(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(1, air_date="2024-01-01"),
            make_episode(12, air_date="2024-03-20"),
        ]
        assert not self._call(make_mediainfo(status="Returning Series"), 1)

    def test_returning_no_episodes(self):
        assert not self._call(make_mediainfo(status="Returning Series"), 1)

    def test_none_mediainfo(self):
        assert not self._call(None, 1)

    def test_no_tmdb_id(self):
        assert not self._call(make_mediainfo(tmdb_id=None), 1)

    def test_zero_season(self):
        assert not self._call(make_mediainfo(), 0)

    def test_finale_among_many_episodes(self):
        eps = [make_episode(i) for i in range(1, 25)]
        eps[-1] = make_episode(24, episode_type="finale")
        self.plugin.tmdb_chain.tmdb_episodes.return_value = eps
        assert self._call(make_mediainfo(status="Returning Series"), 1)

    def test_mid_season_finale(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(10, episode_type="mid_season_finale")]
        assert not self._call(make_mediainfo(status="Returning Series"), 1)

    def test_scenario_P1_returning_no_finale(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(i, air_date="2024-01-01") for i in range(1, 144)]
        assert not self._call(make_mediainfo(status="Returning Series"), 1)

    def test_scenario_P3_wrong_ended(self):
        assert self._call(make_mediainfo(status="Ended"), 1)

    def test_scenario_H1_season_done_show_returning(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(i, air_date="2023-01-01") for i in range(1, 13)]
        assert not self._call(make_mediainfo(status="Returning Series"), 1)


# ===========================================================================
# __get_tv_latest_episode
# ===========================================================================

class TestGetTvLatestEpisode:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, mediainfo, season, episode_group=None):
        return self.plugin._SubscribeAssistant__get_tv_latest_episode(
            mediainfo, season, episode_group)

    def test_latest_and_next(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(1, air_date=_today_str(-14)),
            make_episode(2, air_date=_today_str(-7)),
            make_episode(3, air_date=_today_str(7)),
        ]
        latest, next_ep = self._call(make_mediainfo(), 1)
        assert latest.episode_number == 2
        assert next_ep.episode_number == 3

    def test_all_aired(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(1, air_date=_today_str(-14)),
            make_episode(2, air_date=_today_str(-7)),
            make_episode(3, air_date=_today_str(-1)),
        ]
        latest, next_ep = self._call(make_mediainfo(), 1)
        assert latest.episode_number == 3
        assert next_ep is None

    def test_none_aired(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(1, air_date=_today_str(7)),
            make_episode(2, air_date=_today_str(14)),
        ]
        latest, _ = self._call(make_mediainfo(), 1)
        assert latest is None

    def test_no_air_date_skipped(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(1, air_date=_today_str(-7)),
            make_episode(2),
            make_episode(3, air_date=_today_str(7)),
        ]
        latest, next_ep = self._call(make_mediainfo(), 1)
        assert latest.episode_number == 1
        assert next_ep.episode_number == 3

    def test_none_episode_number_skipped(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(None, air_date=_today_str(-7)),
            make_episode(1, air_date=_today_str(-3)),
        ]
        latest, _ = self._call(make_mediainfo(), 1)
        assert latest.episode_number == 1

    def test_empty_episodes(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = []
        assert self._call(make_mediainfo(), 1) == (None, None)

    def test_none_mediainfo(self):
        assert self._call(None, 1) == (None, None)

    def test_invalid_air_date_skipped(self):
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [
            make_episode(1, air_date="not-a-date"),
            make_episode(2, air_date=_today_str(-3)),
        ]
        latest, _ = self._call(make_mediainfo(), 1)
        assert latest.episode_number == 2


# ===========================================================================
# __check_tv_pending_by_mediainfo
# ===========================================================================

class TestCheckTvPendingByMediainfo:

    def setup_method(self):
        self.plugin = make_plugin()
        self.plugin.tmdb_chain.tmdb_episodes.return_value = []

    def _call(self, subscribe, mediainfo):
        return self.plugin._SubscribeAssistant__check_tv_pending_by_mediainfo(subscribe, mediainfo)

    def test_completed_show_not_pending(self):
        self.plugin._auto_tv_pending_days = 30
        mediainfo = make_mediainfo(status="Ended", season_info=[
            {"season_number": 1, "episode_count": 12, "air_date": _today_str(10)}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert not pending

    def test_completed_by_finale_not_pending(self):
        self.plugin._auto_tv_pending_days = 30
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 12, "air_date": _today_str(10)}])
        self.plugin.tmdb_chain.tmdb_episodes.return_value = [make_episode(12, episode_type="finale")]
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert not pending

    def test_pending_by_days_within_window(self):
        self.plugin._auto_tv_pending_days = 30
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 24, "air_date": _today_str(-10)}])
        pending, air_day = self._call(make_subscribe(), mediainfo)
        assert pending
        assert air_day is not None

    def test_not_pending_days_expired(self):
        self.plugin._auto_tv_pending_days = 5
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 24, "air_date": _today_str(-10)}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert not pending

    def test_days_not_configured(self):
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 24, "air_date": _today_str(10)}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert not pending

    def test_pending_by_episode_count(self):
        self.plugin._auto_tv_pending_episodes = 5
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 3}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert pending

    def test_not_pending_episode_count_above_threshold(self):
        self.plugin._auto_tv_pending_episodes = 5
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 12}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert not pending

    def test_episode_count_equal_threshold(self):
        self.plugin._auto_tv_pending_episodes = 5
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 5}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert pending

    def test_both_conditions_met(self):
        self.plugin._auto_tv_pending_days = 30
        self.plugin._auto_tv_pending_episodes = 5
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 3, "air_date": _today_str(-5)}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert pending

    def test_only_days_met(self):
        self.plugin._auto_tv_pending_days = 30
        self.plugin._auto_tv_pending_episodes = 2
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 12, "air_date": _today_str(-5)}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert pending

    def test_only_episodes_met(self):
        self.plugin._auto_tv_pending_days = 5
        self.plugin._auto_tv_pending_episodes = 10
        mediainfo = make_mediainfo(status="Returning Series", season_info=[
            {"season_number": 1, "episode_count": 3, "air_date": _today_str(-30)}])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert pending

    def test_no_air_date_no_episode_count(self):
        self.plugin._auto_tv_pending_days = 30
        self.plugin._auto_tv_pending_episodes = 5
        mediainfo = make_mediainfo(status="Returning Series", season_info=[])
        pending, _ = self._call(make_subscribe(), mediainfo)
        assert not pending


# ===========================================================================
# __update_tv_pending_episodes
# ===========================================================================

class TestUpdateTvPendingEpisodes:

    def setup_method(self):
        self.plugin = make_plugin()
        self.plugin.tmdb_chain.tmdb_episodes.return_value = []

    def _call(self, subscribe, mediainfo, tv_pending):
        return self.plugin._SubscribeAssistant__update_tv_pending_episodes(
            subscribe, mediainfo, tv_pending)

    def test_config_not_set_returns_none(self):
        result = self._call(make_subscribe(), make_mediainfo(), True)
        assert result is None
        self.plugin.subscribe_oper.update.assert_not_called()

    def test_pending_true_uses_config_value(self):
        self.plugin._auto_update_tv_pending_episodes = 6
        sub = make_subscribe(total_episode=12, lack_episode=0)
        result = self._call(sub, make_mediainfo(), True)
        assert result == 6
        call_args = self.plugin.subscribe_oper.update.call_args
        payload = call_args[1] if call_args[1] else call_args[0][1]
        assert payload["manual_total_episode"] == 1
        assert payload["total_episode"] == 6

    def test_pending_false_restores_real_count(self):
        self.plugin._auto_update_tv_pending_episodes = 6
        mediainfo = make_mediainfo(season_info=[{"season_number": 1, "episode_count": 24}])
        sub = make_subscribe(total_episode=6, lack_episode=0)
        result = self._call(sub, mediainfo, False)
        assert result == 24
        call_args = self.plugin.subscribe_oper.update.call_args
        payload = call_args[1] if call_args[1] else call_args[0][1]
        assert payload["manual_total_episode"] == 0
        assert payload["total_episode"] == 24

    def test_lack_episode_adjusted(self):
        self.plugin._auto_update_tv_pending_episodes = 6
        sub = make_subscribe(total_episode=12, lack_episode=5)
        self._call(sub, make_mediainfo(), True)
        call_args = self.plugin.subscribe_oper.update.call_args
        payload = call_args[1] if call_args[1] else call_args[0][1]
        assert payload["lack_episode"] == -1

    def test_zero_episode_count_no_update(self):
        self.plugin._auto_update_tv_pending_episodes = 6
        mediainfo = make_mediainfo(season_info=[])
        sub = make_subscribe(total_episode=6, lack_episode=0)
        self._call(sub, mediainfo, False)
        call_args = self.plugin.subscribe_oper.update.call_args
        payload = call_args[1] if call_args[1] else call_args[0][1]
        assert "total_episode" not in payload


# ===========================================================================
# __check_subscribe_status / __resolve_subscribe_media_type
# ===========================================================================

class TestCheckSubscribeStatus:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe):
        return self.plugin._SubscribeAssistant__check_subscribe_status(subscribe)

    def test_state_N(self):
        assert self._call(make_subscribe(state="N"))

    def test_state_R(self):
        assert self._call(make_subscribe(state="R"))

    def test_state_P(self):
        assert self._call(make_subscribe(state="P"))

    def test_state_S_rejected(self):
        assert not self._call(make_subscribe(state="S"))

    def test_state_empty_rejected(self):
        assert not self._call(make_subscribe(state=""))

    def test_none_subscribe(self):
        assert not self._call(None)

    def test_invalid_media_type(self):
        assert not self._call(make_subscribe(type="INVALID"))

    def test_movie_type_allowed(self):
        assert self._call(make_subscribe(type=MOVIE, state="R"))


class TestResolveSubscribeMediaType:

    def _call(self, subscribe):
        return SubscribeAssistant._SubscribeAssistant__resolve_subscribe_media_type(subscribe)

    def test_tv_string(self):
        assert self._call(make_subscribe(type=TV)) == MediaType.TV

    def test_movie_string(self):
        assert self._call(make_subscribe(type=MOVIE)) == MediaType.MOVIE

    def test_mediatype_enum(self):
        assert self._call(make_subscribe(type=MediaType.TV)) == MediaType.TV

    def test_none_subscribe(self):
        assert self._call(None) == MediaType.UNKNOWN

    def test_none_type(self):
        assert self._call(make_subscribe(type=None)) == MediaType.UNKNOWN

    def test_empty_string(self):
        assert self._call(make_subscribe(type="")) == MediaType.UNKNOWN

    def test_whitespace_string(self):
        assert self._call(make_subscribe(type="  ")) == MediaType.UNKNOWN

    def test_invalid_string(self):
        assert self._call(make_subscribe(type="INVALID")) == MediaType.UNKNOWN
