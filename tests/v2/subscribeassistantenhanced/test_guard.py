"""guard.py 完成守卫单测。"""
from types import SimpleNamespace
from datetime import date
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType

from subscribeassistantenhanced.guard import CompletionGuard
from subscribeassistantenhanced.engine.types import CompletionSignal


def _ep(num, ep_type="standard", air_date="2026-01-01", season=1):
    """构造 TMDB 集对象替身。"""
    return SimpleNamespace(
        episode_number=num,
        season_number=season,
        air_date=air_date,
        episode_type=ep_type,
        name=f"E{num}",
    )


def _sub(sid=1, stype="电视剧", best_version=0, state="R"):
    return SimpleNamespace(
        id=sid, name="测试剧", tmdbid=100, season=1,
        episode_group=None, type=stype, state=state,
        best_version=best_version, total_episode=12, lack_episode=0,
    )


def _event(subscribe=None, mediainfo=None):
    """链式事件 wrapper：CompletionCheck 业务字段固定放在 event.event_data（对齐主程序投递）。"""
    data = SimpleNamespace(
        subscribe=subscribe or _sub(),
        mediainfo=mediainfo or SimpleNamespace(tmdb_id=100, tmdb_info=SimpleNamespace(
            status="Returning Series", next_episode_to_air=None,
            last_episode_to_air=None, seasons=[],
        )),
        cancel=False, reason="", source="",
    )
    return SimpleNamespace(event_data=data)


def _guard(signal=None, has_active=False):
    """构造 CompletionGuard，mock 依赖。"""
    g = CompletionGuard.__new__(CompletionGuard)
    g.evaluate_fn = MagicMock(return_value=signal or CompletionSignal())
    g.has_active_downloads_fn = MagicMock(return_value=has_active)
    g.detect_existing_episodes_fn = MagicMock(return_value=None)
    g.detect_missing_episodes_fn = MagicMock(return_value=None)
    g.tmdb_episodes_fn = MagicMock(return_value=[])
    g.pending_download_enabled = True
    g.mark_pending_fn = MagicMock()
    g.verifier = MagicMock()
    g.timeout_manager = MagicMock()
    g.timeout_manager.consume_release.return_value = False
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

    def test_high_confidence_releases_no_snapshot(self):
        """高置信度放行，不加 H 快照。"""
        sig = CompletionSignal(completed=True, confidence="high", signals=["E:ended"])
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is False
        g.verifier.snapshot.assert_not_called()

    def test_low_confidence_with_release_token_snapshots(self):
        """低置信观察已释放时才放行并登记 H 快照。"""
        sig = CompletionSignal(completed=True, confidence="low", signals=["I:all_aired"])
        g = _guard(signal=sig)
        g.timeout_manager.consume_release.return_value = True
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is False
        g.verifier.snapshot.assert_called_once()

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
            1,
            signal=sig,
            total_episode=12,
        )
        g.verifier.snapshot.assert_not_called()

    def test_low_confidence_completion_after_observation_release_snapshots(self):
        """低置信观察释放后，同一轮信号允许完成并登记 H 快照。"""
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
        g.verifier.snapshot.assert_called_once()

    def test_medium_confidence_releases_with_snapshot(self):
        sig = CompletionSignal(completed=True, confidence="medium", signals=["I:next_season"])
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is False
        g.verifier.snapshot.assert_called_once()

    def test_not_completed_blocks_with_p_and_j(self):
        """未完结 → 否决 + P + J 计时。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is True
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()

    def test_not_completed_local_targets_and_finale_covered_allows_completion_snapshot(self):
        """目标集全覆盖且 finale 已入库时，允许提前点播完成写入快照。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig)
        g.detect_existing_episodes_fn.return_value = list(range(1, 13))
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 12)] + [_ep(12, ep_type="finale")]
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is False
        g.mark_pending_fn.assert_not_called()
        g.timeout_manager.record_block.assert_not_called()
        g.verifier.snapshot.assert_called_once_with(ev.event_data.subscribe, ev.event_data.mediainfo, None)

    def test_not_completed_local_targets_covered_without_finale_still_blocks(self):
        """只满足订阅目标集不足以放行，必须确认目标范围 finale 集也在本地。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig)
        g.detect_existing_episodes_fn.return_value = list(range(1, 12))
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 12)] + [_ep(12, ep_type="finale")]
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "无信号"
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()
        g.verifier.snapshot.assert_not_called()

    def test_not_completed_local_targets_covered_without_scope_finale_still_blocks(self):
        """TMDB 未给出明确 finale 时，不用本地覆盖推断整季完结。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig)
        g.detect_existing_episodes_fn.return_value = list(range(1, 13))
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = [_ep(i) for i in range(1, 13)]
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "无信号"
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()
        g.verifier.snapshot.assert_not_called()

    def test_not_completed_local_targets_covered_with_multiple_finales_still_blocks(self):
        """TMDB 同范围多 finale 时不做本地完成兜底，避免把异常排期当作可靠大结局。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无信号")
        g = _guard(signal=sig)
        g.detect_existing_episodes_fn.return_value = list(range(1, 13))
        g.detect_missing_episodes_fn.return_value = []
        g.tmdb_episodes_fn.return_value = (
            [_ep(i) for i in range(1, 6)]
            + [_ep(6, ep_type="finale")]
            + [_ep(i) for i in range(7, 12)]
            + [_ep(12, ep_type="finale")]
        )
        ev = _event()

        g.handle(ev)

        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "无信号"
        g.mark_pending_fn.assert_called_once()
        g.timeout_manager.record_block.assert_called_once()
        g.verifier.snapshot.assert_not_called()

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
        g.verifier.snapshot.assert_not_called()

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
        """CompletionGuard 必须读写 event.event_data，并补齐 source（原实现漏写）。"""
        sig = CompletionSignal(completed=False, stable=True, signals=["none"], reason="无完结信号")
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "无完结信号"
        assert ev.event_data.source == "subscribeassistantenhanced"
        g.mark_pending_fn.assert_called_once()
