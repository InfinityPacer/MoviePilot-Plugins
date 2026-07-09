"""lifecycle/ 生命周期编排单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from subscribeassistantenhanced.engine.types import PauseRecord
from subscribeassistantenhanced.lifecycle import LifecycleResult, SubscribeLifecycleCoordinator


@pytest.fixture
def fake_lifecycle():
    """构造生命周期协调器所需的窄替身，避免初始化完整插件。"""
    calls = []

    pending_judge = MagicMock()

    def mark_pending(subscribe, source="pending_judge", reason=""):
        calls.append(f"mark_pending:{source}:{reason}")

    pending_judge.mark_pending.side_effect = mark_pending

    pending_state = MagicMock()
    pending_state.mark_active.side_effect = (
        lambda subscribe, source, reason="": calls.append(f"pending_state_mark:{source}:{reason}") or True
    )
    pending_state.clear_active.side_effect = (
        lambda subscribe, source, reason="": calls.append(f"pending_state_clear:{source}:{reason}") or True
    )
    pending_state.clear_all_owned.return_value = True
    pending_state.reconcile_orphaned.return_value = True
    pending_state.has_active.return_value = False

    pause_manager = MagicMock()
    pause_manager.check_auto_pause_for_user.return_value = False
    pause_manager.pause.return_value = True
    pause_manager.resume.return_value = True
    pause_manager.adopt_external.return_value = True
    pause_manager.get_pause_record.return_value = SimpleNamespace(reason="external")

    airing = MagicMock()
    airing.check_pre_air.return_value = None
    airing.check.return_value = None

    def tmdb_episodes_side_effect(_tmdbid, _season, episode_group=None):
        calls.append("episodes")
        return []

    tmdb_episodes = MagicMock(side_effect=tmdb_episodes_side_effect)
    recognize = MagicMock()
    clear_tasks_for_pause = MagicMock()
    subscribe_oper = MagicMock()

    coordinator = SubscribeLifecycleCoordinator(
        config=MagicMock(),
        subscribe_oper=subscribe_oper,
        pause_manager=pause_manager,
        pending_judge=pending_judge,
        pending_state=pending_state,
        airing_checker=airing,
        tmdb_episodes_fn=tmdb_episodes,
        recognize_mediainfo_fn=recognize,
        is_tv_fn=lambda _mediainfo: True,
        schedule_initial_pending_search_fn=lambda subscribe: calls.append(f"schedule_search:{subscribe.id}"),
        clear_tasks_for_pause_fn=clear_tasks_for_pause,
    )
    return SimpleNamespace(
        coordinator=coordinator,
        pending_judge=pending_judge,
        pending_state=pending_state,
        pause_manager=pause_manager,
        airing=airing,
        tmdb_episodes=tmdb_episodes,
        subscribe_oper=subscribe_oper,
        recognize=recognize,
        clear_tasks_for_pause=clear_tasks_for_pause,
        calls=calls,
    )


def test_lifecycle_result_defaults():
    result = LifecycleResult()
    assert result.changed is False
    assert result.stopped is False
    assert result.state is None
    assert result.reason == ""
    assert result.message == ""


def test_pending_from_judge_schedules_search_before_pending_for_new_subscribe(fake_lifecycle):
    subscribe = SimpleNamespace(id=1, state="N", tmdbid=100, season=1, episode_group=None)
    fake_lifecycle.pending_judge.should_enter_pending.return_value = (True, "开播日期未知")

    result = fake_lifecycle.coordinator.enter_pending_from_judge(subscribe, object(), [])

    assert result.changed is True
    assert result.stopped is True
    assert result.state == "P"
    assert fake_lifecycle.calls == ["schedule_search:1", "mark_pending:pending_judge:开播日期未知"]


def test_subscribe_added_auto_user_pause_stops_lifecycle(fake_lifecycle):
    fake_lifecycle.pause_manager.check_auto_pause_for_user.return_value = True
    subscribe = SimpleNamespace(id=10, state="N", best_version=False)

    result = fake_lifecycle.coordinator.handle_subscribe_added(subscribe, object())

    assert result.stopped is True
    assert result.state == "S"
    fake_lifecycle.pending_judge.should_enter_pending.assert_not_called()


def test_subscribe_added_pre_air_stops_before_pending(fake_lifecycle):
    subscribe = SimpleNamespace(id=11, state="N", best_version=False, tmdbid=100, season=1, episode_group=None)
    record = PauseRecord(reason="pre_air", since=1.0, detail="开播日期未知")
    fake_lifecycle.airing.check_pre_air.return_value = record

    result = fake_lifecycle.coordinator.handle_subscribe_added(subscribe, object())

    assert result.stopped is True
    assert result.state == "S"
    fake_lifecycle.pause_manager.pause.assert_called_once_with(subscribe, record)
    fake_lifecycle.pending_judge.should_enter_pending.assert_not_called()


def test_subscribe_added_pending_for_new_state_schedules_search_once(fake_lifecycle):
    subscribe = SimpleNamespace(id=12, state="N", best_version=False, tmdbid=100, season=1, episode_group=None)
    fake_lifecycle.pending_judge.should_enter_pending.return_value = (True, "开播日期未知")

    result = fake_lifecycle.coordinator.handle_subscribe_added(subscribe, object())

    assert result.state == "P"
    assert fake_lifecycle.calls == ["episodes", "schedule_search:12", "mark_pending:pending_judge:开播日期未知"]


def test_subscribe_added_uses_episode_group_scope(fake_lifecycle):
    subscribe = SimpleNamespace(id=13, state="R", best_version=False, tmdbid=100, season=1, episode_group="eg-1")
    fake_lifecycle.pending_judge.should_enter_pending.return_value = (False, "")

    fake_lifecycle.coordinator.handle_subscribe_added(subscribe, SimpleNamespace(next_episode_to_air=None))

    fake_lifecycle.tmdb_episodes.assert_called_once_with(100, 1, episode_group="eg-1")


def test_subscribe_added_non_tv_skips_tv_pending_flow(fake_lifecycle):
    subscribe = SimpleNamespace(id=14, state="R", best_version=False, tmdbid=100, season=1, episode_group=None)
    fake_lifecycle.coordinator._is_tv = lambda _mediainfo: False

    result = fake_lifecycle.coordinator.handle_subscribe_added(subscribe, SimpleNamespace(next_episode_to_air=None))

    assert result.changed is False
    fake_lifecycle.tmdb_episodes.assert_not_called()
    fake_lifecycle.pending_judge.should_enter_pending.assert_not_called()
    fake_lifecycle.airing.check_pre_air.assert_called_once_with(
        subscribe, SimpleNamespace(next_episode_to_air=None), episodes=[]
    )


def test_subscribe_added_new_subscription_skips_airing_gap_when_not_pending(fake_lifecycle):
    subscribe = SimpleNamespace(id=15, state="N", best_version=False, tmdbid=100, season=1, episode_group=None)
    fake_lifecycle.pending_judge.should_enter_pending.return_value = (False, "")
    fake_lifecycle.airing.check.return_value = PauseRecord(reason="airing_gap", detail="下一集距今 7 天")

    result = fake_lifecycle.coordinator.handle_subscribe_added(
        subscribe, SimpleNamespace(next_episode_to_air=None)
    )

    assert result.state == "N"
    fake_lifecycle.airing.check.assert_not_called()
    fake_lifecycle.pause_manager.pause.assert_not_called()


def test_subscribe_added_running_subscription_pauses_after_library_update(fake_lifecycle):
    subscribe = SimpleNamespace(id=16, state="R", best_version=False, tmdbid=100, season=1, episode_group=None)
    fake_lifecycle.pending_judge.should_enter_pending.return_value = (False, "")
    record = PauseRecord(reason="airing_gap", detail="下一集距今 7 天")
    fake_lifecycle.airing.check.return_value = record
    mediainfo = SimpleNamespace(next_episode_to_air=None)

    result = fake_lifecycle.coordinator.handle_subscribe_added(subscribe, mediainfo)

    assert result.changed is True
    assert result.state == "S"
    fake_lifecycle.airing.check.assert_called_once_with(
        subscribe,
        mediainfo,
        next_episode=None,
        latest_episode=None,
        episodes=[],
    )
    fake_lifecycle.pause_manager.pause.assert_called_once_with(subscribe, record)


def test_meta_check_refreshes_same_pause_silently(fake_lifecycle):
    subscribe = SimpleNamespace(id=20, state="S", best_version=False, tmdbid=100, season=1, episode_group=None)
    existing = PauseRecord(reason="pre_air", since=1.0, detail="旧原因")
    current = PauseRecord(reason="pre_air", since=2.0, detail="新原因")
    fake_lifecycle.pause_manager.get_pause_record.return_value = existing
    fake_lifecycle.airing.check_pre_air.return_value = current
    fake_lifecycle.recognize.return_value = object()

    result = fake_lifecycle.coordinator.handle_meta_check_subscription(subscribe)

    assert result.changed is False
    fake_lifecycle.pause_manager.pause.assert_called_once_with(subscribe, current, notify=False)


def test_meta_check_restores_orphan_p_before_pause(fake_lifecycle):
    subscribe = SimpleNamespace(id=21, state="P", best_version=False)
    fake_lifecycle.pending_state.has_active.return_value = False
    fake_lifecycle.pending_state.reconcile_orphaned.return_value = True

    result = fake_lifecycle.coordinator.handle_meta_check_subscription(subscribe)

    assert result.changed is True
    assert result.stopped is True
    assert result.state == "R"
    fake_lifecycle.recognize.assert_not_called()


def test_meta_check_reports_p_when_pending_exit_leaves_another_source(fake_lifecycle):
    """元数据巡检只释放一个待定来源时，返回状态必须仍是待定（P）。"""
    subscribe = SimpleNamespace(id=25, state="P", best_version=False, tmdbid=100, season=1, episode_group=None)
    fake_lifecycle.pending_state.has_active.return_value = True
    fake_lifecycle.pending_judge.check_exit.return_value = True
    fake_lifecycle.recognize.return_value = object()

    result = fake_lifecycle.coordinator.handle_meta_check_subscription(subscribe)

    assert result.changed is True
    assert result.stopped is True
    assert result.state == "P"


def test_no_download_pause_clears_tasks_after_success(fake_lifecycle):
    subscribe = SimpleNamespace(id=22, state="R")
    fake_lifecycle.pause_manager.pause.return_value = True

    result = fake_lifecycle.coordinator.pause_for_no_download(subscribe, "上映后长期无下载")

    assert result.changed is True
    fake_lifecycle.clear_tasks_for_pause.assert_called_once_with(22)


def test_restore_owned_states_before_reset_recovers_pending_and_airing_pause(fake_lifecycle):
    pending = SimpleNamespace(id=23, state="P", name="待定剧", season=1)
    paused = SimpleNamespace(id=24, state="S", name="暂停剧", season=2)
    fake_lifecycle.subscribe_oper.list.side_effect = [[pending], [paused]]
    fake_lifecycle.pending_state.clear_all_owned.return_value = True
    fake_lifecycle.pause_manager.get_pause_record.return_value = PauseRecord(
        reason="airing_gap",
        since=1.0,
        detail="播出间隔",
    )
    fake_lifecycle.pause_manager.resume.return_value = True

    result = fake_lifecycle.coordinator.restore_owned_states_before_reset()

    assert result.changed is True
    assert result.state == "R"
    assert "待定剧 S1" in result.message
    assert "暂停剧 S2" in result.message
    fake_lifecycle.pending_state.clear_all_owned.assert_called_once_with(
        pending,
        reason="插件任务重置",
    )
    fake_lifecycle.pause_manager.resume.assert_called_once_with(paused, notify=False)


def test_subscribe_added_full_best_version_stops_before_pending(fake_lifecycle):
    subscribe = SimpleNamespace(id=17, state="R", best_version=True, best_version_full=True, type="电视剧",
                                tmdbid=100, season=1, episode_group=None)

    result = fake_lifecycle.coordinator.handle_subscribe_added(subscribe, object())

    assert result.stopped is True
    assert result.changed is False
    fake_lifecycle.pending_judge.should_enter_pending.assert_not_called()
    fake_lifecycle.airing.check.assert_not_called()


def test_guard_pending_uses_lifecycle_pending_source(fake_lifecycle):
    subscribe = SimpleNamespace(id=2, state="R")

    result = fake_lifecycle.coordinator.enter_guard_pending(subscribe, "完成证据需观察")

    assert result.changed is True
    assert result.state == "P"
    fake_lifecycle.pending_judge.mark_pending.assert_called_once_with(
        subscribe, source="guard_veto", reason="完成证据需观察"
    )


def test_download_pending_adapter_routes_through_lifecycle(fake_lifecycle):
    subscribe = SimpleNamespace(id=3, state="R")
    adapter = fake_lifecycle.coordinator.download_pending_adapter()

    adapter.mark_active(subscribe, source="download_pending", reason="下载器已创建任务，等待整理入库")
    adapter.clear_active(SimpleNamespace(id=3, state="P"), source="download_pending", reason="下载待定已清除")

    assert fake_lifecycle.calls == [
        "pending_state_mark:download_pending:下载器已创建任务，等待整理入库",
        "pending_state_clear:download_pending:下载待定已清除",
    ]


def test_download_added_resumes_plugin_pause_and_sets_guard(fake_lifecycle):
    subscribe = SimpleNamespace(id=30, state="S", name="测试", season=1)
    fake_lifecycle.pause_manager.get_pause_record.return_value = PauseRecord(
        reason="pre_air", since=1.0, detail="开播前"
    )
    fake_lifecycle.pause_manager.resume.return_value = True
    fake_lifecycle.pause_manager.set_resume_guard.return_value = True

    result = fake_lifecycle.coordinator.handle_download_added_for_subscribe(subscribe)

    assert result.changed is True
    assert result.state == "R"
    assert result.reason == "pre_air"
    assert "写入防打回=True" in result.message
    fake_lifecycle.pause_manager.resume.assert_called_once_with(subscribe, notify=False)
    fake_lifecycle.pause_manager.clear_probe_fields_for_resume.assert_called_once_with(subscribe)
    fake_lifecycle.pause_manager.set_resume_guard.assert_called_once_with(subscribe, "pre_air", hours=48)


def test_download_added_external_resume_has_no_resume_guard(fake_lifecycle):
    subscribe = SimpleNamespace(id=31, state="S", name="测试", season=1)
    fake_lifecycle.pause_manager.get_pause_record.return_value = PauseRecord(
        reason="external", since=1.0, detail="插件命令手动暂停"
    )
    fake_lifecycle.pause_manager.resume.return_value = True

    result = fake_lifecycle.coordinator.handle_download_added_for_subscribe(subscribe)

    assert result.changed is True
    assert result.state == "R"
    fake_lifecycle.pause_manager.resume.assert_called_once_with(subscribe, notify=False)
    fake_lifecycle.pause_manager.set_resume_guard.assert_not_called()


def test_download_added_missing_pause_record_is_adopted_as_external(fake_lifecycle):
    subscribe = SimpleNamespace(id=33, state="S", name="测试", season=1)
    fake_lifecycle.pause_manager.get_pause_record.side_effect = [
        None,
        PauseRecord(reason="external", since=1.0, detail="外部暂停"),
    ]
    fake_lifecycle.pause_manager.resume.return_value = True

    result = fake_lifecycle.coordinator.handle_download_added_for_subscribe(subscribe)

    assert result.changed is True
    assert result.reason == "external"
    fake_lifecycle.pause_manager.adopt_external.assert_called_once_with(subscribe)
    fake_lifecycle.pause_manager.resume.assert_called_once_with(subscribe, notify=False)
    fake_lifecycle.pause_manager.set_resume_guard.assert_not_called()


def test_library_updated_checks_airing_gap_only_for_active_tv(fake_lifecycle):
    subscribe = SimpleNamespace(id=32, state="R", best_version=False, tmdbid=100, season=1, episode_group=None)
    fake_lifecycle.subscribe_oper.get.return_value = subscribe
    mediainfo = SimpleNamespace(next_episode_to_air=None)
    fake_lifecycle.recognize.return_value = mediainfo
    fake_lifecycle.is_tv = MagicMock(return_value=True)
    fake_lifecycle.coordinator._is_tv = fake_lifecycle.is_tv
    fake_lifecycle.airing.check.return_value = PauseRecord(reason="airing_gap", since=1.0, detail="下一集较远")

    result = fake_lifecycle.coordinator.handle_library_updated(32)

    assert result.changed is True
    assert result.state == "S"
    fake_lifecycle.recognize.assert_called_once_with(subscribe)
    fake_lifecycle.is_tv.assert_called_once_with(mediainfo)
    fake_lifecycle.tmdb_episodes.assert_called_once_with(100, 1, episode_group=None)


def test_release_pending_judge_reports_p_when_guard_veto_remains(fake_lifecycle):
    """显式释放 pending_judge 后若 guard_veto 仍活跃，生命周期结果保持 P。"""
    subscribe = SimpleNamespace(id=31, state="P", best_version=False)
    fake_lifecycle.recognize.return_value = object()
    fake_lifecycle.pending_judge.check_exit.return_value = True
    fake_lifecycle.pending_state.has_active.return_value = True

    result = fake_lifecycle.coordinator.release_pending_source(
        subscribe,
        source="pending_judge",
        reason="待定释放巡检",
    )

    assert result.changed is True
    assert result.stopped is True
    assert result.state == "P"
    assert fake_lifecycle.pending_judge.check_exit.call_args.kwargs["source"] == "pending_judge"


def test_release_guard_veto_passes_explicit_source_when_pending_judge_is_primary(fake_lifecycle):
    """显式释放 guard_veto 时，生命周期层必须把 source 原样传给 PendingJudge。"""
    subscribe = SimpleNamespace(id=32, state="P", best_version=False)
    fake_lifecycle.recognize.return_value = object()
    fake_lifecycle.pending_judge.check_exit.return_value = True
    fake_lifecycle.pending_state.has_active.return_value = True

    result = fake_lifecycle.coordinator.release_pending_source(
        subscribe,
        source="guard_veto",
        reason="完成前观察到期",
    )

    assert result.changed is True
    assert result.state == "P"
    assert fake_lifecycle.pending_judge.check_exit.call_args.kwargs["source"] == "guard_veto"


def test_subscribe_modified_external_pause_ownership_moves_to_lifecycle(fake_lifecycle):
    subscribe = SimpleNamespace(id=14, state="S")

    result = fake_lifecycle.coordinator.handle_subscribe_modified_state_change(
        subscribe, old_state="R", new_state="S"
    )

    assert result.changed is True
    assert result.state == "S"
    fake_lifecycle.pause_manager.adopt_external.assert_called_once_with(subscribe)


def test_subscribe_modified_resume_clears_plugin_pause_record(fake_lifecycle):
    subscribe = SimpleNamespace(id=15, state="R")

    result = fake_lifecycle.coordinator.handle_subscribe_modified_state_change(
        subscribe, old_state="S", new_state="R"
    )

    assert result.changed is True
    assert result.state == "R"
    fake_lifecycle.pause_manager.clear_pause_record.assert_called_once_with(subscribe)


def test_toggle_command_pause_uses_external_and_resume_silent(fake_lifecycle):
    subscribe = SimpleNamespace(id=4, state="R")

    paused = fake_lifecycle.coordinator.toggle_subscribe_by_user_command(subscribe)
    subscribe.state = "S"
    resumed = fake_lifecycle.coordinator.toggle_subscribe_by_user_command(subscribe)

    assert paused.changed is True
    assert paused.state == "S"
    assert resumed.changed is True
    assert resumed.state == "R"
    assert fake_lifecycle.pause_manager.pause.call_args.args[1].reason == "external"
    assert fake_lifecycle.pause_manager.pause.call_args.kwargs["notify"] is False
    assert fake_lifecycle.pause_manager.resume.call_args.kwargs["notify"] is False


def test_toggle_command_resume_adopts_missing_external_record_first(fake_lifecycle):
    subscribe = SimpleNamespace(id=5, state="S")
    fake_lifecycle.pause_manager.get_pause_record.return_value = None

    result = fake_lifecycle.coordinator.toggle_subscribe_by_user_command(subscribe)

    assert result.changed is True
    assert result.state == "R"
    fake_lifecycle.pause_manager.adopt_external.assert_called_once_with(
        subscribe, detail="插件命令手动暂停"
    )
    fake_lifecycle.pause_manager.resume.assert_called_once_with(subscribe, notify=False)
