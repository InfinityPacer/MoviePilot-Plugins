"""pending/refresh.py EpisodesRefresh 观察单测。"""
from types import SimpleNamespace

from subscribeassistantenhanced.pending.refresh import PendingRefresh


def _event(subscribe_id=1, current_total=12, season=1, mediainfo=None):
    return SimpleNamespace(
        subscribe_id=subscribe_id,
        current_total_episode=current_total,
        season=season,
        mediainfo=mediainfo or SimpleNamespace(season_info=[], tmdb_info={}),
        total_episode=None,
        updated=False,
        source="main",
        reason="keep",
    )


class TestPendingRefresh:

    def test_observer_preserves_refresh_event(self):
        """P 状态只保护生命周期，不覆盖主程序计算出的 total。"""
        refresh = PendingRefresh()
        event = _event(current_total=12)

        refresh.handle_refresh(event)

        assert event.updated is False
        assert event.total_episode is None
        assert event.source == "main"
        assert event.reason == "keep"

    def test_observer_does_not_keep_legacy_override_dependencies(self):
        """待定刷新观察器不再保留旧集数覆盖依赖。"""
        refresh = PendingRefresh()

        assert vars(refresh) == {}
