"""guard.py 完成守卫单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from app.schemas.types import MediaType

from subscribeassistantenhanced.engine.local import check_l_signal
from subscribeassistantenhanced.engine.pipeline import CompletionEvidencePipeline
from subscribeassistantenhanced.engine.scope import build_scope
from subscribeassistantenhanced.engine.types import CompletionEvidence, CompletionSignal
from subscribeassistantenhanced import SubscribeAssistantEnhanced
from subscribeassistantenhanced.guard import CompletionGuard
from subscribeassistantenhanced.shared.config import PluginConfig
from subscribeassistantenhanced.shared.subscribe import pending_subscription_episodes


def _ep(num, ep_type="standard", air_date="2026-01-01", season=1):
    """构造 TMDB 集对象替身。"""
    return SimpleNamespace(
        episode_number=num,
        season_number=season,
        air_date=air_date,
        episode_type=ep_type,
        name=f"E{num}",
    )


def _sub(sid=1, stype="电视剧", best_version=0, best_version_full=0, state="R"):
    return SimpleNamespace(
        id=sid, name="测试剧", tmdbid=100, season=1,
        year=None,
        episode_group=None, type=stype, state=state,
        best_version=best_version, best_version_full=best_version_full,
        total_episode=12, lack_episode=0,
        start_episode=1, note=[], episode_priority={},
    )


def _event(subscribe=None, mediainfo=None):
    """链式事件 wrapper：CompletionCheck 业务字段固定放在 event.event_data。"""
    data = SimpleNamespace(
        subscribe=subscribe or _sub(),
        mediainfo=mediainfo or SimpleNamespace(tmdb_id=100, tmdb_info=SimpleNamespace(
            status="Returning Series", next_episode_to_air=None,
            last_episode_to_air=None, seasons=[],
        )),
        meta=SimpleNamespace(type=MediaType.TV, begin_season=1, season=1),
        cancel=False, reason="", source="",
    )
    return SimpleNamespace(event_data=data)


def _signal(completed=False, confidence="none", stable=True, signals=None,
            reason="无信号确认当前目标范围已播完", scope_total=12,
            scope_high_risk=False, volatility_direction=None):
    return CompletionSignal(
        completed=completed,
        confidence=confidence,
        stable=stable,
        signals=signals if signals is not None else ["none"],
        reason=reason,
        scope_total=scope_total,
        scope_high_risk=scope_high_risk,
        volatility_direction=volatility_direction,
    )


def _evidence(primary=None, **kwargs):
    primary = primary or _signal()
    evidence = CompletionEvidence(
        scope_total=primary.scope_total,
        scope_high_risk=primary.scope_high_risk,
        primary_signal=primary,
    )
    for key, value in kwargs.items():
        setattr(evidence, key, value)
    return evidence


def _guard(evidence=None, has_active=False, mode="strict"):
    """构造 CompletionGuard，使用 fake evidence pipeline 注入守卫证据。"""
    pipeline = SimpleNamespace(evaluate=MagicMock(return_value=evidence or _evidence()))
    timeout_manager = MagicMock()
    timeout_manager.consume_release_token.return_value = False
    guard = CompletionGuard(
        evidence_pipeline=pipeline,
        has_active_downloads_fn=MagicMock(return_value=has_active),
        mark_pending_fn=MagicMock(),
        timeout_manager=timeout_manager,
        mode=mode,
        pending_download_enabled=True,
        resolve_missing_fn=MagicMock(side_effect=lambda subscribe, **_kwargs: (
            not pending_subscription_episodes(subscribe),
            {},
        )),
    )
    return guard


class TestCompletionGuard:

    def test_completion_guard_routes_guard_veto_to_lifecycle(self):
        """入口构造的 guard_veto 回调经生命周期协调器登记。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        guard = plugin._modules["guard"]
        lifecycle = plugin._modules["lifecycle"]
        lifecycle.enter_guard_pending = MagicMock()
        subscribe = SimpleNamespace(id=1)

        guard.mark_pending_fn(subscribe, source="guard_veto", reason="观察")

        lifecycle.enter_guard_pending.assert_called_once_with(subscribe, reason="观察")

    def test_movie_not_intercepted(self):
        """电影订阅不拦截，也不计算完成证据。"""
        guard = _guard()
        event = _event(subscribe=_sub(stype="电影"))

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.evidence_pipeline.evaluate.assert_not_called()

    def test_movie_active_download_blocks_before_media_return(self):
        """电影订阅仍先受下载中保护，避免下载任务尚未入库时提前完成。"""
        guard = _guard(has_active=True)
        event = _event(subscribe=_sub(stype="电影"))

        guard.handle(event)

        assert event.event_data.cancel is True
        assert "下载" in event.event_data.reason
        guard.evidence_pipeline.evaluate.assert_not_called()
        guard.mark_pending_fn.assert_not_called()

    def test_unknown_media_type_not_intercepted(self):
        """未知媒体类型不按剧集完成守卫处理，避免无效类型被写入待定。"""
        guard = _guard()
        event = _event(subscribe=_sub(stype=MediaType.UNKNOWN))

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.evidence_pipeline.evaluate.assert_not_called()
        guard.mark_pending_fn.assert_not_called()

    def test_active_download_blocks_before_evidence(self):
        """存在进行中下载时直接否决，不计算证据、不写 P。"""
        guard = _guard(has_active=True)
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert "下载" in event.event_data.reason
        guard.evidence_pipeline.evaluate.assert_not_called()
        guard.mark_pending_fn.assert_not_called()
        guard.timeout_manager.record_observation.assert_not_called()

    def test_active_download_does_not_block_when_pending_download_disabled(self):
        """关闭自动待定下载中订阅后，下载中状态不再单独否决完成。"""
        high = _signal(completed=True, confidence="high", signals=["E:ended"], reason="已完结")
        guard = _guard(evidence=_evidence(primary=high, high_completion=high), has_active=True)
        guard.pending_download_enabled = False
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.evidence_pipeline.evaluate.assert_called_once()

    def test_full_best_version_skips_completion_evidence_after_pending_check(self):
        """全集洗版不由完成守卫裁决，下载中保护通过后直接交还主程序洗版链路。"""
        guard = _guard()
        event = _event(subscribe=_sub(best_version=1, best_version_full=1))

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.evidence_pipeline.evaluate.assert_not_called()
        guard.resolve_missing_fn.assert_not_called()
        guard.mark_pending_fn.assert_not_called()

    def test_full_best_version_active_download_blocks_before_skip(self):
        """全集洗版仍先检查下载中待定，避免资源已选中但尚未入库时结束订阅。"""
        guard = _guard(has_active=True)
        event = _event(subscribe=_sub(best_version=1, best_version_full=1))

        guard.handle(event)

        assert event.event_data.cancel is True
        assert "下载" in event.event_data.reason
        guard.evidence_pipeline.evaluate.assert_not_called()

    def test_wenxin_like_40_episode_l_satisfied_balanced_completes_without_guard_veto(self):
        """40 集普通剧集不再因超长季风险进入完成前观察，L+I 证据可在 balanced 放行。"""
        subscribe = _sub()
        subscribe.total_episode = 40
        episodes = [_ep(i) for i in range(1, 41)]
        volatility = SimpleNamespace(is_stable=MagicMock(return_value=True))
        pipeline = CompletionEvidencePipeline(
            tmdb_episodes_fn=MagicMock(return_value=episodes),
            volatility_tracker=volatility,
            config=PluginConfig({}),
        )
        guard = CompletionGuard(
            evidence_pipeline=pipeline,
            has_active_downloads_fn=MagicMock(return_value=False),
            mark_pending_fn=MagicMock(),
            timeout_manager=MagicMock(),
            mode="balanced",
            pending_download_enabled=True,
            resolve_missing_fn=MagicMock(return_value=(True, {})),
        )
        event = _event(subscribe=subscribe)

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.mark_pending_fn.assert_not_called()
        guard.timeout_manager.record_observation.assert_not_called()

    def test_evidence_pipeline_receives_missing_resolver_and_meta(self):
        """完成守卫把主程序缺集口径与 CompletionCheck meta 交给 evidence pipeline。"""
        high = _signal(completed=True, confidence="high", signals=["E:ended"], reason="已完结")
        guard = _guard(evidence=_evidence(primary=high, high_completion=high))
        event = _event()

        guard.handle(event)

        guard.evidence_pipeline.evaluate.assert_called_once_with(
            event.event_data.subscribe,
            event.event_data.mediainfo,
            resolve_missing_fn=guard.resolve_missing_fn,
            meta=event.event_data.meta,
            consume_site_evidence=True,
        )

    def test_evidence_pipeline_receives_none_when_event_meta_absent(self):
        """CompletionCheck 事件未携带 meta 时，完成证据流水线按缺省媒体信息处理。"""
        high = _signal(completed=True, confidence="high", signals=["E:ended"], reason="已完结")
        guard = _guard(evidence=_evidence(primary=high, high_completion=high))
        event = _event()
        delattr(event.event_data, "meta")

        guard.handle(event)

        guard.evidence_pipeline.evaluate.assert_called_once_with(
            event.event_data.subscribe,
            event.event_data.mediainfo,
            resolve_missing_fn=guard.resolve_missing_fn,
            meta=None,
            consume_site_evidence=True,
        )

    def test_hard_veto_blocks_even_when_target_complete_exists(self):
        """F down 硬否决不可被 target_complete 完成证据覆盖。"""
        hard = _signal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            reason="目标总集数缩小",
            volatility_direction="down",
        )
        target = _signal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "I:all_aired"],
            reason="当前目标完成",
        )
        guard = _guard(evidence=_evidence(primary=hard, hard_veto=hard,
                                          target_complete_signal=target), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "目标总集数缩小"
        assert guard.timeout_manager.method_calls[0] == call.clear_release_token(event.event_data.subscribe)
        guard.mark_pending_fn.assert_called_once_with(
            event.event_data.subscribe,
            source="guard_veto",
            reason="目标总集数缩小",
        )
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=hard,
            total_episode=12,
        )

    def test_f_up_with_medium_target_complete_releases_in_balanced(self):
        """F up/普通不稳定只在 balanced/loose 且 target_complete 存在时放行。"""
        unstable = _signal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            reason="目标总集数增加",
            volatility_direction="up",
        )
        target = _signal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "I:all_aired"],
            reason="当前目标完成",
        )
        guard = _guard(evidence=_evidence(primary=target, unstable_signal=unstable,
                                          target_complete_signal=target), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.mark_pending_fn.assert_not_called()
        guard.timeout_manager.record_observation.assert_not_called()

    def test_high_completion_primary_releases_even_when_unstable_context_exists(self):
        """pipeline 已确认 E 高置信可绕过 F 时，guard 不再按 F 进入观察。"""
        unstable = _signal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            reason="目标总集数增加",
            volatility_direction="up",
        )
        high = _signal(
            completed=True,
            confidence="high",
            signals=["E:ended"],
            reason="TMDB 状态为 Ended",
        )
        guard = _guard(evidence=_evidence(primary=high, unstable_signal=unstable,
                                          high_completion=high), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.mark_pending_fn.assert_not_called()
        guard.timeout_manager.record_observation.assert_not_called()

    def test_f_up_with_independent_medium_i_still_observes_unstable(self):
        """独立中置信 I 不覆盖 F up，仍进入不稳定观察。"""
        unstable = _signal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            reason="目标总集数增加",
            volatility_direction="up",
        )
        i_signal = _signal(
            completed=True,
            confidence="medium",
            signals=["I:next_season"],
            reason="下一季已存在",
        )
        guard = _guard(evidence=_evidence(primary=unstable, unstable_signal=unstable,
                                          i_signal=i_signal), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "目标总集数增加"
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=unstable,
            total_episode=12,
        )

    def test_ordinary_unstable_observation_clears_stale_release_token(self):
        """普通 F 不稳定观察前清理旧完成释放令牌。"""
        unstable = _signal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            reason="目标总集数最近发生变化",
        )
        guard = _guard(evidence=_evidence(primary=unstable, unstable_signal=unstable), mode="loose")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.mark_pending_fn.assert_called_once()
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=unstable,
            total_episode=12,
        )

    def test_high_confidence_releases_and_clears_stale_token(self):
        """高置信完成直接放行，并清理旧完成释放令牌。"""
        high = _signal(completed=True, confidence="high", signals=["E:ended"], reason="已完结")
        guard = _guard(evidence=_evidence(primary=high, high_completion=high))
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.timeout_manager.consume_release_token.assert_not_called()
        guard.mark_pending_fn.assert_not_called()

    def test_balanced_medium_target_complete_releases_and_clears_token(self, monkeypatch):
        """balanced 接受 L+I 合成的当前目标完成证据，并清理旧完成释放令牌。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.guard.detail", messages.append)
        target = _signal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "I:all_aired"],
            reason="当前目标完成",
        )
        guard = _guard(evidence=_evidence(primary=target, target_complete_signal=target),
                       mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.timeout_manager.record_observation.assert_not_called()
        assert any("L:target_satisfied + I:all_aired" in message for message in messages)

    def test_strict_medium_target_complete_enters_observation(self):
        """strict 把 target_complete 作为 guard_veto 观察，不直接完成。"""
        target = _signal(
            completed=True,
            confidence="medium",
            signals=["L:target_satisfied", "I:all_aired"],
            reason="当前目标完成",
        )
        guard = _guard(evidence=_evidence(primary=target, target_complete_signal=target),
                       mode="strict")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "当前目标完成"
        guard.timeout_manager.consume_release_token.assert_not_called()
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=target,
            total_episode=12,
        )

    def test_independent_medium_i_releases_and_clears_token(self):
        """无活跃 F 时独立 medium I 仍按中置信完成证据放行。"""
        i_signal = _signal(
            completed=True,
            confidence="medium",
            signals=["I:next_season"],
            reason="下一季已存在",
        )
        guard = _guard(evidence=_evidence(primary=i_signal, i_signal=i_signal),
                       mode="strict")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)

    def test_allowed_single_low_releases_and_clears_stale_token(self):
        """balanced 接受三集及以上、非高风险的单一低置信 L 证据。"""
        low = _signal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            reason="订阅目标范围已无待下载集",
            scope_total=12,
        )
        guard = _guard(evidence=_evidence(primary=low, local_signal=low), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.timeout_manager.consume_release_token.assert_not_called()

    def test_low_confidence_with_release_token_releases(self):
        """不允许直接完成的低置信观察，命中释放令牌后放行。"""
        low = _signal(
            completed=True,
            confidence="low",
            signals=["I:all_aired"],
            reason="全部已播",
            scope_total=2,
        )
        guard = _guard(evidence=_evidence(primary=low, i_low_signal=low), mode="balanced")
        guard.timeout_manager.consume_release_token.return_value = True
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.timeout_manager.consume_release_token.assert_called_once_with(
            event.event_data.subscribe,
            low,
            total_episode=2,
        )
        guard.timeout_manager.clear_release_token.assert_not_called()
        guard.mark_pending_fn.assert_not_called()
        guard.timeout_manager.record_observation.assert_not_called()

    def test_short_l_low_still_enters_observation_even_in_loose_and_clears_token(self):
        """宽松模式也不直接接受一至两集短样本 L。"""
        low = _signal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            reason="订阅目标范围已无待下载集",
            scope_total=2,
        )
        guard = _guard(evidence=_evidence(primary=low, local_signal=low), mode="loose")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "订阅目标范围已无待下载集"
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.mark_pending_fn.assert_called_once()
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=low,
            total_episode=2,
        )

    def test_balanced_short_l_low_enters_observation(self):
        """平衡模式保留一至两集 L 观察，避免短样本提前完成。"""
        low = _signal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            reason="订阅目标范围已无待下载集",
            scope_total=2,
        )
        guard = _guard(evidence=_evidence(primary=low, local_signal=low), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "订阅目标范围已无待下载集"
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=low,
            total_episode=2,
        )

    def test_balanced_high_risk_l_low_enters_observation(self):
        """平衡模式下高风险目标范围的 L 信号仍进入完成前观察。"""
        low = _signal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            reason="订阅目标范围已无待下载集",
            scope_total=80,
            scope_high_risk=True,
        )
        guard = _guard(evidence=_evidence(primary=low, local_signal=low), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=low,
            total_episode=80,
        )

    def test_balanced_i_low_long_scope_releases(self):
        """平衡模式立即接受三集及以上、非高风险的低置信 I 信号。"""
        low = _signal(
            completed=True,
            confidence="low",
            signals=["I:all_aired"],
            reason="全部已播",
            scope_total=26,
        )
        guard = _guard(evidence=_evidence(primary=low, i_low_signal=low), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is False
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.timeout_manager.consume_release_token.assert_not_called()

    def test_low_confidence_completion_enters_guard_observation(self):
        """低置信 I 完成首次命中时进入 guard_veto 观察。"""
        low = _signal(
            completed=True,
            confidence="low",
            signals=["I:all_aired"],
            reason="目标范围内所有集已播且未发现后续集",
            scope_total=2,
        )
        guard = _guard(evidence=_evidence(primary=low, i_low_signal=low))
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "目标范围内所有集已播且未发现后续集"
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.mark_pending_fn.assert_called_once()
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=low,
            total_episode=2,
        )

    def test_none_blocks_with_local_blocked_reason_when_useful(self):
        """无完成信号时优先展示 pipeline 产出的 L 失败诊断。"""
        none = _signal(
            completed=False,
            stable=True,
            signals=["none"],
            reason="无信号确认当前目标范围已播完",
        )
        guard = _guard(evidence=_evidence(
            primary=none,
            local_blocked_reason="TMDB 已存在目标范围外的后续集：S01E13",
        ), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "TMDB 已存在目标范围外的后续集：S01E13"
        guard.mark_pending_fn.assert_called_once_with(
            event.event_data.subscribe,
            source="guard_veto",
            reason=event.event_data.reason,
        )

    def test_none_blocks_with_primary_signal_reason_by_default(self):
        """无更具体 L 诊断时使用 primary_signal 原因。"""
        none = _signal(completed=False, stable=True, signals=["none"], reason="无完结信号")
        guard = _guard(evidence=_evidence(primary=none), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "无完结信号"
        assert event.event_data.source == "subscribeassistantenhanced"
        guard.mark_pending_fn.assert_called_once()

    def test_mid_season_hard_veto_blocks(self):
        """M:mid_season 作为硬否决进入完成前观察。"""
        hard = _signal(
            completed=False,
            stable=True,
            signals=["M:mid_season"],
            reason="最后已播集为 mid_season，阶段中场",
        )
        guard = _guard(evidence=_evidence(primary=hard, hard_veto=hard), mode="balanced")
        event = _event()

        guard.handle(event)

        assert event.event_data.cancel is True
        assert event.event_data.reason == "最后已播集为 mid_season，阶段中场"
        guard.timeout_manager.clear_release_token.assert_called_once_with(event.event_data.subscribe)
        guard.timeout_manager.record_observation.assert_called_once_with(
            event.event_data.subscribe,
            signal=hard,
            total_episode=12,
        )


class TestLocalSignal:

    def test_l_signal_reports_target_satisfied(self):
        """L 信号按主程序缺集查询确认当前目标范围已无待下载集，不要求 finale。"""
        subscribe = _sub()
        event = _event(subscribe=subscribe)
        mediainfo = event.event_data.mediainfo
        episodes = [_ep(i) for i in range(1, 13)]
        scope = build_scope(subscribe, mediainfo, lambda *_args, **_kwargs: episodes)
        resolve_missing = MagicMock(return_value=(True, {}))

        signal = check_l_signal(
            subscribe,
            scope,
            mediainfo=mediainfo,
            meta=event.event_data.meta,
            resolve_missing_fn=resolve_missing,
        )

        assert signal.completed is True
        assert signal.confidence == "low"
        assert signal.signals == ["L:target_satisfied"]
        assert signal.scope_total == 12
        resolve_missing.assert_called_once_with(
            subscribe=subscribe,
            meta=event.event_data.meta,
            mediainfo=mediainfo,
            best_version_accept_downloaded=False,
        )

    def test_l_signal_not_emitted_when_missing_resolver_reports_gap(self):
        """主程序缺集查询仍有剩余目标时不生成 L 信号。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        event = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe,
            event.event_data.mediainfo,
            lambda *_args, **_kwargs: [_ep(i) for i in range(1, 13)],
        )
        resolve_missing = MagicMock(return_value=(False, {100: {1: SimpleNamespace(episodes=[12])}}))

        signal = check_l_signal(
            subscribe,
            scope,
            mediainfo=event.event_data.mediainfo,
            meta=event.event_data.meta,
            resolve_missing_fn=resolve_missing,
        )

        assert signal is None
        resolve_missing.assert_called_once()

    def test_l_signal_uses_subscribe_total_when_scope_is_temporarily_empty(self):
        """TMDB 集列表暂不可用时，L 使用订阅目标总数参与模式判断。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        event = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe, event.event_data.mediainfo,
            lambda *_args, **_kwargs: [],
        )
        resolve_missing = MagicMock(return_value=(True, {}))

        signal = check_l_signal(
            subscribe,
            scope,
            mediainfo=event.event_data.mediainfo,
            meta=event.event_data.meta,
            resolve_missing_fn=resolve_missing,
        )

        assert signal.scope_total == 12

    def test_l_signal_not_emitted_when_target_range_is_unknown(self):
        """订阅总集数未知时不能把空目标范围误判为已经全部下载。"""
        subscribe = _sub()
        subscribe.total_episode = 0
        event = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe,
            event.event_data.mediainfo,
            lambda *_args, **_kwargs: [],
        )
        resolve_missing = MagicMock(return_value=(True, {}))

        assert check_l_signal(
            subscribe,
            scope,
            mediainfo=event.event_data.mediainfo,
            meta=event.event_data.meta,
            resolve_missing_fn=resolve_missing,
        ) is None
        resolve_missing.assert_not_called()

    def test_check_l_signal_without_resolver_fails_closed(self):
        """L 信号缺少主程序缺集查询入口时不自行创建订阅链。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        event = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe,
            event.event_data.mediainfo,
            lambda *_args, **_kwargs: [_ep(i) for i in range(1, 13)],
        )

        with patch("subscribeassistantenhanced.engine.local.SubscribeChain", create=True) as chain_cls:
            chain_cls.return_value.resolve_subscribe_missing.return_value = (True, {})
            signal = check_l_signal(
                subscribe,
                scope,
                mediainfo=event.event_data.mediainfo,
                meta=None,
            )

        assert signal is None
        chain_cls.assert_not_called()

    def test_check_l_signal_preserves_special_season_when_building_meta(self):
        """特别季 S0 是合法订阅目标，构造主程序 MetaInfo 时不能按未指定季处理。"""
        subscribe = _sub()
        subscribe.season = 0
        subscribe.note = list(range(1, 13))
        event = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe,
            event.event_data.mediainfo,
            lambda *_args, **_kwargs: [_ep(i, season=0) for i in range(1, 13)],
        )
        resolve_missing = MagicMock(return_value=(True, {}))

        signal = check_l_signal(
            subscribe,
            scope,
            mediainfo=event.event_data.mediainfo,
            meta=None,
            resolve_missing_fn=resolve_missing,
        )

        assert signal is not None
        _, kwargs = resolve_missing.call_args
        assert kwargs["meta"].begin_season == 0
