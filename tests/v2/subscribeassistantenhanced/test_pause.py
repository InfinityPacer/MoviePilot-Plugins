"""pause/ 暂停管理单测。"""
import time
from types import SimpleNamespace
from datetime import date, timedelta
from unittest.mock import MagicMock

from app.schemas.types import MediaType

from subscribeassistantenhanced.pause.airing import AiringPauseChecker
from subscribeassistantenhanced.pause.manager import PauseManager
from subscribeassistantenhanced.pause.nodownload import NoDownloadPolicy
from subscribeassistantenhanced.engine.types import CompletionSignal, PauseRecord


def _sub(sid=1, state="R", username="", media_type="电视剧"):
    return SimpleNamespace(
        id=sid,
        state=state,
        username=username,
        tmdbid=100,
        season=1,
        episode_group=None,
        type=media_type,
        name="测试剧",
        start_episode=1,
        total_episode=12,
        lack_episode=0,
        note=[],
        episode_priority={},
        date=None,
        last_update=None,
    )


def _ep(air_date, episode_number=1, season_number=1):
    return SimpleNamespace(
        air_date=air_date,
        episode_number=episode_number,
        season_number=season_number,
    )


def test_clear_pause_record_drops_metadata_without_state_change():
    """clear_pause_record 丢弃插件暂停元数据，但不调用 subscribe_oper 改订阅状态。"""
    store = {"subscribes": {"9": {"pause_reason": "airing_gap", "pause_since": 1.0, "pause_detail": "x"}}}
    oper = MagicMock()
    mgr = PauseManager(
        task_data_read=lambda k: store.get(k, {}),
        task_data_update=lambda k, fn: store.__setitem__(k, fn(store.get(k, {}))),
        subscribe_oper=oper,
    )
    mgr.clear_pause_record(_sub(sid=9))
    task = store["subscribes"]["9"]
    assert "pause_reason" not in task and "pause_since" not in task and "pause_detail" not in task
    oper.update.assert_not_called()


# ---------- AiringPauseChecker ----------

class TestAiringPause:

    def test_pre_air_pauses_movie_before_release(self):
        """电影距离上映窗口较远时暂停。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=7,
            tv_air_days=0,
        )
        mediainfo = SimpleNamespace(release_date="2026-01-31")

        result = checker.check_pre_air(
            _sub(media_type="电影"),
            mediainfo,
            as_of=date(2026, 1, 1),
        )

        assert result is not None
        assert result.reason == "pre_air"
        assert result.detail == "上映日期：2026-01-31，距今 30 天，暂未到订阅窗口"

    def test_pre_air_within_window_returns_none(self):
        """电影进入上映前订阅窗口后不暂停。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=7,
            tv_air_days=0,
        )
        mediainfo = SimpleNamespace(release_date="2026-01-04")

        result = checker.check_pre_air(
            _sub(media_type="电影"),
            mediainfo,
            as_of=date(2026, 1, 1),
        )

        assert result is None

    def test_pre_air_pauses_tv_before_air(self):
        """电视剧距离目标季开播窗口较远时暂停。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=0,
            tv_air_days=5,
        )
        mediainfo = SimpleNamespace(
            season_info=[{"season_number": 1, "air_date": "2026-02-01"}],
            first_air_date="2026-01-20",
        )

        result = checker.check_pre_air(
            _sub(),
            mediainfo,
            as_of=date(2026, 1, 1),
        )

        assert result is not None
        assert result.reason == "pre_air"
        assert result.detail == "开播日期：2026-02-01，距今 31 天，暂未到订阅窗口"

    def test_pre_air_tv_falls_back_to_first_scope_episode_air_date(self):
        """剧集季日期和首播日期缺失时，使用当前分集范围 E01 日期判断开播窗口。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=0,
            tv_air_days=5,
        )
        mediainfo = SimpleNamespace(season_info=[], first_air_date=None)

        result = checker.check_pre_air(
            _sub(),
            mediainfo,
            as_of=date(2026, 1, 1),
            episodes=[
                _ep("2026-02-02", episode_number=2),
                _ep("2026-02-01", episode_number=1),
            ],
        )

        assert result is not None
        assert result.reason == "pre_air"
        assert result.detail == "开播日期：2026-02-01，距今 31 天，暂未到订阅窗口"

    def test_pre_air_tv_episode_group_fallback_ignores_original_season_number(self):
        """剧集组分集已由调用方按组缩窄，E01 fallback 不再按原始 season_number 过滤。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=0,
            tv_air_days=5,
        )
        subscribe = _sub()
        subscribe.season = 2
        subscribe.episode_group = "eg-1"
        mediainfo = SimpleNamespace(season_info=[], first_air_date=None)

        result = checker.check_pre_air(
            subscribe,
            mediainfo,
            as_of=date(2026, 1, 1),
            episodes=[_ep("2026-02-01", episode_number=1, season_number=1)],
        )

        assert result is not None
        assert result.detail == "开播日期：2026-02-01，距今 31 天，暂未到订阅窗口"

    def test_pre_air_tv_missing_all_air_dates_does_not_pause(self):
        """剧集季日期、首播日期和 E01 日期都缺失时不做未知日期暂停。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=0,
            tv_air_days=5,
        )
        mediainfo = SimpleNamespace(season_info=[], first_air_date=None)

        result = checker.check_pre_air(
            _sub(),
            mediainfo,
            as_of=date(2026, 1, 1),
            episodes=[_ep(None, episode_number=1)],
        )

        assert result is None

    def test_pre_air_unknown_media_type_returns_none(self):
        """未知媒体类型不走电影或剧集上映前暂停，避免脏数据被误暂停。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=7,
            tv_air_days=5,
        )
        mediainfo = SimpleNamespace(
            release_date="2026-02-01",
            season_info=[{"season_number": 1, "air_date": "2026-02-01"}],
            first_air_date="2026-02-01",
        )

        result = checker.check_pre_air(
            _sub(media_type=MediaType.UNKNOWN),
            mediainfo,
            as_of=date(2026, 1, 1),
        )

        assert result is None

    def test_pre_air_zero_days_disabled(self):
        """电影上映前暂停天数为零时关闭该规则。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=0,
            tv_air_days=0,
        )
        mediainfo = SimpleNamespace(release_date="2026-12-31")

        result = checker.check_pre_air(
            _sub(media_type="电影"),
            mediainfo,
            as_of=date(2026, 1, 1),
        )

        assert result is None

    def test_completed_signal_no_pause(self):
        """完结信号确认 → 不暂停。"""
        evaluate = MagicMock(return_value=CompletionSignal(completed=True))
        checker = AiringPauseChecker(pause_days=14, evaluate_fn=evaluate)
        result = checker.check(_sub(), None, next_episode=_ep("2027-01-01"), latest_episode=None)
        assert result is None

    def test_next_episode_far_away_pauses(self):
        """下一集超阈值 → 暂停。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=14, evaluate_fn=evaluate)
        far = (date(2026, 6, 1) + timedelta(days=30)).isoformat()
        result = checker.check(_sub(), None, next_episode=_ep(far), latest_episode=None,
                               as_of=date(2026, 6, 1))
        assert result is not None
        assert result.reason == "airing_gap"
        assert result.detail == "下一集日期：2026-07-01，距今 30 天"

    def test_next_episode_dict_far_away_pauses(self):
        """下一集为 TMDB dict 形态时，仍按 air_date 判断播出间隔。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=14, evaluate_fn=evaluate)
        far = (date(2026, 6, 1) + timedelta(days=30)).isoformat()
        result = checker.check(_sub(), None, next_episode={"air_date": far}, latest_episode=None,
                               as_of=date(2026, 6, 1))
        assert result is not None
        assert result.reason == "airing_gap"

    def test_next_episode_near_no_pause(self):
        """下一集在阈值内 → 不暂停。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=14, evaluate_fn=evaluate)
        near = (date(2026, 6, 1) + timedelta(days=5)).isoformat()
        result = checker.check(_sub(), None, next_episode=_ep(near), latest_episode=None,
                               as_of=date(2026, 6, 1))
        assert result is None

    def test_stale_same_day_aggregate_falls_back_to_scope_first_missing_episode(self):
        """聚合字段停留在当天已播集时，按分集表中的订阅首缺集判断播出间隔。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 92
        subscribe.note = list(range(1, 88))
        episodes = [
            _ep("2026-06-14", episode_number=87),
            _ep("2026-06-21", episode_number=88),
            _ep("2026-06-28", episode_number=89),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-14", episode_number=87),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 14),
        )

        assert result is not None
        assert result.reason == "airing_gap"
        assert result.detail == "下一集日期：2026-06-21，距今 7 天"

    def test_future_scope_episode_does_not_pause_when_it_is_not_first_missing(self):
        """未来排期不是订阅首缺集时不暂停，避免冻结仍有早期缺集可搜索的订阅。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 12
        subscribe.lack_episode = 2
        subscribe.note = [1, 2, 3, 4, 6, 7, 8, 9, 10, 11]
        episodes = [
            _ep("2026-01-01", episode_number=5),
            _ep("2026-06-21", episode_number=12),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-21", episode_number=12),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 14),
        )

        assert result is None

    def test_inventory_caught_up_uses_future_episode_when_note_has_historical_gap(self):
        """媒体库实缺只剩未来集时，note 历史空洞不应阻止播出暂停。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 92
        subscribe.lack_episode = 5
        subscribe.note = list(range(31, 88))
        episodes = [
            _ep("2026-06-14", episode_number=87),
            _ep("2026-06-21", episode_number=88),
            _ep("2026-06-28", episode_number=89),
            _ep("2026-07-05", episode_number=90),
            _ep("2026-07-12", episode_number=91),
            _ep("2026-07-19", episode_number=92),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-14", episode_number=87),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 14),
        )

        assert result is not None
        assert result.reason == "airing_gap"
        assert "2026-06-21" in result.detail

    def test_short_window_does_not_pause_before_same_day_episode_is_ingested(self):
        """当天已播集尚未入库时，短窗口配置不应提前暂停。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 92
        subscribe.lack_episode = 6
        subscribe.note = list(range(31, 87))
        episodes = [
            _ep("2026-06-15", episode_number=87),
            _ep("2026-06-21", episode_number=88),
            _ep("2026-06-28", episode_number=89),
            _ep("2026-07-05", episode_number=90),
            _ep("2026-07-12", episode_number=91),
            _ep("2026-07-19", episode_number=92),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-15", episode_number=87),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 15),
        )

        assert result is None

    def test_short_window_pauses_after_same_day_episode_is_ingested(self):
        """当天已播集入库后，短窗口配置应立即暂停等待下一集。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 92
        subscribe.lack_episode = 5
        subscribe.note = list(range(31, 88))
        episodes = [
            _ep("2026-06-15", episode_number=87),
            _ep("2026-06-21", episode_number=88),
            _ep("2026-06-28", episode_number=89),
            _ep("2026-07-05", episode_number=90),
            _ep("2026-07-12", episode_number=91),
            _ep("2026-07-19", episode_number=92),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-15", episode_number=87),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 15),
        )

        assert result is not None
        assert result.reason == "airing_gap"
        assert "2026-06-21" in result.detail

    def test_inventory_fallback_requires_lack_to_match_future_count(self):
        """媒体库实缺数量少于未来排期时不按库存口径暂停，避免陈旧缺集数量误判。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 92
        subscribe.lack_episode = 4
        subscribe.note = list(range(31, 88))
        episodes = [
            _ep("2026-06-14", episode_number=87),
            _ep("2026-06-21", episode_number=88),
            _ep("2026-06-28", episode_number=89),
            _ep("2026-07-05", episode_number=90),
            _ep("2026-07-12", episode_number=91),
            _ep("2026-07-19", episode_number=92),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-14", episode_number=87),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 14),
        )

        assert result is None

    def test_inventory_fallback_counts_manual_total_tail_without_tmdb_schedule(self):
        """手动总集数大于 TMDB 已知排期时，尾部未知集也属于实缺未来目标。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 95
        subscribe.lack_episode = 8
        subscribe.note = list(range(31, 88))
        episodes = [
            _ep("2026-06-14", episode_number=87),
            _ep("2026-06-21", episode_number=88),
            _ep("2026-06-28", episode_number=89),
            _ep("2026-07-05", episode_number=90),
            _ep("2026-07-12", episode_number=91),
            _ep("2026-07-19", episode_number=92),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-14", episode_number=87),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 14),
        )

        assert result is not None
        assert result.reason == "airing_gap"
        assert "2026-06-21" in result.detail

    def test_airing_gap_resumes_when_next_episode_reaches_airing_day_with_historical_note_gap(self):
        """下一集已到播出日时，即使 note 有历史空洞也应明确释放播出暂停。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 92
        subscribe.lack_episode = 5
        subscribe.note = list(range(31, 88))
        episodes = [
            _ep("2026-06-21", episode_number=88),
            _ep("2026-06-28", episode_number=89),
            _ep("2026-07-05", episode_number=90),
            _ep("2026-07-12", episode_number=91),
            _ep("2026-07-19", episode_number=92),
        ]

        result = checker.should_resume_airing_gap(
            subscribe,
            None,
            next_episode=None,
            episodes=episodes,
            as_of=date(2026, 6, 21),
        )

        assert result is True

    def test_airing_gap_resumes_when_check_runs_after_next_episode_air_day(self):
        """巡检晚于下一集播出日时，已进入窗口的锚点集仍应释放播出暂停。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 92
        subscribe.lack_episode = 5
        subscribe.note = list(range(31, 88))
        episodes = [
            _ep("2026-06-21", episode_number=88),
            _ep("2026-06-28", episode_number=89),
            _ep("2026-07-05", episode_number=90),
            _ep("2026-07-12", episode_number=91),
            _ep("2026-07-19", episode_number=92),
        ]

        result = checker.should_resume_airing_gap(
            subscribe,
            None,
            next_episode=None,
            episodes=episodes,
            current_record=PauseRecord(reason="airing_gap", detail="下一集 2026-06-21，距今 7 天"),
            as_of=date(2026, 6, 23),
        )

        assert result is True

    def test_deleted_downloaded_episode_does_not_override_note(self):
        """已下载集即使从媒体库删除，播出暂停仍按 note 推导首个待下载集。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.total_episode = 12
        subscribe.note = list(range(1, 12))
        episodes = [
            _ep("2026-01-01", episode_number=5),
            _ep("2026-06-21", episode_number=12),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-21", episode_number=12),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 14),
        )

        assert result is not None
        assert result.reason == "airing_gap"
        assert "2026-06-21" in result.detail

    def test_episode_best_version_uses_positive_priority_as_downloaded(self):
        """分集洗版已有任意优先级版本的集不再作为首待下载集。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=1, evaluate_fn=evaluate)
        subscribe = _sub()
        subscribe.best_version = 1
        subscribe.best_version_full = 0
        subscribe.total_episode = 12
        subscribe.note = list(range(1, 11))
        subscribe.episode_priority = {"11": 10}
        episodes = [
            _ep("2026-01-01", episode_number=11),
            _ep("2026-06-21", episode_number=12),
        ]

        result = checker.check(
            subscribe,
            None,
            next_episode=_ep("2026-06-21", episode_number=12),
            latest_episode=episodes[0],
            episodes=episodes,
            as_of=date(2026, 6, 14),
        )

        assert result is not None
        assert result.reason == "airing_gap"
        assert "2026-06-21" in result.detail

    def test_no_next_last_old_no_pause(self):
        """无下一集 + 最后集超阈值不再直接暂停，避免历史季全缺被搜索前冻结。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=14, evaluate_fn=evaluate)
        old = (date(2026, 6, 1) - timedelta(days=30)).isoformat()
        result = checker.check(_sub(), None, next_episode=None, latest_episode=_ep(old),
                               as_of=date(2026, 6, 1))
        assert result is None

    def test_latest_episode_dict_old_no_pause(self):
        """最后集为 TMDB dict 形态时，也不因无下一集直接暂停。"""
        evaluate = MagicMock(return_value=CompletionSignal())
        checker = AiringPauseChecker(pause_days=14, evaluate_fn=evaluate)
        old = (date(2026, 6, 1) - timedelta(days=30)).isoformat()
        result = checker.check(_sub(), None, next_episode=None, latest_episode={"air_date": old},
                               as_of=date(2026, 6, 1))
        assert result is None

    def test_pre_air_unknown_date_pauses_when_movie_air_days_configured(self):
        """电影上映日期无法解析且 movie_air_days 已配置时，默认暂停等待。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=7,
            tv_air_days=0,
        )
        # release_date 为 None，无法解析
        mediainfo = SimpleNamespace(release_date=None)
        result = checker.check_pre_air(_sub(media_type="电影"), mediainfo)
        assert result is not None
        assert result.reason == "pre_air"

    def test_pre_air_unknown_date_returns_none_when_movie_air_days_zero(self):
        """电影上映日期无法解析但 movie_air_days=0（规则未开）时，不暂停。"""
        checker = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(),
            movie_air_days=0,
            tv_air_days=0,
        )
        mediainfo = SimpleNamespace(release_date=None)
        result = checker.check_pre_air(_sub(media_type="电影"), mediainfo)
        assert result is None


# ---------- NoDownloadPolicy ----------

class TestNoDownloadPolicy:
    """无下载处理策略按媒体类型、期限和配置动作顺序给出结果。"""

    def test_overdue_movie_without_download_completes(self):
        """电影上映后超过期限且无下载时执行完成动作。"""
        policy = NoDownloadPolicy(movie_days=365, actions=["complete_movie"])
        mediainfo = SimpleNamespace(release_date=(date.today() - timedelta(days=400)).isoformat())

        result = policy.evaluate(_sub(media_type="电影"), mediainfo, last_download_date=None)

        assert result == "complete"

    def test_overdue_movie_detail_includes_release_and_deadline_context(self):
        """电影无下载命中原因展示上映日期、无下载截止日和超期天数。"""
        policy = NoDownloadPolicy(movie_days=30, actions=["complete_movie"])
        mediainfo = SimpleNamespace(release_date="2025-01-01")

        decision = policy.evaluate_detail(
            _sub(media_type="电影"),
            mediainfo,
            last_download_date=None,
            as_of=date(2025, 2, 10),
        )

        assert decision.action == "complete"
        assert decision.reason == "上映日期：2025-01-01，已过 40 天，无下载截止日：2025-01-31，已超过 10 天"

    def test_recent_download_pushes_out_deadline(self):
        """最近下载日期晚于上映日期时，以最近下载日期重新计算期限。"""
        policy = NoDownloadPolicy(movie_days=365, actions=["complete_movie"])
        mediainfo = SimpleNamespace(release_date=(date.today() - timedelta(days=400)).isoformat())

        result = policy.evaluate(
            _sub(media_type="电影"),
            mediainfo,
            last_download_date=date.today() - timedelta(days=10),
        )

        assert result is None

    def test_within_window_returns_none(self):
        """上映后仍在配置期限内时不执行动作。"""
        policy = NoDownloadPolicy(movie_days=30, actions=["complete_movie"])
        mediainfo = SimpleNamespace(release_date=(date.today() - timedelta(days=29)).isoformat())

        result = policy.evaluate(_sub(media_type="电影"), mediainfo, last_download_date=None)

        assert result is None

    def test_overdue_tv_without_download_deletes(self):
        """目标季开播后超过期限且无下载时执行删除动作。"""
        policy = NoDownloadPolicy(tv_days=180, actions=["delete_tv"])
        mediainfo = SimpleNamespace(
            season_info=[{
                "season_number": 1,
                "air_date": (date.today() - timedelta(days=181)).isoformat(),
            }],
            first_air_date=None,
        )

        result = policy.evaluate(_sub(), mediainfo, last_download_date=None)

        assert result == "delete"

    def test_unknown_media_type_no_action(self):
        """未知媒体类型不套用电影或剧集无下载动作。"""
        policy = NoDownloadPolicy(
            movie_days=180,
            tv_days=180,
            actions=["delete_tv", "complete_movie"],
        )
        mediainfo = SimpleNamespace(
            release_date=(date.today() - timedelta(days=181)).isoformat(),
            season_info=[{
                "season_number": 1,
                "air_date": (date.today() - timedelta(days=181)).isoformat(),
            }],
            first_air_date=(date.today() - timedelta(days=181)).isoformat(),
        )

        result = policy.evaluate(_sub(media_type=MediaType.UNKNOWN), mediainfo, last_download_date=None)

        assert result is None

    def test_first_configured_action_wins(self):
        """同一媒体类型配置多个动作时按配置顺序取第一个。"""
        policy = NoDownloadPolicy(tv_days=180, actions=["pause_tv", "delete_tv"])
        mediainfo = SimpleNamespace(
            season_info=[{
                "season_number": 1,
                "air_date": (date.today() - timedelta(days=181)).isoformat(),
            }],
            first_air_date=None,
        )

        result = policy.evaluate(_sub(), mediainfo, last_download_date=None)

        assert result == "pause"


# ---------- PauseManager ----------

class TestPauseManager:

    def _make_manager(self, store=None, auto_users=None, notify=None):
        store = store if store is not None else {}
        mgr = PauseManager(
            task_data_read=lambda key: store.get(key, {}),
            task_data_update=lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
            subscribe_oper=MagicMock(),
            auto_pause_users=auto_users,
            notify_fn=notify,
        )
        mgr._store = store
        return mgr

    def test_pause_writes_record(self):
        mgr = self._make_manager()
        mgr.pause(_sub(), PauseRecord(reason="airing_gap", detail="test"))
        rec = mgr.get_pause_record(_sub())
        assert rec is not None
        assert rec.reason == "airing_gap"

    def test_airing_gap_overrides_pre_air(self):
        """播出间隔暂停优先于上映前暂停。"""
        mgr = self._make_manager()
        mgr.pause(_sub(), PauseRecord(reason="pre_air"))
        mgr.pause(_sub(), PauseRecord(reason="airing_gap"))
        rec = mgr.get_pause_record(_sub())
        assert rec.reason == "airing_gap"

    def test_pre_air_does_not_override_airing_gap(self):
        """上映前暂停不覆盖已有播出间隔暂停。"""
        mgr = self._make_manager()
        mgr.pause(_sub(), PauseRecord(reason="airing_gap"))
        mgr.pause(_sub(), PauseRecord(reason="pre_air"))
        rec = mgr.get_pause_record(_sub())
        assert rec.reason == "airing_gap"

    def test_resume_clears_airing_gap(self):
        mgr = self._make_manager()
        mgr.pause(_sub(), PauseRecord(reason="airing_gap"))
        assert mgr.resume(_sub()) is True
        assert mgr.get_pause_record(_sub()) is None

    def test_resume_clears_any_reason_record(self):
        """恢复会清理插件侧标记并把订阅置回启用态。"""
        mgr = self._make_manager()
        mgr.pause(_sub(), PauseRecord(reason="auto_user"))
        assert mgr.resume(_sub()) is True
        assert mgr.get_pause_record(_sub()) is None
        payload = mgr._subscribe_oper.update.call_args.args[1]
        assert payload["state"] == "R"
        assert payload["last_update"]

    def test_no_record_state_s_returns_none(self):
        """无插件暂停记录时即便 state=S 也返回 None，不合成外部暂停。"""
        mgr = self._make_manager()
        assert mgr.get_pause_record(_sub(state="S")) is None

    def test_auto_pause_for_user_uses_auto_user_reason(self):
        """按用户名自动暂停写入 auto_user 原因（可被上映检查与 resume 视为标记暂停处理）。"""
        mgr = self._make_manager(auto_users=["testuser"])
        assert mgr.check_auto_pause_for_user(_sub(username="testuser")) is True
        rec = mgr.get_pause_record(_sub())
        assert rec.reason == "auto_user"

    def test_pause_sends_status_notification_for_airing_rule(self):
        """播出类暂停应发送状态通知。"""
        notify = MagicMock()
        mgr = self._make_manager(notify=notify)

        mgr.pause(_sub(), PauseRecord(reason="airing_gap", detail="即将播出日期：2026-07-01"))

        notify.assert_called_once()
        assert "满足订阅暂停，已标记暂停" in notify.call_args.args[1]

    def test_no_download_pause_does_not_duplicate_notification(self):
        """无下载流程由巡检统一通知，PauseManager 不重复发送。"""
        notify = MagicMock()
        mgr = self._make_manager(notify=notify)

        mgr.pause(_sub(), PauseRecord(reason="no_download", detail="无下载"))

        notify.assert_not_called()

    def test_resume_sends_status_notification(self):
        """插件暂停恢复应发送状态通知。"""
        notify = MagicMock()
        mgr = self._make_manager(notify=notify)
        sub = _sub()
        mgr.pause(sub, PauseRecord(reason="airing_gap", detail="即将播出日期：2026-07-01"))
        notify.reset_mock()

        assert mgr.resume(sub) is True

        notify.assert_called_once()
        assert "不再满足订阅暂停，已标记订阅中" in notify.call_args.args[1]

    def test_resume_notification_does_not_reuse_stale_pause_detail(self):
        """恢复通知正文应描述当前恢复动作，不复用旧暂停窗口说明。"""
        notify = MagicMock()
        mgr = self._make_manager(notify=notify)
        sub = _sub()
        mgr.pause(sub, PauseRecord(reason="pre_air", detail="开播日期：2026-06-25，距今 20 天，暂未到订阅窗口"))
        notify.reset_mock()

        assert mgr.resume(sub) is True

        notify.assert_called_once()
        assert "不再满足订阅暂停，已标记订阅中" in notify.call_args.args[1]
        assert notify.call_args.kwargs["detail"] == "开播日期：2026-06-25，已进入订阅窗口"

    def test_resume_notification_strips_legacy_media_type_prefix(self):
        """恢复旧暂停记录时不重复输出媒体类型前缀。"""
        notify = MagicMock()
        mgr = self._make_manager(notify=notify)
        sub = _sub()
        mgr.pause(sub, PauseRecord(reason="pre_air", detail="电视剧 2026-06-25 开播，暂未到订阅窗口"))
        notify.reset_mock()

        assert mgr.resume(sub) is True

        notify.assert_called_once()
        assert notify.call_args.kwargs["detail"] == "2026-06-25 开播，已进入订阅窗口"

    def test_resume_notification_keeps_airing_gap_date(self):
        """播出暂停恢复通知应保留下一集日期。"""
        notify = MagicMock()
        mgr = self._make_manager(notify=notify)
        sub = _sub()
        mgr.pause(sub, PauseRecord(reason="airing_gap", detail="下一集日期：2026-07-01，距今 30 天"))
        notify.reset_mock()

        assert mgr.resume(sub) is True

        notify.assert_called_once()
        assert "不再满足订阅暂停，已标记订阅中" in notify.call_args.args[1]
        assert notify.call_args.kwargs["detail"] == "下一集日期：2026-07-01，已进入播出窗口"

    def test_auto_pause_for_user_sends_status_notification(self):
        """用户名自动暂停应发送状态通知。"""
        notify = MagicMock()
        mgr = self._make_manager(auto_users=["testuser"], notify=notify)

        assert mgr.check_auto_pause_for_user(_sub(username="testuser")) is True

        notify.assert_called_once()
        assert "满足订阅暂停，已标记暂停" in notify.call_args.args[1]

    def test_auto_pause_no_match(self):
        mgr = self._make_manager(auto_users=["other"])
        assert mgr.check_auto_pause_for_user(_sub(username="testuser")) is False
