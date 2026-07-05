"""engine/pipeline.py 完成证据流水线单测。"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from subscribeassistantenhanced.engine.pipeline import CompletionEvidencePipeline
from subscribeassistantenhanced.engine.site import SITE_EVIDENCE_TTL_HOURS, SiteEvidence
from subscribeassistantenhanced.engine.volatility import VolatilityTracker
from subscribeassistantenhanced.shared.config import PluginConfig
from subscribeassistantenhanced.shared.task import TaskDataManager


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


def _make_tracker(stable=True, direction="up"):
    store = {}
    mgr = TaskDataManager(get_data_fn=lambda k: store.get(k), save_data_fn=lambda k, v: store.__setitem__(k, v))
    tracker = VolatilityTracker(mgr, window_days=7)
    if not stable:
        subscribe = SimpleNamespace(
            id=1, tmdbid=100, season=1, episode_group=None
        )
        if direction == "down":
            tracker.record(total=15, subscribe=subscribe)
            tracker.record(total=10, subscribe=subscribe)
        else:
            tracker.record(total=10, subscribe=subscribe)
            tracker.record(total=15, subscribe=subscribe)
    return tracker


def _sub(sid=1, season=1, episode_group=None, best_version=0, name="测试剧",
         start_episode=1, total_episode=12, state="R", manual_total_episode=False,
         stype="电视剧", best_version_full=0):
    return SimpleNamespace(
        id=sid, name=name, tmdbid=100, season=season,
        episode_group=episode_group, best_version=best_version,
        start_episode=start_episode, total_episode=total_episode,
        state=state, manual_total_episode=manual_total_episode,
        type=stype, best_version_full=best_version_full,
    )


def _cfg(**overrides):
    return PluginConfig(overrides)


def _tmdb_fn(episodes):
    def fn(tmdbid, season, episode_group=None):
        return episodes
    return fn


def _evidence(subscribe, mediainfo, tmdb_episodes_fn, volatility_tracker, config,
              as_of=None, resolve_missing_fn=None, meta=None, site_provider=None,
              consume_site_evidence=None, now=None):
    now = now or datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    pipeline = CompletionEvidencePipeline(
        tmdb_episodes_fn=tmdb_episodes_fn,
        volatility_tracker=volatility_tracker,
        config=config,
        site_evidence_provider=site_provider,
        now_fn=lambda: now,
    )
    return pipeline.evaluate(
        subscribe,
        mediainfo,
        as_of=as_of,
        resolve_missing_fn=resolve_missing_fn,
        meta=meta,
        consume_site_evidence=(
            site_provider is not None if consume_site_evidence is None else consume_site_evidence
        ),
    )


def _primary(*args, **kwargs):
    return _evidence(*args, **kwargs).primary_signal


def _resolver(result=True):
    return MagicMock(return_value=(result, {}))


def _site(kind, candidate_total=12, current_total=10, now=None, site_total=None, **kwargs):
    now = now or datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    reliable_total = candidate_total if site_total is None else site_total
    defaults = {
        "kind": kind,
        "confidence": "medium" if kind != "site_complete_pack" else "low",
        "tmdbid": 100,
        "season": 1,
        "episode_group": "",
        "type": "电视剧",
        "site_candidate_total": candidate_total,
        "max_episode": candidate_total,
        "site_total": reliable_total,
        "complete_hint": kind in ("site_complete_total", "site_complete_pack"),
        "current_target_total": current_total,
        "match_level": "strict",
        "source": "rss",
        "sample_titles": ["测试剧 S01"],
        "scanned_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=SITE_EVIDENCE_TTL_HOURS)).isoformat(),
        "reason": f"站点证据 {kind}",
    }
    defaults.update(kwargs)
    return SiteEvidence(**defaults)


class TestCompletionEvidencePipeline:
    """完成证据流水线按固定阶段保留候选信号。"""

    def test_l_target_satisfied_and_i_all_aired_builds_medium_target_complete(self):
        """L 与 I:all_aired 共同证明当前订阅目标完成，主信号升级为目标完成。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        resolve_missing = _resolver(True)

        evidence = _evidence(
            subscribe=_sub(total_episode=12),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(),
            as_of=date(2026, 6, 1),
            resolve_missing_fn=resolve_missing,
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
        )

        assert evidence.local_signal.signals == ["L:target_satisfied"]
        assert evidence.i_low_signal.signals == ["I:all_aired"]
        assert evidence.target_complete_signal is evidence.primary_signal
        assert evidence.primary_signal.completed is True
        assert evidence.primary_signal.confidence == "medium"
        assert evidence.primary_signal.signals == ["L:target_satisfied", "I:all_aired"]
        assert evidence.primary_signal.scope_total == 12
        assert evidence.primary_signal.scope_high_risk is False
        assert evidence.observation_kind == "medium_target_complete"
        assert evidence.cadence_expired is False

    def test_l_target_satisfied_and_i_cooldown_builds_medium_target_complete(self):
        """L 与 I:cooldown 可共同证明当前订阅目标完成。"""
        episodes = [
            _ep(1, air_date="2026-01-01"),
            SimpleNamespace(episode_number=None, season_number=1, air_date=None, episode_type="standard"),
        ]
        resolve_missing = _resolver(True)

        evidence = _evidence(
            subscribe=_sub(total_episode=1),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(season_cooldown_days=14),
            as_of=date(2026, 2, 1),
            resolve_missing_fn=resolve_missing,
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
        )

        assert evidence.local_signal.signals == ["L:target_satisfied"]
        assert evidence.i_low_signal.signals == ["I:cooldown"]
        assert evidence.target_complete_signal is evidence.primary_signal
        assert evidence.primary_signal.confidence == "medium"
        assert evidence.primary_signal.signals == ["L:target_satisfied", "I:cooldown"]
        assert evidence.observation_kind == "medium_target_complete"

    def test_l_target_satisfied_and_site_complete_total_builds_medium_target_complete(self):
        """L 与 S:site_complete_total 可共同证明当前订阅目标完成。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        site_provider = MagicMock(return_value=_site("site_complete_total", site_total=12, current_total=12))

        evidence = _evidence(
            subscribe=_sub(total_episode=12),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_completion_evidence_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.local_signal.signals == ["L:target_satisfied"]
        assert evidence.site_signal is evidence.target_complete_signal
        assert evidence.target_complete_signal is evidence.primary_signal
        assert evidence.primary_signal.confidence == "medium"
        assert evidence.primary_signal.signals == ["L:target_satisfied", "S:site_complete_total"]
        assert evidence.observation_kind == "medium_target_complete"

    def test_site_complete_pack_with_l_builds_medium_target_complete(self):
        """低置信 S:site_complete_pack 必须与 L 合成后才升级为 medium。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        site_provider = MagicMock(return_value=_site("site_complete_pack", site_total=0))

        evidence = _evidence(
            subscribe=_sub(total_episode=12),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_completion_evidence_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.site_signal is evidence.primary_signal
        assert evidence.primary_signal.confidence == "medium"
        assert evidence.primary_signal.signals == ["L:target_satisfied", "S:site_complete_pack"]

    def test_site_complete_without_l_is_diagnostic_only(self):
        """S 完结证据没有 L 目标满足时不能单独放行完成。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        site_provider = MagicMock(return_value=_site("site_complete_total", site_total=12, current_total=12))

        evidence = _evidence(
            subscribe=_sub(total_episode=12),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_completion_evidence_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(False),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.site_signal is None
        assert evidence.site_conflict.signals == ["S:site_conflict"]
        assert evidence.site_conflict.reason.startswith("site_complete_total:")
        assert evidence.target_complete_signal is None

    @pytest.mark.parametrize(
        ("site_kind", "site_kwargs"),
        [
            ("site_complete_total", {"candidate_total": 1, "site_total": 1, "current_total": 1}),
            ("site_complete_pack", {"candidate_total": 0, "site_total": 0, "current_total": 1}),
        ],
    )
    @pytest.mark.parametrize(
        "subscribe_kwargs",
        [
            {"manual_total_episode": True},
            {"best_version": 1, "best_version_full": 1},
            {"state": "S"},
        ],
    )
    def test_site_completion_is_ignored_when_subscribe_is_not_site_evidence_eligible(
            self, site_kind, site_kwargs, subscribe_kwargs):
        """S 完结信号只适用于 P/R 剧集普通订阅和分集洗版。"""
        episodes = [_ep(1, air_date="2026-02-01")]
        site_provider = MagicMock(return_value=_site(site_kind, **site_kwargs))

        evidence = _evidence(
            subscribe=_sub(total_episode=1, **subscribe_kwargs),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_completion_evidence_enabled=True),
            as_of=date(2026, 1, 9),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.site_signal is None
        assert evidence.target_complete_signal is None
        assert evidence.primary_signal is evidence.local_signal
        assert evidence.primary_signal.signals == ["L:target_satisfied"]

    def test_old_site_ahead_snapshot_normalizes_to_complete_when_live_total_catches_up(self):
        """旧 ahead 快照在 live total 追上后归一为 S 完结证据，不继续 hard veto。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        site_provider = MagicMock(return_value=_site("site_total_ahead", site_total=12, current_total=10))

        evidence = _evidence(
            subscribe=_sub(total_episode=12),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=True, site_completion_evidence_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.hard_veto is None
        assert evidence.site_total_ahead_veto is None
        assert evidence.primary_signal.signals == ["L:target_satisfied", "S:site_complete_total"]

    def test_site_ahead_equal_live_total_without_reliable_total_is_diagnostic_only(self):
        """旧 ahead 追平当前目标时，缺少可靠 total 或完结标题只能诊断。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        site_provider = MagicMock(return_value=_site(
            "site_total_ahead",
            candidate_total=12,
            current_total=10,
            site_total=0,
            complete_hint=False,
        ))

        evidence = _evidence(
            subscribe=_sub(total_episode=12),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=True, site_completion_evidence_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.site_signal is None
        assert evidence.site_conflict.signals == ["S:site_conflict"]
        assert evidence.site_conflict.reason.startswith("site_total_ahead:")
        assert evidence.target_complete_signal is not evidence.site_signal

    def test_site_ahead_equal_live_total_with_complete_hint_builds_medium_target_complete(self):
        """旧 ahead 追平当前目标时，完结标题可与 L 合成 S 完成证据。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        site_provider = MagicMock(return_value=_site(
            "site_total_ahead",
            candidate_total=12,
            current_total=10,
            site_total=0,
            complete_hint=True,
        ))

        evidence = _evidence(
            subscribe=_sub(total_episode=12),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=True, site_completion_evidence_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.site_signal is evidence.primary_signal
        assert evidence.primary_signal.signals == ["L:target_satisfied", "S:site_complete_total"]

    def test_site_ahead_hard_veto_when_live_total_still_lower_and_no_e(self):
        """站点 total 高于 live target 且未命中 E 时，S:ahead 一票否决完成。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 11)]
        site_provider = MagicMock(return_value=_site("site_total_ahead", site_total=12, current_total=10))

        evidence = _evidence(
            subscribe=_sub(total_episode=10),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.hard_veto is evidence.site_total_ahead_veto
        assert evidence.primary_signal.signals == ["S:site_total_ahead"]
        assert evidence.observation_kind == "hard_veto"

    def test_site_evidence_ttl_uses_current_time_not_end_of_day(self):
        """同一天稍后才过期的 S 快照仍可参与本轮完成检查。"""
        now = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 11)]
        site_provider = MagicMock(return_value=_site(
            "site_total_ahead",
            candidate_total=12,
            current_total=10,
            expires_at=(now + timedelta(hours=1)).isoformat(),
        ))

        evidence = _evidence(
            subscribe=_sub(total_episode=10),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
            now=now,
        )

        assert evidence.hard_veto is evidence.site_total_ahead_veto
        assert evidence.primary_signal.signals == ["S:site_total_ahead"]

    def test_site_evidence_is_not_consumed_without_completion_check_gate(self):
        """完成守卫以外复用流水线时不消费 S 快照，避免巡检路径参与 S 裁决。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 11)]
        site_provider = MagicMock(return_value=_site("site_total_ahead", candidate_total=12, current_total=10))

        evidence = _evidence(
            subscribe=_sub(total_episode=10),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
            consume_site_evidence=False,
        )

        assert evidence.site_total_ahead_veto is None
        assert evidence.site_conflict is None
        assert evidence.primary_signal.signals == ["L:target_satisfied", "I:all_aired"]

    def test_site_ahead_is_diagnostic_when_subscribe_cannot_expand_total(self):
        """订阅已由手动总集数接管时，旧 ahead 快照不能继续 hard veto。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 11)]
        site_provider = MagicMock(return_value=_site("site_total_ahead", site_total=12, current_total=10))

        evidence = _evidence(
            subscribe=_sub(total_episode=10, manual_total_episode=True),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.hard_veto is None
        assert evidence.site_conflict.signals == ["S:site_conflict"]

    def test_site_ahead_is_diagnostic_when_total_evidence_disabled(self):
        """关闭站点集数探测后，ahead 只记录诊断，不否决完成。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 11)]
        site_provider = MagicMock(return_value=_site("site_total_ahead", site_total=12, current_total=10))

        evidence = _evidence(
            subscribe=_sub(total_episode=10),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=False),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.hard_veto is None
        assert evidence.site_conflict.signals == ["S:site_conflict"]
        assert evidence.site_conflict.reason.startswith("site_total_ahead:")

    def test_site_ahead_is_diagnostic_when_high_confidence_e_is_present(self):
        """事件携带的 TMDB 完结信号成立时，S:ahead 不否决，只保留冲突诊断。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 11)]
        site_provider = MagicMock(return_value=_site("site_total_ahead", site_total=12, current_total=10))

        evidence = _evidence(
            subscribe=_sub(total_episode=10),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(site_total_probe_enabled=True),
            as_of=date(2026, 7, 5),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
            site_provider=site_provider,
        )

        assert evidence.high_completion is evidence.primary_signal
        assert evidence.site_conflict.signals == ["S:site_conflict"]
        assert evidence.site_conflict.reason.startswith("site_total_ahead:")

    def test_missing_resolver_keeps_i_all_aired_low_without_target_complete(self):
        """没有主程序缺集入口时不生成 L，中低置信 I 不能升级为目标完成。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 4)]

        evidence = _evidence(
            subscribe=_sub(total_episode=3),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(),
            as_of=date(2026, 6, 1),
        )

        assert evidence.local_signal is None
        assert evidence.target_complete_signal is None
        assert evidence.primary_signal is evidence.i_low_signal
        assert evidence.primary_signal.confidence == "low"
        assert evidence.primary_signal.signals == ["I:all_aired"]
        assert evidence.observation_kind == "i_low"

    def test_l_without_i_stays_low_l_primary_signal(self):
        """只有 L 命中时保留 single low 语义，供守卫按模式决定观察或放行。"""
        episodes = [_ep(1, air_date="2026-02-01")]

        evidence = _evidence(
            subscribe=_sub(total_episode=1),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(),
            as_of=date(2026, 1, 9),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
        )

        assert evidence.local_signal is evidence.primary_signal
        assert evidence.i_low_signal is None
        assert evidence.target_complete_signal is None
        assert evidence.primary_signal.confidence == "low"
        assert evidence.primary_signal.signals == ["L:target_satisfied"]
        assert evidence.observation_kind == "low_l"

    def test_medium_i_next_season_remains_i_signal_not_target_complete(self):
        """既有中置信 I 信号不与 L 合成 target_complete。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 4)]
        mediainfo = _mi(seasons=[SimpleNamespace(season_number=1), SimpleNamespace(season_number=2)])

        evidence = _evidence(
            subscribe=_sub(total_episode=3),
            mediainfo=mediainfo,
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(),
            as_of=date(2026, 6, 1),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
        )

        assert evidence.local_signal.signals == ["L:target_satisfied"]
        assert evidence.i_signal is evidence.primary_signal
        assert evidence.i_signal.signals == ["I:next_season"]
        assert evidence.i_signal.confidence == "medium"
        assert evidence.target_complete_signal is None

    def test_stable_e_ended_remains_high_with_scope_future(self):
        """稳定状态下剧级 Ended 是高置信完成事实，不被 scope 后续集降级。"""
        episodes = [_ep(1, air_date="2026-01-01"), _ep(2, air_date="2026-02-01")]

        evidence = _evidence(
            subscribe=_sub(total_episode=1),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(),
            as_of=date(2026, 1, 9),
        )

        assert evidence.high_completion is evidence.primary_signal
        assert evidence.primary_signal.completed is True
        assert evidence.primary_signal.confidence == "high"
        assert evidence.primary_signal.signals == ["E:ended"]

    def test_e_ended_with_future_tail_does_not_override_unstable_observation(self):
        """scope 仍有后续集时，Ended 不绕过活跃的 F 不稳定观察。"""
        episodes = [_ep(1, air_date="2026-01-01"), _ep(2, air_date=None)]

        evidence = _evidence(
            subscribe=_sub(total_episode=1),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(),
            as_of=date(2026, 1, 9),
        )

        assert evidence.high_completion.signals == ["E:ended"]
        assert evidence.unstable_signal is evidence.primary_signal
        assert evidence.primary_signal.stable is False
        assert evidence.primary_signal.signals == ["F:unstable"]

    def test_f_down_is_hard_veto_before_completion_candidates(self):
        """total 缩小风险不可被 E 或 L/I 目标完成候选绕过。"""
        episodes = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]

        evidence = _evidence(
            subscribe=_sub(total_episode=12),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(stable=False, direction="down"),
            config=_cfg(),
            as_of=date(2026, 6, 1),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
        )

        assert evidence.hard_veto is evidence.primary_signal
        assert evidence.primary_signal.signals == ["F:unstable"]
        assert evidence.primary_signal.volatility_direction == "down"
        assert evidence.high_completion is None
        assert evidence.local_signal is None
        assert evidence.target_complete_signal is None
        assert evidence.observation_kind == "hard_veto"

    def test_future_outside_target_blocks_i_low_l_and_target_complete(self):
        """目标范围外后续集只阻断候选信号，不升级为全局硬否决。"""
        future = (date(2026, 1, 9) + timedelta(days=14)).isoformat()
        episodes = [_ep(1, air_date="2026-01-01"), _ep(2, air_date=future)]
        resolve_missing = _resolver(True)

        evidence = _evidence(
            subscribe=_sub(total_episode=1),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(),
            as_of=date(2026, 1, 9),
            resolve_missing_fn=resolve_missing,
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
        )

        assert evidence.hard_veto is None
        assert evidence.local_signal is None
        assert evidence.i_low_signal is None
        assert evidence.target_complete_signal is None
        assert evidence.primary_signal.signals == ["none"]
        assert "E2" in evidence.local_blocked_reason
        resolve_missing.assert_not_called()

    def test_future_outside_target_blocks_cooldown_candidate(self):
        """目标范围外后续集存在时，不按目标内最后已播集生成 I:cooldown。"""
        future = (date(2026, 2, 1) + timedelta(days=14)).isoformat()
        episodes = [_ep(1, air_date="2026-01-01"), _ep(2, air_date=future)]

        evidence = _evidence(
            subscribe=_sub(total_episode=1),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(season_cooldown_days=14),
            as_of=date(2026, 2, 1),
            resolve_missing_fn=_resolver(True),
            meta=SimpleNamespace(type="电视剧", begin_season=1, season=1),
        )

        assert evidence.i_low_signal is None
        assert evidence.local_signal is None
        assert evidence.target_complete_signal is None
        assert evidence.primary_signal.signals == ["none"]

    def test_i_cooldown_without_l_stays_low(self):
        """I:cooldown 没有 L 目标满足证据时不能升级为 target_complete。"""
        episodes = [
            _ep(1, air_date="2026-01-01"),
            SimpleNamespace(episode_number=None, season_number=1, air_date=None, episode_type="standard"),
        ]

        evidence = _evidence(
            subscribe=_sub(total_episode=1),
            mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(episodes),
            volatility_tracker=_make_tracker(),
            config=_cfg(season_cooldown_days=14),
            as_of=date(2026, 2, 1),
        )

        assert evidence.local_signal is None
        assert evidence.target_complete_signal is None
        assert evidence.primary_signal is evidence.i_low_signal
        assert evidence.primary_signal.confidence == "low"
        assert evidence.primary_signal.signals == ["I:cooldown"]
        assert evidence.observation_kind == "i_low"


class TestPipelinePrimarySignal:
    """M → F → E → I → G → 兜底。"""

    def test_mid_season_vetoes_first(self):
        """M 硬否决优先于一切。"""
        eps = [_ep(1), _ep(2, ep_type="mid_season")]
        sig = _primary(
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
        sig = _primary(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is False
        assert sig.stable is False
        assert "F:unstable" in sig.signals
        assert sig.reason == "目标总集数最近 3 天发生变化（10 -> 15）"
        assert "total_episode" not in sig.reason

    def test_ended_without_scope_future_confirms_completion_despite_recent_total_change(self):
        """Ended 且未发现后续集时，可跳过 F 观察。"""
        eps = [_ep(i, air_date="2026-06-28") for i in range(1, 13)]

        sig = _primary(
            subscribe=_sub(),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(),
            as_of=date(2026, 6, 30),
        )

        assert sig.completed is True
        assert sig.confidence == "high"
        assert "E:ended" in sig.signals

    def test_canceled_without_scope_future_confirms_completion_despite_recent_total_change(self):
        """Canceled 且未发现后续集时，也可跳过 F 观察。"""
        eps = [_ep(i, air_date="2026-06-28") for i in range(1, 3)]

        sig = _primary(
            subscribe=_sub(),
            mediainfo=_mi(status="Canceled"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(),
            as_of=date(2026, 6, 30),
        )

        assert sig.completed is True
        assert sig.confidence == "high"
        assert "E:canceled" in sig.signals

    def test_ended_with_scope_future_still_uses_volatility_observation(self):
        """Ended 若仍有后续播出日期，不应绕过 F 观察。"""
        eps = [
            _ep(1, air_date="2026-06-28"),
            _ep(2, air_date="2026-07-01"),
        ]

        sig = _primary(
            subscribe=_sub(),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(),
            as_of=date(2026, 6, 30),
        )

        assert sig.completed is False
        assert sig.stable is False
        assert "F:unstable" in sig.signals

    def test_ended_with_scope_unknown_tail_still_uses_volatility_observation(self):
        """Ended 若仍有播出日期未知的后续集，也不应绕过 F 观察。"""
        eps = [
            _ep(1, air_date="2026-06-28"),
            _ep(2, air_date=None),
        ]

        sig = _primary(
            subscribe=_sub(),
            mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(),
            as_of=date(2026, 6, 30),
        )

        assert sig.completed is False
        assert sig.stable is False
        assert "F:unstable" in sig.signals

    def test_canceled_with_scope_unknown_tail_still_uses_volatility_observation(self):
        """Canceled 若仍有播出日期未知的后续集，也不应绕过 F 观察。"""
        eps = [
            _ep(1, air_date="2026-06-28"),
            _ep(2, air_date=None),
        ]

        sig = _primary(
            subscribe=_sub(),
            mediainfo=_mi(status="Canceled"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(),
            as_of=date(2026, 6, 30),
        )

        assert sig.completed is False
        assert sig.stable is False
        assert "F:unstable" in sig.signals

    def test_f_unstable_carries_recent_change_direction(self):
        """F 信号携带窗口内最近变化方向，供守卫识别 total 缩小风险。"""
        eps = [_ep(1)]
        sig = _primary(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(), as_of=date(2026, 6, 1),
        )

        assert sig.volatility_direction == "up"

    def test_f_unstable_carries_recent_total_change_detail(self):
        """F 信号携带窗口内最近 total 变化明细，供状态通知展示。"""
        eps = [_ep(1)]
        sig = _primary(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(), as_of=date(2026, 6, 1),
        )

        assert sig.volatility_detail == "10 -> 15"

    def test_finale_at_scope_end_can_confirm_completion_despite_recent_total_change(self):
        """可信末集 finale 可以在总集数刚变化时确认完成。"""
        eps = [_ep(i, air_date="2026-06-01") for i in range(1, 33)]
        eps.append(_ep(33, ep_type="finale", air_date="2026-06-17"))

        sig = _primary(
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

        sig = _primary(
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
        """稳定状态下，scope 内后续播出日期也应压过可信 finale。"""
        eps = [
            _ep(1, air_date="2026-02-01"),
            _ep(2, ep_type="finale", air_date="2026-01-08"),
        ]

        sig = _primary(
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

        sig = _primary(
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
        """Canceled 由 H 兜底，scope 播出日期未知的后续集不压过剧级完成。"""
        eps = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=None),
        ]

        sig = _primary(
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
        sig = _primary(
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
        sig = _primary(
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
        sig = _primary(
            subscribe=_sub(), mediainfo=mi,
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True
        assert "I:next_season" in sig.signals

    def test_signal_carries_scope_total_for_timeout_observation(self):
        """信号携带事件内 TMDB scope 总集数，避免待定释放依赖滞后的订阅表字段。"""
        eps = [_ep(1), _ep(2), _ep(3)]
        sig = _primary(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.scope_total == 3

    def test_i_all_aired_no_next_releases(self):
        """I-3：所有集已播 + 无 next → 低置信度放行。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 13)]
        sig = _primary(
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

        sig = _primary(
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

        sig = _primary(
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
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 81)]
        mediainfo = SimpleNamespace(tmdb_id=100, tmdb_info={
            "status": "Returning Series",
            "seasons": [{"season_number": 1}],
            "last_episode_to_air": None,
            "next_episode_to_air": {"season_number": 1, "episode_number": 81},
        })

        sig = _primary(
            subscribe=_sub(), mediainfo=mediainfo,
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )

        assert sig.completed is False
        assert sig.cadence_expired is True

    def test_high_risk_scope_unknown_tail_blocks_cadence_release(self):
        """高风险 scope 内后续集缺 air_date 时，G 辅助释放继续保持观察。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 80)]
        eps.append(_ep(80, air_date=None))

        sig = _primary(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )

        assert sig.completed is False
        assert sig.cadence_expired is False

    def test_high_risk_blocks_i3(self):
        """高风险绝对季 I-3 不放行。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 81)]
        sig = _primary(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is False
        assert sig.cadence_expired is True  # I-3 降级为辅助

        evidence = _evidence(
            subscribe=_sub(), mediainfo=_mi(),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert evidence.observation_kind == "none"

    def test_fallback_not_completed(self):
        """无信号 → 未完成。"""
        future = (date(2026, 6, 1) + timedelta(days=30)).isoformat()
        eps = [_ep(1, air_date=future)]
        sig = _primary(
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
        sig = _primary(
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
        sig = _primary(
            subscribe=_sub(), mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=True),
            config=_cfg(), as_of=date(2026, 6, 1),
        )
        assert sig.completed is True
        assert sig.confidence == "high"
        assert sig.stable is True

    def test_volatility_disabled_skips_f_even_when_pending_volatility_requested(self):
        """volatility_enabled=False → 即便待定参考 F，信号层也不生成 F。"""
        eps = [_ep(1)]
        sig = _primary(
            subscribe=_sub(), mediainfo=_mi(status="Ended"),
            tmdb_episodes_fn=_tmdb_fn(eps),
            volatility_tracker=_make_tracker(stable=False),
            config=_cfg(volatility_enabled=False, pending_use_volatility=True),
            as_of=date(2026, 6, 1),
        )
        assert "F:unstable" not in sig.signals
        assert sig.completed is True
        assert sig.confidence == "high"
