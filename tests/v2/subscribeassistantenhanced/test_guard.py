"""guard.py 完成守卫单测。"""
from types import SimpleNamespace
from datetime import date
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

    def test_unstable_signal_still_blocks_short_l_target_satisfied(self):
        """F 不稳定时，一至两集低可信 L 仍不能直接完成。"""
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
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_not_called()

    def test_unstable_total_shrink_blocks_l_target_satisfied(self):
        """近期 total 缩小时，可信 L 也不能绕过 F 的低估风险。"""
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
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_not_called()

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
            reason="目标范围内所有集已播且无同季下一集",
        )
        g = _guard(signal=sig)
        g.timeout_manager.consume_release.return_value = False
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "目标范围内所有集已播且无同季下一集"
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
            reason="目标范围内所有集已播且无同季下一集",
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
        """L 信号按 note 确认当前目标范围已无待下载集，不要求 finale。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        mediainfo = _event().event_data.mediainfo
        episodes = [_ep(i) for i in range(1, 13)]
        scope = build_scope(subscribe, mediainfo, lambda *_args, **_kwargs: episodes)

        signal = check_l_signal(subscribe, scope)

        assert signal.completed is True
        assert signal.confidence == "low"
        assert signal.signals == ["L:target_satisfied"]
        assert signal.scope_total == 12

    def test_l_signal_uses_note_when_downloaded_episode_was_deleted(self):
        """普通订阅已下载集由 note 认定覆盖，不因媒体库文件后来删除而重新变成待下载。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        scope = build_scope(
            subscribe,
            _event().event_data.mediainfo,
            lambda *_args, **_kwargs: [_ep(i) for i in range(1, 13)],
        )

        signal = check_l_signal(subscribe, scope)

        assert signal is not None
        assert signal.completed is True

    def test_l_signal_uses_subscribe_total_when_scope_is_temporarily_empty(self):
        """TMDB 集列表暂不可用时，L 使用订阅目标总数参与模式判断。"""
        subscribe = _sub()
        subscribe.note = list(range(1, 13))
        scope = build_scope(
            subscribe, _event().event_data.mediainfo,
            lambda *_args, **_kwargs: [],
        )

        signal = check_l_signal(subscribe, scope)

        assert signal.scope_total == 12

    def test_l_signal_not_emitted_when_target_range_is_unknown(self):
        """订阅总集数未知时不能把空目标范围误判为已经全部下载。"""
        subscribe = _sub()
        subscribe.total_episode = 0
        scope = build_scope(
            subscribe,
            _event().event_data.mediainfo,
            lambda *_args, **_kwargs: [],
        )

        assert check_l_signal(subscribe, scope) is None

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

    def test_episode_best_version_stable_completion_still_only_blocks_f(self):
        """分集洗版稳定时完成守卫只挡 F，不用低置信 L 反向取消完成。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="strict")
        g.tmdb_episodes_fn.return_value = [_ep(1), _ep(2)]
        subscribe = _sub(best_version=1, best_version_full=0)
        subscribe.total_episode = 2
        subscribe.note = [1, 2]
        ev = _event(subscribe=subscribe)

        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.resolve_missing_fn.assert_not_called()
        g.mark_pending_fn.assert_not_called()
        g.timeout_manager.record_block.assert_not_called()

    def test_full_best_version_l_signal_does_not_accept_any_downloaded_version(self):
        """全集洗版仍按整季洗版处理，不能使用任意版本已下载即满足的 L 口径。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig, mode="balanced")
        g.tmdb_episodes_fn.return_value = [_ep(1), _ep(2), _ep(3)]
        subscribe = _sub(best_version=1, best_version_full=1)
        subscribe.total_episode = 3
        subscribe.note = [1, 2, 3]
        ev = _event(subscribe=subscribe)

        g.resolve_missing_fn = MagicMock(return_value=(True, {}))

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.resolve_missing_fn.assert_not_called()

    def test_local_coverage_does_not_complete_when_scope_has_future_episode(self):
        """聚合下一集缺失但 SeasonScope 已有未来集时，L 信号不得提前完成订阅。"""
        g = _guard(mode="balanced")
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = [
            *[_ep(i, air_date="2026-01-01") for i in range(1, 88)],
            _ep(88, air_date="2026-06-21"),
        ]
        subscribe = _sub()
        subscribe.total_episode = 87
        subscribe.note = list(range(1, 88))
        mediainfo = _event().event_data.mediainfo
        mediainfo.tmdb_info.next_episode_to_air = None

        signal = g._local_signal(subscribe, mediainfo)

        assert signal is None

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

    def test_best_version_only_checks_f(self):
        """洗版订阅只检查 F，不要求 E/I。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"])
        g = _guard(signal=sig)
        ev = _event(subscribe=_sub(best_version=1))
        g.handle(ev)
        assert ev.event_data.cancel is False  # stable=True → 洗版放行

    def test_best_version_blocked_when_unstable(self):
        """洗版订阅 F 不稳定 → 否决。"""
        sig = CompletionSignal(completed=False, stable=False, signals=["F:unstable"])
        g = _guard(signal=sig)
        ev = _event(subscribe=_sub(best_version=1))
        g.handle(ev)
        assert ev.event_data.cancel is True

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
