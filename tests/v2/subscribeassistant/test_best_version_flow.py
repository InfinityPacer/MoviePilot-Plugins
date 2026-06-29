"""
SubscribeAssistant 洗版流程单测（扩展覆盖）。

覆盖洗版流程中 test_best_version.py 未覆盖的方法：
- 目标集数范围 / 分集洗版判定 / 待定任务判定 / 状态集数提取
- 缺失集判断 / 完成标记 / 回填前置条件 / 载荷构造
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.db.subscribe_oper import Subscribe
from app.schemas.mediaserver import NotExistMediaInfo
from app.schemas.subscribe import Subscribe as SchemaSubscribe
from app.schemas.types import MediaType
from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value
MOVIE = MediaType.MOVIE.value


def make_plugin(**overrides) -> SubscribeAssistant:
    plugin = object.__new__(SubscribeAssistant)
    plugin.tmdb_chain = MagicMock()
    plugin.subscribe_oper = MagicMock()
    plugin.plugin_name = "订阅助手"
    plugin._download_pending_hash_grace_seconds = 600
    for k, v in overrides.items():
        setattr(plugin, k, v)
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    base = dict(
        id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
        tmdbid=100, imdbid=None, tvdbid=None, doubanid=None, bangumiid=None,
        best_version=1, best_version_full=0, start_episode=1, total_episode=12,
        lack_episode=0, state="R", manual_total_episode=0,
        note=[], episode_priority={}, current_priority=0, username="test",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def make_mediainfo(type_=MediaType.TV, **kwargs) -> SimpleNamespace:
    base = dict(
        type=type_, tmdb_id=100, title="测试剧", title_year="测试剧 (2024)",
        status="Returning Series", season_info=[], seasons={},
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


# ===========================================================================
# __get_best_version_target_episodes
# ===========================================================================

class TestGetBestVersionTargetEpisodes:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe):
        return self.plugin._SubscribeAssistant__get_best_version_target_episodes(subscribe)

    def test_standard_range(self):
        assert self._call(make_subscribe(start_episode=1, total_episode=12)) == list(range(1, 13))

    def test_custom_start(self):
        assert self._call(make_subscribe(start_episode=5, total_episode=10)) == list(range(5, 11))

    def test_start_none_defaults_to_1(self):
        assert self._call(make_subscribe(start_episode=None, total_episode=3)) == [1, 2, 3]

    def test_total_zero_returns_empty(self):
        assert self._call(make_subscribe(total_episode=0)) == []

    def test_total_none_returns_empty(self):
        assert self._call(make_subscribe(total_episode=None)) == []

    def test_total_less_than_start_returns_empty(self):
        assert self._call(make_subscribe(start_episode=5, total_episode=3)) == []

    def test_movie_returns_empty(self):
        assert self._call(make_subscribe(type=MOVIE)) == []

    def test_start_zero_clamped_to_1(self):
        assert self._call(make_subscribe(start_episode=0, total_episode=3)) == [1, 2, 3]

    def test_start_negative_clamped_to_1(self):
        assert self._call(make_subscribe(start_episode=-1, total_episode=3)) == [1, 2, 3]

    def test_invalid_episode_range_returns_empty(self):
        assert self._call(make_subscribe(start_episode="bad", total_episode=3)) == []
        assert self._call(make_subscribe(start_episode=1, total_episode="bad")) == []


# ===========================================================================
# __is_episode_best_version_subscribe
# ===========================================================================

class TestIsEpisodeBestVersionSubscribe:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe):
        return self.plugin._SubscribeAssistant__is_episode_best_version_subscribe(subscribe)

    def test_valid_episode_best_version(self):
        assert self._call(make_subscribe(best_version=1, best_version_full=0, total_episode=12))

    def test_full_best_version_excluded(self):
        assert not self._call(make_subscribe(best_version=1, best_version_full=1, total_episode=12))

    def test_not_best_version(self):
        assert not self._call(make_subscribe(best_version=0))

    def test_movie_excluded(self):
        assert not self._call(make_subscribe(type=MOVIE))

    def test_no_target_episodes(self):
        assert not self._call(make_subscribe(total_episode=0))

    def test_none_subscribe(self):
        assert not self._call(None)


# ===========================================================================
# __get_episode_best_version_state_episodes
# ===========================================================================

class TestGetEpisodeBestVersionStateEpisodes:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe):
        return self.plugin._SubscribeAssistant__get_episode_best_version_state_episodes(subscribe)

    def test_from_note_only(self):
        sub = make_subscribe(note=[1, 3, 5], total_episode=5, episode_priority={})
        assert self._call(sub) == [1, 3, 5]

    def test_from_episode_priority_only(self):
        sub = make_subscribe(note=[], total_episode=5, episode_priority={"1": 80, "3": 90})
        assert self._call(sub) == [1, 3]

    def test_combined_dedup(self):
        sub = make_subscribe(note=[1, 2], total_episode=5, episode_priority={"2": 80, "4": 90})
        assert self._call(sub) == [1, 2, 4]

    def test_priority_zero_excluded(self):
        sub = make_subscribe(note=[], total_episode=5, episode_priority={"1": 0, "2": 80})
        assert self._call(sub) == [2]

    def test_priority_none_excluded(self):
        sub = make_subscribe(note=[], total_episode=5, episode_priority={"1": None, "2": 80})
        assert self._call(sub) == [2]

    def test_out_of_range_excluded(self):
        sub = make_subscribe(note=[1, 99], total_episode=5, episode_priority={"100": 80})
        assert self._call(sub) == [1]

    def test_note_non_list(self):
        sub = make_subscribe(note="not-a-list", total_episode=5, episode_priority={"1": 80})
        assert self._call(sub) == [1]

    def test_episode_priority_non_dict(self):
        sub = make_subscribe(note=[1], total_episode=5, episode_priority="not-a-dict")
        assert self._call(sub) == [1]

    def test_no_target_episodes_returns_empty(self):
        assert self._call(make_subscribe(note=[1, 2], total_episode=0)) == []

    def test_sorted_output(self):
        sub = make_subscribe(note=[5, 3, 1], total_episode=5, episode_priority={})
        assert self._call(sub) == [1, 3, 5]

    def test_invalid_state_values_are_ignored(self):
        sub = make_subscribe(
            note=[1, "bad", None],
            total_episode=5,
            episode_priority={"2": "80", "3": "bad", "x": 90},
        )
        assert self._call(sub) == [1, 2]


# ===========================================================================
# __is_subscribe_target_no_lefts
# ===========================================================================

class TestIsSubscribeTargetNoLefts:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe, no_exists, mediakey, state_episodes):
        return self.plugin._SubscribeAssistant__is_subscribe_target_no_lefts(
            subscribe, no_exists, mediakey, state_episodes)

    def test_no_exists_empty_returns_false(self):
        assert not self._call(make_subscribe(total_episode=3), {}, 100, [1, 2, 3])

    def test_no_exists_none_returns_false(self):
        assert not self._call(make_subscribe(total_episode=3), None, 100, [])

    def test_no_target_episodes_returns_false(self):
        assert not self._call(make_subscribe(total_episode=0), {100: {1: None}}, 100, [])

    def test_mediakey_not_in_no_exists(self):
        assert not self._call(make_subscribe(total_episode=3), {999: {}}, 100, [])

    def test_season_not_in_no_exists_all_covered(self):
        assert self._call(make_subscribe(total_episode=3), {100: {2: None}}, 100, [1, 2, 3])

    def test_season_not_in_no_exists_without_state_returns_false(self):
        assert not self._call(make_subscribe(total_episode=3), {100: {2: None}}, 100, [])

    def test_empty_episode_list_uses_start_total_range(self):
        no_exist_season = NotExistMediaInfo(
            season=1, episodes=[], total_episode=5, start_episode=2)
        assert not self._call(make_subscribe(start_episode=1, total_episode=5),
                              {100: {1: no_exist_season}}, 100, [1, 2, 3])
        assert self._call(make_subscribe(start_episode=1, total_episode=5),
                          {100: {1: no_exist_season}}, 100, [1, 2, 3, 4, 5])

    def test_has_missing_episodes(self):
        no_exist_season = NotExistMediaInfo(
            season=1, episodes=[4, 5], total_episode=5, start_episode=1)
        assert not self._call(make_subscribe(total_episode=5), {100: {1: no_exist_season}}, 100, [1, 2, 3])

    def test_all_covered_by_state(self):
        no_exist_season = NotExistMediaInfo(
            season=1, episodes=[4, 5], total_episode=5, start_episode=1)
        assert self._call(make_subscribe(total_episode=5), {100: {1: no_exist_season}}, 100, [1, 2, 3, 4, 5])


# ===========================================================================
# __mark_best_version_subscription_complete
# ===========================================================================

class TestMarkBestVersionSubscriptionComplete:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe):
        self.plugin._SubscribeAssistant__mark_best_version_subscription_complete(subscribe)

    @patch("subscribeassistant.SubscribeChain")
    def test_tv_uses_main_backfill_contract(self, mock_chain_cls):
        sub = make_subscribe(start_episode=1, total_episode=3)
        self._call(sub)
        mock_chain_cls.return_value.backfill_existing_episodes.assert_called_once_with(
            sub,
            [1, 2, 3],
            priority=100,
            scene="plugin_complete<订阅助手>",
        )
        self.plugin.subscribe_oper.update.assert_not_called()

    def test_movie_writes_current_priority_only(self):
        self._call(make_subscribe(type=MOVIE, total_episode=0))
        payload = self.plugin.subscribe_oper.update.call_args[1]["payload"]
        assert payload["current_priority"] == 100
        assert "episode_priority" not in payload
        assert "lack_episode" not in payload


# ===========================================================================
# __should_backfill_priority
# ===========================================================================

class TestShouldBackfillPriority:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe):
        return self.plugin._SubscribeAssistant__should_backfill_priority(subscribe)

    def test_valid_candidate(self):
        assert self._call(make_subscribe(best_version=1, best_version_full=0, total_episode=12, tmdbid=100))

    def test_not_best_version(self):
        assert not self._call(make_subscribe(best_version=0))

    def test_full_best_version(self):
        assert not self._call(make_subscribe(best_version=1, best_version_full=1))

    def test_movie(self):
        assert not self._call(make_subscribe(type=MOVIE))

    def test_no_season(self):
        assert not self._call(make_subscribe(season=None))

    def test_zero_total(self):
        assert not self._call(make_subscribe(total_episode=0))

    def test_invalid_season_or_total(self):
        assert not self._call(make_subscribe(season="bad"))
        assert not self._call(make_subscribe(total_episode="bad"))

    def test_no_media_id(self):
        assert not self._call(make_subscribe(tmdbid=None, doubanid=None))

    def test_none_subscribe(self):
        assert not self._call(None)

    def test_doubanid_sufficient(self):
        assert self._call(make_subscribe(
            best_version=1, best_version_full=0, total_episode=12, tmdbid=None, doubanid="12345"))


# ===========================================================================
# 载荷构造
# ===========================================================================

class TestSanitizeSubscribePayload:

    def _call(self, d):
        return SubscribeAssistant._SubscribeAssistant__sanitize_subscribe_payload(d)

    def test_known_fields_kept(self):
        payload = self._call({"name": "test", "tmdbid": 100})
        assert "name" in payload
        assert "tmdbid" in payload

    def test_unknown_fields_removed(self):
        payload = self._call({"name": "test", "_internal_junk": 42})
        assert "_internal_junk" not in payload

    def test_none_input(self):
        assert self._call(None) == {}

    def test_empty_dict(self):
        assert self._call({}) == {}


class TestDropBestVersionMediaFields:

    def _call(self, d):
        SubscribeAssistant._SubscribeAssistant__drop_best_version_media_fields(d)
        return d

    def test_media_fields_removed(self):
        payload = {"name": "test", "year": "2024", "tmdbid": 100, "season": 1, "best_version": 1}
        result = self._call(payload)
        assert "name" not in result
        assert "year" not in result
        assert "tmdbid" not in result
        assert "season" in result
        assert "best_version" in result

    def test_missing_fields_no_error(self):
        assert self._call({"season": 1}) == {"season": 1}


class TestBuildBestVersionPayload:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe_dict, mediainfo, force_full_tv=False):
        return self.plugin._SubscribeAssistant__build_best_version_payload(
            subscribe_dict, mediainfo, force_full_tv)

    def test_basic_tv_payload(self):
        d = {"id": 1, "name": "test", "season": 1, "total_episode": 12, "type": TV, "year": "2024", "tmdbid": 100}
        result = self._call(d, make_mediainfo())
        assert result["best_version"] == 1
        assert result["state"] == "N"
        assert "id" not in result
        assert result["lack_episode"] == 12
        assert result["username"] == "订阅助手"

    def test_force_full_tv(self):
        d = {"season": 1, "total_episode": 12, "type": TV, "episode_priority": {"1": 80}}
        result = self._call(d, make_mediainfo(), force_full_tv=True)
        assert result.get("best_version_full") == 1
        assert "episode_priority" not in result

    def test_episode_group_removed(self):
        d = {"season": 1, "total_episode": 12, "type": TV, "episode_group": "abc"}
        result = self._call(d, make_mediainfo())
        assert "episode_group" not in result


class TestBuildRestoreSubscribePayload:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, d):
        return self.plugin._SubscribeAssistant__build_restore_subscribe_payload(d)

    def test_only_subscribe_model_fields(self):
        d = {"id": 1, "name": "test", "tmdbid": 100, "_random_junk": "bad"}
        result = self._call(d)
        assert "name" in result
        assert "_random_junk" not in result

    def test_none_input(self):
        assert self._call(None) == {}


# ===========================================================================
# __has_pending_subscribe_task
# ===========================================================================

class TestHasPendingSubscribeTask:

    def setup_method(self):
        self.plugin = make_plugin()

    def _call(self, subscribe):
        return self.plugin._SubscribeAssistant__has_pending_subscribe_task(subscribe)

    def test_state_P_returns_true(self):
        assert self._call(make_subscribe(state="P"))

    def test_none_subscribe(self):
        assert not self._call(None)

    def test_no_task_data(self):
        with patch.object(self.plugin, '_SubscribeAssistant__get_data', return_value={}):
            assert not self._call(make_subscribe(state="R"))

    def test_task_has_pending(self):
        task = {
            "1": {
                "id": 1, "name": "测试剧", "season": 1,
                "tmdbid": 100, "episode_group": None,
                "tv_pending": True, "torrent_tasks": []
            }
        }
        with patch.object(self.plugin, '_SubscribeAssistant__get_data', return_value=task):
            assert self._call(make_subscribe(state="R"))

    def test_task_no_pending(self):
        task = {
            "1": {
                "id": 1, "name": "测试剧", "season": 1,
                "tmdbid": 100, "episode_group": None,
                "tv_pending": False, "torrent_tasks": []
            }
        }
        with patch.object(self.plugin, '_SubscribeAssistant__get_data', return_value=task):
            assert not self._call(make_subscribe(state="R"))
