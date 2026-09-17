"""ArchiveManager 宿主控制层、持久化状态与重试边界测试。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import app.plugins.archivemanager as manager_module
import pytest
from app.sdk.config import settings
from app.db.plugin.container import PluginDatabaseHandle
from app.plugins.archivemanager.config import TaskConfig, parse_config
from app.plugins.archivemanager.runner import (
    cleanup_stale_staging,
    remove_staging,
    staging_path,
)
from app.plugins.archivemanager.scanner import (
    Cancelled,
    directory_identity,
    fingerprint,
    identity,
)
from app.plugins.archivemanager.store import (
    Base,
    BatchRow,
    DirectoryRow,
    FileRow,
    Store,
    TaskRow,
)
from app.runtime.extensions.plugin.contracts import supports_plugin_hook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import scoped_session, sessionmaker

pytestmark = pytest.mark.v3
PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins.v3/archivemanager"


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
    store.create(batch_id, task.public(), [entry], "全部文件")
    return store.save(batch_id, status="failed", error="engine failed")


def test_staging_cleanup_keeps_recoverable_batches_and_removes_stale(tmp_path: Path) -> None:
    task = _task(tmp_path, id="staging-task")
    recoverable = staging_path(task, "recoverable")
    stale = staging_path(task, "stale")
    recoverable.mkdir(parents=True)
    stale.mkdir(parents=True)
    (recoverable / "archive.7z").write_bytes(b"keep")
    (stale / "archive.7z").write_bytes(b"remove")

    assert cleanup_stale_staging(task, {"recoverable"}) == 1
    assert recoverable.is_dir()
    assert not stale.exists()

    remove_staging(task, "recoverable")
    assert not recoverable.exists()


def test_cleanup_results_commit_batch_and_file_states_together(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="cleanup-results-task")
    source = Path(task.source_dir)
    first = _entry(source, "first.txt")
    second = _entry(source, "second.txt")
    store.inventory(task.id, [first, second], task.source_dir, task.public())
    batch = store.create("cleanup-results-batch", task.public(), [first, second], "全部文件")

    store.cleanup_intent(batch["id"], first["relative_path"])
    interim = store.get(batch["id"])
    assert interim["cleanup"] == {"first.txt": "deleting"}

    result = store.cleanup_results(
        batch["id"],
        {"first.txt": "deleted", "second.txt": "changed"},
    )

    assert result["cleanup"] == {"first.txt": "deleted", "second.txt": "changed"}
    with store.handle.session() as session:
        rows = {
            row.relative_path: row
            for row in session.scalars(select(FileRow).where(FileRow.batch_id == batch["id"]))
        }
        assert rows["first.txt"].status == "deleted"
        assert rows["first.txt"].present is False
        assert rows["second.txt"].status == "changed"
        assert rows["second.txt"].present is True


def test_daily_archive_bytes_uses_publication_day_and_keeps_moved_artifacts_counted(store: Store) -> None:
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    with store.handle.session() as session, session.begin():
        session.add_all(
            [
                BatchRow(
                    id="today-published",
                    task_id="task-1",
                    status="completed",
                    created_at=yesterday.isoformat(),
                    data={
                        "published_at": now.isoformat(),
                        "archive_size": 125,
                        "source_bytes": 250,
                        "file_count": 3,
                    },
                ),
                BatchRow(
                    id="legacy-today",
                    task_id="task-2",
                    status="completed",
                    created_at=now.isoformat(),
                    data={"archive_size": 75, "source_bytes": 150, "file_count": 2},
                ),
                BatchRow(
                    id="not-published",
                    task_id="task-2",
                    status="building",
                    created_at=now.isoformat(),
                    data={"archive_size": 900, "source_bytes": 1800, "file_count": 9},
                ),
            ]
        )

    configured_timezone = ZoneInfo(settings.TZ)
    assert store.daily_archive_bytes(now.astimezone(configured_timezone).date()) == 200
    assert store.daily_archive_bytes(yesterday.astimezone(configured_timezone).date()) == 0
    summary = store.summary()
    assert summary["today_archived_files"] == 5
    assert summary["today_archive_count"] == 2
    assert summary["today_archive_bytes"] == 200


def test_reset_data_clears_all_runtime_tables_and_keeps_physical_files(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="reset-task")
    source = Path(task.source_dir)
    entry = _entry(source, "nested/file.txt")
    directory_path = source / "nested"
    directory = {
        "relative_path": "nested",
        "source_root": str(source.resolve()),
        **directory_identity(directory_path),
    }
    store.inventory(task.id, [entry], task.source_dir, task.public())
    store.inventory_directories(task.id, [directory], task.public())
    store.create("reset-batch", task.public(), [entry], "全部文件", [directory])
    store.set_task_state(task.id, active=True, phase="history")

    result = store.reset_data()

    assert result == {"batch_count": 1, "file_count": 1, "directory_count": 1, "task_state_count": 1}
    assert (source / "nested/file.txt").is_file()
    with store.handle.session() as session:
        assert session.query(BatchRow).count() == 0
        assert session.query(FileRow).count() == 0
        assert session.query(DirectoryRow).count() == 0
        assert session.query(TaskRow).count() == 0


def test_pending_reset_clears_runtime_data_after_database_is_ready(monkeypatch) -> None:
    manager = manager_module.ArchiveManager()
    manager._previews = {"preview-1": {"status": "complete"}}
    store = MagicMock()
    store.reset_data.return_value = {"batch_count": 2, "file_count": 8, "directory_count": 3, "task_state_count": 1}
    save_data = MagicMock()
    update_config = MagicMock()
    monkeypatch.setattr(manager, "get_database", lambda: object())
    monkeypatch.setattr(manager_module, "Store", lambda _handle: store)
    monkeypatch.setattr(manager, "save_data", save_data)
    monkeypatch.setattr(manager, "get_config", lambda: {"enabled": True, "reset_data": True})
    monkeypatch.setattr(manager, "update_config", update_config)
    manager._reset_data_pending = True

    result_store = manager._store()

    assert result_store is store
    store.reset_data.assert_called_once_with()
    assert manager._reset_data_pending is False
    assert manager._previews == {"preview-1": {"status": "complete"}}
    save_data.assert_called_once_with("last_error", None)
    update_config.assert_called_once_with({"enabled": True, "reset_data": False})


def test_archive_manager_constructs_real_plugin_and_declares_persistence_contract() -> None:
    manager = manager_module.ArchiveManager()

    assert manager.get_state() is False
    assert manager.get_database_models() == [
        manager_module.BatchRow,
        manager_module.FileRow,
        manager_module.DirectoryRow,
        manager_module.TaskRow,
    ]
    assert manager.get_form() == (
        [],
        {
            "enabled": False,
            "notify": False,
            "notify_events": ["failure"],
            "daily_archive_limit_bytes": 0,
            "reset_data": False,
            "tasks": [],
        },
    )
    assert supports_plugin_hook(manager, "get_page") is False
    assert manager.get_service() == []


def test_task_public_omits_timezone_and_decimal_reserved_space_is_valid(tmp_path: Path) -> None:
    task = _task(tmp_path, min_free_bytes=1.5 * 1024**3)

    assert "timezone" not in task.public()
    assert task.min_free_bytes == 1.5 * 1024**3


def test_cron_service_uses_moviepilot_timezone(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "TZ", "UTC")
    task = _task(tmp_path, cron="0 0 * * *")
    manager = manager_module.ArchiveManager()
    manager._enabled = True
    manager._tasks = [task]

    service = manager.get_service()[0]

    assert str(service["trigger"].timezone) == "UTC"


def test_enabled_tasks_may_share_output_directory(tmp_path: Path) -> None:
    shared = tmp_path / "shared-output"
    first = _task(tmp_path / "first", id="first", output_dir=str(shared))
    second = _task(tmp_path / "second", id="second", output_dir=str(shared))

    assert len(parse_config({"tasks": [first.model_dump(), second.model_dump()]})) == 2


def test_api_run_rejects_global_disabled_plugin(tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, id="disabled-run")
    manager = manager_module.ArchiveManager()
    manager._tasks = [task]
    manager._enabled = False

    response = manager.api_run(manager_module.TaskRequest(task_id=task.id))

    assert response.success is False
    assert "未启用" in response.message


def test_api_run_without_task_id_submits_all_tasks(tmp_path: Path, monkeypatch) -> None:
    first = _task(tmp_path / "first", id="first")
    second = _task(tmp_path / "second", id="second")
    manager = manager_module.ArchiveManager()
    manager._tasks = [first, second]
    manager._enabled = True
    submitted = []
    monkeypatch.setattr(manager, "_enqueue_task", lambda task_id: submitted.append(task_id) or f"job-{task_id}")

    response = manager.api_run(manager_module.TaskRequest())

    assert response.success is True
    assert response.data == {"job_ids": ["job-first", "job-second"], "task_count": 2}
    assert submitted == ["first", "second"]


def test_archive_manager_frontend_has_reproducible_lockfile() -> None:
    """联邦前端提交 yarn.lock，未来发布时可以按冻结依赖构建。"""
    lockfile = PLUGIN_ROOT / "frontend/yarn.lock"

    assert lockfile.is_file()
    assert lockfile.read_text(encoding="utf-8").startswith("# THIS IS AN AUTOGENERATED FILE")


def test_notifications_respect_switch_events_and_channel_failure(tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, password="archive-test-secret")
    manager = manager_module.ArchiveManager()
    messages = []
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))

    manager._notify_event("failure", task, "归档失败", "默认关闭")
    assert messages == []
    manager._settings = manager_module.PluginConfig(notify=True, notify_events=["failure"])
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


def test_cancelled_job_is_silent_but_failure_includes_reason(store: Store, tmp_path: Path, monkeypatch) -> None:
    """停止只更新状态；真正异常才发送带原因的失败通知。"""
    task = _task(tmp_path, id="notify-stop-task")
    manager = manager_module.ArchiveManager()
    manager._tasks = [task]
    manager._settings = manager_module.PluginConfig(notify=True, notify_events=["failure", "other"])
    messages = []
    monkeypatch.setattr(manager, "_store", lambda: store)
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))
    monkeypatch.setattr(manager, "save_data", lambda *_args: None)

    def cancelled(*_args):
        raise Cancelled("插件正在停止")

    monkeypatch.setattr(manager, "_execute_cycle", cancelled)
    manager._queue.append({"id": "cancelled-job", "kind": "run", "task": task, "batch_id": ""})
    manager._work()

    assert messages == []
    assert store.task_state(task.id)["phase"] == "stopped"

    def failed(*_args):
        raise RuntimeError("读取源文件失败")

    monkeypatch.setattr(manager, "_execute_cycle", failed)
    manager._queue.append({"id": "failed-job", "kind": "run", "task": task, "batch_id": ""})
    manager._work()

    assert len(messages) == 1
    assert messages[0]["title"] == "压缩归档：归档失败"
    assert "读取源文件失败" in messages[0]["text"]


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
    log = MagicMock()

    monkeypatch.setattr(manager, "get_data", lambda _key: {})
    monkeypatch.setattr(manager_module, "logger", log)

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
    assert all(password not in str(call) for call in log.method_calls)


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


def test_clean_batches_removes_database_records_and_releases_files(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="clean-task")
    entry = _entry(Path(task.source_dir), "rearchive.mp4")
    assert store.inventory(task.id, [entry], task.source_dir, task.public()) == [entry]
    batch = store.create("clean-batch", task.public(), [entry], "全部文件")
    store.save(batch["id"], status="completed", archive_path="", manifest_path="")

    result = store.clean_batches([batch["id"]])

    assert result == {"batch_count": 1, "file_count": 1}
    with pytest.raises(ValueError, match="归档批次不存在"):
        store.get(batch["id"])
    with store.handle.session() as session:
        assert session.scalar(select(FileRow).where(FileRow.fingerprint == fingerprint(entry))) is None
    assert store.inventory(task.id, [entry], task.source_dir, task.public()) == [entry]


def test_api_cleanup_scans_old_staging_but_keeps_recoverable_batches(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path, id="staging-scan-task")
    entry = _entry(Path(task.source_dir), "failed.mp4")
    assert store.inventory(task.id, [entry], task.source_dir, task.public()) == [entry]
    selected = store.create("selected-cleanup-batch", task.public(), [entry], "全部文件")
    store.save(selected["id"], status="cancelled")
    recoverable = store.create("recoverable-batch", task.public(), [], "全部文件")
    store.save(recoverable["id"], status="building")

    selected_staging = staging_path(task, selected["id"])
    orphan_staging = staging_path(task, "legacy-stopped-batch")
    recoverable_staging = staging_path(task, recoverable["id"])
    for staging in (selected_staging, orphan_staging, recoverable_staging):
        staging.mkdir(parents=True)
        (staging / "partial.7z").write_bytes(b"staging")

    manager = manager_module.ArchiveManager()
    manager._tasks = [task]
    manager._enabled = True
    monkeypatch.setattr(manager, "_store", lambda: store)

    response = manager.api_cleanup(
        manager_module.BatchCleanupRequest(batch_ids=[selected["id"]], delete_artifacts=False)
    )

    assert response.success is True
    assert not selected_staging.exists()
    assert not orphan_staging.exists()
    assert recoverable_staging.is_dir()


def test_api_cleanup_can_remove_local_artifacts_without_touching_source(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path, id="artifact-clean-task")
    entry = _entry(Path(task.source_dir), "keep-source.mp4")
    assert store.inventory(task.id, [entry], task.source_dir, task.public()) == [entry]
    archive = Path(task.output_dir) / "2026" / "05" / "artifact-clean-batch" / "artifact.7z"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"archive")
    archive.with_name(archive.name + ".sha256").write_text("sha", encoding="utf-8")
    staging = staging_path(task, "artifact-clean-batch")
    staging.mkdir(parents=True)
    (staging / "partial.7z").write_bytes(b"staging")
    batch = store.create("artifact-clean-batch", task.public(), [entry], "全部文件")
    store.save(
        batch["id"],
        status="completed",
        archive_path=str(archive),
        archive_size=archive.stat().st_size,
        archive_sha256="sha",
    )
    manager = manager_module.ArchiveManager()
    manager._tasks = [task]
    manager._enabled = True
    monkeypatch.setattr(manager, "_store", lambda: store)

    response = manager.api_cleanup(
        manager_module.BatchCleanupRequest(batch_ids=[batch["id"]], delete_artifacts=True)
    )

    assert response.success is True
    assert not archive.exists()
    assert not archive.with_name(archive.name + ".sha256").exists()
    assert not archive.parent.exists()
    assert not (Path(task.output_dir) / "2026" / "05").exists()
    assert not (Path(task.output_dir) / "2026").exists()
    assert Path(task.output_dir).is_dir()
    assert not staging.exists()
    assert Path(task.source_dir, entry["relative_path"]).is_file()


def test_api_cleanup_encrypted_snapshot_does_not_require_password(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path, id="encrypted-clean-task", encryption="aes256", password="secret")
    entry = _entry(Path(task.source_dir), "encrypted.mp4")
    assert store.inventory(task.id, [entry], task.source_dir, task.public()) == [entry]
    batch = store.create("encrypted-clean-batch", task.public(), [entry], "全部文件")
    archive = Path(task.output_dir) / "encrypted.7z"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"archive")
    store.save(
        batch["id"],
        status="completed",
        archive_path=str(archive),
        archive_size=archive.stat().st_size,
        archive_sha256="sha",
    )
    manager = manager_module.ArchiveManager()
    manager._tasks = [task]
    manager._enabled = True
    monkeypatch.setattr(manager, "_store", lambda: store)

    response = manager.api_cleanup(
        manager_module.BatchCleanupRequest(batch_ids=[batch["id"]], delete_artifacts=True)
    )

    assert response.success is True
    assert not archive.exists()
    assert Path(task.source_dir, entry["relative_path"]).is_file()


def test_complete_files_persists_directory_manifest_archive_path(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="directory-manifest")
    source = Path(task.source_dir)
    entry = _entry(source, "nested/file.txt")
    directory_path = source / "nested"
    directory = {"relative_path": "nested", "source_root": str(source.resolve()), **directory_identity(directory_path)}
    store.inventory(task.id, [entry], task.source_dir, task.public())
    store.inventory_directories(task.id, [directory], task.public())
    batch = store.create("directory-manifest-batch", task.public(), [entry], "nested", [directory])
    batch["manifest"] = {
        "files": [{**entry, "archive_path": "files/nested/file.txt", "sha256": "a" * 64}],
        "directories": [{**directory, "archive_path": "files/nested"}],
    }
    batch["cleanup"] = {}
    store.complete_files(batch)
    with store.handle.session() as session:
        row = session.scalar(select(DirectoryRow).where(DirectoryRow.batch_id == batch["id"]))
        assert row.data["archive_path"] == "files/nested"
