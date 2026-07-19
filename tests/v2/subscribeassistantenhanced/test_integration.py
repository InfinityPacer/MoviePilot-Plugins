"""端到端集成测试——验证完成证据流水线到守门到待定到暂停的完整链路。"""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.types import MediaType

from subscribeassistantenhanced.engine.pipeline import CompletionEvidencePipeline
from subscribeassistantenhanced.engine.volatility import VolatilityTracker
from subscribeassistantenhanced.engine.types import (
    CompletionEvidence,
    CompletionObservationDecision,
    CompletionSignal,
    SeasonScope,
)
from subscribeassistantenhanced.guard import CompletionGuard
from subscribeassistantenhanced.pending.judge import PendingJudge
from subscribeassistantenhanced.postcheck.timeout import PendingTimeoutManager
from subscribeassistantenhanced.postcheck.verifier import CompletionVerifier
from subscribeassistantenhanced.download.monitor import DownloadMonitor
from subscribeassistantenhanced.download.cleanup import TorrentCleanup
from subscribeassistantenhanced.pause.manager import PauseManager
from subscribeassistantenhanced.best_version.orchestrator import BestVersionOrchestrator
from subscribeassistantenhanced.shared.config import PluginConfig
from subscribeassistantenhanced.shared.task import TaskDataManager


def _ep(num, ep_type="standard", air_date="2026-01-01", season=1):
    return SimpleNamespace(
        episode_number=num, season_number=season,
        air_date=air_date, episode_type=ep_type, name=f"E{num}",
    )


def _mi(status="Returning Series", next_ep=None, last_ep=None, seasons=None):
    return SimpleNamespace(
        tmdb_id=100,
        tmdb_info=SimpleNamespace(
            status=status, next_episode_to_air=next_ep,
            last_episode_to_air=last_ep,
            seasons=seasons or [SimpleNamespace(season_number=1)],
        ),
    )


def _sub(sid=1, season=1, episode_group=None, best_version=0, state="R",
         total_episode=12, **kw):
    defaults = dict(
        id=sid, tmdbid=100, season=season, episode_group=episode_group,
        best_version=best_version, state=state, type="电视剧",
        name="测试剧", total_episode=total_episode, lack_episode=0,
        episode_priority={}, current_priority=0,
        start_episode=1, best_version_full=0,
        save_path=None, sites=None, filter=None, filter_groups=[],
        year=None, username="", date=None, last_update=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _store():
    d = {}
    return TaskDataManager(
        get_data_fn=lambda k: d.get(k),
        save_data_fn=lambda k, v: d.__setitem__(k, v),
    ), d


def _tracker(stable=True):
    tm, _ = _store()
    t = VolatilityTracker(tm, window_days=7)
    if not stable:
        subscribe = _sub()
        t.record(10, subscribe=subscribe)
        t.record(15, subscribe=subscribe)
    return t


def _cfg(**kw):
    return PluginConfig(kw)


def _tmdb_fn(episodes):
    return lambda *a, **k: episodes


def _primary(subscribe, mediainfo, tmdb_episodes_fn, volatility_tracker, config, as_of=None):
    pipeline = CompletionEvidencePipeline(
        tmdb_episodes_fn=tmdb_episodes_fn,
        volatility_tracker=volatility_tracker,
        config=config,
    )
    return pipeline.evaluate(subscribe, mediainfo, as_of=as_of).primary_signal


def _pipeline_for_signal(signal, **evidence_fields):
    evidence = CompletionEvidence(primary_signal=signal, scope_total=signal.scope_total)
    for key, value in evidence_fields.items():
        setattr(evidence, key, value)
    return SimpleNamespace(evaluate=MagicMock(return_value=evidence))


# ---------- 正常完成 ----------

class TestNormalCompletion:

    def test_ended_show_completes_immediately(self):
        eps = [_ep(i) for i in range(1, 13)]
        sig = _primary(_sub(), _mi(status="Ended"), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is True
        assert sig.confidence == "high"

    def test_returning_with_next_season_completes(self):
        eps = [_ep(i) for i in range(1, 13)]
        mi = _mi(seasons=[SimpleNamespace(season_number=1), SimpleNamespace(season_number=2)])
        sig = _primary(_sub(), mi, _tmdb_fn(eps), _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is True

    def test_returning_with_finale_as_last_ep(self):
        eps = [_ep(i) for i in range(1, 12)] + [_ep(12, ep_type="finale")]
        sig = _primary(_sub(), _mi(), _tmdb_fn(eps), _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is True
        assert "E:finale" in sig.signals


# ---------- 异常完成 ----------

class TestAbnormalCompletion:

    def test_volatile_total_blocks(self):
        eps = [_ep(1)]
        sig = _primary(_sub(), _mi(), _tmdb_fn(eps),
                       _tracker(stable=False), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is False
        assert sig.stable is False

    def test_mid_season_hard_veto(self):
        eps = [_ep(i) for i in range(1, 72)] + [_ep(72, ep_type="mid_season")]
        sig = _primary(_sub(), _mi(status="Ended"), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is False
        assert "M:mid_season" in sig.signals

    def test_high_risk_i3_not_release(self):
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 81)]
        sig = _primary(_sub(), _mi(), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is False
        assert sig.cadence_expired is True


# ---------- 绝对季 ----------

class TestAbsoluteSeason:

    def test_rezero_mid_finale_not_complete_main(self):
        """Re:ZERO 主 S1 (85集) E66 有 finale 但不是末集 → 不放行。"""
        eps = [_ep(i) for i in range(1, 86)]
        eps[65] = _ep(66, ep_type="finale")
        sig = _primary(_sub(), _mi(), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is False

    def test_rezero_group_season3_finale(self):
        """Re:ZERO Group S3 (E51-E66), E66=末集 finale → 放行。"""
        eps = [_ep(i) for i in range(51, 67)]
        eps[-1] = _ep(66, ep_type="finale")
        sig = _primary(_sub(episode_group="eg-s3"), _mi(), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is True

    def test_rezero_group_s4_mid_season_blocks(self):
        """Re:ZERO Group S4 E77 mid_season → 否决。"""
        eps = [_ep(i) for i in range(67, 78)]
        eps[-1] = _ep(77, ep_type="mid_season")
        sig = _primary(_sub(episode_group="eg-s4"), _mi(), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is False
        assert "M:mid_season" in sig.signals

    def test_rezero_group_s4_finale(self):
        """Re:ZERO Group S4 E85 finale 是末集 → 放行。"""
        eps = [_ep(i) for i in range(67, 86)]
        eps[-1] = _ep(85, ep_type="finale")
        sig = _primary(_sub(episode_group="eg-s4"), _mi(), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is True

    def test_fanren_mid_season_veto(self):
        """凡人修仙传 E72 mid_season。"""
        eps = [_ep(i) for i in range(1, 73)]
        eps[-1] = _ep(72, ep_type="mid_season")
        sig = _primary(_sub(), _mi(), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is False

    def test_fanren_standard_hiatus_high_risk(self):
        """凡人修仙传 E152 standard + high_risk → 不完成。"""
        eps = [_ep(i, air_date="2026-01-01") for i in range(1, 153)]
        sig = _primary(_sub(), _mi(), _tmdb_fn(eps),
                       _tracker(), _cfg(), as_of=date(2026, 6, 1))
        assert sig.completed is False


# ---------- 洗版 ----------

class TestBestVersionFlow:

    def test_episode_best_version_uses_normal_tv_completion_guard(self):
        """分集洗版与普通剧集订阅共用完成守卫策略。"""
        sig = CompletionSignal(
            completed=True,
            confidence="low",
            stable=True,
            signals=["L:target_satisfied"],
            reason="订阅目标范围已无待下载集",
            scope_total=2,
        )
        guard = CompletionGuard.__new__(CompletionGuard)
        guard.evidence_pipeline = _pipeline_for_signal(sig, local_signal=sig)
        guard.has_active_downloads_fn = MagicMock(return_value=False)
        guard.mark_pending_fn = MagicMock()
        guard.verifier = MagicMock()
        guard.timeout_manager = MagicMock()
        guard.timeout_manager.consume_release_token.return_value = False
        guard.pending_download_enabled = True
        guard.mode = "strict"
        guard.resolve_missing_fn = MagicMock(return_value=(True, {}))
        ev = SimpleNamespace(event_data=SimpleNamespace(subscribe=_sub(best_version=1, note=[1, 2], total_episode=2), mediainfo=_mi(),
                             meta=SimpleNamespace(type=MediaType.TV, begin_season=1, season=1),
                             cancel=False, reason="", source=""))
        guard.handle(ev)
        assert ev.event_data.cancel is True
        assert ev.event_data.reason == "订阅目标范围已无待下载集"
        guard.mark_pending_fn.assert_called_once()

    def test_payload_preserves_episode_group(self):
        orch = BestVersionOrchestrator(
            priority_manager=MagicMock(),
        )
        payload = orch.build_payload(_sub(episode_group="eg-1"))
        assert payload["episode_group"] == "eg-1"


# ---------- P 来源分治 ----------

class TestPendingSourceSplit:

    def test_guard_veto_stays_until_signal(self):
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        tm = TaskDataManager(
            get_data_fn=lambda k: store.get(k, {}),
            save_data_fn=lambda k, v: store.__setitem__(k, v),
        )
        sig = CompletionSignal(completed=False, stable=True)
        judge = PendingJudge.__new__(PendingJudge)
        judge._config = _cfg()
        judge._evidence_pipeline = _pipeline_for_signal(sig)
        judge._resolve_missing_fn = None
        judge._subscribe_oper = MagicMock()
        judge._timeout = MagicMock()
        judge._timeout.check_observation.return_value = CompletionObservationDecision.hold("继续观察")
        judge._read = tm.read
        judge._update = tm.update
        judge._state = MagicMock()
        result = judge.check_exit(_sub(state="P"), _mi(), lambda *a: [])
        assert result is False

    def test_guard_veto_released_by_j(self):
        tm, store = _store()
        timeout = PendingTimeoutManager(tm.read, tm.update, timeout_days=21)
        timeout.record_observation(1)
        store["blocks"]["1"]["blocked_at"] -= 25 * 86400
        sig = CompletionSignal(stable=True, cadence_expired=False)
        evidence = CompletionEvidence(primary_signal=sig, observation_kind="none")
        assert timeout.check_observation(1, evidence, mode="balanced").action == "release_guard"


# ---------- 下载待定 ----------

class TestDownloadPending:

    def test_active_download_blocks_no_p(self):
        guard = CompletionGuard.__new__(CompletionGuard)
        guard.evidence_pipeline = SimpleNamespace(evaluate=MagicMock())
        guard.has_active_downloads_fn = MagicMock(return_value=True)
        guard.mark_pending_fn = MagicMock()
        guard.verifier = MagicMock()
        guard.timeout_manager = MagicMock()
        guard.pending_download_enabled = True
        ev = SimpleNamespace(event_data=SimpleNamespace(subscribe=_sub(), mediainfo=_mi(),
                             meta=SimpleNamespace(type=MediaType.TV, begin_season=1, season=1),
                             cancel=False, reason="", source=""))
        guard.handle(ev)
        assert ev.event_data.cancel is True
        guard.mark_pending_fn.assert_not_called()
        guard.timeout_manager.record_observation.assert_not_called()

    def test_no_p_no_j_on_download_block(self):
        guard = CompletionGuard.__new__(CompletionGuard)
        guard.evidence_pipeline = SimpleNamespace(evaluate=MagicMock())
        guard.has_active_downloads_fn = MagicMock(return_value=True)
        guard.mark_pending_fn = MagicMock()
        guard.verifier = MagicMock()
        guard.timeout_manager = MagicMock()
        guard.pending_download_enabled = True
        ev = SimpleNamespace(event_data=SimpleNamespace(subscribe=_sub(), mediainfo=_mi(),
                             meta=SimpleNamespace(type=MediaType.TV, begin_season=1, season=1),
                             cancel=False, reason="", source=""))
        guard.handle(ev)
        guard.mark_pending_fn.assert_not_called()
        guard.timeout_manager.record_observation.assert_not_called()

    def test_transfer_clears_then_recheck(self):
        tm, store = _store()
        monitor = DownloadMonitor(tm.read, tm.update)
        monitor.mark_download_pending(1, "hash1")
        assert monitor.has_active_downloads(1) is True
        monitor.clear_download_pending(1, "hash1")
        assert monitor.has_active_downloads(1) is False


# ---------- H 验证 ----------

class TestHVerifier:

    def test_scope_aware_verification(self):
        tm, store = _store()
        rebuild = MagicMock(return_value=True)
        verifier = CompletionVerifier(
            tm.read, tm.update,
            tmdb_episodes_fn=lambda *a, **kw: [object()] * 15 if kw.get("episode_group") == "eg-1"
                else [object()] * 85,
            subscribe_oper=MagicMock(list=MagicMock(return_value=[])),
            rebuild_subscribe_fn=rebuild,
        )
        sub = _sub(episode_group="eg-1", total_episode=12)
        verifier.snapshot(sub, None, SeasonScope(source="episode_group"))
        verifier.verify_all()
        rebuild.assert_called_once()

    def test_rebuild_deletes_bv(self):
        tm, store = _store()
        oper = MagicMock()
        bv = SimpleNamespace(
            id=99, tmdbid=100, season=1, episode_group=None,
            type="电视剧", best_version=1, best_version_full=1,
            total_episode=12,
            name="测试剧", save_path=None, sites=None, filter=None, filter_groups=[],
        )
        oper.list.return_value = [bv]
        verifier = CompletionVerifier(
            tm.read, tm.update,
            tmdb_episodes_fn=lambda *a, **kw: [object()] * 15,
            subscribe_oper=oper,
            rebuild_subscribe_fn=MagicMock(return_value=True),
        )
        verifier.snapshot(_sub(total_episode=12), None, SeasonScope(source="main_season"))
        verifier.verify_all()
        oper.delete.assert_called_once_with(99)


# ---------- Codex Review FAIL 修复验证 ----------

class TestCodexReviewFindings:

    def test_manual_review_reachable(self):
        """MANUAL_REVIEW 状态可达：范围级低进度计数达到上限后保留种子。"""
        tm, store = _store()
        import time
        store["torrents"] = {
            "h1": {
                "baseline_progress": 0.5,
                "baseline_at": time.time() - 7200,
                "subscribe_id": 1,
                "episodes": [1],
            },
        }
        store["subscribes"] = {"1": {"timeout_states": {
            "movie": {"fail_count": 2, "window_start": time.time() - 60},
        }}}
        monitor = DownloadMonitor(tm.read, tm.update, timeout_minutes=60, retry_limit=3)
        from subscribeassistantenhanced.download.torrent import TorrentInfo
        info = TorrentInfo(hash="h1", progress=0.5)

        result = monitor.check_torrent(info, subscribe_id=1)
        assert result == "manual_review"
        state = store["subscribes"]["1"]["timeout_states"]["movie"]
        assert state["fail_count"] == 3
        assert state["ignore_until"] > time.time()

    def test_cleanup_call_order(self):
        """删除后恢复调用顺序：rollback → clean → clear_pending；不暂停订阅。"""
        calls = []
        priority = MagicMock()
        priority.rollback.side_effect = lambda *a, **kw: calls.append("rollback")
        clear_fn = MagicMock(side_effect=lambda *a, **kw: calls.append("clear_pending"))

        tm, store = _store()
        cleanup = TorrentCleanup(
            priority_manager=priority,
            clear_download_pending_fn=clear_fn,
            task_data_update=tm.update,
        )
        sub = _sub(best_version=1)
        cleanup.handle_torrent_deleted(sub, "hash1")

        assert calls == ["rollback", "clear_pending"]
