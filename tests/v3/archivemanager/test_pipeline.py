"""ArchiveManager 编排层的文件系统、账本与恢复边界测试。"""

from __future__ import annotations

import json
import importlib.util
import os
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import scoped_session, sessionmaker
from zoneinfo import ZoneInfo

from app.db.plugin.container import PluginDatabaseHandle
import app.plugins.archivemanager as manager_module
import app.plugins.archivemanager.capacity as capacity_module
from app.plugins.archivemanager import runner as runner_module
from app.plugins.archivemanager.capacity import CapacityWait
from app.plugins.archivemanager.capacity import allowance, fit_batch
from app.plugins.archivemanager.catalog import rebuild_index, write_catalog
from app.plugins.archivemanager.config import TaskConfig, parse_config
from app.plugins.archivemanager.runner import Runner
from app.plugins.archivemanager.scanner import Cancelled, identity, partition, scan
from app.plugins.archivemanager.store import Base, BatchRow, FileRow, Store, TaskRow


pytestmark = pytest.mark.v3
requires_archive_backend = pytest.mark.skipif(
    importlib.util.find_spec("py7zr") is None or importlib.util.find_spec("pyzipper") is None,
    reason="归档后端依赖未安装",
)


def _task_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source"
    output = tmp_path / "output"
    manifest = tmp_path / "manifest"
    source.mkdir(parents=True)
    return source, output, manifest


def _task(tmp_path: Path, **overrides) -> TaskConfig:
    source, output, manifest = _task_dirs(tmp_path)
    values = {
        "id": "archive-test",
        "name": "测试归档",
        "enabled": True,
        "source_dir": str(source),
        "output_dir": str(output),
        "manifest_dir": str(manifest),
        "archive_age_days": 0,
        "stability_seconds": 1,
        "verify": True,
        "delete_source": False,
        "max_pending_archives": 0,
        "max_pending_bytes": 0,
        "min_free_bytes": 0,
    }
    values.update(overrides)
    return TaskConfig.model_validate(values)


def _write_old(path: Path, content: bytes = b"archive data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    old = time.time() - 3600
    os.utime(path, (old, old))
    return path


def _write_age(path: Path, age_days: float, content: bytes = b"archive data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def _entry(source: Path, relative_path: str, content: bytes = b"archive data") -> dict:
    path = _write_old(source / relative_path, content)
    return {"relative_path": relative_path, "source_root": str(source.resolve()), **identity(path)}


def _entry_at(relative_path: str, size: int, when: datetime) -> dict:
    return {
        "relative_path": relative_path,
        "size": size,
        "mtime_ns": int(when.timestamp() * 1_000_000_000),
    }


def _manifest_batch(task: TaskConfig, *, batch_id: str = "batch-1") -> dict:
    entry = {
        "relative_path": "movie|[1].mkv",
        "size": 12,
        "mtime_ns": 1_700_000_000_000_000_000,
        "sha256": "a" * 64,
    }
    return {
        "id": batch_id,
        "task_id": task.id,
        "task_name": task.name,
        "task": {**task.public(), "password": "not-in-documents"},
        "status": "completed",
        "created_at": "2026-09-10T12:00:00+00:00",
        "archive_path": str(Path(task.output_dir) / batch_id / f"{batch_id}.7z"),
        "archive_size": 123,
        "archive_sha256": "b" * 64,
        "verified": True,
        "cleanup": {entry["relative_path"]: "retained"},
        "manifest": {
            "schema_version": 1,
            "batch_id": batch_id,
            "task_id": task.id,
            "task_name": task.name,
            "created_at": "2026-09-10T12:00:00+00:00",
            "files": [entry],
        },
    }


def _handle(tmp_path: Path) -> PluginDatabaseHandle:
    db_path = tmp_path / "archive.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 20})
    session_factory = sessionmaker(bind=engine)
    handle = PluginDatabaseHandle(
        plugin_id="archivemanager-test",
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


def _create_batch(store: Store, task: TaskConfig, source: Path, relative_paths: list[str], batch_id: str) -> dict:
    entries = [_entry(source, relative_path, f"content:{relative_path}".encode()) for relative_path in relative_paths]
    assert store.inventory(task.id, entries, task.source_dir) == entries
    return store.create(batch_id, task.public(), entries, "全部文件")


def test_config_rejects_overlapping_directories_and_validates_all_active_tasks(tmp_path: Path) -> None:
    source, output, manifest = _task_dirs(tmp_path)
    with pytest.raises(ValueError, match="不能重叠"):
        parse_config(
            {
                "tasks": [
                    {
                        "id": "same-task",
                        "enabled": True,
                        "source_dir": str(source),
                        "output_dir": str(source / "artifacts"),
                        "manifest_dir": str(manifest),
                    }
                ]
            }
        )

    source_b = source / "nested"
    source_b.mkdir()
    with pytest.raises(ValueError, match="源目录不能重叠"):
        parse_config(
            {
                "tasks": [
                    {
                        "id": "task-a",
                        "enabled": True,
                        "source_dir": str(source),
                        "output_dir": str(output),
                        "manifest_dir": str(manifest),
                    },
                    {
                        "id": "task-b",
                        "enabled": True,
                        "source_dir": str(source_b),
                        "output_dir": str(tmp_path / "out-b"),
                        "manifest_dir": str(tmp_path / "manifest-b"),
                    },
                ]
            }
        )


def test_config_delete_source_always_keeps_full_verification_and_public_snapshot_hides_password(tmp_path: Path) -> None:
    task = _task(tmp_path, delete_source=True, password="secret", encryption="none", verify=False)

    assert task.verify is True
    public = task.public()
    assert "password" not in public
    assert public["delete_source"] is True


def test_scan_preview_is_read_only_and_applies_include_exclude_rules(tmp_path: Path) -> None:
    source, output, manifest = _task_dirs(tmp_path)
    _write_old(source / "keep.txt")
    _write_old(source / "skip.tmp")
    _write_old(source / "nested" / "keep.txt")
    task = TaskConfig(
        id="preview",
        source_dir=str(source),
        output_dir=str(output),
        manifest_dir=str(manifest),
        archive_age_days=0,
        include_patterns=["*.txt"],
        exclude_patterns=["nested/*"],
    )
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    entries, skipped = scan(task, Event())

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert [entry["relative_path"] for entry in entries] == ["keep.txt"]
    assert skipped == 2
    assert before == after
    assert not output.exists()
    assert not manifest.exists()


def test_scan_stable_observation_skips_file_that_changes_during_wait(tmp_path: Path) -> None:
    source, output, manifest = _task_dirs(tmp_path)
    target = _write_old(source / "changing.bin", b"before")
    task = TaskConfig(
        id="stable",
        source_dir=str(source),
        output_dir=str(output),
        manifest_dir=str(manifest),
        archive_age_days=0,
        stability_seconds=1,
    )

    class MutatingStop:
        def is_set(self) -> bool:
            return False

        def wait(self, _timeout: float) -> bool:
            target.write_bytes(b"after")
            return False

    entries, skipped = scan(task, MutatingStop(), stable=True)

    assert entries == []
    assert skipped == 1


def test_scan_stable_observation_honors_cancellation(tmp_path: Path) -> None:
    source, output, manifest = _task_dirs(tmp_path)
    _write_old(source / "cancel.bin")
    task = TaskConfig(
        id="cancel",
        source_dir=str(source),
        output_dir=str(output),
        manifest_dir=str(manifest),
        archive_age_days=0,
        stability_seconds=1,
    )

    class CancelDuringWait:
        def is_set(self) -> bool:
            return False

        def wait(self, _timeout: float) -> bool:
            return True

    with pytest.raises(Cancelled, match="稳定性观察"):
        scan(task, CancelDuringWait(), stable=True)


def test_scan_uses_seven_day_archive_age_threshold(tmp_path: Path) -> None:
    source, output, manifest = _task_dirs(tmp_path)
    _write_age(source / "old-enough.txt", 8)
    _write_age(source / "too-new.txt", 6)
    _write_age(source / "recent.txt", 0.5)
    task = TaskConfig(
        id="seven-days",
        source_dir=str(source),
        output_dir=str(output),
        manifest_dir=str(manifest),
        archive_age_days=7,
    )

    entries, skipped = scan(task, Event())

    assert [entry["relative_path"] for entry in entries] == ["old-enough.txt"]
    assert entries[0]["source_root"] == str(source.resolve())
    assert skipped == 2


def test_partition_splits_by_file_count_and_bytes_without_dropping_oversized_files(tmp_path: Path) -> None:
    task = _task(tmp_path, grouping="none", max_files=2, max_bytes=5)
    entries = [
        _entry_at("a.bin", 4, datetime(2026, 9, 10, tzinfo=timezone.utc)),
        _entry_at("b.bin", 3, datetime(2026, 9, 10, 0, 1, tzinfo=timezone.utc)),
        _entry_at("c.bin", 2, datetime(2026, 9, 10, 0, 2, tzinfo=timezone.utc)),
        _entry_at("huge.bin", 10, datetime(2026, 9, 10, 0, 3, tzinfo=timezone.utc)),
    ]

    batches = partition(task, entries)

    assert [batch["group"] for batch in batches] == ["全部文件"] * 3
    assert [[entry["relative_path"] for entry in batch["entries"]] for batch in batches] == [
        ["a.bin"],
        ["b.bin", "c.bin"],
        ["huge.bin"],
    ]
    assert [batch["total_bytes"] for batch in batches] == [4, 5, 10]


def test_partition_uses_directory_and_timezone_aware_date_rules(tmp_path: Path) -> None:
    task = _task(
        tmp_path,
        grouping="directory_date",
        directory_depth=1,
        time_grain="month",
        timezone="Asia/Shanghai",
        max_files=0,
        max_bytes=0,
    )
    entries = [
        _entry_at("series/episode-1.mkv", 1, datetime(2026, 9, 30, 16, 30, tzinfo=timezone.utc)),
        _entry_at("series/episode-2.mkv", 1, datetime(2026, 10, 1, 16, 30, tzinfo=timezone.utc)),
        _entry_at("film/movie.mkv", 1, datetime(2026, 10, 1, 16, 30, tzinfo=timezone.utc)),
    ]

    batches = partition(task, entries)

    assert [batch["group"] for batch in batches] == [
        "series | 2026-10",
        "film | 2026-10",
    ]
    assert [[entry["relative_path"] for entry in batch["entries"]] for batch in batches] == [
        ["series/episode-1.mkv", "series/episode-2.mkv"],
        ["film/movie.mkv"],
    ]


def test_capacity_allowance_enforces_local_artifact_count_and_bytes(tmp_path: Path, monkeypatch) -> None:
    task = _task(
        tmp_path,
        max_pending_archives=1,
        max_pending_bytes=64 * 1024**2 + 11,
        min_free_bytes=0,
    )
    archive = Path(task.output_dir) / "existing" / "existing.7z"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"1234")
    monkeypatch.setattr(capacity_module, "available_space", lambda _path: 4 * 1024**3)

    limited_by_count = allowance(task, [{"archive_path": str(archive)}])
    assert limited_by_count["pending_archives"] == 1
    assert limited_by_count["pending_bytes"] == 4
    assert limited_by_count["budget"] == 0
    assert "数量达到上限" in limited_by_count["reason"]

    unlimited_count = task.model_copy(update={"max_pending_archives": 0})
    limited_by_bytes = allowance(unlimited_count, [{"archive_path": str(archive)}])
    assert limited_by_bytes["budget"] == 6


def test_fit_batch_keeps_history_order_and_never_splits_a_file(tmp_path: Path) -> None:
    task = _task(tmp_path, grouping="none")
    batch = {
        "group": "全部文件",
        "entries": [
            {"relative_path": "first", "size": 3},
            {"relative_path": "second", "size": 3},
        ],
        "total_bytes": 6,
    }

    selected = fit_batch(batch, 5)

    assert selected is not None
    assert [entry["relative_path"] for entry in selected["entries"]] == ["first"]
    assert selected["total_bytes"] == 3
    assert fit_batch(batch, 2) is None


def test_execute_cycle_waits_for_capacity_without_creating_failed_batch(tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, id="capacity-cycle", max_pending_archives=1)
    source = Path(task.source_dir)
    entry = _entry(source, "pending.txt")
    (tmp_path / "db").mkdir()
    handle = _handle(tmp_path / "db")
    store = Store(handle)
    manager = manager_module.ArchiveManager()
    manager._check_execution_paths = lambda _task: None
    manager._stop.clear()

    class RunnerProbe:
        def execute(self, *_args) -> None:
            raise AssertionError("容量不足时不应创建或执行批次")

    monkeypatch.setattr(manager_module, "scan", lambda *_args, **_kwargs: ([entry], 0))
    monkeypatch.setattr(manager_module, "partition", lambda *_args: [{"group": "全部文件", "entries": [entry], "total_bytes": entry["size"]}])
    monkeypatch.setattr(
        manager_module,
        "allowance",
        lambda *_args, **_kwargs: {
            "pending_archives": 1,
            "pending_bytes": 10,
            "free_bytes": 0,
            "budget": 0,
            "reason": "等待外部移走成品",
        },
    )
    try:
        manager._execute_cycle(task, store, RunnerProbe())
        assert store.batches(task.id)["total"] == 0
        state = store.task_state(task.id)
        assert state["phase"] == "waiting_capacity"
        assert state["reason"] == "等待外部移走成品"
    finally:
        handle.dispose()


def test_store_local_archives_ignores_an_externally_moved_artifact(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="external-move")
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["artifact-source.txt"], "external-move-batch")
    archive = Path(task.output_dir) / "external-move-batch" / "external-move-batch.7z"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"artifact")
    store.save(batch["id"], status="completed", archive_path=str(archive), archive_size=archive.stat().st_size)

    assert [item["id"] for item in store.local_archives(task.id)] == [batch["id"]]
    archive.unlink()
    assert store.local_archives(task.id) == []


def test_store_inventory_prioritizes_history_and_does_not_release_new_files_while_history_is_reserved(
    store: Store, tmp_path: Path
) -> None:
    task = _task(tmp_path, id="store-task")
    source = Path(task.source_dir)
    entry = _entry(source, "movie.mkv")

    assert store.inventory(task.id, [entry], task.source_dir) == [entry]
    assert store.exclude_reserved(task.id, [entry]) == [entry]

    batch = store.create("batch-1", task.public(), [entry], "全部文件")
    new_entry = _entry(source, "new.mkv", b"new version")

    assert store.inventory(task.id, [entry, new_entry], task.source_dir) == []
    assert store.exclude_reserved(task.id, [new_entry]) == [new_entry]
    assert store.get("batch-1")["status"] == "building"
    with store.handle.session() as session:
        row = session.scalar(select(FileRow).where(FileRow.task_id == task.id, FileRow.relative_path == "movie.mkv"))
        assert row is not None
        assert row.batch_id == batch["id"]
        assert row.present is True
        new_row = session.scalar(select(FileRow).where(FileRow.task_id == task.id, FileRow.relative_path == "new.mkv"))
        assert new_row is not None
        assert new_row.historical is False
        assert new_row.batch_id is None


def test_store_inventory_records_changed_and_missing_historical_files_separately(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="history-status")
    source = Path(task.source_dir)
    changed = _entry(source, "changed.txt", b"before")
    missing = _entry(source, "missing.txt", b"before")

    assert store.inventory(task.id, [changed, missing], task.source_dir) == [changed, missing]
    (source / "changed.txt").write_bytes(b"after")
    (source / "missing.txt").unlink()

    assert store.inventory(task.id, [], task.source_dir) == []
    with store.handle.session() as session:
        rows = list(session.scalars(select(FileRow).where(FileRow.task_id == task.id).order_by(FileRow.id)))
        assert len(rows) == 2
        assert {row.relative_path: row.status for row in rows} == {
            "changed.txt": "changed",
            "missing.txt": "missing",
        }
        assert all(row.historical for row in rows)
    state = store.task_state(task.id)
    assert state["history_total"] == 2
    assert state["history_remaining"] == 0
    assert state["history_unavailable"] == 2


def test_store_persists_batch_across_reopened_sqlite_handle(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    try:
        first = Store(handle)
        task = _task(tmp_path / "task", id="persistent")
        source = Path(task.source_dir)
        entry = _entry(source, "persisted.txt")
        first.inventory(task.id, [entry], task.source_dir)
        first.create("persistent-batch", task.public(), [entry], "全部文件")
        handle.scoped_session_factory.remove()

        reopened_engine = create_engine(f"sqlite:///{tmp_path / 'archive.db'}", connect_args={"timeout": 20})
        reopened_factory = sessionmaker(bind=reopened_engine)
        reopened = PluginDatabaseHandle(
            plugin_id="archivemanager-test-reopened",
            engine=reopened_engine,
            session_factory=reopened_factory,
            scoped_session_factory=scoped_session(reopened_factory),
            db_path=tmp_path / "archive.db",
            schema=None,
            owns_engine=True,
        )
        try:
            assert Store(reopened).get("persistent-batch")["task_id"] == task.id
            assert Store(reopened).batches(task.id)["total"] == 1
        finally:
            reopened.scoped_session_factory.remove()
            reopened.dispose()
    finally:
        handle.scoped_session_factory.remove()
        handle.dispose()


def test_failed_historical_batch_does_not_release_new_files_until_config_supersedes_it(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="history-failed")
    source = Path(task.source_dir)
    historical = _entry(source, "historical.txt")
    new_entry = _entry(source, "new.txt", b"new")

    assert store.inventory(task.id, [historical], task.source_dir, task.public()) == [historical]
    store.create("history-failed-batch", task.public(), [historical], "全部文件")
    store.save("history-failed-batch", status="failed", error="engine failed")

    assert store.inventory(task.id, [historical, new_entry], task.source_dir, task.public()) == []
    assert store.get("history-failed-batch")["status"] == "failed"

    changed_task = task.model_copy(update={"max_bytes": task.max_bytes + 1})
    eligible = store.inventory(task.id, [historical, new_entry], task.source_dir, changed_task.public())

    assert eligible == [historical]
    assert store.get("history-failed-batch")["status"] == "superseded"


def test_history_snapshot_and_task_state_survive_sqlite_reopen(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    task = _task(tmp_path / "task", id="history-reopen")
    source = Path(task.source_dir)
    historical = _entry(source, "historical.txt")
    new_entry = _entry(source, "new.txt", b"new")
    try:
        first = Store(handle)
        assert first.inventory(task.id, [historical], task.source_dir, task.public()) == [historical]
        first.set_task_state(task.id, active=True, reason="waiting")
        handle.scoped_session_factory.remove()

        reopened_engine = create_engine(f"sqlite:///{tmp_path / 'archive.db'}", connect_args={"timeout": 20})
        reopened_factory = sessionmaker(bind=reopened_engine)
        reopened = PluginDatabaseHandle(
            plugin_id="archivemanager-history-reopened",
            engine=reopened_engine,
            session_factory=reopened_factory,
            scoped_session_factory=scoped_session(reopened_factory),
            db_path=tmp_path / "archive.db",
            schema=None,
            owns_engine=True,
        )
        try:
            second = Store(reopened)
            assert second.inventory(task.id, [historical, new_entry], task.source_dir, task.public()) == [historical]
            state = second.task_state(task.id)
            assert state["phase"] == "history"
            assert state["active"] is True
            with reopened.session() as session:
                task_row = session.get(TaskRow, task.id)
                assert task_row is not None
                assert task_row.data["initialized"] is True
                rows = list(session.scalars(select(FileRow).where(FileRow.task_id == task.id)))
                assert {row.relative_path: row.historical for row in rows} == {
                    "historical.txt": True,
                    "new.txt": False,
                }
        finally:
            reopened.scoped_session_factory.remove()
            reopened.dispose()
    finally:
        handle.scoped_session_factory.remove()
        handle.dispose()


def test_catalog_writes_json_markdown_and_rebuildable_indexes_without_password(tmp_path: Path) -> None:
    task = _task(tmp_path, name="任务 | <主目录>")
    batch = _manifest_batch(task)

    markdown_path = write_catalog(batch)

    folder = Path(markdown_path).parent
    json_path = Path(markdown_path).with_suffix(".json")
    index_path = folder.parent / "index.json"
    assert Path(markdown_path).exists()
    assert json_path.exists()
    assert index_path.exists()
    record = json.loads(json_path.read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert record["batch_id"] == "batch-1"
    assert index["batches"][0]["batch_id"] == "batch-1"
    assert "not-in-documents" not in json_path.read_text(encoding="utf-8")
    assert "not-in-documents" not in Path(markdown_path).read_text(encoding="utf-8")
    assert "&#124;" in Path(markdown_path).read_text(encoding="utf-8")


def test_rebuild_index_is_independent_and_rejects_corrupt_entries_without_replacing_existing_index(tmp_path: Path) -> None:
    folder = tmp_path / "catalog"
    folder.mkdir()
    valid = {
        "schema_version": 1,
        "batch_id": "first",
        "task_id": "task",
        "task_name": "任务",
        "created_at": "2026-09-10T12:00:00+00:00",
        "archive_name": "first.7z",
        "archive_size": 1,
        "archive_sha256": "a" * 64,
        "verified": True,
    }
    (folder / "first.json").write_text(json.dumps(valid), encoding="utf-8")

    rebuild_index(folder)
    original_index = (folder / "index.json").read_text(encoding="utf-8")
    assert json.loads(original_index)["batches"][0]["batch_id"] == "first"

    invalid = {**valid, "batch_id": "wrong"}
    (folder / "second.json").write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="清单格式或批次 ID 不匹配"):
        rebuild_index(folder)
    assert (folder / "index.json").read_text(encoding="utf-8") == original_index


@pytest.mark.parametrize("layout", ["directory", "flat"])
@requires_archive_backend
def test_runner_real_engine_completes_archive_and_manifest_chain(store: Store, tmp_path: Path, layout: str) -> None:
    task = _task(tmp_path, id="complete", archive_name_template="backup_{date}", archive_layout=layout)
    source = Path(task.source_dir)
    entries = [_entry(source, name) for name in ["folder/sub/one.txt", "folder/sub/two.txt"]]
    store.inventory(task.id, entries, task.source_dir)
    batch = store.create("complete-batch", task.public(), entries, "folder | 20260128")
    phases: list[str] = []

    Runner(store, Event(), lambda phase, _batch_id: phases.append(phase)).execute(batch, task)

    final = store.get(batch["id"])
    archive = Path(final["archive_path"])
    assert final["status"] == "completed"
    assert final["verified"] is True
    assert archive.is_file()
    assert archive.name == batch["archive_name"]
    assert archive.name.startswith("backup_")
    assert archive.name.endswith(".7z")
    expected_directory = Path("folder") / batch["batch_name"] if layout == "directory" else Path(f"folder_{batch['batch_name']}")
    assert archive.parent == Path(task.output_dir) / expected_directory
    assert Path(final["manifest_path"]).is_file()
    assert archive.with_name(archive.name + ".sha256").is_file()
    assert Path(final["manifest_path"]).with_suffix(".json").is_file()
    assert (Path(task.manifest_dir) / "index.md").is_file()
    assert phases[:3] == ["building", "verifying", "publishing"]
    assert "manifest_pending" in phases
    assert (source / "folder/sub/one.txt").exists()
    assert (source / "folder/sub/two.txt").exists()
    catalog = json.loads(Path(final["manifest_path"]).with_suffix(".json").read_text())
    assert catalog["batch_name"] == batch["batch_name"]
    assert catalog["archive_name"] == archive.name
    task.archive_name_template = "changed_{id}"
    Runner(store, Event(), lambda *_: None).execute(final, task)
    assert Path(store.get(batch["id"])["archive_path"]) == archive


@requires_archive_backend
def test_runner_human_directory_collision_never_overwrites_another_batch(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, batch_name_template="固定批次")
    source = Path(task.source_dir)
    first = _create_batch(store, task, source, ["one.txt"], "first-batch")
    runner = Runner(store, Event(), lambda *_: None)
    runner.execute(first, task)
    completed = store.get(first["id"])
    original = Path(completed["archive_path"]).read_bytes()

    second = _create_batch(store, task, source, ["two.txt"], "second-batch")
    with pytest.raises(RuntimeError, match="不允许覆盖"):
        runner.execute(second, task)

    assert store.get(second["id"])["status"] == "failed"
    assert Path(completed["archive_path"]).read_bytes() == original
    assert (source / "two.txt").exists()


@requires_archive_backend
def test_runner_failed_manifest_never_deletes_sources(store: Store, tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, id="manifest-failure", delete_source=True)
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["keep.txt"], "manifest-failure-batch")

    def fail_catalog(_batch: dict) -> str:
        raise OSError("catalog unavailable")

    monkeypatch.setattr(runner_module, "write_catalog", fail_catalog)
    with pytest.raises(RuntimeError, match="catalog unavailable"):
        Runner(store, Event(), lambda *_args: None).execute(batch, task)

    final = store.get(batch["id"])
    assert final["status"] == "manifest_pending"
    assert (source / "keep.txt").exists()
    assert Path(final["archive_path"]).is_file()


@requires_archive_backend
def test_runner_interrupted_after_publish_rebuilds_documents_without_rearchiving(store: Store, tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, id="resume")
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["resume.txt"], "resume-batch")
    stop = Event()
    original_catalog = runner_module.write_catalog
    original_engine = runner_module.run_engine
    engine_calls: list[str] = []

    def track_engine(payload: dict, event: Event) -> dict:
        engine_calls.append(payload["action"])
        return original_engine(payload, event)

    def interrupt_after_publish(_batch: dict) -> str:
        stop.set()
        raise Cancelled("中断清单发布")

    monkeypatch.setattr(runner_module, "run_engine", track_engine)
    monkeypatch.setattr(runner_module, "write_catalog", interrupt_after_publish)
    with pytest.raises(Cancelled, match="中断清单发布"):
        Runner(store, stop, lambda *_args: None).execute(batch, task)

    first = store.get(batch["id"])
    archive_path = Path(first["archive_path"])
    archive_stat = archive_path.stat()
    assert first["status"] == "interrupted"
    assert archive_path.is_file()

    monkeypatch.setattr(runner_module, "write_catalog", original_catalog)
    stop.clear()
    Runner(store, stop, lambda *_args: None).execute(first, task)

    final = store.get(batch["id"])
    assert final["status"] == "completed"
    assert final["archive_path"] == str(archive_path)
    assert archive_path.stat().st_ino == archive_stat.st_ino
    assert engine_calls.count("build") == 1
    assert engine_calls.count("verify") == 2
    assert Path(final["manifest_path"]).is_file()


@requires_archive_backend
def test_runner_source_change_is_recorded_and_not_deleted(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="changed", delete_source=True)
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["changed.txt"], "changed-batch")

    def change_source(phase: str, _batch_id: str) -> None:
        if phase == "cleaning":
            (source / "changed.txt").write_bytes(b"changed after archive")

    Runner(store, Event(), change_source).execute(batch, task)

    final = store.get(batch["id"])
    assert final["status"] == "completed"
    assert final["cleanup"] == {"changed.txt": "changed"}
    assert (source / "changed.txt").exists()


@requires_archive_backend
def test_runner_moved_archive_aborts_cleanup_and_keeps_sources(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="moved", delete_source=True)
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["moved.txt"], "moved-batch")

    def move_archive(phase: str, _batch_id: str) -> None:
        if phase == "cleaning":
            archive = Path(store.get(batch["id"])["archive_path"])
            archive.unlink()

    with pytest.raises(RuntimeError, match="外部移走"):
        Runner(store, Event(), move_archive).execute(batch, task)

    final = store.get(batch["id"])
    assert final["status"] == "cleanup_failed"
    assert (source / "moved.txt").exists()
    assert final["cleanup"] == {"moved.txt": "deleting"}


@requires_archive_backend
def test_runner_cleanup_records_each_file_state_independently(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="cleanup", delete_source=True)
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["deleted.txt", "changed.txt", "missing.txt"], "cleanup-batch")

    def prepare_cleanup(phase: str, _batch_id: str) -> None:
        if phase == "cleaning":
            (source / "changed.txt").write_bytes(b"changed before cleanup")
            (source / "missing.txt").unlink()

    Runner(store, Event(), prepare_cleanup).execute(batch, task)

    final = store.get(batch["id"])
    assert final["status"] == "completed"
    assert final["cleanup"] == {
        "deleted.txt": "deleted",
        "changed.txt": "changed",
        "missing.txt": "missing",
    }
    assert not (source / "deleted.txt").exists()
    assert (source / "changed.txt").exists()
    assert not (source / "missing.txt").exists()


def test_runner_rejects_unrelated_partial_staging_file(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="staging-name")
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["staging.txt"], "staging-batch")
    staging = Path(task.output_dir).parent / ".archivemanager-staging" / task.id / batch["id"]
    staging.mkdir(parents=True)
    (staging / ".staging-batch.7z.wrong.part").write_bytes(b"partial")

    with pytest.raises(RuntimeError, match="暂存区包含非预期文件"):
        Runner(store, Event(), lambda *_args: None).execute(batch, task)

    assert store.get(batch["id"])["status"] == "failed"
    assert not (Path(task.output_dir) / batch["id"]).exists()
    assert (source / "staging.txt").exists()


@requires_archive_backend
def test_runner_fsyncs_archive_before_publishing(store: Store, tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path, id="fsync-archive")
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["fsync.txt"], "fsync-batch")
    original_fsync = runner_module.os.fsync
    original_rename = runner_module.os.rename
    fsync_kinds: list[str] = []

    def record_fsync(fd: int) -> None:
        mode = os.fstat(fd).st_mode
        fsync_kinds.append("file" if stat.S_ISREG(mode) else "directory" if stat.S_ISDIR(mode) else "other")
        original_fsync(fd)

    def publish(source_path, target_path) -> None:
        assert "file" in fsync_kinds
        original_rename(source_path, target_path)

    monkeypatch.setattr(runner_module.os, "fsync", record_fsync)
    monkeypatch.setattr(runner_module.os, "rename", publish)

    Runner(store, Event(), lambda *_args: None).execute(batch, task)

    assert store.get(batch["id"])["status"] == "completed"
    assert fsync_kinds.count("file") >= 1
    assert fsync_kinds.count("directory") >= 1


@requires_archive_backend
def test_runner_real_engine_stop_then_retry_completes(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="stop-retry")
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["stop-retry.txt"], "stop-retry-batch")
    stop = Event()

    def stop_before_engine(phase: str, _batch_id: str) -> None:
        if phase == "building":
            stop.set()

    with pytest.raises(Cancelled, match="已停止归档"):
        Runner(store, stop, stop_before_engine).execute(batch, task)

    interrupted = store.get(batch["id"])
    assert interrupted["status"] == "cancelled"
    assert (source / "stop-retry.txt").exists()
    assert not (Path(task.output_dir) / batch["id"]).exists()

    stop.clear()
    Runner(store, stop, lambda *_args: None).execute(interrupted, task)

    final = store.get(batch["id"])
    assert final["status"] == "completed"
    assert Path(final["archive_path"]).is_file()


def test_runner_missing_published_directory_never_rebuilds_recorded_batch(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path, id="moved-directory")
    source = Path(task.source_dir)
    batch = _create_batch(store, task, source, ["moved-directory.txt"], "moved-directory-batch")
    published = Path(task.output_dir) / batch["id"]
    archive = published / f"{batch['id']}.{task.format}"
    published.mkdir(parents=True)
    archive.write_bytes(b"recorded archive")
    store.save(
        batch["id"],
        status="interrupted",
        archive_path=str(archive),
        archive_sha256="a" * 64,
        archive_size=archive.stat().st_size,
        manifest={"files": []},
        verified=True,
    )
    moved = tmp_path / "moved-out"
    published.rename(moved)

    def unexpected_engine(*_args, **_kwargs):
        raise AssertionError("已记录成品被移走后不应重新打包")

    monkeypatch.setattr(runner_module, "run_engine", unexpected_engine)
    with pytest.raises(RuntimeError, match="已记录成品不在本地"):
        Runner(store, Event(), lambda *_args: None).execute(store.get(batch["id"]), task)

    assert moved.is_dir()
    assert not (Path(task.output_dir) / batch["id"]).exists()
    assert (source / "moved-directory.txt").exists()
