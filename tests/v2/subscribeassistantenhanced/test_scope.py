"""engine/scope.py SeasonScope 构建与高风险检测单测。"""
from types import SimpleNamespace

from subscribeassistantenhanced.engine.scope import build_scope, detect_high_risk
from subscribeassistantenhanced.engine.types import SeasonScope


def _ep(num, ep_type="standard", season=1, air_date="2026-01-01"):
    return SimpleNamespace(
        episode_number=num, season_number=season,
        air_date=air_date, episode_type=ep_type, name=f"E{num}",
    )


class TestBuildScope:
    """build_scope 根据 subscribe.episode_group 构建 scope。"""

    def test_main_season_scope(self, make_subscribe, make_mediainfo):
        episodes = [_ep(1), _ep(2), _ep(3)]
        sub = make_subscribe(tmdbid=100, season=1, episode_group=None)

        def fake_tmdb_episodes(tmdbid, season, episode_group=None):
            assert episode_group is None
            return episodes

        scope = build_scope(sub, make_mediainfo(), fake_tmdb_episodes)
        assert scope.source == "main_season"
        assert scope.tmdbid == 100
        assert scope.season == 1
        assert scope.episode_group_id is None
        assert scope.episodes == episodes
        assert scope.total == 3

    def test_episode_group_scope(self, make_subscribe, make_mediainfo):
        group_eps = [_ep(51), _ep(52)]
        sub = make_subscribe(tmdbid=100, season=1, episode_group="eg-abc")

        def fake_tmdb_episodes(tmdbid, season, episode_group=None):
            assert episode_group == "eg-abc"
            return group_eps

        scope = build_scope(sub, make_mediainfo(), fake_tmdb_episodes)
        assert scope.source == "episode_group"
        assert scope.episode_group_id == "eg-abc"
        assert scope.total == 2


class TestDetectHighRisk:
    """detect_high_risk 三条件检测。"""

    def test_normal_12ep_not_high_risk(self, make_mediainfo):
        scope = SeasonScope(episodes=[_ep(i) for i in range(1, 13)], total=12)
        assert detect_high_risk(scope, make_mediainfo()) is False

    def test_exactly_40_episodes_high_risk(self, make_mediainfo):
        """条件 1 边界：scope 集数 == 40 → high_risk。"""
        scope = SeasonScope(episodes=[_ep(i) for i in range(1, 41)], total=40)
        assert detect_high_risk(scope, make_mediainfo()) is True

    def test_39_episodes_not_high_risk(self, make_mediainfo):
        """条件 1 边界：scope 集数 == 39 → not high_risk。"""
        scope = SeasonScope(episodes=[_ep(i) for i in range(1, 40)], total=39)
        assert detect_high_risk(scope, make_mediainfo()) is False

    def test_50_episodes_high_risk(self, make_mediainfo):
        """条件 1：scope 集数 >= 40。"""
        scope = SeasonScope(episodes=[_ep(i) for i in range(1, 51)], total=50)
        assert detect_high_risk(scope, make_mediainfo()) is True

    def test_mid_season_in_middle_high_risk(self, make_mediainfo):
        """条件 2：中间有 mid_season。"""
        eps = [_ep(1), _ep(2, ep_type="mid_season"), _ep(3)]
        scope = SeasonScope(episodes=eps, total=3)
        assert detect_high_risk(scope, make_mediainfo()) is True

    def test_mid_season_dict_episode_high_risk(self, make_mediainfo):
        """dict 分集进入 SeasonScope 时，高风险检测仍能读取 mid_season。"""
        eps = [
            {"episode_number": 1, "air_date": "2026-01-01", "episode_type": "standard"},
            {"episode_number": 2, "air_date": "2026-01-08", "episode_type": "mid_season"},
            {"episode_number": 3, "air_date": "2026-01-15", "episode_type": "standard"},
        ]
        scope = SeasonScope(episodes=eps, total=3)

        assert detect_high_risk(scope, make_mediainfo()) is True

    def test_single_finale_in_middle_high_risk(self, make_mediainfo):
        """条件 2：唯一 finale 不在末集，代表范围后续仍有内容。"""
        eps = [_ep(1), _ep(2, ep_type="finale"), _ep(3)]
        scope = SeasonScope(episodes=eps, total=3)
        assert detect_high_risk(scope, make_mediainfo()) is True

    def test_single_finale_dict_episode_in_middle_high_risk(self, make_mediainfo):
        """dict 分集进入 SeasonScope 时，高风险检测仍能读取中段 finale。"""
        eps = [
            {"episode_number": 1, "air_date": "2026-01-01", "episode_type": "standard"},
            {"episode_number": 2, "air_date": "2026-01-08", "episode_type": "finale"},
            {"episode_number": 3, "air_date": "2026-01-15", "episode_type": "standard"},
        ]
        scope = SeasonScope(episodes=eps, total=3)

        assert detect_high_risk(scope, make_mediainfo()) is True

    def test_multiple_finales_not_high_risk_by_itself(self, make_mediainfo):
        """多个 finale 只说明标记不可信，不单独阻止后续低置信观察。"""
        eps = [_ep(1), _ep(2, ep_type="finale"), _ep(3, ep_type="finale")]
        scope = SeasonScope(episodes=eps, total=3)
        assert detect_high_risk(scope, make_mediainfo()) is False

    def test_finale_as_last_ep_not_high_risk(self, make_mediainfo):
        """末集 finale 不算高风险。"""
        eps = [_ep(1), _ep(2), _ep(3, ep_type="finale")]
        scope = SeasonScope(episodes=eps, total=3)
        assert detect_high_risk(scope, make_mediainfo()) is False

    def test_two_production_groups_high_risk(self, make_mediainfo):
        """条件 3：≥2 个 production 类剧集组。"""
        mi = make_mediainfo(tmdb_info=SimpleNamespace(
            status="Returning Series",
            next_episode_to_air=None, last_episode_to_air=None,
            seasons=[],
            episode_groups=SimpleNamespace(results=[
                SimpleNamespace(type=7, id="g1"),  # production
                SimpleNamespace(type=7, id="g2"),  # production
            ]),
        ))
        eps = [_ep(i) for i in range(1, 13)]
        scope = SeasonScope(episodes=eps, total=12)
        assert detect_high_risk(scope, mi) is True

    def test_two_production_groups_from_tmdb_info_dict_high_risk(self, make_mediainfo):
        """TMDB 原始信息为 dict 时，production 剧集组仍参与高风险判断。"""
        mi = make_mediainfo(tmdb_info={
            "status": "Returning Series",
            "next_episode_to_air": None,
            "last_episode_to_air": None,
            "seasons": [],
            "episode_groups": {
                "results": [
                    {"type": 7, "id": "g1"},
                    {"type": 7, "id": "g2"},
                ],
            },
        })
        eps = [_ep(i) for i in range(1, 13)]
        scope = SeasonScope(episodes=eps, total=12)

        assert detect_high_risk(scope, mi) is True

    def test_one_production_group_not_high_risk(self, make_mediainfo):
        """只有 1 个 production group 不算。"""
        mi = make_mediainfo(tmdb_info=SimpleNamespace(
            status="Returning Series",
            next_episode_to_air=None, last_episode_to_air=None,
            seasons=[],
            episode_groups=SimpleNamespace(results=[
                SimpleNamespace(type=7, id="g1"),
            ]),
        ))
        eps = [_ep(i) for i in range(1, 13)]
        scope = SeasonScope(episodes=eps, total=12)
        assert detect_high_risk(scope, mi) is False

    def test_rezero_main_season_high_risk(self, make_mediainfo):
        """Re:ZERO 主 Season 1（85集）→ high_risk=True。"""
        eps = [_ep(i) for i in range(1, 86)]
        eps[24] = _ep(25, ep_type="finale")  # E25 finale
        eps[49] = _ep(50, ep_type="finale")  # E50 finale
        eps[65] = _ep(66, ep_type="finale")  # E66 finale
        scope = SeasonScope(episodes=eps, total=85)
        assert detect_high_risk(scope, make_mediainfo()) is True

    def test_rezero_group_season3_not_high_risk(self, make_mediainfo):
        """Re:ZERO Episode Group Season 3（E51-E66，16集，E66=末集 finale）→ not high_risk。"""
        eps = [_ep(i) for i in range(51, 67)]
        eps[-1] = _ep(66, ep_type="finale")
        scope = SeasonScope(episodes=eps, total=16)
        assert detect_high_risk(scope, make_mediainfo()) is False

    def test_no_episode_groups_attribute(self, make_mediainfo):
        """mediainfo 没有 episode_groups 属性时不报错。"""
        scope = SeasonScope(episodes=[_ep(i) for i in range(1, 13)], total=12)
        assert detect_high_risk(scope, make_mediainfo()) is False
