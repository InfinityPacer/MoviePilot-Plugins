"""shared/ 工具函数单测——log.py + subscribe.py + media.py 补充覆盖。"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.shared.log import truncate_log_value, format_log_title_desc
from subscribeassistantenhanced.shared.subscribe import (
    format_subscribe, format_subscribe_desc, format_subscribe_label, match_subscribe,
    identity_matches, pending_subscription_episodes, resolve_subscribe_media_type,
    subscribe_from_source, subscribe_identity, is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
)
from subscribeassistantenhanced.shared.update import update_subscribe
from subscribeassistantenhanced.shared.media import (
    parse_date, is_same_season, get_tv_season_info,
    get_tv_season_air_date,
    count_aired_episodes, last_aired_episode, all_aired,
    episode_candidates_after, resolve_airing_next_episode,
    resolve_inventory_next_episodes, target_episode_range,
    unknown_tail_episode_count,
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

    def test_with_special_season_zero(self):
        sub = SimpleNamespace(name="测试剧", season=0)
        assert format_subscribe(sub) == "测试剧 S0"

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


class TestPendingSubscriptionEpisodes:

    def test_episode_best_version_uses_note_and_positive_priority(self):
        """按集订阅统一合并下载历史和正优先级状态。"""
        subscribe = SimpleNamespace(
            start_episode=3,
            total_episode=7,
            note=[3, "4"],
            episode_priority={"5": 10, "6": 0, "7": 100},
        )

        assert pending_subscription_episodes(subscribe) == [6]

    def test_invalid_priority_values_are_ignored(self):
        """非法优先级不应让未下载集被误判为已存在版本。"""
        subscribe = SimpleNamespace(
            start_episode=1,
            total_episode=3,
            note=["x"],
            episode_priority={"1": "bad", "2": None, "3": -1},
        )

        assert pending_subscription_episodes(subscribe) == [1, 2, 3]


class TestBestVersionSubscribeSemantics:
    """洗版订阅形态判断区分电影、剧集全集和剧集分集。"""

    def _sub(self, **kwargs):
        defaults = {
            "type": "电视剧",
            "best_version": 0,
            "best_version_full": 0,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_movie_best_version_is_full_best_version_subscribe(self):
        """电影 best_version 是真正的洗版订阅，不依赖 best_version_full。"""
        subscribe = self._sub(type="电影", best_version=1, best_version_full=0)

        assert is_full_best_version_subscribe(subscribe) is True
        assert is_tv_episode_best_version_subscribe(subscribe) is False

    def test_tv_full_best_version_is_full_best_version_subscribe(self):
        """剧集 best_version + best_version_full 是全集洗版订阅。"""
        subscribe = self._sub(type="电视剧", best_version=1, best_version_full=1)

        assert is_full_best_version_subscribe(subscribe) is True
        assert is_tv_episode_best_version_subscribe(subscribe) is False

    def test_tv_episode_best_version_is_not_full_best_version_subscribe(self):
        """剧集 best_version 且非 best_version_full 是分集洗版订阅。"""
        subscribe = self._sub(type="电视剧", best_version=1, best_version_full=0)

        assert is_full_best_version_subscribe(subscribe) is False
        assert is_tv_episode_best_version_subscribe(subscribe) is True

    def test_normal_subscriptions_are_not_best_version_subscribe(self):
        """普通订阅不属于任何洗版订阅形态。"""
        for media_type in ("电影", "电视剧"):
            subscribe = self._sub(type=media_type, best_version=0, best_version_full=0)

            assert is_full_best_version_subscribe(subscribe) is False
            assert is_tv_episode_best_version_subscribe(subscribe) is False


class TestFormatSubscribeLabel:

    def test_named_subscribe_includes_id(self):
        sub = SimpleNamespace(id=1, name="测试剧", season=2)
        assert format_subscribe_label(sub) == "测试剧 S2(id=1)"

    def test_id_only_fallback(self):
        assert format_subscribe_label(subscribe_id=9) == "订阅 9"

    def test_missing_subscribe_fallback(self):
        assert format_subscribe_label() == "未知订阅"

    def test_broken_subscribe_falls_back_to_id(self):
        """订阅对象字段不完整时仍应保留 ID，避免日志标签直接异常。"""
        sub = SimpleNamespace(id=8)

        assert format_subscribe_label(sub) == "订阅 8"


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


class TestSubscribeIdentity:

    def test_resolve_media_type_accepts_enum_string_and_invalid(self):
        """媒体类型解析应兼容枚举、字符串和异常值。"""
        assert resolve_subscribe_media_type(SimpleNamespace(type="电视剧")).value == "电视剧"
        assert resolve_subscribe_media_type(SimpleNamespace(type="bad")).value == "未知"
        assert resolve_subscribe_media_type(None).value == "未知"

    def test_identity_matches_current_subscribe(self):
        """持久化身份必须完整匹配当前订阅，避免 ID 复用串状态。"""
        subscribe = SimpleNamespace(id=1, tmdbid=100, season=1, episode_group="eg-1")
        identity = subscribe_identity(subscribe)

        assert identity_matches(identity, subscribe) is True
        assert identity_matches({**identity, "episode_group": "eg-2"}, subscribe) is False
        assert identity_matches({}, subscribe) is False

    def test_subscribe_from_source_parses_valid_origin(self):
        """Subscribe|json 来源应解析快照并读取当前订阅。"""
        subscribe = SimpleNamespace(id=1)
        oper = MagicMock()
        oper.get.return_value = subscribe

        data, current = subscribe_from_source('Subscribe|{"id": 1, "name": "测试"}', oper)

        assert data == {"id": 1, "name": "测试"}
        assert current is subscribe

    def test_subscribe_from_source_rejects_invalid_origin(self):
        """非订阅来源、坏 JSON 或缺少订阅 ID 时按空结果处理。"""
        oper = MagicMock()

        assert subscribe_from_source("Manual|{}", oper) == (None, None)
        assert subscribe_from_source("Subscribe|{bad", oper) == (None, None)
        assert subscribe_from_source("Subscribe|{}", oper) == (None, None)


class TestUpdateSubscribe:

    def test_missing_oper_skips_update(self):
        """订阅写库依赖缺失时跳过，避免事件补偿链路报错。"""
        assert update_subscribe(None, 1, {"state": "R"}) is None


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

    def test_episode_group_order_match(self):
        assert is_same_season({"order": 2}, 2) is True


class TestGetTvSeasonInfo:

    def test_found(self):
        mi = SimpleNamespace(season_info=[{"season_number": 1, "episode_count": 12}])
        info = get_tv_season_info(mi, 1)
        assert info["episode_count"] == 12

    def test_episode_group_order_found(self):
        mi = SimpleNamespace(season_info=[{"order": 2, "episode_count": 10}])
        info = get_tv_season_info(mi, 2)
        assert info["episode_count"] == 10

    def test_not_found(self):
        mi = SimpleNamespace(season_info=[{"season_number": 2}])
        assert get_tv_season_info(mi, 1) is None

    def test_empty(self):
        mi = SimpleNamespace(season_info=[])
        assert get_tv_season_info(mi, 1) is None

    def test_none_season_info(self):
        mi = SimpleNamespace(season_info=None)
        assert get_tv_season_info(mi, 1) is None


class TestGetTvSeasonAirDate:

    def test_found(self):
        mi = SimpleNamespace(season_info=[{"season_number": 1, "air_date": "2026-01-15"}])
        assert get_tv_season_air_date(mi, 1) == "2026-01-15"

    def test_not_found(self):
        mi = SimpleNamespace(season_info=[])
        assert get_tv_season_air_date(mi, 1) is None


class TestMediaHelpers:

    def test_target_episode_range_rejects_invalid_range(self):
        """订阅目标范围无效时不应推导出待下载集。"""
        subscribe = SimpleNamespace(start_episode=5, total_episode=3)

        assert target_episode_range(subscribe) == []

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

    def test_unknown_tail_counts_only_current_season_known_episodes(self):
        """尾部未知集数只参考当前季已知集，避免跨季集数影响暂停判断。"""
        subscribe = SimpleNamespace(season=1, start_episode=1, total_episode=5)
        episodes = [
            SimpleNamespace(season_number=2, episode_number=99, air_date="2026-01-01"),
            SimpleNamespace(season_number=1, episode_number=3, air_date="2026-01-01"),
        ]

        assert unknown_tail_episode_count(subscribe, episodes) == 2

    def test_unknown_tail_keeps_special_season_zero_boundary(self):
        """特别季 S0 必须与主季分开计算未知尾集。"""
        subscribe = SimpleNamespace(season=0, start_episode=1, total_episode=5)
        episodes = [
            SimpleNamespace(season_number=1, episode_number=99, air_date="2026-01-01"),
            SimpleNamespace(season_number=0, episode_number=3, air_date="2026-01-01"),
        ]

        assert unknown_tail_episode_count(subscribe, episodes) == 2

    def test_episode_candidates_after_skips_other_season_and_outside_target(self):
        """后续播出候选必须同时属于当前季和订阅目标范围。"""
        subscribe = SimpleNamespace(season=1, start_episode=2, total_episode=3)
        episodes = [
            SimpleNamespace(season_number=2, episode_number=2, air_date="2026-07-01"),
            SimpleNamespace(season_number=1, episode_number=1, air_date="2026-07-01"),
            SimpleNamespace(season_number=1, episode_number=2, air_date="2026-07-01"),
        ]

        assert episode_candidates_after(subscribe, episodes, date(2026, 6, 1)) == [episodes[2]]

    def test_episode_candidates_after_keeps_special_season_zero_boundary(self):
        """特别季 S0 的后续播出候选不能混入主季分集。"""
        subscribe = SimpleNamespace(season=0, start_episode=2, total_episode=3)
        episodes = [
            SimpleNamespace(season_number=1, episode_number=2, air_date="2026-07-01"),
            SimpleNamespace(season_number=0, episode_number=2, air_date="2026-07-01"),
        ]

        assert episode_candidates_after(subscribe, episodes, date(2026, 6, 1)) == [episodes[1]]

    def test_inventory_next_episodes_rejects_missing_invalid_or_negative_lack_count(self):
        """媒体库实缺数量不可用时，不应把后续播出候选误判为可暂停依据。"""
        episodes = [SimpleNamespace(season_number=1, episode_number=2, air_date="2026-07-01")]

        for lack_episode in (None, "bad", -1):
            subscribe = SimpleNamespace(
                season=1,
                start_episode=1,
                total_episode=2,
                lack_episode=lack_episode,
                note=[1],
                episode_priority={},
            )

            assert resolve_inventory_next_episodes(subscribe, episodes, as_of=date(2026, 6, 1)) == []


class TestResolveAiringNextEpisode:

    def test_valid_aggregate_candidate_is_kept(self):
        """聚合下一集匹配首待下载集和后续播出日期时，播出暂停可继续使用该候选。"""
        subscribe = SimpleNamespace(
            season=1, start_episode=1, total_episode=3,
            note=[1], episode_priority={}, lack_episode=2,
        )
        aggregate = SimpleNamespace(season_number=1, episode_number=2, air_date="2026-06-21")
        episodes = [
            SimpleNamespace(season_number=1, episode_number=2, air_date="2026-06-21"),
            SimpleNamespace(season_number=1, episode_number=3, air_date="2026-06-28"),
        ]

        result = resolve_airing_next_episode(
            subscribe, aggregate, episodes, as_of=date(2026, 6, 14)
        )

        assert result is aggregate

    def test_special_season_zero_rejects_other_season_aggregate(self):
        """S0 订阅的聚合下一集必须仍属于 S0，否则回退到当前季分集表。"""
        subscribe = SimpleNamespace(
            season=0, start_episode=1, total_episode=3,
            note=[1], episode_priority={}, lack_episode=2,
        )
        aggregate = SimpleNamespace(season_number=1, episode_number=2, air_date="2026-06-21")
        episodes = [
            SimpleNamespace(season_number=0, episode_number=2, air_date="2026-06-21"),
            SimpleNamespace(season_number=0, episode_number=3, air_date="2026-06-28"),
        ]

        result = resolve_airing_next_episode(
            subscribe, aggregate, episodes, as_of=date(2026, 6, 14)
        )

        assert result is episodes[0]

    def test_stale_aggregate_falls_back_to_episode_list(self):
        """聚合字段停留在已播集时，播出暂停回退到分集表中的首待下载集。"""
        subscribe = SimpleNamespace(
            season=1, start_episode=1, total_episode=3,
            note=[1], episode_priority={}, lack_episode=2,
        )
        aggregate = SimpleNamespace(season_number=1, episode_number=1, air_date="2026-06-14")
        episodes = [
            SimpleNamespace(season_number=1, episode_number=2, air_date="2026-06-21"),
            SimpleNamespace(season_number=1, episode_number=3, air_date="2026-06-28"),
        ]

        result = resolve_airing_next_episode(
            subscribe, aggregate, episodes, as_of=date(2026, 6, 14)
        )

        assert result is episodes[0]

    def test_invalid_aggregate_without_inventory_fallback_returns_none(self):
        """聚合下一集缺少播出日期且无分集表候选时，不进入播出暂停。"""
        subscribe = SimpleNamespace(
            season=1, start_episode=1, total_episode=3,
            note=[1], episode_priority={}, lack_episode=2,
        )
        aggregate = SimpleNamespace(season_number=1, episode_number=2, air_date=None)

        result = resolve_airing_next_episode(
            subscribe, aggregate, [], as_of=date(2026, 6, 14)
        )

        assert result is None
