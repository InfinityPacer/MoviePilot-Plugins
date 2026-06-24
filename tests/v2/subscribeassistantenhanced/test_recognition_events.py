"""识别增强 ResourceSelection 事件集成测试。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.context import Context, MediaInfo, TorrentInfo
from app.core.metainfo import MetaInfo
from app.schemas.event import ResourceDownloadEventData, ResourceSelectionEventData
from app.schemas.types import MediaType

from subscribeassistantenhanced.events import EventProxy
from subscribeassistantenhanced.recognition.guard import RecognitionGuard
from subscribeassistantenhanced.recognition.types import RecognitionRuntime, RecognitionSettings


def _ctx(title, episodes=None):
    return SimpleNamespace(
        torrent_info=SimpleNamespace(
            title=title,
            description="",
            site_name="站点",
            enclosure=f"enclosure-{title}",
            page_url=f"https://site/{title}",
        ),
        meta_info=SimpleNamespace(episode_list=episodes or [], begin_episode=None, end_episode=None),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )


def _sub(**kwargs):
    defaults = dict(
        id=1,
        name="测试剧",
        year="2026",
        tmdbid=100,
        doubanid=None,
        season=1,
        episode_group=None,
        type="电视剧",
        best_version=0,
        best_version_full=0,
        start_episode=1,
        total_episode=12,
        episode_priority={},
        custom_words="",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_resource_selection_runs_recognition_between_serial_and_delete_filter():
    calls = []
    blocked_by_serial = _ctx("serial", [1])
    blocked_by_guard = _ctx("guard", [2])
    blocked_by_delete = _ctx("delete", [3])
    kept = _ctx("kept", [4])
    guard = MagicMock()
    guard.filter.side_effect = lambda contexts, **kw: calls.append(("guard", list(contexts))) or [
        blocked_by_delete,
        kept,
    ]
    guard.finalize_batch.side_effect = lambda final_count, stage_counts=None: calls.append(
        ("finalize", final_count, list(stage_counts or []))
    )
    deletes_store = MagicMock()
    deletes_store.match.side_effect = lambda enclosure=None, page_url=None: (
        calls.append(("delete", enclosure, page_url)) or enclosure == "enclosure-delete"
    )
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(best_version=1, best_version_full=0)
    task_manager = MagicMock()
    task_manager.read.side_effect = lambda key: {
        "subscribes": {"1": {"download_pending": {"h1": True}}},
        "torrents": {"h1": {"episodes": [1]}},
    }.get(key, {})
    data = SimpleNamespace(
        origin='Subscribe|{"id": 1}',
        contexts=[blocked_by_serial, blocked_by_guard, blocked_by_delete, kept],
        updated=False,
        updated_contexts=None,
        source="",
    )

    EventProxy(
        task_manager=task_manager,
        subscribe_oper=subscribe_oper,
        pending_download_enabled=True,
        recognition_guard=guard,
        deletes_store=deletes_store,
        skip_deletion=True,
    ).on_resource_selection(SimpleNamespace(event_data=data))

    assert guard.filter.call_args.kwargs["subscribe"].id == 1
    assert guard.filter.call_args.kwargs["stage_counts"][0] == {
        "stage": "wash_serial",
        "input": 4,
        "output": 3,
    }
    assert guard.filter.call_args.args[0] == [blocked_by_guard, blocked_by_delete, kept]
    assert data.updated is True
    assert data.updated_contexts == [kept]
    assert calls[0] == ("guard", [blocked_by_guard, blocked_by_delete, kept])
    assert [call[0] for call in calls[1:3]] == ["delete", "delete"]
    assert calls[-1] == (
        "finalize",
        1,
        [
            {"stage": "wash_serial", "input": 4, "output": 3},
            {"stage": "delete_fingerprint", "input": 2, "output": 1},
        ],
    )


def test_resource_selection_full_best_version_pending_records_zero_recognition_input():
    guard = MagicMock()
    guard.filter.side_effect = lambda contexts, **kw: list(contexts)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(best_version=1, best_version_full=1)
    task_manager = MagicMock()
    task_manager.read.side_effect = lambda key: {
        "subscribes": {"1": {"download_pending": {"h1": True}}},
        "torrents": {"h1": {"episodes": [1]}},
    }.get(key, {})
    data = SimpleNamespace(
        origin='Subscribe|{"id": 1}',
        contexts=[_ctx("A", [1]), _ctx("B", [2])],
        updated=False,
        updated_contexts=None,
        source="",
    )

    EventProxy(
        task_manager=task_manager,
        subscribe_oper=subscribe_oper,
        pending_download_enabled=True,
        recognition_guard=guard,
    ).on_resource_selection(SimpleNamespace(event_data=data))

    assert guard.filter.call_args.args[0] == []
    assert guard.filter.call_args.kwargs["stage_counts"][0] == {
        "stage": "wash_serial",
        "input": 2,
        "output": 0,
    }
    assert guard.filter.call_args.kwargs["selection_original_count"] == 2
    assert data.updated is True
    assert data.updated_contexts == []


def test_resource_selection_recognition_uses_existing_updated_contexts():
    removed_before_guard = _ctx("removed-before-guard", [1])
    candidate_a = _ctx("candidate-a", [2])
    candidate_b = _ctx("candidate-b", [3])
    guard = MagicMock()
    guard.filter.side_effect = lambda contexts, **kw: list(contexts)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub()
    data = SimpleNamespace(
        origin='Subscribe|{"id": 1}',
        contexts=[removed_before_guard, candidate_a, candidate_b],
        updated=True,
        updated_contexts=[candidate_a, candidate_b],
        source="upstream",
    )

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert guard.filter.call_args.args[0] == [candidate_a, candidate_b]
    assert guard.filter.call_args.kwargs["selection_original_count"] == 3
    assert guard.filter.call_args.kwargs["stage_counts"][0] == {
        "stage": "wash_serial",
        "input": 2,
        "output": 2,
    }
    assert data.updated is True
    assert data.updated_contexts == [candidate_a, candidate_b]
    assert data.source == "upstream"


def test_full_best_version_pending_zero_input_still_has_recognition_audit():
    guard = RecognitionGuard(RecognitionSettings(mode="balanced"))
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(best_version=1, best_version_full=1)
    task_manager = MagicMock()
    task_manager.read.side_effect = lambda key: {
        "subscribes": {"1": {"download_pending": {"h1": True}}},
        "torrents": {"h1": {"episodes": [1]}},
    }.get(key, {})
    data = SimpleNamespace(
        origin='Subscribe|{"id": 1}',
        contexts=[_ctx("A", [1]), _ctx("B", [2])],
        updated=False,
        updated_contexts=None,
        source="",
    )

    EventProxy(
        task_manager=task_manager,
        subscribe_oper=subscribe_oper,
        pending_download_enabled=True,
        recognition_guard=guard,
    ).on_resource_selection(SimpleNamespace(event_data=data))

    assert guard.last_batch.selection_original_count == 2
    assert guard.last_batch.recognition_input_count == 0
    assert guard.last_batch.recognition_evaluated_count == 0
    assert guard.last_batch.recognition_output_count == 0
    assert guard.last_batch.final_count == 0
    assert "stage=wash_serial" in guard.last_audit_summary
    assert "recognition_evaluated_count=0" in guard.last_audit_summary


def test_resource_selection_without_subscription_origin_skips_recognition():
    guard = MagicMock()
    data = SimpleNamespace(origin="Manual|{}", contexts=[_ctx("A")], updated=False, updated_contexts=None, source="")

    EventProxy(recognition_guard=guard).on_resource_selection(SimpleNamespace(event_data=data))

    guard.filter.assert_not_called()
    assert data.updated is False


def test_resource_selection_runs_recognition_for_all_subscription_modes():
    guard = MagicMock()
    guard.filter.side_effect = lambda contexts, **kw: list(contexts)
    subscribe_oper = MagicMock()
    modes = [
        _sub(id=1, type="电影", season=None, best_version=0, best_version_full=0),
        _sub(id=2, type="电视剧", best_version=0, best_version_full=0),
        _sub(id=3, type="电视剧", best_version=1, best_version_full=0),
        _sub(id=4, type="电视剧", best_version=1, best_version_full=1),
    ]

    for sub in modes:
        subscribe_oper.get.return_value = sub
        data = SimpleNamespace(
            origin=f'Subscribe|{{"id": {sub.id}}}',
            contexts=[_ctx(f"candidate-{sub.id}", [1])],
            updated=False,
            updated_contexts=None,
            source="",
        )

        EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
            SimpleNamespace(event_data=data)
        )

    assert guard.filter.call_count == 4
    assert [call.kwargs["subscribe"].id for call in guard.filter.call_args_list] == [1, 2, 3, 4]


def _settings(mode="balanced", keyword_config=""):
    return RecognitionSettings(mode=mode, keyword_config=keyword_config)


def _real_context(
        title,
        episodes,
        *,
        enclosure=None,
        page_url=None,
        allowed_episodes=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
        media_tmdb_id=100,
        media_douban_id="db100",
        media_type=MediaType.TV,
        year=None,
):
    meta = MetaInfo(title)
    parsed_episodes = list(episodes)
    meta.year = year
    meta.begin_episode = min(parsed_episodes) if parsed_episodes else None
    meta.end_episode = max(parsed_episodes) if len(parsed_episodes) > 1 else None
    meta.total_episode = len(parsed_episodes) if len(parsed_episodes) > 1 else None
    return Context(
        torrent_info=TorrentInfo(
            title=title,
            description="",
            site_name="站点",
            enclosure=enclosure,
            page_url=page_url,
        ),
        meta_info=meta,
        media_info=MediaInfo(type=media_type, title="将夜", year=year, tmdb_id=media_tmdb_id,
                             douban_id=media_douban_id, season=1),
        candidate_recognized=candidate_recognized,
        match_source=match_source,
        media_info_is_target=media_info_is_target,
        allowed_episodes=allowed_episodes,
    )


def test_real_resource_selection_uses_real_contexts_and_sanitizes_audit():
    logger_fn = MagicMock()
    guard = RecognitionGuard(
        _settings(mode="balanced"),
        runtime=RecognitionRuntime(logger_fn=logger_fn),
    )
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    contexts = [
        _real_context(
            "将夜 全60集",
            range(1, 61),
            enclosure="https://tracker/download?passkey=SECRET",
            page_url="https://tracker/details?token=TOKEN",
        ),
        _real_context("将夜 第8集", [8], year="2026"),
    ]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert data.updated is True
    assert data.updated_contexts == [contexts[1]]
    assert "SECRET" not in guard.last_audit_summary
    assert "TOKEN" not in guard.last_audit_summary
    assert "soft_block=1" in guard.last_audit_summary
    assert "allow=1" in guard.last_audit_summary
    assert "final_action=soft_block" in guard.last_audit_summary
    assert "final_action=allow" in guard.last_audit_summary
    assert "fingerprint=" in guard.last_audit_summary
    assert "reason=" in guard.last_audit_summary
    assert "stage=recognition" in guard.last_audit_summary
    assert "stage=wash_serial" in guard.last_audit_summary
    logger_fn.assert_called()
    assert guard.last_audit_summary in logger_fn.call_args.args[0]


def test_real_resource_selection_blocks_disjoint_range_without_using_allowed_episodes_as_candidate_range():
    guard = RecognitionGuard(_settings(mode="balanced"))
    contexts = [
        _real_context("将夜 E40-E60", range(40, 61), allowed_episodes={8}),
        _real_context("将夜 第8集", [8], allowed_episodes={8}),
    ]
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert data.updated is True
    assert data.updated_contexts == [contexts[1]]
    assert "target_range_not_covered" in guard.last_audit_summary


def test_real_resource_selection_movie_blocks_series_candidate():
    guard = RecognitionGuard(_settings(mode="balanced"))
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(
        name="测试电影",
        type="电影",
        season=None,
        start_episode=None,
        total_episode=None,
    )
    contexts = [_real_context("测试电影 S01E01", [1], media_type=MediaType.MOVIE, year="2026")]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert data.updated is True
    assert data.updated_contexts == []
    assert guard.last_batch.decisions[0].code == "movie_series_conflict"
    assert "range_source=movie" in guard.last_audit_summary


def test_real_resource_selection_episode_best_version_blocks_disjoint_candidate_range():
    guard = RecognitionGuard(_settings(mode="balanced"))
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(best_version=1, best_version_full=0, start_episode=8, total_episode=19)
    contexts = [
        _real_context("将夜 S01E40-E60", range(40, 61), year="2026"),
        _real_context("将夜 S01E08", [8], year="2026"),
    ]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert data.updated is True
    assert data.updated_contexts == [contexts[1]]
    assert "range_source=episode_best_version" in guard.last_audit_summary
    assert "target_range_not_covered" in guard.last_audit_summary


def test_real_resource_selection_full_season_best_version_uses_episode_group_resolver():
    target_resolver = MagicMock(return_value=MediaInfo(type=MediaType.TV, title="将夜", season=1,
                                                       tmdb_id=100, names=["将夜"]))
    tmdb_episodes_fn = MagicMock(return_value=[
        SimpleNamespace(episode_number=1),
        SimpleNamespace(episode_number=2),
    ])
    guard = RecognitionGuard(
        _settings(mode="balanced"),
        runtime=RecognitionRuntime(
            target_mediainfo_resolver=target_resolver,
            tmdb_episodes_fn=tmdb_episodes_fn,
        ),
    )
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(best_version=1, best_version_full=1, episode_group="eg-1",
                                           start_episode=1, total_episode=2)
    contexts = [_real_context("将夜 S01E01", [1])]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    target_resolver.assert_called_once()
    tmdb_episodes_fn.assert_called_once()
    assert "range_source=episode_group" in guard.last_audit_summary


def test_audit_mode_real_resource_selection_does_not_change_candidate_choice():
    guard = RecognitionGuard(_settings(mode="audit"))
    contexts = [
        _real_context("将夜 E40-E60", range(40, 61), allowed_episodes={8}),
        _real_context("将夜 第8集", [8], allowed_episodes={8}),
    ]
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert data.updated is False
    assert data.updated_contexts is None
    assert "target_range_not_covered" in guard.last_audit_summary
    assert "would_action=block" in guard.last_audit_summary


def test_real_context_trusted_tmdb_identity_downgrades_weak_risk():
    guard = RecognitionGuard(_settings(mode="balanced"))
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    contexts = [
        _real_context(
            "将夜 S01E08 缺少年份",
            [8],
            candidate_recognized=True,
            match_source="tmdbid",
            media_info_is_target=False,
            media_tmdb_id=100,
        )
    ]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert data.updated is False
    assert "candidate_same_identity" in guard.last_audit_summary
    assert "missing_year" not in guard.last_audit_summary


def test_real_context_target_media_info_is_not_trusted_candidate_identity_when_recognized():
    guard = RecognitionGuard(_settings(mode="balanced"))
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    contexts = [
        _real_context(
            "将夜 S01E08 缺少年份",
            [8],
            candidate_recognized=True,
            match_source="tmdbid",
            media_info_is_target=True,
            media_tmdb_id=100,
        )
    ]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert "candidate_same_identity" not in guard.last_audit_summary
    assert "missing_year" in guard.last_audit_summary


def test_real_context_secondary_recognizer_runs_for_balanced_mode():
    secondary = MagicMock(return_value=MediaInfo(type=MediaType.TV, title="其它剧", year="2026", tmdb_id=200))
    guard = RecognitionGuard(
        _settings(mode="balanced"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    contexts = [_real_context("其它标题 S01E08", [8], year="2026")]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    secondary.assert_called_once()
    assert data.updated is True
    assert data.updated_contexts == []
    assert guard.last_batch.decisions[0].code == "secondary_identity_conflict"


def test_real_context_secondary_failure_is_audited_as_fail_open_without_filtering():
    secondary = MagicMock(side_effect=RuntimeError("tmdb token=SECRET"))
    guard = RecognitionGuard(
        _settings(mode="balanced"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    contexts = [_real_context("将夜 S01E08", [8], year="2026")]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    secondary.assert_called_once()
    assert data.updated is False
    assert guard.last_batch.decisions[0].final_action == "fail_open"
    assert guard.last_batch.decisions[0].code == "secondary_recognition_fail_open"
    assert "secondary_recognition_fail_open" in guard.last_audit_summary
    assert "SECRET" not in guard.last_audit_summary


def test_trusted_identity_counters_oversized_pack_soft_risk():
    guard = RecognitionGuard(_settings(mode="balanced"))
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    contexts = [
        _real_context(
            "将夜 全60集",
            range(1, 61),
            candidate_recognized=True,
            match_source="tmdbid",
            media_info_is_target=False,
            media_tmdb_id=100,
            year="2026",
        )
    ]
    data = ResourceSelectionEventData(origin='Subscribe|{"id": 1}', contexts=contexts)

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert data.updated is False
    assert "candidate_same_identity" in guard.last_audit_summary
    assert "target_range_oversized" not in guard.last_audit_summary


def test_resource_download_does_not_call_recognition_guard_or_cancel_download():
    guard = MagicMock()
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub(start_episode=8, total_episode=19)
    monitor = MagicMock()
    subscription_cleanup = MagicMock()
    priority_manager = MagicMock()
    data = ResourceDownloadEventData(
        origin='Subscribe|{"id": 1}',
        context=_real_context("将夜 第8集", [8]),
        episodes={8},
        downloader="downloader",
    )

    EventProxy(
        subscribe_oper=subscribe_oper,
        recognition_guard=guard,
        download_monitor=monitor,
        subscription_cleanup=subscription_cleanup,
        priority_manager=priority_manager,
        pending_download_enabled=True,
    ).on_resource_download(SimpleNamespace(event_data=data))

    guard.filter.assert_not_called()
    guard.evaluate.assert_not_called()
    guard.notification_payload.assert_not_called()
    monitor.mark_download_started.assert_called_once()
    subscription_cleanup.handle_resource_download_history_clear.assert_called_once()
    assert data.cancel is False
    assert data.reason == ""


def test_recognition_guard_notification_payload_is_dispatched():
    guard = MagicMock()
    guard.filter.return_value = []
    guard.notification_payload.return_value = ("识别增强汇总", "拦截 1 条")
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub()
    notify_fn = MagicMock()
    data = SimpleNamespace(origin='Subscribe|{"id": 1}', contexts=[_ctx("A")],
                           updated=False, updated_contexts=None, source="")
    proxy = EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard, notify_fn=notify_fn)

    proxy.on_resource_selection(SimpleNamespace(event_data=data))

    notify_fn.assert_called_once_with("识别增强汇总", text="拦截 1 条", diagnostic=True)


def test_recognition_guard_audit_is_generated_when_notification_dispatch_is_disabled():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="hard_block:\n  - 强制错误\n"))
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = _sub()
    data = SimpleNamespace(origin='Subscribe|{"id": 1}', contexts=[_ctx("强制错误", [1])],
                           updated=False, updated_contexts=None, source="")

    EventProxy(subscribe_oper=subscribe_oper, recognition_guard=guard).on_resource_selection(
        SimpleNamespace(event_data=data)
    )

    assert data.updated is True
    assert guard.last_audit_summary
    assert "user_hard_block" in guard.last_audit_summary
    assert guard.last_notification is None


def test_recognition_guard_notification_rate_limit_does_not_suppress_audit():
    guard = RecognitionGuard(_settings(mode="balanced"))
    subscribe = _sub(id=1)
    guard.last_batch = SimpleNamespace(decisions=[
        SimpleNamespace(final_action="block", code="tmdb_id_mismatch", reason="候选 ID 错配")
    ])
    guard.last_audit_summary = "candidate=1 block=1"

    first = guard.notification_payload(subscribe)
    second = guard.notification_payload(subscribe)

    assert first is not None
    assert second is None
    assert guard.last_audit_summary == "candidate=1 block=1"
