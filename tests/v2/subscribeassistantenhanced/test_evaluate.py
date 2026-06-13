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
        tracker.record(total=10, subscribe_id=1)
        tracker.record(total=15, subscribe_id=1)
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

    def test_high_risk_next_ep_dict_blocks_cadence_release(self):
        """高风险 scope 中，dict 形态的同季 next_episode 会阻止 G 辅助释放。"""
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
