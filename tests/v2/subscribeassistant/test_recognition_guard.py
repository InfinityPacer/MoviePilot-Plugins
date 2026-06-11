"""
SubscribeAssistant 识别增强判定器单测。

覆盖强制关键字、显式 ID、类型/形态/年份冲突、二次识别缓存和批量过滤等核心判定语义。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType
from subscribeassistant.recognition_guard import (
    CachedRecognitionInfo,
    RecognitionGuard,
    RecognitionGuardConfig,
)


def make_config(**overrides) -> RecognitionGuardConfig:
    """构造默认开启的识别增强配置。"""
    base = dict(
        mode="strict",
        same_name_protection=True,
        movie_year_mode="loose",
        tv_year_mode="season_first",
        no_year_action="allow",
        tmdb_recheck_mode="off",
        cache_maxsize=16,
    )
    base.update(overrides)
    return RecognitionGuardConfig(**base)


def make_media(type_=MediaType.TV, **overrides) -> SimpleNamespace:
    """构造订阅目标媒体信息。"""
    base = dict(
        type=type_,
        tmdb_id=100,
        douban_id="db100",
        title="目标",
        year="2024",
        genre_ids=[],
        category="",
        season=1,
        season_years={1: "2024", 2: "2025"},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_meta(**overrides) -> SimpleNamespace:
    """构造候选资源标题解析结果。"""
    base = dict(
        tmdbid=None,
        doubanid=None,
        type=None,
        year="2024",
        begin_season=1,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_torrent(**overrides) -> SimpleNamespace:
    """构造候选种子信息。"""
    base = dict(
        title="目标 S01 2024",
        description="描述",
        site_name="站点",
        site=1,
        category=None,
        labels=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_context(**overrides) -> SimpleNamespace:
    """构造识别增强输入上下文。"""
    base = dict(
        torrent_info=make_torrent(),
        media_info=make_media(),
        meta_info=make_meta(),
        match_source="title",
        candidate_recognized=False,
        media_info_is_target=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class RecognitionGuardEvaluateTest:
    """识别增强 evaluate 主流程判定。"""

    def test_evaluate_allows_when_mode_off_or_context_incomplete(self):
        guard = RecognitionGuard(make_config(mode="off"))
        assert guard.evaluate(make_context()).code == "allow"
        assert guard.evaluate(SimpleNamespace(torrent_info=None)).candidate_title == ""

    def test_evaluate_skips_when_allow_pattern_matches(self):
        context = make_context(torrent_info=make_torrent(title="目标 PROPER 2024"))
        guard = RecognitionGuard(make_config(allow_patterns=["PROPER"], block_patterns=["目标"]))
        decision = guard.evaluate(context)
        assert not decision.observed
        assert not decision.blocked

    def test_evaluate_blocks_when_block_pattern_matches(self):
        context = make_context(torrent_info=make_torrent(title="目标 真人版"))
        guard = RecognitionGuard(make_config(block_patterns=["真人版"]))
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.observed
        assert decision.code == "manual_block"
        assert "真人版" in decision.reason

    def test_observe_mode_records_but_does_not_block(self):
        context = make_context(torrent_info=make_torrent(title="目标 真人版"))
        guard = RecognitionGuard(make_config(mode="observe", block_patterns=["真人版"]))
        decision = guard.evaluate(context)
        assert decision.observed
        assert not decision.blocked

    def test_evaluate_allows_when_target_media_missing(self):
        guard = RecognitionGuard(make_config())
        decision = guard.evaluate(make_context(media_info=None))
        assert not decision.observed
        assert decision.candidate_title == "目标 S01 2024"

    def test_explicit_tmdb_id_mismatch_blocks_candidate(self):
        context = make_context(meta_info=make_meta(tmdbid=999))
        guard = RecognitionGuard(make_config())
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "tmdb_id_mismatch"

    def test_explicit_douban_id_mismatch_blocks_candidate(self):
        context = make_context(meta_info=make_meta(doubanid="db999", tmdbid=None))
        guard = RecognitionGuard(make_config())
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "douban_id_mismatch"

    def test_direct_id_check_allows_when_meta_missing(self):
        context = make_context(meta_info=None)
        guard = RecognitionGuard(make_config())
        decision = guard._evaluate_direct_ids(context, context.media_info, "候选")
        assert not decision.observed

    def test_trusted_candidate_identity_skips_heuristic_checks(self):
        context = make_context(
            candidate_recognized=True,
            media_info_is_target=False,
            match_source="tmdbid",
            media_info=make_media(tmdb_id=100),
            torrent_info=make_torrent(title="目标 电影版"),
        )
        guard = RecognitionGuard(make_config(movie_patterns=["电影版"]))
        decision = guard.evaluate(context)
        assert decision.trusted
        assert decision.code == "candidate_same_identity"

    def test_tv_subscription_blocks_movie_signal(self):
        context = make_context(torrent_info=make_torrent(title="目标 电影版"))
        guard = RecognitionGuard(make_config(movie_patterns=["电影版"]))
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "tv_movie_mismatch"

    def test_movie_subscription_blocks_tv_signal(self):
        context = make_context(
            media_info=make_media(MediaType.MOVIE),
            torrent_info=make_torrent(title="目标 S01"),
        )
        guard = RecognitionGuard(make_config(tv_patterns=[r"S\d{2}"]))
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "movie_tv_mismatch"

    def test_type_conflict_disabled_allows_candidate_type_signal(self):
        context = make_context(torrent_info=make_torrent(title="目标 电影版"))
        guard = RecognitionGuard(make_config(movie_patterns=["电影版"], same_name_protection=False))
        decision = guard.evaluate(context)
        assert not decision.observed

    def test_animation_target_blocks_live_action_signal(self):
        context = make_context(
            media_info=make_media(genre_ids=[16], category="动画"),
            torrent_info=make_torrent(title="目标 真人版"),
        )
        guard = RecognitionGuard(make_config(live_action_patterns=["真人版"]))
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "animation_live_action_conflict"

    def test_forced_live_action_target_blocks_animation_signal(self):
        context = make_context(torrent_info=make_torrent(title="目标 动画版"))
        guard = RecognitionGuard(make_config(target_mode="live_action", animation_patterns=["动画版"]))
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "live_action_animation_conflict"

    def test_movie_year_strict_blocks_mismatch(self):
        context = make_context(
            media_info=make_media(MediaType.MOVIE, year="2024"),
            meta_info=make_meta(type=MediaType.MOVIE, year="2022"),
        )
        guard = RecognitionGuard(make_config(movie_year_mode="strict"))
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "movie_year_mismatch"

    def test_movie_year_loose_allows_adjacent_year(self):
        context = make_context(
            media_info=make_media(MediaType.MOVIE, year="2024"),
            meta_info=make_meta(type=MediaType.MOVIE, year="2023"),
        )
        guard = RecognitionGuard(make_config(movie_year_mode="loose"))
        decision = guard.evaluate(context)
        assert not decision.observed

    def test_movie_year_ignores_off_missing_or_unparseable_years(self):
        candidate = "候选"
        assert not RecognitionGuard(make_config(movie_year_mode="off"))._evaluate_movie_year(
            "2020", make_media(MediaType.MOVIE, year="2024"), candidate).observed
        assert not RecognitionGuard(make_config())._evaluate_movie_year(
            "2020", make_media(MediaType.MOVIE, year=None), candidate).observed
        assert not RecognitionGuard(make_config())._evaluate_movie_year(
            "bad", make_media(MediaType.MOVIE, year="2024"), candidate).observed

    def test_movie_year_missing_follows_missing_year_policy(self):
        decision = RecognitionGuard(make_config(no_year_action="filter"))._evaluate_movie_year(
            None, make_media(MediaType.MOVIE, year="2024"), "候选")
        assert decision.blocked
        assert decision.code == "movie_year_missing"

    def test_tv_season_first_blocks_non_season_year(self):
        context = make_context(
            media_info=make_media(year="2020", season=2, season_years={1: "2020", 2: "2025"}),
            meta_info=make_meta(year="2020", begin_season=2),
        )
        guard = RecognitionGuard(make_config(tv_year_mode="season_first"))
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "tv_year_mismatch"

    def test_tv_year_ignores_off_empty_allowed_or_unparseable_resource_year(self):
        media = make_media(year="2024", season_years={})
        context = make_context(meta_info=make_meta(begin_season=2), media_info=media)
        assert not RecognitionGuard(make_config(tv_year_mode="off"))._evaluate_tv_year(
            "2020", media, context, "候选").observed
        assert not RecognitionGuard(make_config(tv_year_mode="season_strict"))._evaluate_tv_year(
            "2020", media, context, "候选").observed
        assert not RecognitionGuard(make_config())._evaluate_tv_year(
            "bad", make_media(year="2024"), make_context(), "候选").observed

    def test_tv_year_missing_follows_missing_year_policy(self):
        decision = RecognitionGuard(make_config(no_year_action="filter"))._evaluate_tv_year(
            None, make_media(year="2024"), make_context(), "候选")
        assert decision.blocked
        assert decision.code == "tv_year_missing"

    def test_year_evaluation_ignores_unknown_media_type(self):
        decision = RecognitionGuard(make_config())._evaluate_year(
            make_context(media_info=make_media(MediaType.UNKNOWN)), make_media(MediaType.UNKNOWN), "候选")
        assert not decision.observed

    def test_missing_year_observe_records_without_blocking(self):
        context = make_context(meta_info=make_meta(year=None))
        guard = RecognitionGuard(make_config(mode="observe", no_year_action="observe"))
        decision = guard.evaluate(context)
        assert decision.observed
        assert not decision.blocked
        assert decision.code == "tv_year_missing"

    def test_filter_contexts_retains_unblocked_and_reports_observed(self):
        allowed = make_context(torrent_info=make_torrent(title="目标 2024"))
        blocked = make_context(torrent_info=make_torrent(title="目标 电影版"))
        guard = RecognitionGuard(make_config(movie_patterns=["电影版"]))
        retained, decisions = guard.filter_contexts([allowed, blocked])
        assert retained == [allowed]
        assert [decision.code for decision in decisions] == ["tv_movie_mismatch"]


class RecognitionGuardSecondaryRecognitionTest:
    """TMDB 二次识别和缓存判定。"""

    def test_secondary_recognition_blocks_tmdb_mismatch(self):
        recognizer = MagicMock(return_value=make_media(tmdb_id=999, type=MediaType.TV))
        guard = RecognitionGuard(make_config(tmdb_recheck_mode="all"), recognizer=recognizer)
        decision = guard.evaluate(make_context())
        assert decision.blocked
        assert decision.code == "secondary_tmdb_mismatch"
        recognizer.assert_called_once()

    def test_secondary_recognition_trusts_same_identity(self):
        recognizer = MagicMock(return_value=make_media(tmdb_id=100, type=MediaType.TV))
        guard = RecognitionGuard(make_config(tmdb_recheck_mode="all"), recognizer=recognizer)
        decision = guard.evaluate(make_context(torrent_info=make_torrent(title="目标 同一身份 2024")))
        assert decision.trusted
        assert decision.code == "secondary_same_identity"

    def test_secondary_recognition_blocks_type_mismatch_without_shared_id(self):
        recognizer = MagicMock(return_value=make_media(MediaType.MOVIE, tmdb_id=None, douban_id=None))
        context = make_context(
            media_info=make_media(tmdb_id=None, douban_id=None),
            torrent_info=make_torrent(title="目标 类型错配 2024"),
        )
        guard = RecognitionGuard(make_config(tmdb_recheck_mode="all"), recognizer=recognizer)
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "secondary_type_mismatch"

    def test_secondary_recognition_blocks_douban_mismatch(self):
        recognizer = MagicMock(return_value=make_media(tmdb_id=None, douban_id="db999", type=MediaType.TV))
        context = make_context(
            media_info=make_media(tmdb_id=None, douban_id="db100"),
            torrent_info=make_torrent(title="目标 豆瓣错配 2024"),
        )
        guard = RecognitionGuard(make_config(tmdb_recheck_mode="all"), recognizer=recognizer)
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "secondary_douban_mismatch"

    def test_secondary_recognition_blocks_animation_shape_mismatch(self):
        recognizer = MagicMock(return_value=make_media(tmdb_id=None, douban_id=None, genre_ids=[], category=""))
        context = make_context(
            media_info=make_media(tmdb_id=None, douban_id=None, genre_ids=[16], category="动画"),
            torrent_info=make_torrent(title="目标 动画形态错配 2024"),
        )
        guard = RecognitionGuard(make_config(tmdb_recheck_mode="all"), recognizer=recognizer)
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "secondary_animation_mismatch"

    def test_secondary_recognition_blocks_live_action_shape_mismatch(self):
        recognizer = MagicMock(return_value=make_media(tmdb_id=None, douban_id=None, genre_ids=[16], category="动画"))
        context = make_context(
            media_info=make_media(tmdb_id=None, douban_id=None),
            torrent_info=make_torrent(title="目标 真人形态错配 2024"),
        )
        guard = RecognitionGuard(
            make_config(tmdb_recheck_mode="all", target_mode="live_action"),
            recognizer=recognizer,
        )
        decision = guard.evaluate(context)
        assert decision.blocked
        assert decision.code == "secondary_live_action_mismatch"

    def test_secondary_recognition_allows_when_recognizer_returns_none(self):
        recognizer = MagicMock(return_value=None)
        guard = RecognitionGuard(make_config(tmdb_recheck_mode="all"), recognizer=recognizer)
        decision = guard.evaluate(make_context(torrent_info=make_torrent(title="目标 无二次结果 2024")))
        assert not decision.observed
        recognizer.assert_called_once()

    def test_secondary_recognition_uses_cache_for_same_input(self):
        recognizer = MagicMock(return_value=make_media(tmdb_id=999, type=MediaType.TV))
        guard = RecognitionGuard(make_config(tmdb_recheck_mode="all"), recognizer=recognizer)
        context = make_context(torrent_info=make_torrent(title="目标 缓存复用 2024"))
        first = guard.evaluate(context)
        second = guard.evaluate(context)
        assert first.code == "secondary_tmdb_mismatch"
        assert second.code == "secondary_tmdb_mismatch"
        recognizer.assert_called_once()

    def test_secondary_recognition_handles_recognizer_error(self):
        recognizer = MagicMock(side_effect=RuntimeError("boom"))
        guard = RecognitionGuard(make_config(tmdb_recheck_mode="all"), recognizer=recognizer)
        with patch("subscribeassistant.recognition_guard.logger.warning") as warning:
            decision = guard.evaluate(make_context(torrent_info=make_torrent(title="目标 识别异常 2024")))
        assert not decision.observed
        warning.assert_called_once()


class RecognitionGuardHelperTest:
    """识别增强辅助函数的边界处理。"""

    def test_cached_info_roundtrip_handles_invalid_media_type(self):
        guard = RecognitionGuard(make_config())
        data = guard._cached_info_to_dict(CachedRecognitionInfo(
            type=MediaType.TV,
            tmdb_id=100,
            douban_id="db100",
            title="目标",
            year="2024",
            genre_ids=[16],
            category="动画",
        ))
        assert guard._cached_info_from_dict(data).type == MediaType.TV
        assert guard._cached_info_from_dict({"type": "bad"}).type is None

    def test_candidate_type_prefers_category_then_meta_then_patterns(self):
        guard = RecognitionGuard(make_config(movie_patterns=["电影"], tv_patterns=["剧集"]))
        assert guard._candidate_type(make_context(torrent_info=make_torrent(category=MediaType.MOVIE.value)), "") \
               == MediaType.MOVIE
        assert guard._candidate_type(make_context(torrent_info=make_torrent(category="bad")), "剧集") == MediaType.TV
        assert guard._candidate_type(make_context(meta_info=make_meta(type=MediaType.TV)), "") == MediaType.TV
        assert guard._candidate_type(make_context(meta_info=make_meta(type=None)), "电影") == MediaType.MOVIE
        assert guard._candidate_type(make_context(meta_info=make_meta(type=None)), "无类型") is None

    def test_cache_key_changes_with_custom_words_and_site_input(self):
        meta = SimpleNamespace(title="目标", name="目标", year="2024")
        context = make_context(torrent_info=make_torrent(site=1, title="目标"))
        first = RecognitionGuard(make_config(custom_words=["A"]))
        second = RecognitionGuard(make_config(custom_words=["B"]))
        assert first._recognition_cache_key(meta, MediaType.TV, context) != \
               second._recognition_cache_key(meta, MediaType.TV, context)

    def test_match_patterns_skips_invalid_regex(self):
        guard = RecognitionGuard(make_config())
        with patch("subscribeassistant.recognition_guard.logger.warning") as warning:
            assert guard._match_patterns(["[", "目标"], "目标") == "目标"
        warning.assert_called_once()

    def test_match_patterns_ignores_empty_text_and_empty_pattern(self):
        guard = RecognitionGuard(make_config())
        assert guard._match_patterns(["目标"], "") is None
        assert guard._match_patterns(["", "目标"], "目标") == "目标"

    def test_truncate_log_text_limits_long_values(self):
        assert RecognitionGuard._truncate_log_text("abcdef", 4) == "a..."
        assert RecognitionGuard._truncate_log_text("abc", 4) == "abc"

    def test_safe_int_handles_year_prefix_and_invalid_values(self):
        assert RecognitionGuard._safe_int("2024-01-01") == 2024
        assert RecognitionGuard._safe_int("") is None
        assert RecognitionGuard._safe_int("bad") is None

    def test_should_secondary_recognize_respects_mode_matrix(self):
        assert not RecognitionGuard(make_config(tmdb_recheck_mode="off"))._should_secondary_recognize()
        assert RecognitionGuard(make_config(mode="observe", tmdb_recheck_mode="all"))._should_secondary_recognize()
        assert not RecognitionGuard(make_config(mode="observe", tmdb_recheck_mode="strict"))._should_secondary_recognize()
        assert RecognitionGuard(make_config(mode="strict", tmdb_recheck_mode="strict"))._should_secondary_recognize()
        assert RecognitionGuard(make_config(mode="conservative",
                                            tmdb_recheck_mode="conservative_strict"))._should_secondary_recognize()
        assert not RecognitionGuard(make_config(tmdb_recheck_mode="bad"))._should_secondary_recognize()

    def test_handle_missing_year_filters_in_strict_modes(self):
        decision = RecognitionGuard(make_config(no_year_action="filter"))._handle_missing_year(
            "missing", "缺少年份", "候选")
        assert decision.blocked
        assert decision.code == "missing"

    def test_handle_missing_year_allows_when_policy_allows(self):
        decision = RecognitionGuard(make_config(no_year_action="allow"))._handle_missing_year(
            "missing", "缺少年份", "候选")
        assert not decision.observed

    def test_target_season_prefers_meta_then_media(self):
        guard = RecognitionGuard(make_config())
        assert guard._target_season(make_context(meta_info=make_meta(begin_season=2))) == 2
        assert guard._target_season(make_context(meta_info=make_meta(begin_season=None),
                                                 media_info=make_media(season=3))) == 3
        assert guard._target_season(make_context(meta_info=make_meta(begin_season=None),
                                                 media_info=make_media(season=None))) is None

    def test_allowed_tv_years_supports_loose_and_season_strict_modes(self):
        media = make_media(year="2020", season_years={1: "2020", 2: "2025", 3: "bad"})
        context = make_context(meta_info=make_meta(begin_season=2), media_info=media)
        assert RecognitionGuard(make_config(tv_year_mode="loose"))._allowed_tv_years(media, context) == {2020, 2025}
        assert RecognitionGuard(make_config(tv_year_mode="season_strict"))._allowed_tv_years(media, context) == {2025}
        assert RecognitionGuard(make_config(tv_year_mode="bad"))._allowed_tv_years(media, context) == set()

    def test_animation_helpers_detect_category_keywords(self):
        guard = RecognitionGuard(make_config())
        assert not guard._is_animation_media(None)
        assert guard._is_animation_media(make_media(genre_ids=[16], category=""))
        assert guard._is_animation_media(make_media(genre_ids=[], category="Anime"))
        assert not guard._is_animation_info(None)
        assert guard._is_animation_info(CachedRecognitionInfo(genre_ids=[16]))
        assert guard._is_animation_info(CachedRecognitionInfo(category="国漫"))
        assert not guard._is_animation_info(CachedRecognitionInfo(category="剧情"))

    def test_cached_info_helpers_accept_empty_values(self):
        guard = RecognitionGuard(make_config())
        assert guard._cached_info_from_media(None) is None
        assert guard._cached_info_to_dict(None) is None
        assert guard._cached_info_from_dict(None) is None

    def test_trusted_candidate_identity_requires_explicit_source_and_id(self):
        guard = RecognitionGuard(make_config())
        assert not guard._is_trusted_candidate_media_identity(make_context(candidate_recognized=False))
        assert not guard._is_trusted_candidate_media_identity(make_context(
            candidate_recognized=True, media_info_is_target=True, match_source="tmdbid"))
        assert not guard._is_trusted_candidate_media_identity(make_context(
            candidate_recognized=True, media_info_is_target=False, match_source="title"))
        assert guard._is_trusted_candidate_media_identity(make_context(
            candidate_recognized=True,
            media_info_is_target=False,
            match_source="doubanid",
            media_info=make_media(tmdb_id=None, douban_id="db100"),
        ))

    def test_candidate_log_text_handles_empty_and_truncates_description(self):
        guard = RecognitionGuard(make_config())
        assert guard._candidate_log_text(None) == ""
        text = guard._candidate_log_text(make_context(torrent_info=make_torrent(
            title="t" * 130,
            description="d" * 130,
        )))
        assert "..." in text

    def test_build_text_handles_missing_torrent_and_optional_fields(self):
        guard = RecognitionGuard(make_config())
        assert guard._build_text(SimpleNamespace(torrent_info=None)) == ""
        text = guard._build_text(make_context(torrent_info=make_torrent(
            title="标题", description=None, labels=["中字", None], category="剧集", site_name="站点",
        )))
        assert "标题" in text
        assert "中字" in text
        assert "站点" in text

    def test_same_identity_accepts_matching_douban_id_without_tmdb(self):
        guard = RecognitionGuard(make_config())
        recognized = CachedRecognitionInfo(tmdb_id=None, douban_id="db100", type=MediaType.TV)
        assert guard._is_same_identity(recognized, make_media(tmdb_id=None, douban_id="db100"))
