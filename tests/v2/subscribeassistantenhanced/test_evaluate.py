"""engine/evaluate.py 合并逻辑单测。"""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.engine.evaluate import evaluate
from subscribeassistantenhanced.engine.volatility import VolatilityTracker
from subscribeassistantenhanced.shared.config import PluginConfig
from subscribeassistantenhanced.shared.task import TaskDataManager


def _ep(num, ep_type="standard", air_date="2026-01-01", season=1):
    return SimpleNamespace(
        episode_number=num, season_number=season,
        air_date=air_date, episode_type=ep_type, name=f"E{num}",
    )


def _mi(status="Returning Series", next_ep=None, seasons=None):
    return SimpleNamespace(
        tmdb_id=100,
        tmdb_info=SimpleNamespace(
            status=status,
            next_episode_to_air=next_ep,
            last_episode_to_air=None,
            seasons=seasons or [SimpleNamespace(season_number=1)],
        ),
    )


def _make_tracker(stable=True):
    store = {}
    mgr = TaskDataManager(get_data_fn=lambda k: store.get(k), save_data_fn=lambda k, v: store.__setitem__(k, v))
    tracker = VolatilityTracker(mgr, window_days=7)
    if not stable:
        subscribe = SimpleNamespace(
            id=1, tmdbid=100, season=1, episode_group=None
        )
        tracker.record(total=10, subscribe=subscribe)
        tracker.record(total=15, subscribe=subscribe)
    return tracker


def _sub(sid=1, season=1, episode_group=None, best_version=0, name="测试剧"):
    return SimpleNamespace(
        id=sid, name=name, tmdbid=100, season=season,
        episode_group=episode_group, best_version=best_version,
    )


def _cfg(**overrides):
    return PluginConfig(overrides)


def _tmdb_fn(episodes):
    def fn(tmdbid, season, episode_group=None):
        return episodes
    return fn


class TestEvaluatePipeline:
    """M → F → E → I → G → 兜底。"""

    def test_mid_season_vetoes_first(self):
        """M 硬否决优先于一切。"""
        eps = [_ep(1), _ep(2, ep_type="mid_season")]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is False
        assert "M:mid_season" in sig.signals

    def test_f_unstable_vetoes(self):
        """F 不稳定优先于 E/I。"""
        eps = [_ep(1)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is False
        assert sig.stable is False
        assert "F:unstable" in sig.signals
        assert sig.reason == "目标总集数最近 7 天发生变化"
        assert "total_episode" not in sig.reason

    def test_f_unstable_carries_recent_change_direction(self):
        """F 信号携带窗口内最近变化方向，供守卫识别 total 缩小风险。"""
        eps = [_ep(1)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(), as_of=date(2026, 6, 1),
        )

        assert sig.volatility_direction == "up"

    def test_finale_at_scope_end_can_confirm_completion_despite_recent_total_change(self):
        """可信末集 finale 可以在总集数刚变化时确认完成。"""
        eps = [_ep(i, air_date="2026-06-01") for i in range(1, 33)]
        eps.append(_ep(33, ep_type="finale", air_date="2026-06-17"))

        sig = evaluate(
            subscribe=_sub(),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(),
            as_of=date(2026, 6, 17),
        )

        assert sig.completed is True
        assert sig.confidence == "high"
        assert "E:finale" in sig.signals

    def test_finale_ignores_aggregate_future_next_episode_when_scope_has_no_future(self):
        """可信 finale 只看 SeasonScope，聚合下一集不再压过 F。"""
        eps = [_ep(i, air_date="2026-06-01") for i in range(1, 33)]
        eps.append(_ep(33, ep_type="finale", air_date="2026-06-17"))
        next_ep = SimpleNamespace(
            season_number=1, episode_number=34, air_date="2026-06-24",
        )

        sig = evaluate(
            subscribe=_sub(),
            mediainfo=_mi(next_ep=next_ep),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(),
            as_of=date(2026, 6, 17),
        )

        assert sig.completed is True
        assert sig.confidence == "high"
        assert "E:finale" in sig.signals

    def test_finale_scope_future_blocks_completion_even_when_stable(self):
        """稳定状态下，scope 内未来排期反证也应压过可信 finale。"""
        eps = [
            _ep(1, air_date="2026-02-01"),
            _ep(2, ep_type="finale", air_date="2026-01-08"),
        ]

        sig = evaluate(
            subscribe=_sub(),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(),
            as_of=date(2026, 1, 9),
        )

        assert sig.completed is False

    def test_ended_status_still_completes_with_scope_future_episode(self):
        """Ended/Canceled 由 H 兜底，scope 后续集不压过剧级完成。"""
        eps = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date="2026-02-01"),
        ]

        sig = evaluate(
            subscribe=_sub(),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(),
            as_of=date(2026, 1, 9),
        )

        assert sig.completed is True
        assert "E:ended" in sig.signals

    def test_canceled_status_still_completes_with_scope_unknown_tail(self):
        """Canceled 由 H 兜底，scope 未知排期尾集不压过剧级完成。"""
        eps = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=None),
        ]

        sig = evaluate(
            subscribe=_sub(),
            mediainfo=_mi(status="Canceled"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(),
            as_of=date(2026, 1, 9),
        )

        assert sig.completed is True
        assert "E:canceled" in sig.signals

    def test_e_ended_releases(self):
        """E：status=Ended → 高置信度放行。"""
        eps = [_ep(1)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True
        assert sig.confidence == "high"
        assert "E:ended" in sig.signals

    def test_e_scope_finale_releases(self):
        """E：scope 末集 finale → 放行。"""
        eps = [_ep(1), _ep(2, ep_type="finale")]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True
        assert "E:finale" in sig.signals

    def test_i_next_season_releases(self):
        """I-1：有下一季 → 放行。"""
        eps = [_ep(1)]
        mi = _mi(seasons=[SimpleNamespace(season_number=1), SimpleNamespace(season_number=2)])
        sig = evaluate(
            subscribe=_sub(), mediainfo=mi,
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True
        assert "I:next_season" in sig.signals

    def test_signal_carries_scope_total_for_timeout_observation(self):
        """信号携带本轮 TMDB scope 总集数，避免待定释放依赖滞后的订阅表字段。"""
        eps = [_ep(1), _ep(2), _ep(3)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.scope_total == 3

    def test_i_all_aired_no_next_releases(self):
        """I-3：所有集已播 + 无 next → 低置信度放行。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True
        assert sig.confidence == "low"

    def test_i_all_aired_ignores_same_day_aggregate_next(self):
        """完结守卫忽略聚合下一集，当天已播集由 SeasonScope 判断。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 12)]
        eps.append(_ep(12, air_date="2026-06-13"))
        next_ep = SimpleNamespace(
            season_number=1, episode_number=12, air_date="2026-06-13"
        )

        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(next_ep=next_ep),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 13),
        )

        assert sig.completed is True
        assert sig.signals == ["I:all_aired"]

    def test_multiple_finale_markers_enter_low_confidence_observation(self):
        """同一范围多 finale 不高置信完成，但全播完时可低置信进入完成前观察。"""
        eps = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, ep_type="finale", air_date="2026-01-08"),
            _ep(3, ep_type="finale", air_date="2026-01-15"),
        ]

        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 1, 16),
        )

        assert sig.completed is True
        assert sig.confidence == "low"
        assert sig.signals == ["I:all_aired"]

    def test_high_risk_ignores_aggregate_next_ep_dict_for_cadence_release(self):
        """高风险 scope 的 G 辅助释放只看 SeasonScope 后续集。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 50)]
        mediainfo = SimpleNamespace(tmdb_id=100, tmdb_info={
            "status": "Returning Series",
            "seasons": [{"season_number": 1}],
            "last_episode_to_air": None,
            "next_episode_to_air": {"season_number": 1, "episode_number": 50},
        })

        sig = evaluate(
            subscribe=_sub(), mediainfo=mediainfo,
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )

        assert sig.completed is False
        assert sig.cadence_expired is True

    def test_high_risk_scope_unknown_tail_blocks_cadence_release(self):
        """高风险 scope 内后续集缺 air_date 时，G 辅助释放继续保持观察。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 50)]
        eps.append(_ep(50, air_date=None))

        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )

        assert sig.completed is False
        assert sig.cadence_expired is False

    def test_high_risk_blocks_i3(self):
        """高风险绝对季 I-3 不放行。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 50)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is False
        assert sig.cadence_expired is True  # I-3 降级为辅助

    def test_fallback_not_completed(self):
        """无信号 → 未完成。"""
        future = (date(2026, 6, 1) + timedelta(days=30)).isoformat()
        eps = [_ep(1, air_date=future)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is False
        assert sig.stable is True

    def test_subscribe_id_none_skips_f(self):
        """创建场景 subscribe_id=None → F 跳过。"""
        eps = [_ep(1)]
        sig = evaluate(
            subscribe=SimpleNamespace(id=None, tmdbid=100, season=1, episode_group=None, best_version=0),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True  # F skipped, E releases

    def test_80_percent_fast_path(self):
        """80% 正常数据：stable + Ended → 零延迟。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True
        assert sig.confidence == "high"
        assert sig.stable is True

    def test_volatility_disabled_skips_f(self):
        """volatility_enabled=False → F 不检查。"""
        eps = [_ep(1)]
        sig = evaluate(
            subscribe=_sub(), mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(volatility_enabled=False), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True  # F disabled, E releases
