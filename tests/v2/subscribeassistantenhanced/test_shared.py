"""shared/ 工具函数单测——log.py + subscribe.py + media.py 补充覆盖。"""
from datetime import date
from types import SimpleNamespace

from subscribeassistantenhanced.shared.log import truncate_log_value, format_log_title_desc
from subscribeassistantenhanced.shared.subscribe import (
    format_subscribe, format_subscribe_desc, match_subscribe,
)
from subscribeassistantenhanced.shared.media import (
    parse_date, is_same_season, get_tv_season_info,
    get_tv_season_episode_count, get_tv_season_air_date,
    count_aired_episodes, last_aired_episode, all_aired,
)


# ---------- log.py ----------

class TestTruncateLogValue:

    def test_short_value_unchanged(self):
        assert truncate_log_value("hello") == "hello"

    def test_long_value_truncated(self):
        result = truncate_log_value("x" * 200, max_length=50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_middle_truncation(self):
        result = truncate_log_value("x" * 200, max_length=50, middle=True)
        assert "..." in result
        assert len(result) == 50

    def test_none_value(self):
        assert truncate_log_value(None) == ""

    def test_exact_length(self):
        assert truncate_log_value("12345", max_length=5) == "12345"


class TestFormatLogTitleDesc:

    def test_title_and_desc(self):
        result = format_log_title_desc("Title", "Desc")
        assert "Title" in result
        assert "Desc" in result

    def test_title_only(self):
        result = format_log_title_desc("Title")
        assert result == "Title"

    def test_desc_only(self):
        result = format_log_title_desc(description="Desc")
        assert result == "Desc"

    def test_long_truncated(self):
        result = format_log_title_desc("x" * 300, max_length=100)
        assert len(result) <= 100


# ---------- subscribe.py ----------

class TestFormatSubscribe:

    def test_with_season(self):
        sub = SimpleNamespace(name="测试剧", season=2)
        assert format_subscribe(sub) == "测试剧 S2"

    def test_without_season(self):
        sub = SimpleNamespace(name="测试剧", season=None)
        assert format_subscribe(sub) == "测试剧"

class TestFormatSubscribeDesc:

    def test_with_total(self):
        sub = SimpleNamespace(name="测试", season=1, total_episode=12, lack_episode=3)
        result = format_subscribe_desc(sub)
        assert "9/12" in result

    def test_no_total(self):
        sub = SimpleNamespace(name="测试", season=1, total_episode=0, lack_episode=0)
        result = format_subscribe_desc(sub)
        assert "测试" in result


class TestMatchSubscribe:

    def test_match(self):
        sub = SimpleNamespace(id=1, name="测试", tmdbid=100, season=1, episode_group=None)
        task = {"id": 1, "name": "测试", "tmdbid": 100, "season": 1}
        assert match_subscribe(sub, task) is True

    def test_mismatch_id(self):
        sub = SimpleNamespace(id=1, name="测试", tmdbid=100, season=1, episode_group=None)
        task = {"id": 2, "name": "测试", "tmdbid": 100, "season": 1}
        assert match_subscribe(sub, task) is False

    def test_empty_task(self):
        sub = SimpleNamespace(id=1, name="测试", tmdbid=100, season=1, episode_group=None)
        assert match_subscribe(sub, {}) is False
        assert match_subscribe(sub, None) is False

    def test_episode_group_mismatch(self):
        sub = SimpleNamespace(id=1, name="测试", tmdbid=100, season=1, episode_group="eg-1")
        task = {"id": 1, "name": "测试", "tmdbid": 100, "season": 1}
        assert match_subscribe(sub, task) is False


# ---------- media.py 补充 ----------

class TestParseDate:

    def test_valid_date(self):
        assert parse_date("2026-06-01") == date(2026, 6, 1)

    def test_invalid_date(self):
        assert parse_date("not-a-date") is None

    def test_none(self):
        assert parse_date(None) is None

    def test_empty(self):
        assert parse_date("") is None


class TestIsSameSeason:

    def test_match(self):
        assert is_same_season({"season_number": 1}, 1) is True

    def test_no_match(self):
        assert is_same_season({"season_number": 2}, 1) is False


class TestGetTvSeasonInfo:

    def test_found(self):
        mi = SimpleNamespace(season_info=[{"season_number": 1, "episode_count": 12}])
        info = get_tv_season_info(mi, 1)
        assert info["episode_count"] == 12

    def test_not_found(self):
        mi = SimpleNamespace(season_info=[{"season_number": 2}])
        assert get_tv_season_info(mi, 1) is None

    def test_empty(self):
        mi = SimpleNamespace(season_info=[])
        assert get_tv_season_info(mi, 1) is None

    def test_none_season_info(self):
        mi = SimpleNamespace(season_info=None)
        assert get_tv_season_info(mi, 1) is None


class TestGetTvSeasonEpisodeCount:

    def test_found(self):
        mi = SimpleNamespace(season_info=[{"season_number": 1, "episode_count": 24}])
        assert get_tv_season_episode_count(mi, 1) == 24

    def test_not_found(self):
        mi = SimpleNamespace(season_info=[])
        assert get_tv_season_episode_count(mi, 1) == 0


class TestGetTvSeasonAirDate:

    def test_found(self):
        mi = SimpleNamespace(season_info=[{"season_number": 1, "air_date": "2026-01-15"}])
        assert get_tv_season_air_date(mi, 1) == "2026-01-15"

    def test_not_found(self):
        mi = SimpleNamespace(season_info=[])
        assert get_tv_season_air_date(mi, 1) is None


class TestMediaHelpers:

    def test_count_aired(self):
        eps = [
            SimpleNamespace(air_date="2026-01-01"),
            SimpleNamespace(air_date="2026-06-01"),
            SimpleNamespace(air_date="2027-01-01"),
        ]
        assert count_aired_episodes(eps, as_of=date(2026, 6, 15)) == 2

    def test_count_aired_no_date(self):
        eps = [SimpleNamespace(air_date=None)]
        assert count_aired_episodes(eps) == 0

    def test_last_aired(self):
        eps = [
            SimpleNamespace(air_date="2026-01-01", episode_number=1),
            SimpleNamespace(air_date="2026-03-01", episode_number=2),
            SimpleNamespace(air_date="2027-01-01", episode_number=3),
        ]
        result = last_aired_episode(eps, as_of=date(2026, 6, 1))
        assert result.episode_number == 2

    def test_last_aired_none(self):
        assert last_aired_episode([], as_of=date(2026, 6, 1)) is None

    def test_all_aired_true(self):
        eps = [SimpleNamespace(air_date="2026-01-01"), SimpleNamespace(air_date="2026-02-01")]
        assert all_aired(eps, as_of=date(2026, 6, 1)) is True

    def test_all_aired_false_future(self):
        eps = [SimpleNamespace(air_date="2026-01-01"), SimpleNamespace(air_date="2027-01-01")]
        assert all_aired(eps, as_of=date(2026, 6, 1)) is False

    def test_all_aired_empty(self):
        assert all_aired([], as_of=date(2026, 6, 1)) is False

    def test_all_aired_no_date(self):
        eps = [SimpleNamespace(air_date=None)]
        assert all_aired(eps, as_of=date(2026, 6, 1)) is False
