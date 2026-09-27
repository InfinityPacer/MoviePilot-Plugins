"""ArchiveManager 大目录内存边界测试：紧凑扫描记录、分块入库与按轮截断的规划。"""

from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Event

import app.plugins.archivemanager as manager_module
import app.plugins.archivemanager.store as store_module
import pytest
from app.db.plugin.container import PluginDatabaseHandle
from app.plugins.archivemanager.config import TaskConfig
from app.plugins.archivemanager.planner import plan_cycle
from app.plugins.archivemanager.scanner import FileEntry, fingerprint, identity, scan
from app.plugins.archivemanager.store import Base, BatchRow, FileRow, Store, TaskRow
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import scoped_session, sessionmaker

pytestmark = pytest.mark.v3


def _task(tmp_path: Path, **overrides) -> TaskConfig:
    source = tmp_path / "source"
    source.mkdir(parents=True, exist_ok=True)
    values = {
        "id": "planner-task",
        "name": "规划测试",
        "enabled": True,
        "source_dir": str(source),
        "output_dir": str(tmp_path / "output"),
        "manifest_dir": str(tmp_path / "manifest"),
        "archive_age_days": 0,
        "stability_seconds": 1,
        "grouping": "none",
        "max_files": 1,
        "max_bytes": 0,
        "max_pending_archives": 0,
        "max_pending_bytes": 0,
        "min_free_bytes": 0,
    }
    values.update(overrides)
    return TaskConfig.model_validate(values)


def _write_old(path: Path, content: bytes = b"archive data", age_seconds: int = 3600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))
    return path


def _entry(source: Path, relative_path: str, age_seconds: int = 3600) -> dict:
    path = _write_old(source / relative_path, f"content:{relative_path}".encode(), age_seconds)
    return {"relative_path": relative_path, "source_root": str(source.resolve()), **identity(path)}


class _NoWait:
    """跳过稳定性观察等待，测试不需要真实计时。"""

    def is_set(self) -> bool:
        """从不请求停止。"""
        return False

    def wait(self, _timeout: float) -> bool:
        return False


@pytest.fixture
def store(tmp_path: Path):
    db_path = tmp_path / "archive.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 20})
    factory = sessionmaker(bind=engine)
    handle = PluginDatabaseHandle(
        plugin_id="archivemanager-planner-test",
        engine=engine,
        session_factory=factory,
        scoped_session_factory=scoped_session(factory),
        db_path=db_path,
        schema=None,
        owns_engine=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield Store(handle)
    finally:
        handle.scoped_session_factory.remove()
        handle.dispose()


def test_scan_returns_compact_entries_equal_to_legacy_dict_and_batches_store_plain_dicts(
    store: Store, tmp_path: Path
) -> None:
    task = _task(tmp_path)
    source = Path(task.source_dir)
    expected = _entry(source, "nested/photo.jpg")

    entries, skipped = scan(task, Event())

    assert skipped == 0
    assert len(entries) == 1
    entry = entries[0]
    assert isinstance(entry, FileEntry)
    assert not hasattr(entry, "__dict__")
    assert entry == expected
    assert list(entry) == list(expected)
    assert fingerprint(entry) == fingerprint(expected)
    assert store.inventory(task.id, entries, task.source_dir) == [expected]
    batch = store.create("compact-batch", task.public(), entries, "全部文件")
    assert batch["entries"] == [expected]
    assert type(batch["entries"][0]) is dict
    with store.handle.session() as session:
        row = session.scalar(select(FileRow).where(FileRow.task_id == task.id))
        assert row is not None
        assert row.data == expected


def test_inventory_keeps_history_semantics_across_chunk_boundaries(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(store_module, "INVENTORY_CHUNK", 2)
    task = _task(tmp_path, id="chunked")
    source = Path(task.source_dir)
    historical = [_entry(source, f"history-{index}.txt") for index in range(5)]

    assert store.inventory(task.id, historical, task.source_dir, task.public()) == historical
    store.create("chunk-batch", task.public(), historical[1:3], "全部文件")
    (source / "history-4.txt").unlink()
    new_entry = _entry(source, "new.txt")
    visible = historical[:4] + [new_entry]

    # 历史快照未完成前，新文件不能被释放；已预留成员不会再次返回；消失的历史文件单独记为 missing。
    released = store.inventory(task.id, visible, task.source_dir, task.public())
    assert released == [historical[0], historical[3]]
    assert store.exclude_reserved(task.id, visible) == [historical[0], historical[3], new_entry]
    with store.handle.session() as session:
        statement = select(FileRow).where(FileRow.task_id == task.id)
        rows = {row.relative_path: row for row in session.scalars(statement)}
        assert rows["history-4.txt"].status == "missing"
        assert rows["history-4.txt"].present is False
        assert rows["new.txt"].historical is False
        assert all(rows[f"history-{index}.txt"].present for index in range(4))
        assert rows["history-1.txt"].batch_id == "chunk-batch"

    # 失败快照在配置变化后被废弃，其成员按块重新释放。
    store.save("chunk-batch", status="failed", error="engine failed")
    changed = task.model_copy(update={"max_files": 2})
    assert store.inventory(task.id, visible, task.source_dir, changed.public()) == historical[:4]
    assert store.get("chunk-batch")["status"] == "superseded"


def test_inventory_rolls_back_when_interrupted_mid_way_and_next_run_resumes(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(store_module, "INVENTORY_CHUNK", 2)
    task = _task(tmp_path, id="interrupted")
    source = Path(task.source_dir)
    entries = [_entry(source, f"file-{index}.txt") for index in range(5)]
    real_fingerprint = store_module.fingerprint
    calls = {"count": 0}

    def interrupted(entry):
        calls["count"] += 1
        if calls["count"] == 4:
            raise RuntimeError("进程在第二个分块中断")
        return real_fingerprint(entry)

    monkeypatch.setattr(store_module, "fingerprint", interrupted)
    with pytest.raises(RuntimeError, match="第二个分块"):
        store.inventory(task.id, entries, task.source_dir, task.public())
    with store.handle.session() as session:
        assert session.scalar(select(func.count()).select_from(FileRow)) == 0
        assert session.get(TaskRow, task.id) is None

    monkeypatch.setattr(store_module, "fingerprint", real_fingerprint)
    assert store.inventory(task.id, entries, task.source_dir, task.public()) == entries
    assert store.task_state(task.id)["history_remaining"] == 5


def test_plan_cycle_keeps_only_groups_reachable_in_this_round(store: Store, tmp_path: Path) -> None:
    task = _task(tmp_path, id="truncate", grouping="directory", max_files=2)
    source = Path(task.source_dir)
    # 越旧的文件越先分批；每个顶层目录一组，每组最多两份文件。
    for index, name in enumerate(["a/1.txt", "a/2.txt", "a/3.txt", "b/1.txt", "c/deep/1.txt"]):
        _write_old(source / name, age_seconds=10_000 - index * 100)
    (source / "empty").mkdir()

    plan = plan_cycle(task, _NoWait(), store, 2)

    assert plan.eligible_files == 5
    assert plan.batch_count == 5  # a 两批、b、c 各一批，外加独立空目录批次
    assert plan.has_more is True
    assert [[entry["relative_path"] for entry in group["entries"]] for group in plan.groups] == [
        ["a/1.txt", "a/2.txt"],
        ["a/3.txt"],
    ]
    assert set(plan.directory_map) == {"a"}

    whole = plan_cycle(task, _NoWait(), store, 10)
    assert whole.has_more is False
    assert len(whole.groups) == 5
    assert whole.groups[-1]["directories"][0]["relative_path"] == "empty"
    assert set(whole.directory_map) == {"a", "b", "c", "c/deep"}


def test_execute_cycle_keeps_history_phase_when_candidates_remain_beyond_round_limit(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path, id="round-limit", max_batches=2)
    source = Path(task.source_dir)
    for index in range(4):
        _write_old(source / f"file-{index}.txt", age_seconds=10_000 - index)
    manager = manager_module.ArchiveManager()
    manager._check_execution_paths = lambda _task: None
    manager._stop.clear()
    monkeypatch.setattr(
        manager_module,
        "plan_cycle",
        lambda cycle_task, _stop, cycle_store, limit: plan_cycle(cycle_task, _NoWait(), cycle_store, limit),
    )
    executed = []

    class RunnerProbe:
        def execute(self, batch, _task) -> None:
            executed.append([entry["relative_path"] for entry in batch["entries"]])
            store.save(batch["id"], status="completed")

    manager._execute_cycle(task, store, RunnerProbe())

    assert executed == [["file-0.txt"], ["file-1.txt"]]
    state = store.task_state(task.id)
    assert state["phase"] == "history"
    with store.handle.session() as session:
        assert session.scalar(select(func.count()).select_from(BatchRow)) == 2
