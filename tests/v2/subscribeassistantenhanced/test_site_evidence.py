"""engine/site.py 站点证据分类与存储单测。"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.event import SubscribeEpisodesRefreshEventData

from subscribeassistantenhanced.engine.site import (
    SITE_EVIDENCE_TTL_HOURS,
    SiteEvidence,
    SiteEpisodesRefreshHandler,
    SiteEvidenceStore,
    SiteEvidenceScanner,
    classify_site_contexts,
)
from subscribeassistantenhanced.shared.task import TaskDataManager


def _now() -> datetime:
    return datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)


def _sub(total_episode=12, **kwargs):
    defaults = {
        "id": 1,
        "name": "测试剧",
        "tmdbid": 100,
        "doubanid": None,
        "season": 1,
        "episode_group": None,
        "type": "电视剧",
        "state": "R",
        "best_version": 0,
        "best_version_full": 0,
        "manual_total_episode": False,
        "total_episode": total_episode,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _ctx(
        *,
        title="测试剧 S01E05",
        tmdbid=100,
        doubanid=None,
        explicit_tmdbid=None,
        explicit_doubanid=None,
        season=1,
        episodes=None,
        begin_episode=None,
        end_episode=None,
        site_total=0,
        begin_season=1,
        end_season=None,
        match_source="tmdbid",
        media_info_is_target=False,
) -> SimpleNamespace:
    return SimpleNamespace(
        meta_info=SimpleNamespace(
            title=title,
            subtitle="",
            begin_season=begin_season,
            end_season=end_season,
            begin_episode=begin_episode,
            end_episode=end_episode,
            episode_list=episodes or [],
            total_episode=site_total,
            tmdbid=explicit_tmdbid,
            doubanid=explicit_doubanid,
        ),
        media_info=SimpleNamespace(tmdb_id=tmdbid, douban_id=doubanid, season=season, type="电视剧"),
        torrent_info=SimpleNamespace(title=title, description=""),
        resource_source="rss",
        match_source=match_source,
        candidate_recognized=bool(tmdbid),
        media_info_is_target=media_info_is_target,
    )


def _task_manager():
    store = {}
    return TaskDataManager(
        get_data_fn=lambda key: store.get(key),
        save_data_fn=lambda key, value: store.__setitem__(key, value),
    )


def _cfg(**kwargs):
    defaults = {
        "site_total_probe_enabled": True,
        "site_completion_evidence_enabled": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _site_total_ahead(site_total=12, current_total=10, now=None, **kwargs):
    now = now or _now()
    defaults = {
        "kind": "site_total_ahead",
        "confidence": "medium",
        "tmdbid": 100,
        "season": 1,
        "episode_group": "",
        "type": "电视剧",
        "site_candidate_total": site_total,
        "max_episode": site_total,
        "site_total": site_total,
        "current_target_total": current_total,
        "match_level": "strict",
        "source": "rss",
        "sample_titles": ["测试剧 S01"],
        "scanned_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=SITE_EVIDENCE_TTL_HOURS)).isoformat(),
        "reason": f"站点候选最大集数 {site_total} 大于当前目标 {current_total}",
    }
    defaults.update(kwargs)
    return SiteEvidence(**defaults)


def _site_complete_total(site_total=12, now=None, **kwargs):
    now = now or _now()
    defaults = {
        "kind": "site_complete_total",
        "confidence": "medium",
        "tmdbid": 100,
        "season": 1,
        "episode_group": "",
        "type": "电视剧",
        "site_candidate_total": site_total,
        "max_episode": site_total,
        "site_total": site_total,
        "complete_hint": True,
        "current_target_total": site_total,
        "match_level": "strict",
        "source": "rss",
        "sample_titles": ["测试剧 全集"],
        "scanned_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=SITE_EVIDENCE_TTL_HOURS)).isoformat(),
        "reason": f"站点候选总集数等于当前目标 {site_total}",
    }
    defaults.update(kwargs)
    return SiteEvidence(**defaults)


def _handler(subscribe, store, *, config=None, now=None, resolve_missing_fn=None):
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    return SiteEpisodesRefreshHandler(
        config=config or _cfg(site_total_probe_enabled=True),
        store=store,
        subscribe_oper=subscribe_oper,
        now_fn=lambda: now or _now(),
        resolve_missing_fn=resolve_missing_fn or MagicMock(return_value=(False, {})),
        mediainfo_from_dict=lambda data: SimpleNamespace(**data),
    )


def _ended_mediainfo():
    return SimpleNamespace(tmdb_info={"status": "Ended"}, status="Ended")


def _ep(number, *, episode_type="standard", air_date="2026-06-01"):
    return SimpleNamespace(
        episode_number=number,
        episode_type=episode_type,
        air_date=air_date,
    )


def _finale_mediainfo():
    return SimpleNamespace(
        tmdb_info=SimpleNamespace(status="Returning Series"),
        seasons={1: [_ep(1), _ep(2, episode_type="finale", air_date="2026-06-08")]},
    )


def test_site_total_ahead_from_strict_episode_list():
    evidence = classify_site_contexts(
        _sub(total_episode=3),
        [_ctx(episodes=[1, 2, 3, 4, 5])],
        now=_now(),
    )

    assert evidence.kind == "site_total_ahead"
    assert evidence.confidence == "medium"
    assert evidence.site_candidate_total == 5
    assert evidence.max_episode == 5
    assert evidence.current_target_total == 3
    assert evidence.episode_group == ""
    assert evidence.expires_at == (_now() + timedelta(hours=SITE_EVIDENCE_TTL_HOURS)).isoformat()


def test_live_local_larger_becomes_conflict():
    evidence = classify_site_contexts(
        _sub(total_episode=6),
        [_ctx(episodes=[1, 2, 3, 4, 5])],
        now=_now(),
    )

    assert evidence.kind == "site_conflict"
    assert evidence.site_candidate_total == 5
    assert "小于当前目标" in evidence.reason


def test_site_total_below_target_stays_conflict_even_when_episode_list_reaches_target():
    evidence = classify_site_contexts(
        _sub(total_episode=6),
        [_ctx(site_total=5, episodes=[1, 2, 3, 4, 5, 6])],
        now=_now(),
    )

    assert evidence.kind == "site_conflict"
    assert evidence.site_total == 5
    assert evidence.max_episode == 6
    assert "总集数 5 小于当前目标 6" in evidence.reason


def test_complete_total_equal_target_is_medium():
    evidence = classify_site_contexts(
        _sub(total_episode=12),
        [_ctx(site_total=12, title="测试剧 全 12 集")],
        now=_now(),
    )

    assert evidence.kind == "site_complete_total"
    assert evidence.confidence == "medium"
    assert evidence.site_candidate_total == 12
    assert evidence.site_total == 12


def test_complete_pack_without_total_is_low():
    evidence = classify_site_contexts(
        _sub(total_episode=12),
        [_ctx(title="测试剧 S01 Complete", episodes=[], begin_episode=None, site_total=0)],
        now=_now(),
    )

    assert evidence.kind == "site_complete_pack"
    assert evidence.confidence == "low"
    assert evidence.complete_hint is True
    assert evidence.site_candidate_total == 0


def test_title_fallback_becomes_conflict():
    evidence = classify_site_contexts(
        _sub(total_episode=12),
        [_ctx(tmdbid=None, match_source="title", media_info_is_target=True, episodes=[1, 2, 3])],
        now=_now(),
    )

    assert evidence.kind == "site_conflict"
    assert "标题兜底" in evidence.reason


def test_title_fallback_diagnostic_does_not_mask_strict_site_total_ahead():
    evidence = classify_site_contexts(
        _sub(total_episode=3),
        [
            _ctx(tmdbid=None, match_source="title", media_info_is_target=True, episodes=[1, 2, 3]),
            _ctx(episodes=[1, 2, 3, 4, 5]),
        ],
        now=_now(),
    )

    assert evidence.kind == "site_total_ahead"
    assert evidence.site_candidate_total == 5
    assert evidence.match_level == "strict"


def test_lower_candidate_diagnostic_does_not_mask_larger_strict_site_total_ahead():
    evidence = classify_site_contexts(
        _sub(total_episode=3),
        [
            _ctx(episodes=[1, 2]),
            _ctx(episodes=[1, 2, 3, 4, 5]),
        ],
        now=_now(),
    )

    assert evidence.kind == "site_total_ahead"
    assert evidence.site_candidate_total == 5


def test_explicit_id_conflict_becomes_conflict_even_when_tmdb_matches():
    evidence = classify_site_contexts(
        _sub(total_episode=12, tmdbid=100, doubanid="douban-a"),
        [_ctx(tmdbid=100, doubanid="douban-b", site_total=12)],
        now=_now(),
    )

    assert evidence.kind == "site_conflict"
    assert evidence.match_level == "identity_conflict"
    assert "身份缺失或不匹配" in evidence.reason


def test_meta_explicit_id_conflict_becomes_conflict_even_when_media_tmdb_matches():
    evidence = classify_site_contexts(
        _sub(total_episode=12, tmdbid=100, doubanid="douban-a"),
        [_ctx(tmdbid=100, doubanid=None, explicit_doubanid="douban-b", site_total=12)],
        now=_now(),
    )

    assert evidence.kind == "site_conflict"
    assert evidence.match_level == "identity_conflict"


def test_candidate_extra_id_does_not_conflict_when_subscribe_lacks_that_id():
    evidence = classify_site_contexts(
        _sub(total_episode=12, tmdbid=100, doubanid=None),
        [_ctx(tmdbid=100, explicit_doubanid="douban-extra", site_total=12)],
        now=_now(),
    )

    assert evidence.kind == "site_complete_total"
    assert evidence.match_level == "strict"


def test_multi_season_candidate_becomes_conflict():
    evidence = classify_site_contexts(
        _sub(total_episode=12),
        [_ctx(begin_season=1, end_season=2, episodes=[1, 2, 3])],
        now=_now(),
    )

    assert evidence.kind == "site_conflict"
    assert "多季" in evidence.reason


def test_no_contexts_returns_no_evidence():
    evidence = classify_site_contexts(_sub(total_episode=12), [], now=_now())

    assert evidence.kind == "no_evidence"
    assert evidence.confidence == "none"


def test_context_without_episode_total_or_complete_hint_returns_no_evidence():
    evidence = classify_site_contexts(
        _sub(total_episode=12),
        [_ctx(title="测试剧 S01", episodes=[], begin_episode=None, site_total=0)],
        now=_now(),
    )

    assert evidence.kind == "no_evidence"
    assert evidence.confidence == "none"


def test_incidental_current_total_does_not_mask_larger_strict_candidate():
    evidence = classify_site_contexts(
        _sub(total_episode=1),
        [
            _ctx(title="测试剧 S01E01", episodes=[1], site_total=1),
            _ctx(title="测试剧 S01E01-E06", episodes=[1, 2, 3, 4, 5, 6]),
        ],
        now=_now(),
    )

    assert evidence.kind == "site_total_ahead"
    assert evidence.site_candidate_total == 6


def test_incidental_current_total_does_not_mask_larger_candidate_regardless_of_order():
    evidence = classify_site_contexts(
        _sub(total_episode=1),
        [
            _ctx(title="测试剧 S01E01-E06", episodes=[1, 2, 3, 4, 5, 6]),
            _ctx(title="测试剧 S01E01", episodes=[1], site_total=1),
        ],
        now=_now(),
    )

    assert evidence.kind == "site_total_ahead"
    assert evidence.site_candidate_total == 6


def test_explicit_complete_total_and_site_total_ahead_becomes_conflict():
    evidence = classify_site_contexts(
        _sub(total_episode=12),
        [
            _ctx(title="测试剧 S01E13", episodes=[13]),
            _ctx(title="测试剧 全 12 集", site_total=12),
        ],
        now=_now(),
    )

    assert evidence.kind == "site_conflict"
    assert "扩集与当前目标完成证据" in evidence.reason


def test_lower_explicit_complete_total_and_site_total_ahead_becomes_conflict_regardless_of_order():
    complete = _ctx(title="测试剧 全 10 集", site_total=10)
    ahead = _ctx(title="测试剧 S01E13", episodes=[13])

    for contexts in ([complete, ahead], [ahead, complete]):
        evidence = classify_site_contexts(_sub(total_episode=12), contexts, now=_now())

        assert evidence.kind == "site_conflict"
        assert "扩集与当前目标完成证据" in evidence.reason


def test_complete_total_wins_over_complete_pack_regardless_of_order():
    evidence = classify_site_contexts(
        _sub(total_episode=12),
        [
            _ctx(title="测试剧 S01 Complete", episodes=[], begin_episode=None, site_total=0),
            _ctx(title="测试剧 全 12 集", site_total=12),
        ],
        now=_now(),
    )

    assert evidence.kind == "site_complete_total"
    assert evidence.confidence == "medium"
    assert evidence.site_total == 12


def test_no_evidence_does_not_clear_applied_marker():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=12)
    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead", now=_now())

    store.save_snapshot(subscribe, SiteEvidence.no_evidence(subscribe, now=_now()))

    assert store.read_snapshot(subscribe).kind == "no_evidence"
    assert store.read_applied(subscribe).applied_total == 12


def test_site_evidence_expiry_fails_closed_for_missing_or_invalid_timestamp():
    evidence = _site_total_ahead(expires_at="")

    assert evidence.is_expired(_now()) is True

    evidence.expires_at = "not-a-date"

    assert evidence.is_expired(_now()) is True


def test_site_evidence_expiry_accepts_naive_timestamp_with_current_timezone():
    evidence = _site_total_ahead(expires_at="2026-07-05T13:00:00")

    assert evidence.is_expired(_now()) is False


def test_applied_marker_can_be_cleared():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=12)
    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead", now=_now())

    store.clear_applied(subscribe)

    assert store.read_applied(subscribe) is None


def test_same_applied_total_does_not_renew_lease_but_higher_total_does():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=10)
    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="first", now=_now())

    store.mark_applied(
        subscribe,
        applied_total=12,
        applied_base_total=10,
        reason="same",
        now=_now() + timedelta(hours=5),
    )

    assert store.read_applied(subscribe).applied_at == _now().isoformat()

    store.mark_applied(
        subscribe,
        applied_total=13,
        applied_base_total=10,
        reason="higher",
        now=_now() + timedelta(hours=5),
    )

    assert store.read_applied(subscribe).applied_total == 13
    assert store.read_applied(subscribe).applied_at == (_now() + timedelta(hours=5)).isoformat()


def test_applied_marker_survives_subscribe_total_rollback():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=12)
    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead", now=_now())

    subscribe.total_episode = 10

    assert store.read_applied(subscribe).applied_total == 12


def test_applied_marker_clears_when_manual_total_takes_over():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=12)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=12, current_total=10))
    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead", now=_now())

    subscribe.manual_total_episode = True
    data = SubscribeEpisodesRefreshEventData(current_total_episode=10, subscribe_id=1, season=1)
    _handler(subscribe, store).handle_refresh(data)

    assert store.read_applied(subscribe) is None
    assert store.read_snapshot(subscribe) is None
    subscribe.manual_total_episode = False
    second = SubscribeEpisodesRefreshEventData(current_total_episode=10, subscribe_id=1, season=1)
    _handler(subscribe, store).handle_refresh(second)
    assert second.updated is False


def test_snapshot_ignores_row_with_stale_identity():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, tmdbid=100, season=1, total_episode=12)
    stale_subscribe = _sub(id=7, tmdbid=200, season=1, total_episode=12)
    store.save_snapshot(stale_subscribe, SiteEvidence.no_evidence(stale_subscribe, now=_now()))

    assert store.read_snapshot(subscribe) is None


def test_snapshot_ignores_row_with_stale_episode_group_identity():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, tmdbid=100, season=1, episode_group="group-a", total_episode=12)
    stale_subscribe = _sub(id=7, tmdbid=100, season=1, episode_group="group-b", total_episode=12)
    store.save_snapshot(stale_subscribe, SiteEvidence.no_evidence(stale_subscribe, now=_now()))

    assert store.read_snapshot(subscribe) is None


def test_applied_marker_clears_when_douban_identity_changes():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, tmdbid=100, doubanid="douban-a", total_episode=12)
    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead")

    subscribe.doubanid = "douban-b"

    assert store.read_applied(subscribe) is None


def test_applied_marker_ignores_row_with_stale_identity():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, tmdbid=100, season=1, total_episode=12)
    stale_subscribe = _sub(id=7, tmdbid=200, season=1, total_episode=12)
    store.mark_applied(stale_subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead")

    assert store.read_applied(subscribe) is None


def test_saving_snapshot_for_new_identity_drops_stale_applied_marker():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, tmdbid=100, season=1, total_episode=12)
    stale_subscribe = _sub(id=7, tmdbid=200, season=1, total_episode=12)
    store.mark_applied(stale_subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead")

    store.save_snapshot(subscribe, SiteEvidence.no_evidence(subscribe, now=_now()))

    assert store.read_snapshot(subscribe).kind == "no_evidence"
    assert store.read_applied(subscribe) is None


def test_marking_applied_for_new_identity_drops_stale_snapshot():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, tmdbid=100, season=1, total_episode=12)
    stale_subscribe = _sub(id=7, tmdbid=200, season=1, total_episode=12)
    store.save_snapshot(stale_subscribe, SiteEvidence.no_evidence(stale_subscribe, now=_now()))

    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead")

    assert store.read_applied(subscribe).applied_total == 12
    assert store.read_snapshot(subscribe) is None


def test_saving_snapshot_for_new_season_identity_drops_stale_applied_marker():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, tmdbid=100, season=2, total_episode=12)
    stale_subscribe = _sub(id=7, tmdbid=100, season=1, total_episode=12)
    store.mark_applied(stale_subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead")

    store.save_snapshot(subscribe, SiteEvidence.no_evidence(subscribe, now=_now()))

    assert store.read_snapshot(subscribe).season == 2
    assert store.read_applied(subscribe) is None


def test_saving_snapshot_for_new_type_identity_drops_stale_applied_marker():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, tmdbid=100, season=1, type="电视剧", total_episode=12)
    stale_subscribe = _sub(id=7, tmdbid=100, season=1, type="电影", total_episode=12)
    store.mark_applied(stale_subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead")

    store.save_snapshot(subscribe, SiteEvidence.no_evidence(subscribe, now=_now()))

    assert store.read_snapshot(subscribe).type == "电视剧"
    assert store.read_applied(subscribe) is None


def test_refresh_handler_expands_event_total_from_site_evidence():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=85)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=90, current_total=85))
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(current_total_episode=85, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is True
    assert data.total_episode == 90
    assert data.source == "站点集数探测"
    assert "站点候选最大集数 90" in data.reason
    subscribe.total_episode = data.total_episode
    marker = store.read_applied(subscribe)
    assert marker.applied_total == 90
    assert marker.applied_base_total == 85


def test_refresh_handler_replays_applied_site_total_before_minimum_lease():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=85)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=90, current_total=85))
    store.mark_applied(subscribe, applied_total=90, applied_base_total=85, reason="site_total_ahead", now=_now())
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(current_total_episode=85, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is True
    assert data.total_episode == 90
    assert store.read_applied(subscribe).applied_total == 90


def test_refresh_handler_releases_satisfied_lease_at_six_hours():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=85)
    store.mark_applied(subscribe, applied_total=90, applied_base_total=85, reason="site_total_ahead", now=_now())
    resolve_missing = MagicMock(return_value=(True, {}))
    handler = _handler(
        subscribe,
        store,
        now=_now() + timedelta(hours=6),
        resolve_missing_fn=resolve_missing,
    )
    data = SubscribeEpisodesRefreshEventData(
        current_total_episode=85,
        subscribe_id=1,
        season=1,
        mediainfo=SimpleNamespace(type="电视剧"),
    )

    handler.handle_refresh(data)

    assert data.updated is False
    assert store.read_applied(subscribe).applied_total == 90
    assert resolve_missing.call_args.kwargs["subscribe"].total_episode == 90

    second = SubscribeEpisodesRefreshEventData(
        current_total_episode=85,
        subscribe_id=1,
        season=1,
        mediainfo=SimpleNamespace(type="电视剧"),
    )
    handler.handle_refresh(second)
    assert second.updated is False


def test_refresh_handler_keeps_missing_lease_between_six_and_twenty_four_hours():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=85)
    store.mark_applied(subscribe, applied_total=90, applied_base_total=85, reason="site_total_ahead", now=_now())
    resolve_missing = MagicMock(return_value=(False, {100: {1: SimpleNamespace(episodes=[90])}}))
    handler = _handler(
        subscribe,
        store,
        now=_now() + timedelta(hours=12),
        resolve_missing_fn=resolve_missing,
    )
    data = SubscribeEpisodesRefreshEventData(
        current_total_episode=85,
        subscribe_id=1,
        season=1,
        mediainfo=SimpleNamespace(type="电视剧"),
    )

    handler.handle_refresh(data)

    assert data.updated is True
    assert data.total_episode == 90
    assert store.read_applied(subscribe).applied_total == 90


def test_refresh_handler_forces_release_at_twenty_four_hours():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=85)
    store.mark_applied(subscribe, applied_total=90, applied_base_total=85, reason="site_total_ahead", now=_now())
    resolve_missing = MagicMock(return_value=(False, {}))
    handler = _handler(
        subscribe,
        store,
        now=_now() + timedelta(hours=24),
        resolve_missing_fn=resolve_missing,
    )
    data = SubscribeEpisodesRefreshEventData(current_total_episode=85, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is False
    assert store.read_applied(subscribe).applied_total == 90
    resolve_missing.assert_not_called()

    second = SubscribeEpisodesRefreshEventData(current_total_episode=85, subscribe_id=1, season=1)
    handler.handle_refresh(second)
    assert second.updated is False


def test_refresh_handler_starts_new_lease_for_higher_candidate_after_timeout():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=10)
    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="first", now=_now())
    higher_at = _now() + timedelta(hours=24)
    store.save_snapshot(
        subscribe,
        _site_total_ahead(site_total=13, current_total=10, now=higher_at),
    )
    data = SubscribeEpisodesRefreshEventData(current_total_episode=10, subscribe_id=1, season=1)

    _handler(subscribe, store, now=higher_at).handle_refresh(data)

    assert data.updated is True
    assert data.total_episode == 13
    marker = store.read_applied(subscribe)
    assert marker.applied_total == 13
    assert marker.applied_at == higher_at.isoformat()


def test_refresh_handler_keeps_lease_when_mediainfo_adapter_raises():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=85)
    store.mark_applied(subscribe, applied_total=90, applied_base_total=85, reason="site_total_ahead", now=_now())
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    handler = SiteEpisodesRefreshHandler(
        config=_cfg(site_total_probe_enabled=True),
        store=store,
        subscribe_oper=subscribe_oper,
        resolve_missing_fn=MagicMock(return_value=(True, {})),
        mediainfo_from_dict=MagicMock(side_effect=ValueError("invalid mediainfo")),
        now_fn=lambda: _now() + timedelta(hours=12),
    )
    data = SubscribeEpisodesRefreshEventData(
        current_total_episode=85,
        subscribe_id=1,
        season=1,
        mediainfo={"invalid": True},
    )

    handler.handle_refresh(data)

    assert data.updated is True
    assert data.total_episode == 90


def test_refresh_handler_replays_marker_when_snapshot_is_no_evidence():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=85)
    store.mark_applied(subscribe, applied_total=90, applied_base_total=85, reason="site_total_ahead", now=_now())
    store.save_snapshot(subscribe, SiteEvidence.no_evidence(subscribe, _now()))
    data = SubscribeEpisodesRefreshEventData(current_total_episode=85, subscribe_id=1, season=1)

    _handler(subscribe, store).handle_refresh(data)

    assert data.updated is True
    assert data.total_episode == 90


def test_refresh_handler_releases_invalid_or_future_marker_time():
    for applied_at in ("invalid", (_now() + timedelta(minutes=1)).isoformat()):
        store = SiteEvidenceStore(_task_manager())
        subscribe = _sub(total_episode=85)
        store.mark_applied(subscribe, applied_total=90, applied_base_total=85, reason="site_total_ahead", now=_now())
        marker = store.read_applied(subscribe)
        marker.applied_at = applied_at
        # 直接覆盖测试持久化解析边界，生产入口只会写合法 UTC 时间。
        sid = str(subscribe.id)
        store._task.update("site_evidence", lambda data: {
            **data,
            sid: {**data[sid], "applied": marker.to_dict()},
        })
        data = SubscribeEpisodesRefreshEventData(current_total_episode=85, subscribe_id=1, season=1)

        _handler(subscribe, store).handle_refresh(data)

        assert data.updated is False
        assert store.read_applied(subscribe) is None


def test_refresh_handler_keeps_site_confirmed_target_when_tmdb_temporarily_decreases():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=90)
    store.save_snapshot(subscribe, _site_complete_total(site_total=90))
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(current_total_episode=85, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is True
    assert data.total_episode == 90
    assert store.read_applied(subscribe) is None


def test_refresh_handler_allows_tmdb_decrease_when_completion_signal_is_reliable():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=90)
    store.save_snapshot(subscribe, _site_complete_total(site_total=90))
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(
        current_total_episode=85,
        subscribe_id=1,
        season=1,
        mediainfo=_ended_mediainfo(),
    )

    handler.handle_refresh(data)

    assert data.updated is False
    assert data.total_episode is None


def test_refresh_handler_skips_when_config_disabled():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=10)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=12))
    handler = _handler(subscribe, store, config=_cfg(site_total_probe_enabled=False))
    data = SubscribeEpisodesRefreshEventData(current_total_episode=10, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is False
    assert store.read_applied(subscribe) is None


def test_refresh_handler_skips_when_event_identity_mismatches():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=10, season=1)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=12))
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(current_total_episode=10, subscribe_id=1, season=2)

    handler.handle_refresh(data)

    assert data.updated is False
    assert store.read_applied(subscribe) is None


def test_refresh_handler_clears_applied_marker_when_main_total_catches_up():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=90)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=90, current_total=85))
    store.mark_applied(subscribe, applied_total=90, applied_base_total=85, reason="site_total_ahead", now=_now())
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(current_total_episode=90, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is False
    assert store.read_applied(subscribe) is None


def test_refresh_handler_does_not_use_completion_only_signal_to_refresh_total():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=90)
    store.save_snapshot(subscribe, _site_complete_total(site_total=90))
    handler = _handler(
        subscribe,
        store,
        config=_cfg(
            site_total_probe_enabled=False,
            site_completion_evidence_enabled=True,
        ),
    )
    data = SubscribeEpisodesRefreshEventData(current_total_episode=85, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is False
    assert data.total_episode is None
    assert store.read_applied(subscribe) is None


def test_refresh_handler_ignores_non_total_site_signal():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=10)
    store.save_snapshot(
        subscribe,
        _site_total_ahead(
            kind="site_complete_pack",
            confidence="low",
            site_total=0,
            site_candidate_total=0,
            complete_hint=True,
            reason="站点标题包含完结提示但缺少可靠总集数",
        ),
    )
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(current_total_episode=10, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is False
    assert data.total_episode is None


def test_refresh_handler_skips_when_main_total_is_ahead_of_site_evidence():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=12)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=12, current_total=10))
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(current_total_episode=13, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is False
    assert data.total_episode is None
    assert store.read_applied(subscribe) is None


def test_refresh_handler_skips_when_site_evidence_is_below_live_target():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=100)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=95, current_total=90))
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(current_total_episode=90, subscribe_id=1, season=1)

    handler.handle_refresh(data)

    assert data.updated is False
    assert data.total_episode is None
    assert store.read_applied(subscribe) is None


def test_refresh_handler_does_not_override_when_tmdb_completion_signal_is_reliable():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=10)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=12, current_total=10))
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(
        current_total_episode=10,
        subscribe_id=1,
        season=1,
        mediainfo=_ended_mediainfo(),
    )

    handler.handle_refresh(data)

    assert data.updated is False
    assert data.total_episode is None
    assert store.read_applied(subscribe) is None


def test_refresh_handler_does_not_override_when_tmdb_finale_signal_is_reliable():
    store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(total_episode=10)
    store.save_snapshot(subscribe, _site_total_ahead(site_total=12, current_total=10))
    handler = _handler(subscribe, store)
    data = SubscribeEpisodesRefreshEventData(
        current_total_episode=10,
        subscribe_id=1,
        season=1,
        mediainfo=_finale_mediainfo(),
    )

    handler.handle_refresh(data)

    assert data.updated is False
    assert data.total_episode is None
    assert store.read_applied(subscribe) is None


def test_refresh_handler_ignores_expired_or_identity_mismatch_evidence():
    expired_store = SiteEvidenceStore(_task_manager())
    subscribe = _sub(id=7, total_episode=10)
    expired_store.save_snapshot(
        subscribe,
        _site_total_ahead(
            site_total=12,
            expires_at=(_now() - timedelta(seconds=1)).isoformat(),
        ),
    )
    expired_data = SubscribeEpisodesRefreshEventData(current_total_episode=10, subscribe_id=7, season=1)

    _handler(subscribe, expired_store).handle_refresh(expired_data)

    assert expired_data.updated is False

    mismatch_store = SiteEvidenceStore(_task_manager())
    stale_subscribe = _sub(id=7, tmdbid=200, total_episode=10)
    mismatch_store.save_snapshot(stale_subscribe, _site_total_ahead(site_total=12, tmdbid=200))
    mismatch_data = SubscribeEpisodesRefreshEventData(current_total_episode=10, subscribe_id=7, season=1)

    _handler(subscribe, mismatch_store).handle_refresh(mismatch_data)

    assert mismatch_data.updated is False
    assert mismatch_store.read_snapshot(subscribe) is None


def test_scanner_saves_site_total_ahead_snapshot():
    store = SiteEvidenceStore(_task_manager())
    provider = MagicMock(return_value=[_ctx(episodes=[1, 2, 3, 4, 5])])
    scanner = SiteEvidenceScanner(
        config=_cfg(site_total_probe_enabled=True),
        store=store,
        candidate_provider=provider,
        now_fn=_now,
    )
    subscribe = _sub(total_episode=3)

    evidence = scanner.refresh_subscribe(subscribe)

    provider.assert_called_once_with(subscribe, allow_title_match=True)
    assert evidence.kind == "site_total_ahead"
    assert store.read_snapshot(subscribe).site_candidate_total == 5


def test_scanner_saves_no_evidence_without_clearing_applied_marker():
    store = SiteEvidenceStore(_task_manager())
    provider = MagicMock(return_value=[])
    scanner = SiteEvidenceScanner(
        config=_cfg(site_total_probe_enabled=True),
        store=store,
        candidate_provider=provider,
        now_fn=_now,
    )
    subscribe = _sub(total_episode=12)
    store.mark_applied(subscribe, applied_total=12, applied_base_total=10, reason="site_total_ahead", now=_now())

    evidence = scanner.refresh_subscribe(subscribe)

    assert evidence.kind == "no_evidence"
    assert store.read_snapshot(subscribe).kind == "no_evidence"
    assert store.read_applied(subscribe).applied_total == 12


def test_scanner_skips_when_both_site_switches_disabled():
    store = SiteEvidenceStore(_task_manager())
    provider = MagicMock(return_value=[_ctx(episodes=[1, 2, 3, 4, 5])])
    scanner = SiteEvidenceScanner(
        config=_cfg(site_total_probe_enabled=False, site_completion_evidence_enabled=False),
        store=store,
        candidate_provider=provider,
        now_fn=_now,
    )

    assert scanner.refresh_subscribe(_sub(total_episode=3)) is None
    provider.assert_not_called()


def test_scanner_skips_ineligible_subscribe_without_calling_provider():
    store = SiteEvidenceStore(_task_manager())
    provider = MagicMock(return_value=[_ctx(episodes=[1, 2, 3, 4, 5])])
    scanner = SiteEvidenceScanner(
        config=_cfg(site_total_probe_enabled=True),
        store=store,
        candidate_provider=provider,
        now_fn=_now,
    )

    assert scanner.refresh_subscribe(_sub(total_episode=3, state="S")) is None
    provider.assert_not_called()


def test_scanner_returns_none_when_candidate_provider_fails():
    store = SiteEvidenceStore(_task_manager())
    provider = MagicMock(side_effect=RuntimeError("cache unavailable"))
    scanner = SiteEvidenceScanner(
        config=_cfg(site_total_probe_enabled=True),
        store=store,
        candidate_provider=provider,
        now_fn=_now,
    )

    assert scanner.refresh_subscribe(_sub(total_episode=3)) is None
    provider.assert_called_once()
