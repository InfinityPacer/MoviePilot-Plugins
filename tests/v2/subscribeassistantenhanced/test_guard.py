"""guard.py 完成守卫单测。"""
from types import SimpleNamespace
from datetime import date
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType

from subscribeassistantenhanced.guard import CompletionGuard
from subscribeassistantenhanced.engine.types import CompletionSignal


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
    g.pending_download_enabled = True
    g.mark_pending_fn = MagicMock()
    g.verifier = MagicMock()
    g.timeout_manager = MagicMock()
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

    def test_low_confidence_releases_with_snapshot(self):
        """中/低置信度放行，加 H 快照。"""
        sig = CompletionSignal(completed=True, confidence="low", signals=["I:all_aired"])
        g = _guard(signal=sig)
        ev = _event()
        g.handle(ev)
        assert ev.event_data.cancel is False
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
