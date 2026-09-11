"""ArchiveManager 宿主控制层、持久化状态与重试边界测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import scoped_session, sessionmaker

from app.db.plugin.container import PluginDatabaseHandle
import app.plugins.archivemanager as manager_module
from app.plugins.archivemanager.config import TaskConfig
from app.plugins.archivemanager.scanner import identity
from app.plugins.archivemanager.store import Base, FileRow, Store, TaskRow


pytestmark = pytest.mark.v3


def _task(tmp_path: Path, **overrides) -> TaskConfig:
    source = tmp_path / "source"
    output = tmp_path / "output"
    manifest = tmp_path / "manifest"
    source.mkdir(parents=True)
    values = {
        "id": "control-task",
        "name": "控制测试",
        "enabled": True,
        "source_dir": str(source),
        "output_dir": str(output),
        "manifest_dir": str(manifest),
        "archive_age_days": 0,
        "stability_seconds": 1,
        "max_pending_archives": 0,
        "max_pending_bytes": 0,
        "min_free_bytes": 0,
    }
    values.update(overrides)
    return TaskConfig.model_validate(values)


def _handle(tmp_path: Path) -> PluginDatabaseHandle:
    db_path = tmp_path / "archive.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 20})
    session_factory = sessionmaker(bind=engine)
    handle = PluginDatabaseHandle(
        plugin_id="archivemanager-control-test",
        engine=engine,
        session_factory=session_factory,
        scoped_session_factory=scoped_session(session_factory),
        db_path=db_path,
        schema=None,
        owns_engine=True,
    )
    Base.metadata.create_all(engine)
    return handle


@pytest.fixture
def store(tmp_path: Path):
    handle = _handle(tmp_path)
    try:
        yield Store(handle)
    finally:
        handle.scoped_session_factory.remove()
        handle.dispose()


def _entry(source: Path, relative_path: str, content: bytes = b"control data") -> dict:
    path = source / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"relative_path": relative_path, "source_root": str(source.resolve()), **identity(path)}


def _create_failed_batch(store: Store, task: TaskConfig, batch_id: str) -> dict:
    entry = _entry(Path(task.source_dir), "retry.txt")
    assert store.inventory(task.id, [entry], task.source_dir, task.public()) == [entry]
    batch = store.create(batch_id, task.public(), [entry], "全部文件")
    return store.save(batch_id, status="failed", error="engine failed")


def test_archive_manager_constructs_real_plugin_and_declares_persistence_contract() -> None:
    manager = manager_module.ArchiveManager()

    assert manager.get_state() is False
    assert manager.get_database_models() == [manager_module.BatchRow, manager_module.FileRow, manager_module.TaskRow]
    assert manager.get_form() == ([], {"enabled": False, "notify": False, "notify_events": ["failure"], "tasks": []})
    assert manager.get_service() == []


def test_notifications_respect_switch_events_and_channel_failure(tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, password="archive-test-secret")
    manager = manager_module.ArchiveManager()
    messages = []
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))

    manager._notify_event("failure", task, "归档失败", "默认关闭")
    assert messages == []
    manager._notifications = manager_module.NotificationConfig(notify=True, notify_events=["failure"])
    manager._notify_event("success", task, "归档成功", "未选择此事件")
    assert messages == []
    manager._notify_event("failure", task, "归档失败", task.password)
    assert len(messages) == 1
    assert messages[0]["title"] == "压缩归档：归档失败"
    assert task.password not in messages[0]["text"]

    def failed_channel(**_message):
        raise RuntimeError("channel unavailable")

    monkeypatch.setattr(manager, "post_message", failed_channel)
    manager._notify_event("failure", task, "归档失败", "不应中断归档")


def test_init_plugin_writes_password_only_to_secret_store_and_public_config_has_no_echo(tmp_path: Path, monkeypatch) -> None:
    password = "control-secret-不应回显"
    task = _task(
        tmp_path,
        id="secret-task",
        encryption="aes256",
        password=password,
        password_version="7",
    )
    manager = manager_module.ArchiveManager()
    secret_writes: dict[str, object] = {}
    public_config: dict[str, object] = {}

    monkeypatch.setattr(manager, "get_data", lambda _key: {})

    def save_data(key: str, value: object) -> None:
        secret_writes[key] = value

    def update_config(value: dict) -> bool:
        public_config["value"] = value
        return True

    monkeypatch.setattr(manager, "save_data", save_data)
    monkeypatch.setattr(manager, "update_config", update_config)

    manager.init_plugin({"enabled": True, "tasks": [task.model_dump()]})

    assert secret_writes["task_passwords"] == {
        task.id: {"version": "7", "password": password},
    }
    assert manager._tasks[0].password == password
    serialized = json.dumps(public_config["value"], ensure_ascii=False)
    assert password not in serialized
    assert public_config["value"]["tasks"][0]["password"] == ""
    assert public_config["value"]["tasks"][0]["password_set"] is True


def test_api_stop_persists_task_row_state(store: Store, tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, id="stop-task", auto_continue=True)
    manager = manager_module.ArchiveManager()
    manager._tasks = [task]
    monkeypatch.setattr(manager, "_store", lambda: store)

    response = manager.api_stop(manager_module.TaskRequest(task_id=task.id))

    assert response.success is True
    assert store.task_state(task.id)["active"] is False
    assert store.task_state(task.id)["phase"] == "stopped"
    with store.handle.session() as session:
        row = session.get(TaskRow, task.id)
        assert row is not None
        assert row.data == {"active": False, "phase": "stopped", "reason": "已停止"}


def test_auto_continue_only_enqueues_active_waiting_capacity_tasks(store: Store, tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, id="auto-task", auto_continue=True)
    manager = manager_module.ArchiveManager()
    manager._tasks = [task]
    monkeypatch.setattr(manager, "_store", lambda: store)
    enqueued: list[str] = []
    monkeypatch.setattr(manager, "_enqueue_task", lambda task_id: enqueued.append(task_id))

    store.set_task_state(task.id, active=True, phase="waiting_capacity")
    manager._resume_waiting()
    assert enqueued == [task.id]

    enqueued.clear()
    store.set_task_state(task.id, active=True, phase="waiting_retry")
    manager._resume_waiting()
    store.set_task_state(task.id, active=True, phase="stopped")
    manager._resume_waiting()
    assert enqueued == []


def test_execution_path_check_uses_frozen_history_snapshot(store: Store, tmp_path: Path, monkeypatch) -> None:
    frozen_root = tmp_path / "frozen"
    current_root = tmp_path / "current"
    frozen = _task(
        frozen_root,
        id="history-task",
        source_dir=str(frozen_root / "source"),
        output_dir=str(frozen_root / "output"),
        manifest_dir=str(frozen_root / "manifest"),
    )
    current = _task(
        current_root,
        id="history-task",
        source_dir=str(current_root / "source"),
        output_dir=str(current_root / "output"),
        manifest_dir=str(current_root / "manifest"),
    )
    contender = _task(
        tmp_path / "contender",
        id="contender",
        source_dir=str(Path(frozen.output_dir) / "new-input"),
        output_dir=str(tmp_path / "contender-output"),
        manifest_dir=str(tmp_path / "contender-manifest"),
    )
    manager = manager_module.ArchiveManager()
    manager._tasks = [current, contender]
    manager._running = {"task_id": frozen.id, "batch_id": "frozen-batch"}

    class SnapshotStore:
        def get(self, batch_id: str) -> dict:
            assert batch_id == "frozen-batch"
            return {"task": frozen.public()}

    monkeypatch.setattr(manager, "_store", lambda: SnapshotStore())

    with pytest.raises(ValueError, match="实际执行目录与其他任务重叠"):
        manager._check_execution_paths(contender)


def test_api_retry_supersedes_failed_batch_when_task_config_changed(store: Store, tmp_path: Path, monkeypatch) -> None:
    original = _task(tmp_path, id="retry-task", max_bytes=100)
    changed = original.model_copy(update={"max_bytes": 101})
    batch = _create_failed_batch(store, original, "retry-config-batch")
    manager = manager_module.ArchiveManager()
    manager._tasks = [changed]
    monkeypatch.setattr(manager, "_store", lambda: store)
    calls: list[tuple[str, str]] = []

    def enqueue(task_id: str, batch_id: str = "") -> str:
        calls.append((task_id, batch_id))
        return "queued-job"

    monkeypatch.setattr(manager, "_enqueue_task", enqueue)

    response = manager.api_retry(manager_module.BatchRequest(batch_id=batch["id"]))

    assert response.success is True
    assert response.data == {"job_id": "queued-job"}
    assert calls == [(original.id, "")]
    assert store.get(batch["id"])["status"] == "superseded"
    with store.handle.session() as session:
        row = session.scalar(select(FileRow).where(FileRow.task_id == original.id))
        assert row is not None
        assert row.batch_id is None
        assert row.status == "pending"
