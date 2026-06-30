"""guard.py 完成守卫单测。"""
from types import SimpleNamespace
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType

from subscribeassistantenhanced.guard import CompletionGuard
from subscribeassistantenhanced.engine.local import check_l_signal
from subscribeassistantenhanced.engine.scope import build_scope
from subscribeassistantenhanced.engine.types import CompletionSignal
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
        best_version=best_version, best_version_full=best_version_full, total_episode=12, lack_episode=0,
        start_episode=1, note=[], episode_priority={},
    )


def _event(subscribe=None, mediainfo=None):
    """链式事件 wrapper：CompletionCheck 业务字段固定放在 event.event_data（对齐主程序投递）。"""
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


def _guard(signal=None, has_active=False, mode="strict"):
    """构造 CompletionGuard，mock 依赖。"""
    g = CompletionGuard.__new__(CompletionGuard)
    g.evaluate_fn = MagicMock(return_value=signal or CompletionSignal())
    g.has_active_downloads_fn = MagicMock(return_value=has_active)
    g.detect_existing_episodes_fn = MagicMock(return_value=None)
    g.detect_missing_episodes_fn = MagicMock(return_value=None)
    g.tmdb_episodes_fn = MagicMock(return_value=[])
    g.pending_download_enabled = True
    g.mode = mode
    g.mark_pending_fn = MagicMock()
    g.timeout_manager = MagicMock()
    g.timeout_manager.consume_release.return_value = False
    g.resolve_missing_fn = MagicMock(side_effect=lambda subscribe, **_kwargs: (
        not pending_subscription_episodes(subscribe),
        {},
    ))
    return g


class TestCompletionGuard:

    def test_movie_not_intercepted(self):
        """电影订阅不拦截。"""
        g = _guard()
        ev = _event(subscribe=_sub(stype="电影"))
        g.handle(ev)
        assert ev.event_data.cancel is False
        g.evaluate_fn.assert_not_called()

    def test_movie_active_download_blocks_before_media_return(self):
        """电影订阅仍受下载中待定保护，避免下载任务尚未入库时提前完成。"""
        g = _guard(has_active=True)
        ev = _event(subscribe=_sub(stype="电影"))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert "下载" in ev.event_data.reason
        g.evaluate_fn.assert_not_called()
        g.mark_pending_fn.assert_not_called()

    def test_unknown_media_type_not_intercepted(self):
        """未知媒体类型不按剧集完成守卫处理，避免无效类型被写入待定。"""
        g = _guard()
        ev = _event(subscribe=_sub(stype=MediaType.UNKNOWN))

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.evaluate_fn.assert_not_called()
        g.mark_pending_fn.assert_not_called()

    def test_active_download_blocks_no_p(self):
        """存在进行中下载 → 否决但不写 P。"""
        g = _guard(has_active=True)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is True
        assert "下载" in ev.event_data.reason
        g.mark_pending_fn.assert_not_called()
        g.timeout_manager.record_block.assert_not_called()

    def test_active_download_does_not_block_when_pending_download_disabled(self):
        """关闭自动待定下载中订阅后，下载中状态不再单独否决完成。"""
        sig = CompletionSignal(completed=True, confidence="high", stable=True)
        g = _guard(signal=sig, has_active=True)
        g.pending_download_enabled = False
        ev = _event()
        g.handle(ev)

        assert ev.event_data.cancel is False
        g.evaluate_fn.assert_called_once()

    def test_f_unstable_blocks_with_p(self):
        """F 不稳定 → 否决并写 P(guard_veto)。"""
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is True
        g.mark_pending_fn.assert_called_once()
        call_args = g.mark_pending_fn.call_args
        assert call_args[1].get("source") == "guard_veto" or call_args[0][1] == "guard_veto"
        g.timeout_manager.record_block.assert_called_once_with(
            ev.event_data.subscribe,
            signal=sig,
            total_episode=12,
        )

    def test_unstable_signal_allows_trusted_l_target_satisfied(self):
        """F 不稳定时，可信 L 可作为受控例外放行普通订阅完成。"""
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        ev = _event(subscribe=subscribe)

        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.resolve_missing_fn.assert_called_once_with(
            subscribe=subscribe,
            meta=ev.event_data.meta,
            mediainfo=ev.event_data.mediainfo,
            best_version_accept_downloaded=False,
        )
        g.mark_pending_fn.assert_not_called()
        g.timeout_manager.record_block.assert_not_called()

    def test_unstable_signal_still_blocks_short_l_target_satisfied(self, monkeypatch):
        """F 不稳定时，一至两集低可信 L 仍不能直接完成。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.guard.logger.info", messages.append)
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig, mode="loose")
        g.tmdb_episodes_fn.return_value = [_ep(1), _ep(2)]
        subscribe = _sub()
        subscribe.total_episode = 2
        subscribe.note = [1, 2]
        ev = _event(subscribe=subscribe)

        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "变动"
        assert any("L 兜底未放行" in message and "短样本" in message for message in messages)
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once_with(
            subscribe,
            signal=sig,
            total_episode=2,
        )

    def test_unstable_total_shrink_blocks_l_target_satisfied(self, monkeypatch):
        """近期 total 缩小时，可信 L 也不能绕过 F 的低估风险。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.guard.logger.info", messages.append)
        sig = CompletionSignal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            reason="变动",
            volatility_direction="down",
        )
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "变动"
        assert any("L 兜底未放行" in message and "F 缩小" in message for message in messages)
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once_with(
            subscribe,
            signal=sig,
            total_episode=12,
        )

    def test_unstable_l_not_allowed_logs_missing_resolver_gap(self, monkeypatch):
        """F 不稳定且主程序缺集口径仍未满足时，日志应直接说明 L 未放行原因。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.guard.logger.info", messages.append)
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        subscribe = _sub()
        subscribe.note = list(range(1, 12))
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(False, {100: {1: SimpleNamespace(episodes=[12])}}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert any("L 兜底未放行" in message and "主程序缺集口径未满足" in message for message in messages)

    def test_unstable_l_can_cover_advance_access_future_inside_target_range(self):
        """超前点播已覆盖订阅目标范围时，F 不稳定可由可信 L 放行。"""
        future_air_date = (date.today() + timedelta(days=30)).isoformat()
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=future_air_date),
            _ep(3, air_date=future_air_date),
        ]
        subscribe = _sub()
        subscribe.total_episode = 3
        subscribe.note = [1, 2, 3]
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.resolve_missing_fn.assert_called_once()
        g.mark_pending_fn.assert_not_called()

    def test_unstable_l_not_allowed_logs_future_outside_target_range(self, monkeypatch):
        """SeasonScope 存在目标范围外后续集时，F 不稳定日志应说明 L 被阻断。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.guard.logger.info", messages.append)
        future_air_date = (date.today() + timedelta(days=30)).isoformat()
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=future_air_date),
        ]
        subscribe = _sub()
        subscribe.total_episode = 1
        subscribe.note = [1]
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert any("L 兜底未放行" in message and "目标范围外的后续集" in message for message in messages)
        g.resolve_missing_fn.assert_not_called()

    def test_unstable_l_not_allowed_logs_strict_limit(self, monkeypatch):
        """严格模式下可信 L 只能进入观察，不能覆盖 F 不稳定。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.guard.logger.info", messages.append)
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig, mode="strict")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert any("L 兜底未放行" in message and "strict" in message for message in messages)

    def test_unstable_l_not_allowed_logs_high_risk(self, monkeypatch):
        """高风险 SeasonScope 的 L 信号不能覆盖 F 不稳定。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.guard.logger.info", messages.append)
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 41)]
        subscribe = _sub()
        subscribe.total_episode = 40
        subscribe.note = list(range(1, 41))
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert any("L 兜底未放行" in message and "高风险" in message for message in messages)

    def test_high_confidence_releases(self):
        """高置信度直接放行，快照统一由 SubscribeComplete 记录。"""
        sig = CompletionSignal(completed=True, confidence="high", signals=["E:ended"])
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is False

    def test_low_confidence_with_release_token_releases(self):
        """严格模式低置信观察已释放时放行。"""
        sig = CompletionSignal(completed=True, confidence="low", signals=["I:all_aired"])
        g = _guard(signal=sig)
        g.timeout_manager.consume_release.return_value = True
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is False

    def test_low_confidence_completion_enters_guard_observation_without_snapshot(self):
        """低置信 I 完成首次命中时进入 guard_veto 观察，不登记 H 快照。"""
        sig = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["I:all_aired"],
            reason="目标范围内所有集已播且未发现后续集",
        )
        g = _guard(signal=sig)
        g.timeout_manager.consume_release.return_value = False
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "目标范围内所有集已播且未发现后续集"
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once_with(
            ev.event_data.subscribe,
            signal=sig,
            total_episode=12,
        )

    def test_low_confidence_completion_after_observation_releases(self):
        """低置信观察释放后，同一轮信号允许完成。"""
        sig = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["I:all_aired"],
            reason="目标范围内所有集已播且未发现后续集",
        )
        g = _guard(signal=sig)
        g.timeout_manager.consume_release.return_value = True
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.mark_pending_fn.assert_not_called()
        g.timeout_manager.record_block.assert_not_called()

    def test_medium_confidence_releases(self):
        sig = CompletionSignal(completed=True, confidence="medium", signals=["I:next_season"])
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is False

    def test_not_completed_blocks_with_p_and_j(self):
        """未完结 → 否决 + P + J 计时。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is True
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()

    def test_l_signal_reports_target_satisfied(self):
        """L 信号按主程序缺集查询确认当前目标范围已无待下载集，不要求 finale。"""
        subscribe = _sub()
        ev = _event(subscribe=subscribe)
        mediainfo = ev.event_data.mediainfo
        episodes = [_ep(i) for i in range(1, 13)]
        scope = build_scope(subscribe, mediainfo, lambda *_args, **_kwargs: episodes)
        resolve_missing = MagicMock(return_value=(True, {}))

        signal = check_l_signal(
            subscribe,
            scope,
            mediainfo=mediainfo,
            meta=ev.event_data.meta,
            resolve_missing_fn=resolve_missing,
        )

        assert signal.completed is True
        assert signal.confidence == "low"
        assert signal.signals == ["L:target_satisfied"]
        assert signal.scope_total == 12
        resolve_missing.assert_called_once_with(
            subscribe=subscribe,
            meta=ev.event_data.meta,
            mediainfo=mediainfo,
            best_version_accept_downloaded=False,
        )

    def test_l_signal_not_emitted_when_missing_resolver_reports_gap(self):
        """主程序缺集查询仍有剩余目标时不生成 L 信号。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        ev = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe,
            ev.event_data.mediainfo,
            lambda *_args, **_kwargs: [_ep(i) for i in range(1, 13)],
        )
        resolve_missing = MagicMock(return_value=(False, {100: {1: SimpleNamespace(episodes=[12])}}))

        signal = check_l_signal(
            subscribe,
            scope,
            mediainfo=ev.event_data.mediainfo,
            meta=ev.event_data.meta,
            resolve_missing_fn=resolve_missing,
        )

        assert signal is None
        resolve_missing.assert_called_once()

    def test_l_signal_uses_subscribe_total_when_scope_is_temporarily_empty(self):
        """TMDB 集列表暂不可用时，L 使用订阅目标总数参与模式判断。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        ev = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe, ev.event_data.mediainfo,
            lambda *_args, **_kwargs: [],
        )
        resolve_missing = MagicMock(return_value=(True, {}))

        signal = check_l_signal(
            subscribe,
            scope,
            mediainfo=ev.event_data.mediainfo,
            meta=ev.event_data.meta,
            resolve_missing_fn=resolve_missing,
        )

        assert signal.scope_total == 12

    def test_l_signal_not_emitted_when_target_range_is_unknown(self):
        """订阅总集数未知时不能把空目标范围误判为已经全部下载。"""
        subscribe = _sub()
        subscribe.total_episode = 0
        ev = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe,
            ev.event_data.mediainfo,
            lambda *_args, **_kwargs: [],
        )
        resolve_missing = MagicMock(return_value=(True, {}))

        assert check_l_signal(
            subscribe,
            scope,
            mediainfo=ev.event_data.mediainfo,
            meta=ev.event_data.meta,
            resolve_missing_fn=resolve_missing,
        ) is None
        resolve_missing.assert_not_called()

    def test_balanced_local_targets_covered_allows_completion(self):
        """平衡模式下三集及以上的 L 信号直接放行。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="balanced")
        g.detect_existing_episodes_fn.return_value = list(range(1, 13))
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        ev = _event()
        ev.event_data.subscribe.note = list(range(1, 13))

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.mark_pending_fn.assert_not_called()
        g.timeout_manager.record_block.assert_not_called()

    def test_l_signal_uses_main_missing_resolver_for_existing_library_plus_new_downloads(self):
        """L 信号应复用主程序缺集合并口径，避免只看 note 漏掉订阅前已在库集。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 21)]
        subscribe = _sub()
        subscribe.total_episode = 20
        subscribe.note = list(range(11, 21))
        ev = _event(subscribe=subscribe)

        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.resolve_missing_fn.assert_called_once_with(
            subscribe=subscribe,
            meta=ev.event_data.meta,
            mediainfo=ev.event_data.mediainfo,
            best_version_accept_downloaded=False,
        )
        g.mark_pending_fn.assert_not_called()
        g.timeout_manager.record_block.assert_not_called()

    def test_l_signal_uses_missing_resolver_when_meta_is_absent(self):
        """CompletionCheck 未携带 meta 时仍应走主程序目标缺集口径。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        ev = _event(subscribe=subscribe)
        ev.event_data.meta = None
        g.resolve_missing_fn = MagicMock(return_value=(False, {100: {1: SimpleNamespace(episodes=[12])}}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "无信号"
        g.resolve_missing_fn.assert_called_once()
        _, kwargs = g.resolve_missing_fn.call_args
        assert kwargs["subscribe"] is subscribe
        assert kwargs["meta"].begin_season == 1
        assert kwargs["mediainfo"] is ev.event_data.mediainfo
        assert kwargs["best_version_accept_downloaded"] is False
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()

    def test_check_l_signal_without_resolver_fails_closed(self):
        """L 信号缺少主程序缺集查询入口时不自行创建订阅链。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        ev = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe,
            ev.event_data.mediainfo,
            lambda *_args, **_kwargs: [_ep(i) for i in range(1, 13)],
        )

        with patch("subscribeassistantenhanced.engine.local.SubscribeChain", create=True) as chain_cls:
            chain_cls.return_value.resolve_subscribe_missing.return_value = (True, {})
            signal = check_l_signal(
                subscribe,
                scope,
                mediainfo=ev.event_data.mediainfo,
                meta=None,
            )

        assert signal is None
        chain_cls.assert_not_called()

    def test_check_l_signal_preserves_special_season_when_building_meta(self):
        """特别季 S0 是合法订阅目标，构造主程序 MetaInfo 时不能按未指定季处理。"""
        subscribe = _sub()
        subscribe.season = 0
        subscribe.note = list(range(1, 13))
        ev = _event(subscribe=subscribe)
        scope = build_scope(
            subscribe,
            ev.event_data.mediainfo,
            lambda *_args, **_kwargs: [_ep(i, season=0) for i in range(1, 13)],
        )
        resolve_missing = MagicMock(return_value=(True, {}))

        signal = check_l_signal(
            subscribe,
            scope,
            mediainfo=ev.event_data.mediainfo,
            meta=None,
            resolve_missing_fn=resolve_missing,
        )

        assert signal is not None
        _, kwargs = resolve_missing.call_args
        assert kwargs["meta"].begin_season == 0

    def test_full_best_version_skips_completion_signal_after_pending_check(self):
        """全集洗版不由完成守卫裁决，下载中保护通过后直接交还主程序洗版链路。"""
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"], reason="变动")
        g = _guard(signal=sig, mode="balanced")
        subscribe = _sub(best_version=1, best_version_full=1)
        ev = _event(subscribe=subscribe)

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.evaluate_fn.assert_not_called()
        g.resolve_missing_fn.assert_not_called()
        g.mark_pending_fn.assert_not_called()

    def test_full_best_version_active_download_blocks_before_skip(self):
        """全集洗版仍先检查下载中待定，避免资源已选中但尚未入库时结束订阅。"""
        g = _guard(has_active=True)
        ev = _event(subscribe=_sub(best_version=1, best_version_full=1))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert "下载" in ev.event_data.reason
        g.evaluate_fn.assert_not_called()

    def test_local_coverage_does_not_complete_when_future_episode_outside_target_range(self):
        """聚合下一集缺失但 SeasonScope 目标范围外已有后续播出日期时，L 信号不得提前完成订阅。"""
        g = _guard(mode="balanced")
        g.detect_missing_episodes_fn.return_value = []
        future_air_date = (date.today() + timedelta(days=30)).isoformat()
        g.tmdb_episodes_fn.return_value = [
            *[_ep(i, air_date="2026-01-01") for i in range(1, 88)],
            _ep(88, air_date=future_air_date),
        ]
        subscribe = _sub()
        subscribe.total_episode = 87
        subscribe.note = list(range(1, 88))
        mediainfo = _event().event_data.mediainfo
        mediainfo.tmdb_info.next_episode_to_air = None

        signal = g._local_signal(subscribe, mediainfo)

        assert signal is None
        g.resolve_missing_fn.assert_not_called()

    def test_local_signal_blocks_scope_future_outside_target_even_without_aggregate(self):
        """聚合下一集缺失时，L 信号仍由 SeasonScope 目标范围外后续集阻断。"""
        g = _guard(mode="balanced")
        future_air_date = (date.today() + timedelta(days=30)).isoformat()
        g.tmdb_episodes_fn.return_value = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=future_air_date),
        ]
        subscribe = _sub()
        subscribe.total_episode = 1
        subscribe.note = [1]
        mediainfo = _event(subscribe=subscribe).event_data.mediainfo
        mediainfo.tmdb_info.next_episode_to_air = None
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        signal = g._local_signal(subscribe, mediainfo)

        assert signal is None
        g.resolve_missing_fn.assert_not_called()

    def test_local_signal_allows_future_inside_completed_target_range(self):
        """超前点播已覆盖当前订阅目标范围时，目标内后续播出日期不阻断 L 信号。"""
        g = _guard(mode="balanced")
        future_air_date = (date.today() + timedelta(days=30)).isoformat()
        g.tmdb_episodes_fn.return_value = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=future_air_date),
        ]
        subscribe = _sub()
        subscribe.total_episode = 2
        subscribe.note = [1, 2]
        mediainfo = _event(subscribe=subscribe).event_data.mediainfo
        mediainfo.tmdb_info.next_episode_to_air = None
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        signal = g._local_signal(subscribe, mediainfo)

        assert signal is not None
        assert signal.signals == ["L:target_satisfied"]
        g.resolve_missing_fn.assert_called_once()

    def test_local_signal_blocks_later_future_outside_target_range(self):
        """最早后续播出日期在目标内时，目标外后续集仍应阻断 L 信号。"""
        g = _guard(mode="balanced")
        inside_future_date = (date.today() + timedelta(days=10)).isoformat()
        outside_future_date = (date.today() + timedelta(days=30)).isoformat()
        g.tmdb_episodes_fn.return_value = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=inside_future_date),
            _ep(3, air_date=outside_future_date),
        ]
        subscribe = _sub()
        subscribe.total_episode = 2
        subscribe.note = [1, 2]
        mediainfo = _event(subscribe=subscribe).event_data.mediainfo
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        result = g._local_signal_result(subscribe, mediainfo)

        assert result.signal is None
        assert "E3" in result.blocked_reason
        g.resolve_missing_fn.assert_not_called()

    def test_unfinished_without_l_reports_main_missing_reason_to_user(self):
        """无完成信号且主程序缺集口径未满足时，用户可见原因应包含具体 L 失败原因。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号确认当前目标范围已播完")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        subscribe = _sub()
        subscribe.note = list(range(1, 12))
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(False, {100: {1: SimpleNamespace(episodes=[12])}}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "主程序缺集口径未满足，未命中 L"
        g.mark_pending_fn.assert_called_once_with(
            subscribe,
            source="guard_veto",
            reason=ev.event_data.reason,
        )

    def test_local_signal_ignores_aggregate_future_when_scope_has_no_future(self):
        """SeasonScope 无后续集时，聚合下一集不再阻断 L 放行。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i, air_date="2026-01-01") for i in range(1, 4)]
        subscribe = _sub()
        subscribe.total_episode = 3
        subscribe.note = [1, 2, 3]
        ev = _event(subscribe=subscribe)
        ev.event_data.mediainfo.tmdb_info.next_episode_to_air = SimpleNamespace(
            season_number=1, episode_number=4, air_date="2026-02-01",
        )
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.mark_pending_fn.assert_not_called()

    def test_local_signal_blocks_unknown_air_tail(self):
        """SeasonScope 后续集缺 air_date 时，L 信号不得确认目标满足。"""
        g = _guard(mode="balanced")
        g.tmdb_episodes_fn.return_value = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=None),
        ]
        subscribe = _sub()
        subscribe.total_episode = 1
        subscribe.note = [1]
        mediainfo = _event(subscribe=subscribe).event_data.mediainfo
        mediainfo.tmdb_info.next_episode_to_air = None
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        signal = g._local_signal(subscribe, mediainfo)

        assert signal is None
        g.resolve_missing_fn.assert_not_called()

    def test_unfinished_without_l_reports_specific_future_reason_to_user(self):
        """无完成信号且 L 被目标范围外后续集阻断时，用户可见原因应包含具体集号。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号确认当前目标范围已播完")
        g = _guard(signal=sig, mode="balanced")
        future_air_date = (date.today() + timedelta(days=30)).isoformat()
        g.tmdb_episodes_fn.return_value = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=future_air_date),
        ]
        subscribe = _sub()
        subscribe.total_episode = 1
        subscribe.note = [1]
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason.startswith("TMDB 已存在目标范围外的后续集")
        assert "E2" in ev.event_data.reason
        assert f"播出日期：{future_air_date}" in ev.event_data.reason
        g.mark_pending_fn.assert_called_once_with(
            subscribe,
            source="guard_veto",
            reason=ev.event_data.reason,
        )

    def test_unfinished_without_l_reports_unknown_tail_reason_to_user(self):
        """无完成信号且 L 被目标范围外未知播出日期后续集阻断时，用户可见原因应说明日期未知。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号确认当前目标范围已播完")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [
            _ep(1, air_date="2026-01-01"),
            _ep(2, air_date=None),
        ]
        subscribe = _sub()
        subscribe.total_episode = 1
        subscribe.note = [1]
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason.startswith("TMDB 已存在目标范围外的后续集")
        assert "E2，播出日期：未知" in ev.event_data.reason
        g.mark_pending_fn.assert_called_once_with(
            subscribe,
            source="guard_veto",
            reason=ev.event_data.reason,
        )

    def test_strict_local_targets_covered_enters_observation(self):
        """严格模式把 L 作为低置信信号进入观察。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig)
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        ev = _event()
        ev.event_data.subscribe.note = list(range(1, 13))

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "订阅目标范围已无待下载集"
        g.mark_pending_fn.assert_called_once()
        block = g.timeout_manager.record_block.call_args
        assert block.kwargs["signal"].signals == ["L:target_satisfied"]

    def test_balanced_two_episode_l_signal_enters_observation(self):
        """平衡模式保留一至两集短样本观察，避免镖人 S02 类提前完成。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="balanced")
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = [_ep(1), _ep(2)]
        ev = _event()
        ev.event_data.subscribe.total_episode = 2
        ev.event_data.subscribe.note = [1, 2]

        g.handle(ev)

        assert ev.event_data.cancel is True
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()

    def test_balanced_high_risk_l_signal_enters_observation(self):
        """平衡模式下高风险目标范围的 L 信号仍进入完成前观察。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 41)]
        subscribe = _sub()
        subscribe.total_episode = 40
        subscribe.note = list(range(1, 41))
        ev = _event(subscribe=subscribe)
        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is True
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()

    def test_loose_two_episode_l_signal_enters_observation(self):
        """宽松模式也不直接接受短样本 L 信号。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="loose")
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = [_ep(1), _ep(2)]
        ev = _event()
        ev.event_data.subscribe.total_episode = 2
        ev.event_data.subscribe.note = [1, 2]

        g.handle(ev)

        assert ev.event_data.cancel is True
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()

    def test_not_completed_local_targets_missing_still_blocks(self):
        """仍缺目标集时继续否决完成，避免只因主程序事件触发就放行。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig)
        g.detect_existing_episodes_fn.return_value = list(range(1, 11))
        g.detect_missing_episodes_fn.return_value = [11]
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 12)] + [_ep(12, ep_type="finale")]
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "无信号"
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()

    def test_balanced_low_confidence_long_scope_releases(self):
        """平衡模式立即接受三集及以上的低置信 I 信号。"""
        sig = CompletionSignal(
            completed=True, confidence="low", signals=["I:all_aired"],
            reason="全部已播", scope_total=26,
        )
        g = _guard(signal=sig, mode="balanced")
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.timeout_manager.consume_release.assert_not_called()

    def test_balanced_low_confidence_short_scope_enters_observation(self):
        """平衡模式的一至两集 I 信号继续进入观察。"""
        sig = CompletionSignal(
            completed=True, confidence="low", signals=["I:all_aired"],
            reason="全部已播", scope_total=2,
        )
        g = _guard(signal=sig, mode="balanced")
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is True
        g.timeout_manager.record_block.assert_called_once()

    def test_mid_season_blocks(self):
        """M 信号否决。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["M:mid_season"], reason="mid")
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is True

    def test_completion_check_reads_and_writes_event_data(self):
        """CompletionGuard 必须读写 event.event_data，并在否决完成时补齐 source。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无完结信号")
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "无完结信号"
        assert ev.event_data.source == "subscribeassistantenhanced"
        g.mark_pending_fn.assert_called_once()
