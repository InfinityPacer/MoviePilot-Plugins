"""engine/types.py 数据类型与协议桩单测。"""
from subscribeassistantenhanced.engine.types import (
    CompletionSignal,
    SeasonScope,
    PauseRecord,
    CompletionVerifierProtocol,
    PendingTimeoutManagerProtocol,
    PriorityManagerProtocol,
)


class CompletionSignalTest:
    """CompletionSignal 默认值与构造。"""

    def test_defaults(self):
        sig = CompletionSignal()
        assert sig.completed is False
        assert sig.confidence == "none"
        assert sig.stable is True
        assert sig.cadence_expired is False
        assert sig.signals == []
        assert sig.reason == ""

    def test_custom_construction(self):
        sig = CompletionSignal(
            completed=True,
            confidence="high",
            stable=False,
            cadence_expired=True,
            signals=["finale_aired"],
            reason="finale detected",
        )
        assert sig.completed is True
        assert sig.confidence == "high"
        assert sig.stable is False
        assert sig.cadence_expired is True
        assert sig.signals == ["finale_aired"]
        assert sig.reason == "finale detected"

    def test_signals_list_independence(self):
        """不同实例的 signals 列表互不影响。"""
        a = CompletionSignal()
        b = CompletionSignal()
        a.signals.append("x")
        assert b.signals == []

    def test_partial_override(self):
        sig = CompletionSignal(completed=True, reason="partial")
        assert sig.completed is True
        assert sig.confidence == "none"
        assert sig.reason == "partial"


class SeasonScopeTest:
    """SeasonScope 默认值与构造。"""

    def test_defaults(self):
        scope = SeasonScope()
        assert scope.tmdbid == 0
        assert scope.season == 0
        assert scope.episode_group_id is None
        assert scope.episodes == []
        assert scope.total == 0
        assert scope.source == "main_season"
        assert scope.high_risk is False

    def test_custom_construction(self):
        scope = SeasonScope(
            tmdbid=12345,
            season=2,
            episode_group_id="eg-abc",
            episodes=[1, 2, 3],
            total=12,
            source="episode_group",
            high_risk=True,
        )
        assert scope.tmdbid == 12345
        assert scope.season == 2
        assert scope.episode_group_id == "eg-abc"
        assert scope.episodes == [1, 2, 3]
        assert scope.total == 12
        assert scope.source == "episode_group"
        assert scope.high_risk is True

    def test_episodes_list_independence(self):
        a = SeasonScope()
        b = SeasonScope()
        a.episodes.append(1)
        assert b.episodes == []


class PauseRecordTest:
    """PauseRecord 默认值与构造。"""

    def test_defaults(self):
        rec = PauseRecord()
        assert rec.reason == ""
        assert rec.since == 0.0
        assert rec.detail == ""

    def test_custom_construction(self):
        rec = PauseRecord(reason="airing_gap", since=1700000000.0, detail="gap=14d")
        assert rec.reason == "airing_gap"
        assert rec.since == 1700000000.0
        assert rec.detail == "gap=14d"


class ProtocolStubTest:
    """协议桩 runtime_checkable 验证。"""

    def test_completion_verifier_protocol_checkable(self):
        class Dummy:
            def snapshot(self, subscribe, mediainfo, scope):
                pass

        assert isinstance(Dummy(), CompletionVerifierProtocol)

    def test_pending_timeout_manager_protocol_checkable(self):
        class Dummy:
            def record_block(self, subscribe_id, signal=None, total_episode=None):
                pass

            def clear_block(self, subscribe_id):
                pass

            def check_release(self, subscribe_id, signal, total_episode=None):
                return False

            def consume_release(self, subscribe_id, signal, total_episode=None):
                return False

        assert isinstance(Dummy(), PendingTimeoutManagerProtocol)

    def test_priority_manager_protocol_checkable(self):
        class Dummy:
            def capture_baseline(self, subscribe, torrent_priority):
                return {}

            def update_on_download(self, subscribe, episodes, new_priority):
                pass

            def rollback(self, subscribe, baseline):
                pass

            def can_backfill(self, subscribe):
                return False

            def backfill_existing(self, subscribe, existing_episodes):
                return False

            def is_complete(self, subscribe):
                return False

            def mark_complete(self, subscribe):
                pass

        assert isinstance(Dummy(), PriorityManagerProtocol)
