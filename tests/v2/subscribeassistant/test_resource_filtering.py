"""
SubscribeAssistant P1 识别增强与资源过滤单测。

覆盖识别增强配置装载、通知聚合、选择阶段过滤和下载阶段拦截状态修改。
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType
from subscribeassistant import SubscribeAssistant
from subscribeassistant.recognition_guard import RecognitionGuardConfig, RecognitionGuardDecision


def make_plugin(**overrides) -> SubscribeAssistant:
    """构造带识别增强默认配置的插件实例。"""
    plugin = object.__new__(SubscribeAssistant)
    plugin.plugin_name = "订阅助手"
    plugin.chain = MagicMock()
    plugin.post_message = MagicMock()
    plugin._notify = False
    plugin._recognition_guard_mode = "off"
    plugin._recognition_guard_target_mode = "auto"
    plugin._recognition_guard_same_name_protection = True
    plugin._recognition_guard_movie_year_mode = "loose"
    plugin._recognition_guard_tv_year_mode = "season_first"
    plugin._recognition_guard_no_year_action = "allow"
    plugin._recognition_guard_tmdb_recheck_mode = "off"
    plugin._recognition_guard_cache_maxsize = 100000
    plugin._recognition_guard_keyword_config = ""
    plugin._recognition_guard_notify = "off"
    plugin._recognition_guard_notify_interval = 3600
    plugin._recognition_guard_notify_cache = {}
    for key, value in overrides.items():
        setattr(plugin, key, value)
    return plugin


def make_subscribe(**kwargs) -> SimpleNamespace:
    """构造识别增强订阅上下文。"""
    base = dict(id=1, name="测试剧", year="2024", type=MediaType.TV.value, season=1,
                episode_group=None, custom_words="别名1\n别名2", tmdbid=100, doubanid=None,
                imdbid=None, tvdbid=None, bangumiid=None, backdrop=None, poster=None)
    base.update(kwargs)
    return SimpleNamespace(**base)


def make_context(title="标题") -> SimpleNamespace:
    """构造资源上下文。"""
    return SimpleNamespace(
        torrent_info=SimpleNamespace(title=title, description="副标题", site_name="站点", site=1, category=None),
        media_info=SimpleNamespace(title_year="测试剧 (2024)", type=MediaType.TV, tmdb_id=100),
        resource_source="rss", match_source="title", candidate_recognized=False, media_info_is_target=True,
    )


class ResourceFilteringTest:
    """识别增强配置、选择过滤与下载拦截。"""

    def test_get_recognition_guard_config_normalizes_invalid_choices(self):
        plugin = make_plugin(
            _recognition_guard_mode="bad",
            _recognition_guard_target_mode="bad",
            _recognition_guard_movie_year_mode="bad",
            _recognition_guard_tv_year_mode="bad",
            _recognition_guard_no_year_action="bad",
            _recognition_guard_tmdb_recheck_mode="bad",
            _recognition_guard_cache_maxsize=-1,
        )
        config = plugin._SubscribeAssistant__get_recognition_guard_config(make_subscribe())
        assert config.mode == "off"
        assert config.target_mode == "auto"
        assert config.movie_year_mode == "loose"
        assert config.tv_year_mode == "season_first"
        assert config.no_year_action == "allow"
        assert config.tmdb_recheck_mode == "off"
        assert config.cache_maxsize == 1

    def test_get_recognition_guard_config_loads_custom_words_and_yaml(self):
        plugin = make_plugin(
            _recognition_guard_mode="strict",
            _recognition_guard_keyword_config="allow:\n  - 放行\nblock:\n  - 拦截\nmovie: 电影\n",
        )
        config = plugin._SubscribeAssistant__get_recognition_guard_config(make_subscribe())
        assert config.mode == "strict"
        assert config.custom_words == ["别名1", "别名2"]
        assert config.allow_patterns == ["放行"]
        assert config.block_patterns == ["拦截"]
        assert config.movie_patterns == ["电影"]

    def test_load_recognition_guard_keyword_config_handles_invalid_yaml(self):
        plugin = make_plugin(_recognition_guard_keyword_config=": bad: yaml")
        with patch("subscribeassistant.logger.error"):
            result = plugin._SubscribeAssistant__load_recognition_guard_keyword_config()
        assert result["allow"] == []
        assert result["block"] == []

    def test_load_recognition_guard_keyword_config_normalizes_lists_and_scalars(self):
        plugin = make_plugin(_recognition_guard_keyword_config="""
live_action:
  - 真人
animation: 动画
movie:
  - 电影
tv: 剧集
allow: PROPER
block:
  - 禁止
unknown:
  - ignored
""")
        result = plugin._SubscribeAssistant__load_recognition_guard_keyword_config()
        assert result["live_action"] == ["真人"]
        assert result["animation"] == ["动画"]
        assert result["movie"] == ["电影"]
        assert result["tv"] == ["剧集"]
        assert result["allow"] == ["PROPER"]
        assert result["block"] == ["禁止"]

    def test_load_recognition_guard_keyword_config_ignores_non_object_yaml(self):
        plugin = make_plugin(_recognition_guard_keyword_config="- allow\n- block")
        with patch("subscribeassistant.logger.warning") as warning:
            result = plugin._SubscribeAssistant__load_recognition_guard_keyword_config()
        assert all(value == [] for value in result.values())
        warning.assert_called_once()

    def test_load_recognition_guard_keyword_config_handles_unexpected_loader_error(self):
        plugin = make_plugin(_recognition_guard_keyword_config="allow: PROPER")
        with patch("subscribeassistant.YAML") as yaml_cls, \
                patch("subscribeassistant.logger.error") as error:
            yaml_cls.return_value.load.side_effect = RuntimeError("boom")
            result = plugin._SubscribeAssistant__load_recognition_guard_keyword_config()
        assert all(value == [] for value in result.values())
        error.assert_called_once()

    def test_build_recognition_guard_uses_plugin_recognizer(self):
        plugin = make_plugin(_recognition_guard_mode="observe")
        guard = plugin._SubscribeAssistant__build_recognition_guard(make_subscribe())
        assert isinstance(guard.config, RecognitionGuardConfig)
        assert guard.recognizer.__name__ == "__recognize_guard_candidate"

    def test_recognize_guard_candidate_returns_chain_result(self):
        plugin = make_plugin()
        media = SimpleNamespace(title="目标")
        plugin.chain.recognize_media.return_value = media
        assert plugin._SubscribeAssistant__recognize_guard_candidate(SimpleNamespace(title="标题")) is media
        plugin.chain.recognize_media.assert_called_once()

    def test_recognize_guard_candidate_swallows_exception(self):
        plugin = make_plugin()
        plugin.chain.recognize_media.side_effect = RuntimeError("boom")
        with patch("subscribeassistant.logger.warning"):
            assert plugin._SubscribeAssistant__recognize_guard_candidate(SimpleNamespace(title="标题")) is None

    def test_recognize_media_returns_none_for_invalid_media_type(self):
        plugin = make_plugin()
        subscribe = make_subscribe(type="bad")
        assert plugin._SubscribeAssistant__recognize_media(subscribe) is None
        plugin.chain.recognize_media.assert_not_called()

    def test_recognize_media_returns_none_when_chain_has_no_result(self):
        plugin = make_plugin()
        plugin.chain.recognize_media.return_value = None
        assert plugin._SubscribeAssistant__recognize_media(make_subscribe()) is None

    def test_recognize_media_swallows_chain_exception(self):
        plugin = make_plugin()
        plugin.chain.recognize_media.side_effect = RuntimeError("boom")
        assert plugin._SubscribeAssistant__recognize_media(make_subscribe()) is None

    def test_handle_recognition_guard_decision_ignores_unobserved(self):
        plugin = make_plugin()
        with patch("subscribeassistant.logger.info") as info:
            plugin._SubscribeAssistant__handle_recognition_guard_decision(
                make_subscribe(), RecognitionGuardDecision(observed=False), make_context())
        info.assert_not_called()

    def test_handle_recognition_guard_decision_logs_observed_without_blocking(self):
        plugin = make_plugin()
        decision = RecognitionGuardDecision(observed=True, blocked=False, reason="观察原因", candidate_title="候选")
        with patch("subscribeassistant.logger.info") as info:
            plugin._SubscribeAssistant__handle_recognition_guard_decision(
                make_subscribe(), decision, make_context())
        info.assert_called_once()

    def test_format_recognition_guard_action(self):
        assert SubscribeAssistant._SubscribeAssistant__format_recognition_guard_action(
            RecognitionGuardDecision(blocked=True)) == "拦截"
        assert SubscribeAssistant._SubscribeAssistant__format_recognition_guard_action(
            RecognitionGuardDecision(blocked=False)) == "观察"

    def test_filter_recognition_guard_notify_pairs_limits_same_reason(self):
        plugin = make_plugin(_recognition_guard_notify_interval=3600)
        subscribe = make_subscribe()
        decision = RecognitionGuardDecision(blocked=True, observed=True, code="manual", reason="原因")
        first = plugin._SubscribeAssistant__filter_recognition_guard_notify_pairs(
            subscribe, [(decision, make_context())])
        second = plugin._SubscribeAssistant__filter_recognition_guard_notify_pairs(
            subscribe, [(decision, make_context())])
        assert len(first) == 1
        assert second == []

    def test_filter_recognition_guard_notify_pairs_cleans_old_cache(self):
        plugin = make_plugin(_recognition_guard_notify_interval=10)
        plugin._recognition_guard_notify_cache = {"old": datetime.now() - timedelta(seconds=30)}
        decision = RecognitionGuardDecision(blocked=True, observed=True, code="manual", reason="新原因")
        result = plugin._SubscribeAssistant__filter_recognition_guard_notify_pairs(
            make_subscribe(), [(decision, make_context())])
        assert len(result) == 1
        assert "old" not in plugin._recognition_guard_notify_cache

    def test_format_recognition_guard_summary_groups_reasons(self):
        plugin = make_plugin()
        decision = RecognitionGuardDecision(blocked=True, observed=True, reason="原因")
        text = plugin._SubscribeAssistant__format_recognition_guard_summary(
            [(decision, make_context()), (decision, make_context())])
        assert "命中：2 条" in text
        assert "拦截 2 条：原因" in text

    def test_format_recognition_guard_detail_limits_examples(self):
        plugin = make_plugin()
        decision = RecognitionGuardDecision(blocked=True, observed=True, reason="原因", candidate_title="候选")
        text = plugin._SubscribeAssistant__format_recognition_guard_detail(
            [(decision, make_context()) for _ in range(12)], include_observe=False)
        assert "命中：12 条" in text
        assert "其余明细：2 条" in text

    def test_post_recognition_guard_decisions_skips_when_notify_off(self):
        plugin = make_plugin(_notify=False, _recognition_guard_notify="summary")
        decision = RecognitionGuardDecision(blocked=True, observed=True, reason="原因")
        plugin._SubscribeAssistant__post_recognition_guard_decisions(make_subscribe(), [(decision, make_context())])
        plugin.post_message.assert_not_called()

    def test_post_recognition_guard_decisions_skips_when_notify_mode_off_or_no_blocked_pairs(self):
        decision = RecognitionGuardDecision(blocked=False, observed=True, reason="观察", candidate_title="观察资源")
        plugin = make_plugin(_notify=True, _recognition_guard_notify="off")
        plugin._SubscribeAssistant__post_recognition_guard_decisions(make_subscribe(), [(decision, make_context())])
        plugin.post_message.assert_not_called()

        plugin = make_plugin(_notify=True, _recognition_guard_notify="detail")
        plugin._SubscribeAssistant__post_recognition_guard_decisions(make_subscribe(), [(decision, make_context())])
        plugin.post_message.assert_not_called()

    def test_post_recognition_guard_decisions_sends_summary(self):
        plugin = make_plugin(_notify=True, _recognition_guard_notify="summary")
        decision = RecognitionGuardDecision(blocked=True, observed=True, reason="原因")
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_image", return_value=None):
            plugin._SubscribeAssistant__post_recognition_guard_decisions(make_subscribe(), [(decision, make_context())])
        plugin.post_message.assert_called_once()
        assert "识别增强汇总" in plugin.post_message.call_args.kwargs["title"]

    def test_post_recognition_guard_decisions_skips_when_no_pairs_after_rate_limit(self):
        plugin = make_plugin(_notify=True, _recognition_guard_notify="summary")
        decision = RecognitionGuardDecision(blocked=True, observed=True, code="manual", reason="原因")
        with patch.object(plugin, "_SubscribeAssistant__filter_recognition_guard_notify_pairs", return_value=[]):
            plugin._SubscribeAssistant__post_recognition_guard_decisions(
                make_subscribe(), [(decision, make_context())])
        plugin.post_message.assert_not_called()

    def test_post_recognition_guard_decisions_sends_detail_for_blocked_pairs(self):
        plugin = make_plugin(_notify=True, _recognition_guard_notify="detail")
        blocked = RecognitionGuardDecision(blocked=True, observed=True, reason="拦截", candidate_title="坏资源")
        observed = RecognitionGuardDecision(blocked=False, observed=True, reason="观察", candidate_title="观察资源")
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_image", return_value="img"):
            plugin._SubscribeAssistant__post_recognition_guard_decisions(
                make_subscribe(), [(blocked, make_context()), (observed, make_context())])
        kwargs = plugin.post_message.call_args.kwargs
        assert "识别增强明细" in kwargs["title"]
        assert "坏资源" in kwargs["text"]
        assert "观察资源" not in kwargs["text"]

    def test_post_recognition_guard_decisions_all_mode_includes_observed_pairs(self):
        plugin = make_plugin(_notify=True, _recognition_guard_notify="all")
        observed = RecognitionGuardDecision(blocked=False, observed=True, reason="观察", candidate_title="观察资源")
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_image", return_value="img"):
            plugin._SubscribeAssistant__post_recognition_guard_decisions(
                make_subscribe(), [(observed, make_context())])
        assert "观察资源" in plugin.post_message.call_args.kwargs["text"]

    def test_apply_recognition_guard_selection_returns_false_when_off(self):
        plugin = make_plugin()
        event_data = SimpleNamespace(contexts=[make_context()], updated=False, updated_contexts=None, source=None)
        assert not plugin._SubscribeAssistant__apply_recognition_guard_selection(event_data, make_subscribe())
        assert not event_data.updated

    def test_apply_recognition_guard_selection_filters_blocked_context(self):
        plugin = make_plugin()
        blocked = make_context("bad")
        kept = make_context("good")
        event_data = SimpleNamespace(contexts=[blocked, kept], updated=False, updated_contexts=None, source=None)
        guard = SimpleNamespace(
            config=SimpleNamespace(mode="strict"),
            evaluate=MagicMock(side_effect=[
                RecognitionGuardDecision(blocked=True, observed=True, reason="bad", candidate_title="bad"),
                RecognitionGuardDecision(blocked=False, observed=False, candidate_title="good"),
            ]),
        )
        with patch.object(plugin, "_SubscribeAssistant__build_recognition_guard", return_value=guard):
            changed = plugin._SubscribeAssistant__apply_recognition_guard_selection(event_data, make_subscribe())
        assert changed
        assert event_data.updated_contexts == [kept]
        assert event_data.source == "订阅助手"

    def test_apply_recognition_guard_selection_uses_updated_contexts_and_keeps_all_when_unblocked(self):
        plugin = make_plugin()
        original = make_context("original")
        updated = make_context("updated")
        event_data = SimpleNamespace(contexts=[original], updated=True, updated_contexts=[updated], source=None)
        guard = SimpleNamespace(
            config=SimpleNamespace(mode="strict"),
            evaluate=MagicMock(return_value=RecognitionGuardDecision(
                blocked=False, observed=True, reason="观察", candidate_title="updated")),
        )
        with patch.object(plugin, "_SubscribeAssistant__build_recognition_guard", return_value=guard), \
                patch.object(plugin, "_SubscribeAssistant__handle_recognition_guard_decision") as handle:
            changed = plugin._SubscribeAssistant__apply_recognition_guard_selection(event_data, make_subscribe())
        assert not changed
        assert event_data.updated_contexts == [updated]
        handle.assert_called_once()

    def test_apply_recognition_guard_download_blocks_event(self):
        plugin = make_plugin()
        event_data = SimpleNamespace(context=make_context(), cancel=False, source=None, reason=None)
        guard = SimpleNamespace(
            config=SimpleNamespace(mode="strict"),
            evaluate=MagicMock(return_value=RecognitionGuardDecision(
                blocked=True, observed=True, reason="拦截原因", candidate_title="标题")),
        )
        with patch.object(plugin, "_SubscribeAssistant__build_recognition_guard", return_value=guard):
            changed = plugin._SubscribeAssistant__apply_recognition_guard_download(event_data, make_subscribe())
        assert changed
        assert event_data.cancel
        assert event_data.reason == "拦截原因"

    def test_apply_recognition_guard_download_skips_when_off_or_unobserved(self):
        plugin = make_plugin()
        event_data = SimpleNamespace(context=make_context(), cancel=False, source=None, reason=None)
        off_guard = SimpleNamespace(config=SimpleNamespace(mode="off"))
        with patch.object(plugin, "_SubscribeAssistant__build_recognition_guard", return_value=off_guard):
            assert not plugin._SubscribeAssistant__apply_recognition_guard_download(event_data, make_subscribe())

        guard = SimpleNamespace(
            config=SimpleNamespace(mode="strict"),
            evaluate=MagicMock(return_value=RecognitionGuardDecision(observed=False, candidate_title="标题")),
        )
        with patch.object(plugin, "_SubscribeAssistant__build_recognition_guard", return_value=guard), \
                patch.object(plugin, "_SubscribeAssistant__handle_recognition_guard_decision") as handle:
            assert not plugin._SubscribeAssistant__apply_recognition_guard_download(event_data, make_subscribe())
        handle.assert_not_called()

    def test_apply_recognition_guard_download_observes_without_cancelling(self):
        plugin = make_plugin()
        event_data = SimpleNamespace(context=make_context(), cancel=False, source=None, reason=None)
        guard = SimpleNamespace(
            config=SimpleNamespace(mode="observe"),
            evaluate=MagicMock(return_value=RecognitionGuardDecision(
                blocked=False, observed=True, reason="观察", candidate_title="标题")),
        )
        with patch.object(plugin, "_SubscribeAssistant__build_recognition_guard", return_value=guard), \
                patch.object(plugin, "_SubscribeAssistant__handle_recognition_guard_decision") as handle, \
                patch.object(plugin, "_SubscribeAssistant__post_recognition_guard_decisions") as post:
            assert not plugin._SubscribeAssistant__apply_recognition_guard_download(event_data, make_subscribe())
        assert not event_data.cancel
        handle.assert_called_once()
        post.assert_called_once()
