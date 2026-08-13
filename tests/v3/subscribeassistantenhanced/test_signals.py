"""engine/signals.py M + E + I 信号单测。"""
from types import SimpleNamespace
from datetime import date, timedelta

from subscribeassistantenhanced.engine.signals import (
    check_m_signal, check_e_signal, check_i_signal,
    has_scope_finale, has_scope_future_episode, last_aired_episode,
    scope_future_episode,
)
from subscribeassistantenhanced.engine.types import SeasonScope


def _ep(num, ep_type="standard", air_date="2026-01-01", season=1):
    return SimpleNamespace(
        episode_number=num, season_number=season,
        air_date=air_date, episode_type=ep_type, name=f"E{num}",
    )


def _mi(status="Returning Series", next_ep=None, last_ep=None, seasons=None):
    return SimpleNamespace(
        tmdb_id=100,
        tmdb_info=SimpleNamespace(
            status=status,
            next_episode_to_air=next_ep,
            last_episode_to_air=last_ep,
            seasons=seasons or [SimpleNamespace(season_number=1)],
        ),
    )


# ---------- M：mid_season 硬否决 ----------

class TestMSignal:

    def test_mid_season_last_aired_vetoes(self):
        """最后已播集为 mid_season → 硬否决。"""
        eps = [_ep(1), _ep(2, ep_type="mid_season")]
        scope = SeasonScope(episodes=eps)
        today = date(2026, 6, 1)
        sig = check_m_signal(scope, as_of=today)
        assert sig is not None
        assert sig.completed is False
        assert "M:mid_season" in sig.signals

    def test_standard_last_aired_no_veto(self):
        eps = [_ep(1), _ep(2)]
        scope = SeasonScope(episodes=eps)
        sig = check_m_signal(scope, as_of=date(2026, 6, 1))
        assert sig is None

    def test_mid_season_not_last_aired_no_veto(self):
        """mid_season 不是最后已播集时不否决。"""
        eps = [_ep(1, ep_type="mid_season", air_date="2026-01-01"),
               _ep(2, air_date="2026-03-01")]
        scope = SeasonScope(episodes=eps)
        sig = check_m_signal(scope, as_of=date(2026, 6, 1))
        assert sig is None

    def test_empty_episodes_no_veto(self):
        scope = SeasonScope(episodes=[])
        sig = check_m_signal(scope, as_of=date(2026, 6, 1))
        assert sig is None

    def test_fanren_e72_mid_season(self):
        """凡人修仙传 E72 mid_season。"""
        eps = [_ep(i) for i in range(1, 73)]
        eps[-1] = _ep(72, ep_type="mid_season")
        scope = SeasonScope(episodes=eps)
        sig = check_m_signal(scope, as_of=date(2026, 6, 1))
        assert sig is not None
        assert "M:mid_season" in sig.signals

    def test_mid_season_from_dict_episode_vetoes(self):
        """dict 分集进入 SeasonScope 时，M 信号仍能读取 episode_type。"""
        eps = [
            {"episode_number": 1, "air_date": "2026-01-01", "episode_type": "standard"},
            {"episode_number": 2, "air_date": "2026-01-08", "episode_type": "mid_season"},
        ]
        scope = SeasonScope(episodes=eps)

        sig = check_m_signal(scope, as_of=date(2026, 2, 1))

        assert sig is not None
        assert "M:mid_season" in sig.signals


# ---------- E：基线信号 ----------

class TestESignal:

    def test_ended_status(self):
        scope = SeasonScope(episodes=[_ep(1)])
        sig = check_e_signal(_mi(status="Ended"), scope)
        assert sig is not None
        assert sig.completed is True
        assert sig.confidence == "high"
        assert "E:ended" in sig.signals

    def test_canceled_status(self):
        scope = SeasonScope(episodes=[_ep(1)])
        sig = check_e_signal(_mi(status="Canceled"), scope)
        assert sig is not None
        assert sig.completed is True

    def test_returning_no_finale(self):
        scope = SeasonScope(episodes=[_ep(1), _ep(2)])
        sig = check_e_signal(_mi(), scope)
        assert sig is None

    def test_finale_as_scope_last_ep(self):
        """finale 是 scope 末集 → 放行。"""
        eps = [_ep(1), _ep(2), _ep(3, ep_type="finale")]
        scope = SeasonScope(episodes=eps)
        sig = check_e_signal(_mi(), scope)
        assert sig is not None
        assert sig.completed is True
        assert "E:finale" in sig.signals

    def test_future_finale_does_not_complete_returning_series(self):
        """finale 播出日期晚于当前日期时，不能提前确认仍在播出的目标范围已完结。"""
        eps = [
            _ep(76, air_date="2026-06-10"),
            _ep(77, ep_type="mid_season", air_date="2026-06-17"),
            _ep(85, ep_type="finale", air_date="2026-09-30"),
        ]
        scope = SeasonScope(episodes=eps)
        sig = check_e_signal(_mi(), scope, as_of=date(2026, 6, 13))
        assert sig is None

    def test_multiple_finale_markers_do_not_complete(self):
        """同一目标范围出现多个 finale 标记时按 TMDB 异常处理，不作为高置信完结依据。"""
        eps = [
            _ep(1),
            _ep(2, ep_type="finale", air_date="2026-01-08"),
            _ep(3, ep_type="finale", air_date="2026-01-15"),
        ]
        scope = SeasonScope(episodes=eps)

        sig = check_e_signal(_mi(), scope, as_of=date(2026, 1, 16))

        assert sig is None

    def test_ended_status_from_tmdb_info_dict(self):
        """TMDB 原始信息为 dict 时，E 信号仍能读取剧级状态。"""
        scope = SeasonScope(episodes=[_ep(1)])
        mediainfo = SimpleNamespace(tmdb_info={"status": "Ended"})

        sig = check_e_signal(mediainfo, scope)

        assert sig is not None
        assert sig.completed is True
        assert "E:ended" in sig.signals

    def test_finale_not_scope_last_ep(self):
        """finale 不是 scope 末集 → 不放行（Re:ZERO E66 in 85-ep scope）。"""
        eps = [_ep(i) for i in range(1, 86)]
        eps[65] = _ep(66, ep_type="finale")
        scope = SeasonScope(episodes=eps)
        sig = check_e_signal(_mi(), scope)
        assert sig is None

    def test_rezero_group_season3_finale_at_end(self):
        """Re:ZERO Group Season 3 (E51-E66), E66=finale 是 scope 末集 → 放行。"""
        eps = [_ep(i) for i in range(51, 67)]
        eps[-1] = _ep(66, ep_type="finale")
        scope = SeasonScope(episodes=eps)
        sig = check_e_signal(_mi(), scope)
        assert sig is not None
        assert sig.completed is True

    def test_scope_finale_from_dict_episode_releases(self):
        """dict 分集进入 SeasonScope 时，E 信号仍能读取 finale 和 air_date。"""
        eps = [
            {"episode_number": 1, "air_date": "2026-01-01", "episode_type": "standard"},
            {"episode_number": 2, "air_date": "2026-01-08", "episode_type": "finale"},
        ]
        scope = SeasonScope(episodes=eps)

        sig = check_e_signal(_mi(), scope, as_of=date(2026, 1, 9))

        assert sig is not None
        assert "E:finale" in sig.signals

    def test_finale_with_later_unknown_air_episode_is_not_high_confidence(self):
        """scope 末集后还有播出日期未知的集时，finale 不能高置信完成。"""
        eps = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, ep_type="finale", air_date="2026-01-08"),
            _ep(3, air_date=None),
        ]
        scope = SeasonScope(season=1, episodes=eps)

        sig = check_e_signal(_mi(), scope, as_of=date(2026, 1, 9))

        assert sig is None


# ---------- I：季级信号 ----------

class TestISignal:

    def test_next_season_exists(self):
        """I-1：TMDB 有更晚的季 → 放行。"""
        mi = _mi(seasons=[SimpleNamespace(season_number=1), SimpleNamespace(season_number=2)])
        scope = SeasonScope(season=1, episodes=[_ep(1)])
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False)
        assert sig is not None
        assert sig.completed is True
        assert "I:next_season" in sig.signals

    def test_next_season_exists_from_tmdb_info_dict(self):
        """TMDB 原始信息为 dict 时，I-1 能读取 seasons 内的季号。"""
        mediainfo = SimpleNamespace(tmdb_info={
            "seasons": [{"season_number": 1}, {"season_number": 2}],
            "last_episode_to_air": None,
            "next_episode_to_air": None,
        })
        scope = SeasonScope(season=1, episodes=[_ep(1)])

        sig = check_i_signal(mediainfo, scope, cooldown_days=14, high_risk=False)

        assert sig is not None
        assert sig.completed is True
        assert "I:next_season" in sig.signals

    def test_next_season_blocked_by_scope_future_episode(self):
        """I-1 有后续季时，目标范围内后续播出日期仍应压过 I 信号。"""
        mi = _mi(seasons=[SimpleNamespace(season_number=1), SimpleNamespace(season_number=2)])
        scope = SeasonScope(
            season=1,
            episodes=[
                _ep(1, air_date="2026-01-01"),
                _ep(2, air_date="2026-02-01"),
            ],
        )

        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 1, 15))

        assert sig is None

    def test_no_next_season_with_recent_ep(self):
        """无下一季 + 最近才播出的集 → I-1 不满足，I-3 可能满足。"""
        recent = (date(2026, 6, 1) - timedelta(days=3)).isoformat()
        mi = _mi(seasons=[SimpleNamespace(season_number=1)])
        scope = SeasonScope(season=1, episodes=[_ep(1, air_date=recent)])
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))
        assert sig is not None
        assert "I:all_aired" in sig.signals

    def test_i2_last_ep_beyond_season(self):
        """I-2：last_episode_to_air 季号 > 当前季 → 放行。"""
        last = SimpleNamespace(season_number=2, episode_number=1, air_date="2026-06-01")
        mi = _mi(last_ep=last, seasons=[SimpleNamespace(season_number=1)])
        scope = SeasonScope(season=1, episodes=[_ep(1)])
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False)
        assert sig is not None
        assert "I:last_ep_beyond" in sig.signals

    def test_last_ep_beyond_blocked_by_scope_unknown_tail(self):
        """I-2 有跨季 last_episode 时，目标范围内播出日期未知的后续集仍应压过 I 信号。"""
        last = SimpleNamespace(season_number=2, episode_number=1, air_date="2026-06-01")
        mi = _mi(last_ep=last, seasons=[SimpleNamespace(season_number=1)])
        scope = SeasonScope(
            season=1,
            episodes=[
                _ep(1, air_date="2026-01-01"),
                _ep(2, air_date=None),
            ],
        )

        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 2, 1))

        assert sig is None

    def test_cooldown_not_fire_with_future_episodes(self):
        """scope 有后续播出日期时 I-4 不触发。"""
        old_date = (date(2026, 6, 1) - timedelta(days=20)).isoformat()
        eps = [_ep(1, air_date=old_date), _ep(2, air_date="2027-01-01")]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps)
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))
        assert sig is None

    def test_all_aired_no_next_ep(self):
        """I-3：所有集已播且未发现后续集时放行。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps)
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))
        assert sig is not None
        assert sig.completed is True
        assert "I:all_aired" in sig.signals

    def test_all_aired_from_dict_episodes_releases(self):
        """dict 分集进入 SeasonScope 时，I-3 仍能判断全部已播。"""
        eps = [
            {"episode_number": 1, "air_date": "2026-01-01", "episode_type": "standard"},
            {"episode_number": 2, "air_date": "2026-01-08", "episode_type": "standard"},
        ]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps)

        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 2, 1))

        assert sig is not None
        assert "I:all_aired" in sig.signals

    def test_aggregate_next_ep_same_season_does_not_block_scope_completion(self):
        """完结守卫不使用 next_episode_to_air 作为完成裁决依据。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        next_ep = SimpleNamespace(season_number=1, episode_number=13, air_date="2026-06-13")
        mi = _mi(next_ep=next_ep)
        scope = SeasonScope(season=1, episodes=eps)
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))
        assert sig is not None
        assert "I:all_aired" in sig.signals

    def test_same_day_next_ep_same_season_allows(self):
        """当天播出的 next_episode 已进入可播日期，不应继续阻止完结。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 12)]
        eps.append(_ep(12, air_date="2026-06-13"))
        next_ep = SimpleNamespace(
            season_number=1, episode_number=12, air_date="2026-06-13"
        )
        mi = _mi(next_ep=next_ep)
        scope = SeasonScope(season=1, episodes=eps)

        sig = check_i_signal(
            mi, scope, cooldown_days=14, high_risk=False,
            as_of=date(2026, 6, 13),
        )

        assert sig is not None
        assert sig.signals == ["I:all_aired"]

    def test_aggregate_next_ep_without_air_date_does_not_block_scope_completion(self):
        """聚合下一集缺少播出日期时，不参与完结守卫裁决。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        next_ep = SimpleNamespace(
            season_number=1, episode_number=13, air_date=None
        )
        mi = _mi(next_ep=next_ep)
        scope = SeasonScope(season=1, episodes=eps)

        sig = check_i_signal(
            mi, scope, cooldown_days=14, high_risk=False,
            as_of=date(2026, 6, 13),
        )

        assert sig is not None
        assert "I:all_aired" in sig.signals

    def test_aggregate_next_ep_same_season_from_dict_does_not_block_scope_completion(self):
        """TMDB 原始 dict 的聚合下一集也不参与完结守卫裁决。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        mediainfo = SimpleNamespace(tmdb_info={
            "seasons": [{"season_number": 1}],
            "last_episode_to_air": None,
            "next_episode_to_air": {"season_number": 1, "episode_number": 13},
        })
        scope = SeasonScope(season=1, episodes=eps)

        sig = check_i_signal(mediainfo, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))

        assert sig is not None
        assert "I:all_aired" in sig.signals

    def test_next_ep_different_season_allows(self):
        """next_episode 属于不同季 → I-3 可满足。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        next_ep = SimpleNamespace(season_number=2, episode_number=1, air_date="2026-07-01")
        mi = _mi(next_ep=next_ep)
        scope = SeasonScope(season=1, episodes=eps)
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))
        assert sig is not None

    def test_high_risk_blocks_i3(self):
        """高风险绝对季 I-3 不放行。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps, high_risk=True)
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=True,
                             as_of=date(2026, 6, 1))
        assert sig is None

    def test_cooldown_releases_no_future_eps(self):
        """I-4：最后集播出超冷却期 + 未发现后续集 → 放行。"""
        old_date = (date(2026, 6, 1) - timedelta(days=20)).isoformat()
        eps = [_ep(1, air_date=None), _ep(2, air_date=old_date)]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps)
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))
        assert sig is not None
        assert "I:cooldown" in sig.signals

    def test_cooldown_from_dict_episodes_releases(self):
        """dict 分集进入 SeasonScope 时，I-4 仍能读取最后已播日期。"""
        old_date = (date(2026, 6, 1) - timedelta(days=20)).isoformat()
        eps = [
            {"episode_number": 1, "air_date": None, "episode_type": "standard"},
            {"episode_number": 2, "air_date": old_date, "episode_type": "standard"},
        ]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps)

        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))

        assert sig is not None
        assert "I:cooldown" in sig.signals

    def test_i_all_aired_blocked_by_later_unknown_air_episode(self):
        """后续集已存在但缺 air_date 时，I 信号不能确认完结。"""
        eps = [_ep(1, air_date="2026-01-01"), _ep(2, air_date=None)]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps)

        sig = check_i_signal(
            mi, scope, cooldown_days=14, high_risk=False,
            as_of=date(2026, 2, 1),
        )

        assert sig is None

    def test_i_cooldown_blocked_by_later_unknown_air_episode(self):
        """冷却期已过但后续集缺 air_date 时，I-4 不能确认完结。"""
        old_date = (date(2026, 2, 1) - timedelta(days=20)).isoformat()
        eps = [_ep(1, air_date=old_date), _ep(2, air_date=None)]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps)

        sig = check_i_signal(
            mi, scope, cooldown_days=14, high_risk=False,
            as_of=date(2026, 2, 1),
        )

        assert sig is None

    def test_high_risk_blocks_i4(self):
        """高风险绝对季 I-4 也不放行。"""
        old_date = (date(2026, 6, 1) - timedelta(days=20)).isoformat()
        eps = [_ep(1, air_date=old_date)]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps, high_risk=True)
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=True,
                             as_of=date(2026, 6, 1))
        assert sig is None

    def test_not_all_aired_recent_last_no_release(self):
        """有后续播出日期 + 最后已播集距今 < 冷却期 → 不放行。"""
        recent = (date(2026, 6, 1) - timedelta(days=3)).isoformat()
        eps = [_ep(1, air_date=recent), _ep(2, air_date="2027-01-01")]
        mi = _mi()
        scope = SeasonScope(season=1, episodes=eps)
        sig = check_i_signal(mi, scope, cooldown_days=14, high_risk=False,
                             as_of=date(2026, 6, 1))
        assert sig is None


# ---------- Helper functions ----------

class TestHasScopeFinale:

    def test_finale_at_end(self):
        eps = [_ep(1), _ep(2, ep_type="finale")]
        scope = SeasonScope(episodes=eps)
        assert has_scope_finale(scope) is True

    def test_finale_not_at_end(self):
        eps = [_ep(1, ep_type="finale"), _ep(2)]
        scope = SeasonScope(episodes=eps)
        assert has_scope_finale(scope) is False

    def test_no_finale(self):
        eps = [_ep(1), _ep(2)]
        scope = SeasonScope(episodes=eps)
        assert has_scope_finale(scope) is False

    def test_empty(self):
        scope = SeasonScope(episodes=[])
        assert has_scope_finale(scope) is False


class TestLastAiredEpisode:

    def test_returns_last_aired(self):
        eps = [_ep(1, air_date="2026-01-01"), _ep(2, air_date="2026-02-01"),
               _ep(3, air_date="2027-01-01")]
        result = last_aired_episode(eps, as_of=date(2026, 6, 1))
        assert result.episode_number == 2

    def test_all_future_returns_none(self):
        eps = [_ep(1, air_date="2027-01-01")]
        result = last_aired_episode(eps, as_of=date(2026, 6, 1))
        assert result is None


class TestScopeFutureEpisode:

    def test_returns_later_unknown_air_tail(self):
        """后续集缺少 air_date 时，scope helper 仍应判定为未完结。"""
        eps = [_ep(1, air_date="2026-01-01"), _ep(2, air_date=None)]
        scope = SeasonScope(episodes=eps)

        result = scope_future_episode(scope, as_of=date(2026, 2, 1))

        assert result is eps[1]
        assert has_scope_future_episode(scope, as_of=date(2026, 2, 1)) is True

    def test_ignores_unknown_air_before_last_aired(self):
        """缺排期集号不晚于最后已播集时，不能单独证明范围仍未完结。"""
        eps = [_ep(1, air_date=None), _ep(2, air_date="2026-01-08")]
        scope = SeasonScope(episodes=eps)

        assert scope_future_episode(scope, as_of=date(2026, 2, 1)) is None

    def test_uses_future_date_without_episode_number(self):
        """集号不可比较但 air_date 晚于当天时，播出日期本身即可说明未完结。"""
        ep = _ep(None, air_date="2026-02-01")
        scope = SeasonScope(episodes=[ep])

        assert scope_future_episode(scope, as_of=date(2026, 1, 31)) is ep

    def test_treats_today_as_aired(self):
        """air_date 等于今天按已播处理，不算后续播出日期。"""
        eps = [_ep(1, air_date="2026-02-01")]
        scope = SeasonScope(episodes=eps)

        assert has_scope_future_episode(scope, as_of=date(2026, 2, 1)) is False

    def test_supports_dict_episodes(self):
        """scope helper 兼容 TMDB 原始 dict 分集对象。"""
        eps = [
            {"episode_number": 1, "air_date": "2026-01-01"},
            {"episode_number": 2, "air_date": None},
        ]
        scope = SeasonScope(episodes=eps)

        result = scope_future_episode(scope, as_of=date(2026, 2, 1))

        assert result is eps[1]

    def test_unparseable_last_aired_number_does_not_make_unknown_tail_future(self):
        """最后已播集号不可比较时，unknown-air 集不能仅凭集号证明后续。"""
        eps = [_ep("x", air_date="2026-01-01"), _ep(2, air_date=None)]
        scope = SeasonScope(episodes=eps)

        assert scope_future_episode(scope, as_of=date(2026, 2, 1)) is None

    def test_unknown_air_episode_without_aired_baseline_is_not_future(self):
        """没有已播基准时，缺排期集不能单独证明范围仍有后续。"""
        eps = [_ep(1, air_date=None)]
        scope = SeasonScope(episodes=eps)

        assert scope_future_episode(scope, as_of=date(2026, 2, 1)) is None
