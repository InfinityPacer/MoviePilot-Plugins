"""识别增强核心判定测试。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.types import MediaType

from subscribeassistantenhanced.recognition.audit import (
    candidate_fingerprint,
    redact_sensitive_text,
    sanitize_candidate_summary,
)
from subscribeassistantenhanced.recognition.guard import RecognitionGuard
from subscribeassistantenhanced.recognition.scope import (
    build_target,
    candidate_from_context,
)
from subscribeassistantenhanced.recognition.types import (
    CandidateResource,
    RecognitionRuntime,
    RecognitionSettings,
    RecognitionTarget,
)


def _sub(**kwargs):
    defaults = dict(
        id=1,
        name="测试剧",
        tmdbid=100,
        doubanid=None,
        year="2026",
        season=1,
        episode_group=None,
        type="电视剧",
        best_version=0,
        best_version_full=0,
        start_episode=1,
        total_episode=12,
        episode_priority={},
        custom_words="别名A\n别名B",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _settings(mode="balanced", keyword_config="", custom_config="", notify_mode="off"):
    return RecognitionSettings(
        mode=mode,
        keyword_config=keyword_config,
        custom_config=custom_config,
        notify_mode=notify_mode,
    )


def _target(**kwargs):
    defaults = dict(
        name="测试剧",
        media_type="电视剧",
        tmdb_id=100,
        target_episodes=list(range(1, 13)),
        range_confidence="high",
    )
    defaults.update(kwargs)
    return defaults


def _candidate(**kwargs):
    defaults = dict(
        title="测试剧 S01E08",
        description="动画",
        episodes=[8],
        explicit_tmdb_id=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )
    defaults.update(kwargs)
    return defaults


class RecordingSecondaryRecognizer:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, meta):
        self.calls.append(meta)
        if not self.results:
            return None
        return self.results.pop(0)


def _media_result(tmdb_id=None, douban_id=None):
    return SimpleNamespace(tmdb_id=tmdb_id, douban_id=douban_id)


def test_candidate_fingerprint_uses_sensitive_url_without_leaking_it():
    torrent = SimpleNamespace(
        enclosure="https://tracker.local/download?id=1&passkey=SECRET",
        page_url="https://tracker.local/details/1?token=TOKEN",
        title="候选标题",
        description="副标题",
        site_name="站点A",
        category="TV",
    )

    fingerprint = candidate_fingerprint(torrent)
    summary = sanitize_candidate_summary(torrent)

    assert len(fingerprint) >= 12
    assert "SECRET" not in fingerprint
    assert "TOKEN" not in fingerprint
    assert "SECRET" not in summary
    assert "TOKEN" not in summary
    assert "tracker.local" not in summary
    assert "download" not in summary
    assert "details" not in summary
    assert "passkey" not in summary
    assert "token" not in summary
    assert "候选标题" in summary
    assert "副标题" in summary
    assert "站点A" in summary
    assert len(sanitize_candidate_summary(torrent, max_length=24)) <= 24


def test_candidate_summary_redacts_sensitive_text_in_title_and_description():
    torrent = SimpleNamespace(
        enclosure="",
        page_url="",
        title="资源 https://tracker.local/download?token=TITLE_TOKEN&passkey=TITLE_PASS",
        description="详情 magnet:?xt=urn:btih:abc&token=DESC_TOKEN passkey=DESC_PASS",
        site_name="站点A",
    )

    summary = sanitize_candidate_summary(torrent)

    assert "TITLE_TOKEN" not in summary
    assert "TITLE_PASS" not in summary
    assert "DESC_TOKEN" not in summary
    assert "DESC_PASS" not in summary
    assert "token=" not in summary
    assert "passkey=" not in summary
    assert "tracker.local" not in summary
    assert "magnet:" not in summary


def test_candidate_summary_redacts_cookie_and_local_paths():
    torrent = SimpleNamespace(
        enclosure="",
        page_url="",
        title="资源 Cookie: uid=SECRET /Users/chengyu/Downloads/private.torrent",
        description="本地路径 /media/private/movie.mkv password=DESC_PASS",
        site_name="站点A",
    )

    summary = sanitize_candidate_summary(torrent)

    assert "SECRET" not in summary
    assert "DESC_PASS" not in summary
    assert "/Users/" not in summary
    assert "/media/" not in summary
    assert "Cookie:" not in summary


def test_redact_sensitive_text_handles_space_separated_authorization_tokens():
    text = (
        "请求失败 Authorization: Bearer SECRET_TOKEN authorization=Bearer OTHER_TOKEN "
        "Authorization Bearer THIRD_TOKEN Cookie uid=COOKIE_SECRET"
    )

    redacted = redact_sensitive_text(text)

    assert "SECRET_TOKEN" not in redacted
    assert "OTHER_TOKEN" not in redacted
    assert "THIRD_TOKEN" not in redacted
    assert "COOKIE_SECRET" not in redacted
    assert "Bearer" not in redacted
    assert "Cookie uid" not in redacted
    assert redacted.count("[redacted-secret]") == 4


def test_redact_sensitive_text_redacts_full_cookie_header_without_title_false_positive():
    text = "请求 Cookie: uid=USER123; cf_clearance=CLEAR_VALUE | 普通标题 Cookie 小甜饼 第1集"

    redacted = redact_sensitive_text(text)

    assert "USER123" not in redacted
    assert "CLEAR_VALUE" not in redacted
    assert "cf_clearance" not in redacted
    assert "普通标题 Cookie 小甜饼 第1集" in redacted
    assert "[redacted-secret] | 普通标题" in redacted


def test_candidate_summary_redacts_unicode_local_paths():
    torrent = SimpleNamespace(
        enclosure="",
        page_url="",
        title="资源 /Users/chengyu/Library/CloudStorage/OneDrive-个人/媒体库/剧集/测试剧.mkv",
        description="整理路径 /volume1/影视库/国漫/测试剧/第01集.mkv",
        site_name="站点A",
    )

    summary = sanitize_candidate_summary(torrent)

    assert "/Users/" not in summary
    assert "/volume1/" not in summary
    assert "OneDrive-个人" not in summary
    assert "影视库" not in summary
    assert "测试剧.mkv" not in summary
    assert "[redacted-path]" in summary


def test_keyword_reason_is_sanitized_in_audit_and_notification():
    sensitive_rule = "token=RULE_TOKEN"
    guard = RecognitionGuard(_settings(
        mode="balanced",
        keyword_config=f"hard_block:\n  - '{sensitive_rule}'\n",
        notify_mode="detail",
    ))
    subscribe = _sub(id=1, name="测试剧")
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(
            title=f"测试剧 {sensitive_rule}",
            description="候选说明 /Users/chengyu/private/file.torrent",
            site_name="站点A",
            category="TV",
        ),
        meta_info=SimpleNamespace(year="2026", type=None, episode_list=[8], begin_season=1),
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=subscribe)
    payload = guard.notification_payload(subscribe)
    combined = guard.last_audit_summary + "\n" + ("\n".join(payload) if payload else "")

    assert "RULE_TOKEN" not in combined
    assert "/Users/" not in combined
    assert "[redacted" in combined


def test_build_target_for_normal_tv_uses_subscribe_range():
    target = build_target(_sub(start_episode=8, total_episode=19), mediainfo=None)

    assert target.target_episodes == list(range(8, 20))
    assert target.range_source == "subscribe_range"
    assert target.range_confidence == "high"


def test_build_target_for_normal_movie_has_single_movie_scope():
    target = build_target(_sub(name="测试电影", type="电影", season=None, start_episode=None, total_episode=None))

    assert target.media_type == "电影"
    assert target.target_episodes == []
    assert target.range_source == "movie"
    assert target.range_confidence == "high"


def test_build_target_for_movie_best_version_keeps_movie_scope():
    target = build_target(
        _sub(name="测试电影", type="电影", season=None, best_version=1, best_version_full=0),
        tmdb_episodes_fn=MagicMock(return_value=[SimpleNamespace(episode_number=1)]),
    )

    assert target.media_type == "电影"
    assert target.target_episodes == []
    assert target.range_source == "movie"
    assert target.range_confidence == "high"


def test_build_target_for_episode_best_version_keeps_full_target_window():
    target = build_target(_sub(best_version=1, best_version_full=0, total_episode=12,
                               episode_priority={"1": 100}))

    assert target.target_episodes == list(range(1, 13))
    assert target.range_source == "episode_best_version"


def test_build_target_for_full_best_version_uses_episode_group_scope():
    episodes = [SimpleNamespace(episode_number=51), SimpleNamespace(episode_number=52)]
    target = build_target(
        _sub(best_version=1, best_version_full=1, episode_group="eg-1"),
        mediainfo=None,
        tmdb_episodes_fn=lambda **kw: episodes,
    )

    assert target.target_episodes == [51, 52]
    assert target.range_source == "episode_group"
    assert target.episode_group == "eg-1"


def test_build_target_for_full_best_version_fail_opens_when_scope_unavailable():
    missing_resolver = build_target(_sub(best_version=1, best_version_full=1, episode_group="eg-1"))
    empty_scope = build_target(
        _sub(best_version=1, best_version_full=1, episode_group="eg-1"),
        tmdb_episodes_fn=lambda **kw: [],
    )

    assert missing_resolver.target_episodes == []
    assert missing_resolver.range_source == "scope_unavailable"
    assert missing_resolver.range_confidence == "unknown"
    assert empty_scope.target_episodes == []
    assert empty_scope.range_source == "scope_unavailable"
    assert empty_scope.range_confidence == "unknown"


def test_build_target_for_full_best_version_fail_opens_when_scope_lookup_raises():
    target = build_target(
        _sub(best_version=1, best_version_full=1, episode_group="eg-1"),
        tmdb_episodes_fn=MagicMock(side_effect=RuntimeError("tmdb token=SECRET /volume1/影视库/测试剧")),
    )

    assert target.target_episodes == []
    assert target.range_source == "scope_unavailable"
    assert target.range_confidence == "unknown"


def test_build_target_uses_target_mediainfo_aliases_and_animation_shape():
    mediainfo = SimpleNamespace(
        title="师兄啊师兄",
        en_title="Big Brother",
        names=["师兄啊师兄", "Big Brother"],
        category="动漫",
        genres=[{"name": "动画"}],
    )

    target = build_target(_sub(name="师兄啊师兄", custom_words="一念永恒动画"), mediainfo=mediainfo)

    assert target.shape == "animation"
    assert "师兄啊师兄" in target.aliases
    assert "一念永恒动画" in target.aliases
    assert "Big Brother" in target.aliases
    assert target.alias_strengths["师兄啊师兄"] == "strong"
    assert target.alias_strengths["一念永恒动画"] == "strong"
    assert target.alias_strengths["Big Brother"] == "weak"


def test_english_short_alias_is_marked_weak():
    mediainfo = SimpleNamespace(
        title="师兄啊师兄",
        en_title="Big Brother",
        original_title="Big Brother",
        names=["师兄啊师兄", "Big Brother"],
        category="动漫",
        genres=[{"name": "动画"}],
    )

    target = build_target(_sub(name="师兄啊师兄", custom_words="师兄啊师兄"), mediainfo=mediainfo)

    assert target.alias_strengths["Big Brother"] == "weak"
    assert "Big Brother" in target.aliases


def test_candidate_from_context_reads_main_program_identity_fields():
    ctx = SimpleNamespace(
        torrent_info=SimpleNamespace(title="测试剧 S01E08", description="动画", site_name="站点"),
        meta_info=SimpleNamespace(year="2026", type=None, episode_list=[8], begin_season=1,
                                  begin_episode=8, end_episode=8,
                                  tmdbid=None, doubanid=None),
        media_info=SimpleNamespace(tmdb_id=100, douban_id="db100",
                                   languages=["zh"], origin_country=["CN"]),
        candidate_recognized=True,
        match_source="tmdbid",
        media_info_is_target=False,
    )

    candidate = candidate_from_context(ctx, order=3)

    assert candidate.title == "测试剧 S01E08"
    assert candidate.episodes == [8]
    assert candidate.order == 3
    assert candidate.candidate_recognized is True
    assert candidate.match_source == "tmdbid"
    assert candidate.media_info_is_target is False
    assert candidate.recognized_tmdb_id == 100
    assert candidate.explicit_tmdb_id is None
    assert candidate.season == 1
    assert candidate.season_kind == "main"
    assert candidate.range_source == "meta_info"
    assert candidate.languages == ["zh"]
    assert candidate.origin_countries == ["CN"]


def test_candidate_from_context_normalizes_real_media_type_enum():
    ctx = SimpleNamespace(
        torrent_info=SimpleNamespace(title="测试剧 S01E08", description="", site_name="站点"),
        meta_info=SimpleNamespace(year="2026", type=MediaType.TV, episode_list=[8], begin_season=1,
                                  begin_episode=8, end_episode=8, tmdbid=None, doubanid=None),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    assert candidate_from_context(ctx).media_type == "电视剧"


def test_candidate_from_context_parses_range_from_meta_or_title_without_context_episodes():
    by_meta = SimpleNamespace(
        torrent_info=SimpleNamespace(title="将夜", description="", site_name="站点"),
        meta_info=SimpleNamespace(year=None, type="电视剧", episode_list=list(range(8, 20)),
                                  begin_episode=8, end_episode=19, tmdbid=None, doubanid=None),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )
    by_title = SimpleNamespace(
        torrent_info=SimpleNamespace(title="Ever Night S01 E40-E60", description="", site_name="站点"),
        meta_info=SimpleNamespace(year=None, type="电视剧", episode_list=[], begin_episode=None, end_episode=None,
                                  tmdbid=None, doubanid=None),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    assert candidate_from_context(by_meta).episodes == list(range(8, 20))
    assert candidate_from_context(by_title).episodes == list(range(40, 61))


def test_candidate_from_context_keeps_special_season_scope():
    ctx = SimpleNamespace(
        torrent_info=SimpleNamespace(title="灵笼 S00E07", description="特别篇", site_name="站点"),
        meta_info=SimpleNamespace(year="2026", type="电视剧", episode_list=[7], begin_season=0,
                                  begin_episode=7, end_episode=7, tmdbid=None, doubanid=None),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    candidate = candidate_from_context(ctx)

    assert candidate.season == 0
    assert candidate.season_kind == "special"
    assert candidate.episodes == [7]
    assert candidate.range_source == "meta_info"


def test_candidate_from_context_marks_explicit_sp_without_begin_season_as_special():
    ctx = SimpleNamespace(
        torrent_info=SimpleNamespace(title="灵笼 SP07", description="特别篇", site_name="站点"),
        meta_info=SimpleNamespace(year="2026", type="电视剧", episode_list=[7], begin_season=None,
                                  begin_episode=7, end_episode=7, tmdbid=None, doubanid=None),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    candidate = candidate_from_context(ctx)

    assert candidate.season == 0
    assert candidate.season_kind == "special"
    assert candidate.episodes == [7]


def test_candidate_from_context_cross_season_disjoint_keeps_candidate_season():
    ctx = SimpleNamespace(
        torrent_info=SimpleNamespace(title="测试剧 S02E01", description="", site_name="站点"),
        meta_info=SimpleNamespace(year="2026", type="电视剧", episode_list=[1], begin_season=2,
                                  begin_episode=1, end_episode=1, tmdbid=None, doubanid=None),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    candidate = candidate_from_context(ctx)

    assert candidate.season == 2
    assert candidate.season_kind == "main"
    assert candidate.episodes == [1]


def test_allow_does_not_override_explicit_id_mismatch():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="allow:\n  - 测试剧\n"))
    decision = guard.evaluate_dicts(_target(tmdb_id=100), _candidate(title="测试剧", explicit_tmdb_id=200))

    assert decision.final_action == "block"
    assert decision.code == "tmdb_id_mismatch"
    assert "allow" in decision.reason


def test_regular_block_is_mode_related_not_hard_veto():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="block:\n  - 弱拦截\n"))
    decision = guard.evaluate_dicts(_target(tmdb_id=100), _candidate(title="测试剧 弱拦截"))

    assert decision.final_action == "soft_block"
    assert decision.code == "user_block"


def test_custom_actions_can_block_missing_year_in_balanced():
    guard = RecognitionGuard(_settings(
        mode="balanced",
        custom_config="actions:\n  missing_year: block\n",
    ))

    decision = guard.evaluate_dicts(
        _target(tmdb_id=100),
        _candidate(title="测试剧 S01E08", year=None, description="动画", episodes=[8]),
    )

    assert decision.final_action == "block"
    assert decision.code == "missing_year"
    assert decision.risk == "policy_block"
    assert decision.evidence[0].level == "policy_block"


def test_custom_actions_can_block_oversized_pack_without_empty_pool_recovery():
    guard = RecognitionGuard(_settings(
        mode="balanced",
        custom_config="actions:\n  target_range_oversized: block\n",
    ))
    target = _target(target_episodes=[8, 9], range_confidence="high")
    contexts = [object()]

    batch = guard.filter_candidate_dicts(
        target,
        [_candidate(title="将夜 全60集", year=None, episodes=list(range(1, 61)))],
        contexts,
        selection_original_count=1,
        stage_counts=[],
    )

    assert batch.retained == []
    assert batch.fallback_applied is False
    assert batch.decisions[0].final_action == "block"
    assert batch.decisions[0].code == "target_range_oversized"
    assert batch.decisions[0].risk == "policy_block"


def test_oversized_pack_collects_missing_year_evidence_before_final_action():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(target_episodes=[8, 9], range_confidence="high"),
        _candidate(title="将夜 全60集", year=None, episodes=list(range(1, 61))),
    )

    assert decision.final_action == "soft_block"
    assert decision.code == "target_range_oversized"
    assert {evidence.code for evidence in decision.evidence} >= {"target_range_oversized", "missing_year"}


def test_secondary_fail_open_does_not_override_user_policy_block():
    guard = RecognitionGuard(_settings(
        mode="balanced",
        custom_config=(
            "actions:\n"
            "  user_block: block\n"
            "keywords:\n"
            "  block:\n"
            "    - 禁止资源\n"
        ),
    ))

    decision = guard.evaluate_dicts(
        _target(target_episodes=[8], range_confidence="high"),
        _candidate(title="测试剧 禁止资源 S01E08", year=2026, episodes=[8]),
        secondary_failed=True,
    )

    assert decision.final_action == "block"
    assert decision.code == "user_block"
    assert decision.risk == "policy_block"
    assert {evidence.code for evidence in decision.evidence} >= {
        "user_block",
        "secondary_recognition_fail_open",
    }


def test_secondary_fail_open_still_counters_missing_year_strict_block():
    guard = RecognitionGuard(_settings(mode="strict"))

    decision = guard.evaluate_dicts(
        _target(target_episodes=[8], range_confidence="high"),
        _candidate(title="测试剧 S01E08", year=None, episodes=[8]),
        secondary_failed=True,
    )

    assert decision.final_action == "fail_open"
    assert decision.code == "secondary_recognition_fail_open"
    assert {evidence.code for evidence in decision.evidence} >= {
        "secondary_recognition_fail_open",
        "missing_year",
    }


def test_secondary_fail_open_does_not_override_explicit_missing_year_policy_block():
    guard = RecognitionGuard(_settings(
        mode="balanced",
        custom_config="actions:\n  missing_year: block\n",
    ))

    decision = guard.evaluate_dicts(
        _target(target_episodes=[8], range_confidence="high"),
        _candidate(title="测试剧 S01E08", year=None, episodes=[8]),
        secondary_failed=True,
    )

    assert decision.final_action == "block"
    assert decision.code == "missing_year"
    assert decision.risk == "policy_block"
    assert {evidence.code for evidence in decision.evidence} >= {
        "missing_year",
        "secondary_recognition_fail_open",
    }


def test_non_recoverable_soft_block_is_not_restored_by_empty_pool_protection():
    guard = RecognitionGuard(_settings(
        mode="balanced",
        custom_config="empty_pool:\n  non_recoverable_codes:\n    - target_range_oversized\n",
    ))
    target = _target(target_episodes=[8, 9], range_confidence="high")
    contexts = [object()]

    batch = guard.filter_candidate_dicts(
        target,
        [_candidate(title="将夜 全60集", episodes=list(range(1, 61)))],
        contexts,
        selection_original_count=1,
        stage_counts=[],
    )

    assert batch.retained == []
    assert batch.fallback_applied is False
    assert batch.decisions[0].final_action == "soft_block"
    assert batch.decisions[0].code == "target_range_oversized"


def test_never_recover_empty_pool_policy_keeps_empty_result():
    guard = RecognitionGuard(_settings(
        mode="balanced",
        custom_config="empty_pool:\n  policy: never_recover\n",
    ))
    target = _target(target_episodes=[8, 9], range_confidence="high")
    contexts = [object()]

    batch = guard.filter_candidate_dicts(
        target,
        [_candidate(title="将夜 全60集", episodes=list(range(1, 61)))],
        contexts,
        selection_original_count=1,
        stage_counts=[],
    )

    assert batch.retained == []
    assert batch.fallback_applied is False
    assert batch.decisions[0].final_action == "soft_block"


def test_hard_block_keyword_blocks_in_loose_mode():
    guard = RecognitionGuard(_settings(mode="loose", keyword_config="hard_block:\n  - 强制错误\n"))
    decision = guard.evaluate_dicts(_target(tmdb_id=100), _candidate(title="测试剧 强制错误"))

    assert decision.final_action == "block"
    assert decision.code == "user_hard_block"


def test_audit_mode_records_would_block_but_keeps_candidate():
    guard = RecognitionGuard(_settings(mode="audit", keyword_config="hard_block:\n  - 强制错误\n"))
    batch = guard.filter_candidate_dicts(
        _target(tmdb_id=100),
        [_candidate(title="测试剧 强制错误")],
        [object()],
        selection_original_count=1,
        stage_counts=[],
    )

    assert len(batch.retained) == 1
    assert batch.selection_original_count == 1
    assert batch.recognition_input_count == 1
    assert batch.recognition_evaluated_count == 1
    assert batch.recognition_output_count == 1
    assert batch.final_count == 1
    assert batch.decisions[0].would_action == "block"
    assert batch.decisions[0].final_action == "observe"
    assert batch.action_counts["observe"] == 1
    assert "would_action=block" in batch.audit_summary
    assert "selection_original_count=1" in batch.audit_summary
    assert batch.notification_summary is not None


def test_audit_summary_includes_mode_and_strategy_snapshot():
    guard = RecognitionGuard(RecognitionSettings(mode="balanced", notify_mode="detail", cache_maxsize=128))
    batch = guard.filter_candidate_dicts(
        _target(tmdb_id=100),
        [_candidate(title="测试剧 S01E08")],
        [object()],
        selection_original_count=1,
        stage_counts=[],
    )

    assert "mode=balanced" in batch.audit_summary
    assert "strategy_version=" in batch.audit_summary
    assert "keyword_version=" in batch.audit_summary
    assert "tmdb_recheck_mode=balanced_strict" in batch.audit_summary
    assert "notify_mode=detail" in batch.audit_summary
    assert "cache_maxsize=128" in batch.audit_summary
    assert "strategy=hash=- policy=recover_soft_block" in batch.audit_summary
    assert "fallback_applied=false" in batch.audit_summary


def test_audit_summary_records_fallback_and_strategy_warnings():
    fallback_guard = RecognitionGuard(_settings(mode="balanced"))
    fallback_batch = fallback_guard.filter_candidate_dicts(
        _target(target_episodes=[8, 9], range_confidence="high"),
        [_candidate(title="将夜 全60集", episodes=list(range(1, 61)))],
        [object()],
        selection_original_count=1,
        stage_counts=[],
    )

    assert fallback_batch.fallback_applied is True
    assert fallback_batch.fallback_reason == "soft_block_empty_result_protection"
    assert "fallback_applied=true" in fallback_batch.audit_summary
    assert "fallback_reason=soft_block_empty_result_protection" in fallback_batch.audit_summary

    warning_guard = RecognitionGuard(_settings(mode="balanced", custom_config="actions: ["))
    warning_batch = warning_guard.filter_candidate_dicts(
        _target(tmdb_id=100),
        [_candidate(title="测试剧 S01E08")],
        [object()],
        selection_original_count=1,
        stage_counts=[],
    )

    assert "warnings=invalid_yaml" in warning_batch.audit_summary


def test_audit_summary_records_action_override_and_empty_pool_policy():
    guard = RecognitionGuard(_settings(
        mode="balanced",
        custom_config=(
            "actions:\n"
            "  target_range_oversized: block\n"
            "empty_pool:\n"
            "  policy: never_recover\n"
        ),
    ))
    batch = guard.filter_candidate_dicts(
        _target(target_episodes=[8, 9], range_confidence="high"),
        [_candidate(title="将夜 全60集", episodes=list(range(1, 61)))],
        [object()],
        selection_original_count=1,
        stage_counts=[],
    )

    assert "actions=target_range_oversized" in batch.audit_summary
    assert "policy=never_recover" in batch.audit_summary


def test_notification_modes_control_detail_scope_and_redaction():
    subscribe = _sub(id=1, name="将夜")
    target = _target(target_episodes=[8], range_confidence="high")
    candidates = [
        _candidate(title="将夜 禁止资源 S01E08 token=BLOCK_TOKEN", episodes=[8]),
        _candidate(title="将夜 S01E08", year=None, episodes=[8]),
    ]
    contexts = [object(), object()]
    custom_config = (
        "actions:\n"
        "  user_block: block\n"
        "keywords:\n"
        "  block:\n"
        "    - 禁止资源\n"
    )

    summary_guard = RecognitionGuard(_settings(mode="balanced", custom_config=custom_config, notify_mode="summary"))
    summary_guard.filter_candidate_dicts(target, candidates, contexts, selection_original_count=2)
    summary_payload = summary_guard.notification_payload(subscribe)

    detail_guard = RecognitionGuard(_settings(mode="balanced", custom_config=custom_config, notify_mode="detail"))
    detail_guard.filter_candidate_dicts(target, candidates, contexts, selection_original_count=2)
    detail_payload = detail_guard.notification_payload(subscribe)

    all_guard = RecognitionGuard(_settings(mode="balanced", custom_config=custom_config, notify_mode="all"))
    all_guard.filter_candidate_dicts(target, candidates, contexts, selection_original_count=2)
    all_payload = all_guard.notification_payload(subscribe)

    assert summary_payload is not None
    assert "user_block" not in summary_payload[1]
    assert "missing_year" not in summary_payload[1]
    assert detail_payload is not None
    assert "user_block" in detail_payload[1]
    assert "missing_year" not in detail_payload[1]
    assert "BLOCK_TOKEN" not in detail_payload[1]
    assert all_payload is not None
    assert "user_block" in all_payload[1]
    assert "missing_year" in all_payload[1]
    assert "BLOCK_TOKEN" not in all_payload[1]


def test_missing_year_alone_observes_in_balanced():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(tmdb_id=100),
        _candidate(title="测试剧 S01E08", year=None, description="动画", episodes=[8]),
    )

    assert decision.final_action == "observe"
    assert decision.code == "missing_year"


def test_missing_year_with_live_action_shape_conflict_blocks_in_balanced():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="live_action:\n  - 电视剧版\n"))
    decision = guard.evaluate_dicts(
        _target(media_type="电视剧", tmdb_id=100, shape="animation"),
        _candidate(title="测试剧 电视剧版 S01E08", year=None, episodes=[8]),
    )

    assert decision.final_action == "block"
    assert decision.code == "animation_live_action_conflict"


def test_missing_year_blocks_in_strict():
    guard = RecognitionGuard(_settings(mode="strict"))
    decision = guard.evaluate_dicts(
        _target(tmdb_id=100),
        _candidate(title="测试剧 S01E08", year=None, description="动画", episodes=[8]),
    )

    assert decision.final_action == "block"
    assert decision.code == "missing_year"


def test_trusted_same_identity_does_not_override_range_not_covering_target():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(tmdb_id=100, target_episodes=[8, 9]),
        _candidate(
            explicit_tmdb_id=100,
            candidate_recognized=True,
            match_source="tmdbid",
            media_info_is_target=False,
            episodes=[1, 2],
        ),
    )

    assert decision.final_action == "block"
    assert decision.code == "target_range_not_covered"


def test_trusted_same_identity_does_not_override_hard_shape_conflict():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="live_action:\n  - 真人版\n"))
    decision = guard.evaluate_dicts(
        _target(tmdb_id=100, shape="animation", target_episodes=[8]),
        _candidate(
            title="测试剧 真人版 S01E08",
            description="真人剧",
            explicit_tmdb_id=100,
            candidate_recognized=True,
            match_source="tmdbid",
            media_info_is_target=False,
            episodes=[8],
        ),
    )

    assert decision.final_action == "block"
    assert decision.code == "animation_live_action_conflict"


def test_cross_season_same_episode_number_blocks_when_target_season_is_known():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(season=1, target_episodes=[1], range_confidence="high"),
        _candidate(title="测试剧 S02E01", season=2, episodes=[1]),
    )

    assert decision.final_action == "block"
    assert decision.code == "target_range_not_covered"


def test_cross_season_blocks_even_when_candidate_episode_range_is_unknown():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(season=1, target_episodes=[1], range_confidence="high"),
        _candidate(title="测试剧 S02", season=2, episodes=[]),
    )

    assert decision.final_action == "block"
    assert decision.code == "target_range_not_covered"


def test_unknown_candidate_season_observes_for_range_veto():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(season=1, target_episodes=[1], range_confidence="high"),
        _candidate(title="测试剧 E01", season=None, episodes=[1]),
    )

    assert decision.final_action in {"allow", "observe"}
    assert decision.code != "target_range_not_covered"


def test_weak_english_alias_does_not_counter_hard_veto():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="live_action:\n  - 电视剧版\n"))
    decision = guard.evaluate_dicts(
        _target(
            tmdb_id=218642,
            shape="animation",
            aliases=["Big Brother"],
            alias_strengths={"Big Brother": "weak"},
            target_episodes=[40],
        ),
        _candidate(title="Big Brother 电视剧版 S01E40", description="真人剧", episodes=[40]),
    )

    assert decision.final_action == "block"
    assert decision.code == "animation_live_action_conflict"


def test_secondary_recognition_failure_does_not_override_hard_veto():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="live_action:\n  - 电视剧版\n"))
    decision = guard.evaluate_dicts(
        _target(media_type="电视剧", tmdb_id=100, shape="animation"),
        _candidate(title="测试剧 电视剧版", description=""),
        secondary_failed=True,
    )

    assert decision.final_action == "block"
    assert decision.code == "animation_live_action_conflict"


def test_movie_target_with_series_signal_blocks_in_balanced():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(media_type="电影", tmdb_id=100),
        _candidate(title="测试电影 S01 第1集", explicit_tmdb_id=None, episodes=[1]),
    )

    assert decision.final_action == "block"
    assert decision.code == "movie_series_conflict"


def test_tv_target_with_movie_edition_signal_blocks_without_episode_signal():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(media_type="电视剧", tmdb_id=100),
        _candidate(title="测试剧 剧场版", explicit_tmdb_id=None, episodes=[]),
    )

    assert decision.final_action == "block"
    assert decision.code == "series_movie_conflict"


def test_movie_target_same_identity_counters_weak_series_signal():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(media_type="电影", tmdb_id=100),
        _candidate(
            title="测试电影 S01 特典",
            explicit_tmdb_id=100,
            candidate_recognized=True,
            match_source="tmdbid",
            media_info_is_target=False,
            episodes=[1],
        ),
    )

    assert decision.final_action in {"allow", "observe"}
    assert decision.code != "movie_series_conflict"


def test_allow_keyword_counters_regular_block_keyword():
    guard = RecognitionGuard(
        _settings(mode="balanced", keyword_config="allow:\n  - 官方合集\nblock:\n  - 弱拦截\n")
    )
    decision = guard.evaluate_dicts(
        _target(tmdb_id=100),
        _candidate(title="测试剧 官方合集 弱拦截", episodes=[8]),
    )

    assert decision.final_action == "allow"
    assert decision.code == "user_allow"
    assert decision.counters


def test_allow_keyword_does_not_counter_movie_series_hard_veto():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="allow:\n  - 官方特典\n"))
    decision = guard.evaluate_dicts(
        _target(media_type="电影", tmdb_id=100),
        _candidate(title="测试电影 S01 官方特典", explicit_tmdb_id=None, episodes=[1]),
    )

    assert decision.final_action == "block"
    assert decision.code == "movie_series_conflict"


def test_batch_does_not_recover_hard_veto_when_empty_result():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="live_action:\n  - 电视剧版\n"))
    target = _target(media_type="电影", shape="animation")
    contexts = [
        SimpleNamespace(_candidate=_candidate(title="测试剧 电视剧版")),
        SimpleNamespace(_candidate=_candidate(title="测试电影 S01 第1集", episodes=[1])),
    ]

    batch = guard.filter_candidate_dicts(
        target,
        [ctx._candidate for ctx in contexts],
        contexts,
        selection_original_count=2,
        stage_counts=[],
    )

    assert batch.retained == []
    assert batch.fallback_applied is False
    assert batch.selection_original_count == 2
    assert batch.recognition_input_count == 2
    assert batch.recognition_evaluated_count == 2
    assert batch.recognition_output_count == 0
    assert batch.final_count == 0
    assert [d.final_action for d in batch.decisions] == ["block", "block"]
    assert batch.original_action_counts["block"] == 2


def test_batch_all_hard_veto_can_empty_candidates():
    guard = RecognitionGuard(_settings(mode="balanced", keyword_config="live_action:\n  - 电视剧版\n"))
    target = _target(shape="animation")
    contexts = [object(), object()]
    candidates = [
        _candidate(title="测试剧 电视剧版"),
        _candidate(title="测试剧 真人版"),
    ]

    batch = guard.filter_candidate_dicts(
        target,
        candidates,
        contexts,
        selection_original_count=2,
        stage_counts=[],
    )

    assert batch.retained == []
    assert batch.recognition_evaluated_count == 2
    assert batch.final_count == 0
    assert batch.fallback_applied is False


def test_strict_mode_does_not_recover_all_soft_blocks():
    guard = RecognitionGuard(_settings(mode="strict"))
    target = _target(target_episodes=[8, 9], range_confidence="high")
    contexts = [object()]

    batch = guard.filter_candidate_dicts(
        target,
        [_candidate(title="测试剧 全60集", year=2026, episodes=list(range(1, 61)))],
        contexts,
        selection_original_count=1,
        stage_counts=[],
    )

    assert batch.retained == []
    assert batch.fallback_applied is False
    assert batch.decisions[0].final_action == "soft_block"
    assert batch.decisions[0].code == "target_range_oversized"


def test_filter_builds_target_from_runtime_resolvers():
    target_mediainfo = SimpleNamespace(category="动漫", genres=[{"name": "动画"}], names=["目标别名"])
    target_resolver = MagicMock(return_value=target_mediainfo)
    tmdb_episodes_fn = MagicMock(return_value=[SimpleNamespace(episode_number=1)])
    guard = RecognitionGuard(
        RecognitionSettings(mode="balanced"),
        runtime=RecognitionRuntime(
            target_mediainfo_resolver=target_resolver,
            tmdb_episodes_fn=tmdb_episodes_fn,
        ),
    )
    subscribe = _sub(best_version=1, best_version_full=1, episode_group="eg-1")
    ctx = SimpleNamespace(
        torrent_info=SimpleNamespace(title="测试剧 S01E01", description="", site_name="站点"),
        meta_info=SimpleNamespace(episode_list=[1], begin_episode=1, end_episode=1),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([ctx], subscribe=subscribe)

    target_resolver.assert_called_once_with(subscribe)
    tmdb_episodes_fn.assert_called_once()


def test_locale_difference_is_observe_not_builtin_hard_veto():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate_dicts(
        _target(tmdb_id=100, languages=["zh"], origin_countries=["CN"]),
        _candidate(title="测试剧 S01E08", episodes=[8], languages=["ja"], origin_countries=["JP"]),
    )

    assert decision.final_action in {"allow", "observe"}
    assert decision.code != "locale_hard_veto"


def test_secondary_identity_fields_are_part_of_candidate_contract():
    guard = RecognitionGuard(_settings(mode="balanced"))
    decision = guard.evaluate(
        RecognitionTarget(
            name="师兄啊师兄",
            media_type="电视剧",
            tmdb_id=218642,
            aliases=["师兄啊师兄"],
            target_episodes=[40],
            range_confidence="high",
        ),
        CandidateResource(
            title="Big Brother S01E40",
            description="师兄啊师兄 动画",
            episodes=[40],
            secondary_tmdb_id=237243,
        ),
    )

    assert decision.final_action == "observe"
    assert decision.code == "secondary_identity_conflict_with_alias"


def test_secondary_empty_result_cache_hit_preserves_fail_open_in_strict():
    secondary = MagicMock(return_value=None)
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    subscribe = _sub(start_episode=8, total_episode=8)
    contexts = [
        SimpleNamespace(
            torrent_info=SimpleNamespace(title="测试剧 S01E08", description="", site_name="站点"),
            meta_info=SimpleNamespace(year=None, type=None, episode_list=[8], begin_season=1),
            media_info=None,
            candidate_recognized=False,
            match_source="title",
            media_info_is_target=True,
        ),
        SimpleNamespace(
            torrent_info=SimpleNamespace(title="测试剧 S01E08", description="", site_name="站点"),
            meta_info=SimpleNamespace(year=None, type=None, episode_list=[8], begin_season=1),
            media_info=None,
            candidate_recognized=False,
            match_source="title",
            media_info_is_target=True,
        ),
    ]

    guard.filter([contexts[0]], subscribe=subscribe)
    first = guard.last_batch
    guard.filter([contexts[1]], subscribe=subscribe)
    second = guard.last_batch

    assert secondary.call_count == 1
    assert first.decisions[0].final_action == "fail_open"
    assert first.decisions[0].code == "secondary_recognition_fail_open"
    assert first.decisions[0].candidate.secondary_status == "empty"
    assert second.decisions[0].final_action == "fail_open"
    assert second.decisions[0].code == "secondary_recognition_fail_open"
    assert second.decisions[0].candidate.secondary_status == "empty"


def test_secondary_title_subtitle_route_can_recognize_when_title_route_is_empty():
    secondary = RecordingSecondaryRecognizer([None, _media_result(tmdb_id=100)])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    subscribe = _sub(name="问心", custom_words="The Heart => 问心")
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(
            title="Episode 01",
            description="The Heart 问心 第1集 普通媒体文本",
            site_name="站点",
        ),
        meta_info=SimpleNamespace(year=2026, type=None, episode_list=[1], begin_season=1),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=subscribe)
    decision = guard.last_batch.decisions[0]
    candidate = decision.candidate
    second_meta = secondary.calls[1]

    assert len(secondary.calls) == 2
    assert candidate.secondary_status == "recognized"
    assert candidate.secondary_tmdb_id == 100
    assert decision.code != "secondary_recognition_fail_open"
    assert "secondary_routes=title,title_subtitle" in guard.last_batch.audit_summary
    assert "route=title_subtitle" in guard.last_batch.audit_summary
    assert "route_title=Episode 01 The Heart 问心 第1集 普通媒体文本" in guard.last_batch.audit_summary
    assert "route_subtitle=The Heart 问心 第1集 普通媒体文本" in guard.last_batch.audit_summary
    assert "The Heart => 问心" in second_meta.apply_words
    assert "问心 第1集" in second_meta.subtitle


def test_secondary_route_audit_records_full_route_text_but_redacts_credentials():
    secondary = RecordingSecondaryRecognizer([None, None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(
            title="The Heart S01E01",
            description=(
                "问心=第1集|特典\n正片 普通媒体文本 "
                "https://tracker.local/download?token=SECRET&passkey=PASS "
                "magnet:?xt=urn:btih:abcdef "
                "Authorization Bearer SECRET_BEARER "
                "Cookie session=COOKIE_SECRET"
            ),
            site_name="站点",
        ),
        meta_info=SimpleNamespace(year=2026, type=None, episode_list=[1], begin_season=1),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=_sub(name="问心", custom_words="The Heart => 问心"))
    audit = guard.last_batch.audit_summary

    assert "route_title=" in audit
    assert "route_subtitle=" in audit
    assert "The Heart S01E01" in audit
    assert "问心:第1集/特典\\n正片" in audit
    assert "\n" not in audit
    assert "问心=第1集|特典" not in audit
    assert "SECRET" not in audit
    assert "PASS" not in audit
    assert "SECRET_BEARER" not in audit
    assert "COOKIE_SECRET" not in audit
    assert "magnet:?" not in audit
    assert "token=" not in audit
    assert "passkey=" not in audit
    assert "[redacted-url]" in audit
    assert "[redacted-secret]" in audit


def test_title_subtitle_route_ignores_subtitle_promoted_explicit_ids():
    secondary = RecordingSecondaryRecognizer([None, None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(
            title="The Heart S01E01",
            description="问心 第1集 {[tmdbid=999;type=movie;g=abc123;s=1;e=1]} [tmdbid=888]",
            site_name="站点",
        ),
        meta_info=SimpleNamespace(year=None, type=None, episode_list=[1], begin_season=1),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=_sub(name="问心", custom_words="The Heart => 问心"))
    decision = guard.last_batch.decisions[0]
    route = decision.candidate.secondary_routes[1]
    title_meta, title_subtitle_meta = secondary.calls

    assert "[tmdbid=999" not in route.route_title
    assert "[tmdbid=888]" not in route.route_title
    assert route.control_fields_sanitized is True
    assert getattr(title_subtitle_meta, "tmdbid", None) == getattr(title_meta, "tmdbid", None)
    assert getattr(title_subtitle_meta, "doubanid", None) == getattr(title_meta, "doubanid", None)
    assert getattr(title_subtitle_meta, "episode_group", None) == getattr(title_meta, "episode_group", None)
    assert getattr(title_subtitle_meta, "type", None) == getattr(title_meta, "type", None)
    assert decision.final_action == "fail_open"
    assert decision.code == "secondary_recognition_fail_open"


def test_title_subtitle_route_keeps_type_inferred_from_ordinary_subtitle_text():
    secondary = RecordingSecondaryRecognizer([None, None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(
            title="Weak Title",
            description="问心   第1集\n正片",
            site_name="站点",
        ),
        meta_info=SimpleNamespace(year=None, type=MediaType.UNKNOWN, episode_list=[], begin_season=None),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=_sub(name="问心", custom_words=""))
    route = guard.last_batch.decisions[0].candidate.secondary_routes[1]
    title_subtitle_meta = secondary.calls[1]

    assert route.control_fields_sanitized is False
    assert route.route_title == "Weak Title 问心 第1集 正片"
    assert getattr(title_subtitle_meta, "type", None) == MediaType.TV


def test_secondary_target_route_wins_over_non_target_route_conflict():
    secondary = RecordingSecondaryRecognizer([
        _media_result(tmdb_id=999),
        _media_result(tmdb_id=100),
    ])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(title="The Heart S01E01", description="问心 第1集", site_name="站点"),
        meta_info=SimpleNamespace(year=2026, type=None, episode_list=[1], begin_season=1),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=_sub(name="问心", custom_words="The Heart => 问心"))
    decision = guard.last_batch.decisions[0]
    candidate = decision.candidate

    assert candidate.secondary_tmdb_id == 100
    assert candidate.secondary_selected_route == "title_subtitle"
    assert candidate.secondary_result_target_match is True
    assert candidate.secondary_result_conflict is True
    assert decision.final_action != "block"


def test_secondary_result_conflict_normalizes_same_tmdb_with_partial_douban():
    secondary = RecordingSecondaryRecognizer([
        _media_result(tmdb_id=100),
        _media_result(tmdb_id=100, douban_id="db100"),
    ])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(title="The Heart S01E01", description="问心 第1集", site_name="站点"),
        meta_info=SimpleNamespace(year=2026, type=None, episode_list=[1], begin_season=1),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=_sub(name="问心", custom_words="The Heart => 问心"))
    candidate = guard.last_batch.decisions[0].candidate

    assert candidate.secondary_result_target_match is True
    assert candidate.secondary_result_conflict is False


def test_title_subtitle_meta_build_failure_is_route_failure_and_fail_open(monkeypatch):
    secondary = RecordingSecondaryRecognizer([None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    original_metainfo = __import__(
        "subscribeassistantenhanced.recognition.guard",
        fromlist=["MetaInfo"],
    ).MetaInfo

    def failing_metainfo(*args, **kwargs):
        if len(secondary.calls) >= 1:
            raise RuntimeError("token=SECRET")
        return original_metainfo(*args, **kwargs)

    monkeypatch.setattr("subscribeassistantenhanced.recognition.guard.MetaInfo", failing_metainfo)
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(title="The Heart S01E01", description="问心 第1集", site_name="站点"),
        meta_info=SimpleNamespace(year=None, type=None, episode_list=[1], begin_season=1),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=_sub(name="问心", custom_words="The Heart => 问心"))
    decision = guard.last_batch.decisions[0]
    route = decision.candidate.secondary_routes[1]

    assert len(secondary.calls) == 1
    assert route.route == "title_subtitle"
    assert route.status == "failed"
    assert "SECRET" not in route.failure
    assert "[redacted-secret]" in route.failure
    assert decision.final_action == "fail_open"
    assert decision.code == "secondary_recognition_fail_open"


def test_secondary_route_cache_isolated_by_target_route_and_custom_words():
    secondary = RecordingSecondaryRecognizer([None, None, None, None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )

    def context():
        return SimpleNamespace(
            torrent_info=SimpleNamespace(title="The Heart S01E01", description="问心 第1集", site_name="站点"),
            meta_info=SimpleNamespace(year=None, type=None, episode_list=[1], begin_season=1),
            media_info=None,
            candidate_recognized=False,
            match_source="title",
            media_info_is_target=True,
        )

    guard.filter([context()], subscribe=_sub(id=None, name="问心", custom_words="The Heart => 问心"))
    guard.filter([context()], subscribe=_sub(id=None, name="问心", custom_words="The Heart => 赤心"))

    assert len(secondary.calls) == 4


def test_secondary_route_cache_isolated_by_candidate_media_type():
    secondary = RecordingSecondaryRecognizer([None, None, None, None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )

    def context(media_type):
        return SimpleNamespace(
            torrent_info=SimpleNamespace(title="The Heart S01E01", description="问心 第1集", site_name="站点"),
            meta_info=SimpleNamespace(
                year=2026,
                type=media_type,
                episode_list=[1],
                begin_season=1,
                episode_group="eg1",
            ),
            media_info=None,
            candidate_recognized=False,
            match_source="title",
            media_info_is_target=True,
        )

    subscribe = _sub(id=1, name="问心", custom_words="The Heart => 问心")
    guard.filter([context(MediaType.TV)], subscribe=subscribe)
    guard.filter([context(MediaType.MOVIE)], subscribe=subscribe)

    assert len(secondary.calls) == 4


def test_secondary_route_cache_isolated_by_candidate_episode_group():
    secondary = RecordingSecondaryRecognizer([None, None, None, None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )

    def context(episode_group):
        return SimpleNamespace(
            torrent_info=SimpleNamespace(title="The Heart S01E01", description="问心 第1集", site_name="站点"),
            meta_info=SimpleNamespace(
                year=2026,
                type=MediaType.TV,
                episode_list=[1],
                begin_season=1,
                episode_group=episode_group,
            ),
            media_info=None,
            candidate_recognized=False,
            match_source="title",
            media_info_is_target=True,
        )

    subscribe = _sub(id=1, name="问心", custom_words="The Heart => 问心")
    guard.filter([context("eg1")], subscribe=subscribe)
    guard.filter([context("eg2")], subscribe=subscribe)

    assert len(secondary.calls) == 4


def test_secondary_title_route_audit_and_cache_use_actual_meta_text():
    secondary = RecordingSecondaryRecognizer([None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )

    def context(raw_title):
        return SimpleNamespace(
            torrent_info=SimpleNamespace(title=raw_title, description="", site_name="站点"),
            meta_info=SimpleNamespace(
                title="Meta Title S01E01",
                subtitle="Meta Subtitle 第1集",
                year=None,
                type=None,
                episode_list=[1],
                begin_season=1,
            ),
            media_info=None,
            candidate_recognized=False,
            match_source="title",
            media_info_is_target=True,
        )

    subscribe = _sub(id=1, name="问心", custom_words="The Heart => 问心")
    guard.filter([context("Raw Title A")], subscribe=subscribe)
    guard.filter([context("Raw Title B")], subscribe=subscribe)
    audit = guard.last_batch.audit_summary

    assert len(secondary.calls) == 1
    assert guard.last_batch.decisions[0].candidate.secondary_routes[0].cache_hit is True
    assert "route=title" in audit
    assert "route=title route_status=empty route_title=Meta Title S01E01" in audit
    assert "route=title route_status=empty route_title=Raw Title B" not in audit
    assert "route_subtitle=Meta Subtitle 第1集" in audit


def test_title_subtitle_route_skips_duplicate_after_control_tag_cleanup():
    secondary = RecordingSecondaryRecognizer([None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )
    context = SimpleNamespace(
        torrent_info=SimpleNamespace(
            title="The Heart S01E01",
            description="{[tmdbid=999;type=movie;g=abc123;s=1;e=1]} [tmdbid=888]",
            site_name="站点",
        ),
        meta_info=SimpleNamespace(year=None, type=None, episode_list=[1], begin_season=1),
        media_info=None,
        candidate_recognized=False,
        match_source="title",
        media_info_is_target=True,
    )

    guard.filter([context], subscribe=_sub(name="问心", custom_words="The Heart => 问心"))
    route = guard.last_batch.decisions[0].candidate.secondary_routes[1]

    assert len(secondary.calls) == 1
    assert route.route == "title_subtitle"
    assert route.status == "skipped"
    assert route.skipped_reason == "duplicate_route"
    assert route.control_fields_sanitized is True


def test_secondary_route_cache_hits_each_route_on_repeated_candidate():
    secondary = RecordingSecondaryRecognizer([None, None])
    guard = RecognitionGuard(
        RecognitionSettings(mode="strict", tmdb_recheck_mode="all"),
        runtime=RecognitionRuntime(secondary_recognizer=secondary),
    )

    def context():
        return SimpleNamespace(
            torrent_info=SimpleNamespace(title="The Heart S01E01", description="问心 第1集", site_name="站点"),
            meta_info=SimpleNamespace(year=None, type=None, episode_list=[1], begin_season=1),
            media_info=None,
            candidate_recognized=False,
            match_source="title",
            media_info_is_target=True,
        )

    subscribe = _sub(id=1, name="问心", custom_words="The Heart => 问心")
    guard.filter([context()], subscribe=subscribe)
    first = guard.last_batch
    guard.filter([context()], subscribe=subscribe)
    second = guard.last_batch

    assert len(secondary.calls) == 2
    assert [route.cache_hit for route in first.decisions[0].candidate.secondary_routes] == [False, False]
    assert [route.cache_hit for route in second.decisions[0].candidate.secondary_routes] == [True, True]
    assert first.decisions[0].final_action == "fail_open"
    assert second.decisions[0].final_action == "fail_open"
    assert first.decisions[0].code == "secondary_recognition_fail_open"
    assert second.decisions[0].code == "secondary_recognition_fail_open"


def test_audit_escapes_reason_delimiters():
    guard = RecognitionGuard(RecognitionSettings(mode="strict"))
    batch = guard.filter_candidate_dicts(
        _target(target_episodes=[1], range_confidence="high"),
        [
            CandidateResource(
                title="测试剧 S01E01",
                episodes=[1],
                secondary_status="failed",
                secondary_failure="route failure a=b|c\nD",
            )
        ],
        [object()],
    )
    audit = batch.audit_summary

    assert "reason=二次识别失败，按 fail-open 放行：route failure a:b/c\\nD" in audit
    assert "a=b|c" not in audit
    assert "\n" not in audit
