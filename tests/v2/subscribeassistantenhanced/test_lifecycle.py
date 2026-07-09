"""lifecycle/ 生命周期编排单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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
    pause_manager.pause.return_value = True
    pause_manager.resume.return_value = True
    pause_manager.adopt_external.return_value = True
    pause_manager.get_pause_record.return_value = SimpleNamespace(reason="external")

    coordinator = SubscribeLifecycleCoordinator(
        config=MagicMock(),
        subscribe_oper=MagicMock(),
        pause_manager=pause_manager,
        pending_judge=pending_judge,
        pending_state=pending_state,
        schedule_initial_pending_search_fn=lambda subscribe: calls.append(f"schedule_search:{subscribe.id}"),
    )
    return SimpleNamespace(
        coordinator=coordinator,
        pending_judge=pending_judge,
        pending_state=pending_state,
        pause_manager=pause_manager,
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
