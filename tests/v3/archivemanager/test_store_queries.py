"""ArchiveManager 批次循环内账本查询测试：只读窄列，结果与完整快照一致。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import app.plugins.archivemanager as manager_module
import pytest
from app.db.plugin.container import PluginDatabaseHandle
from app.plugins.archivemanager.config import TaskConfig
from app.plugins.archivemanager.store import Base, BatchRow, Store
from app.sdk.config import settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import scoped_session, sessionmaker
from zoneinfo import ZoneInfo

pytestmark = pytest.mark.v3


@pytest.fixture(name="store")
def store_fixture(tmp_path: Path):
    """每个用例独立的 SQLite 插件库。"""
    db_path = tmp_path / "archive.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 20})
    factory = sessionmaker(bind=engine)
    handle = PluginDatabaseHandle(
        plugin_id="archivemanager-store-query-test",
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


def _batch(batch_id: str, task_id: str, created_at: datetime, **data) -> BatchRow:
    return BatchRow(
        id=batch_id,
        task_id=task_id,
        status=data.pop("status", "completed"),
        created_at=created_at.isoformat(),
        data={"archive_path": "", "archive_size": 0, "entries": [], "manifest": None, **data},
    )


def test_daily_archive_bytes_sums_archives_larger_than_32bit_integers(store: Store) -> None:
    now = datetime.now(timezone.utc)
    with store.handle.session() as session, session.begin():
        session.add_all(
            [
                _batch("large", "task", now, published_at=now.isoformat(), archive_size=5_000_000_000),
                _batch("legacy", "task", now, archive_size=3_000_000_000),
                _batch("null-size", "task", now, published_at=now.isoformat(), archive_size=None),
                _batch("building", "task", now, status="building", archive_size=7),
            ]
        )

    today = now.astimezone(ZoneInfo(settings.TZ)).date()
    assert store.daily_archive_bytes(today) == 8_000_000_000


def test_local_archives_returns_full_snapshots_only_for_artifacts_still_on_disk(
    store: Store, tmp_path: Path
) -> None:
    now = datetime.now(timezone.utc)
    present = tmp_path / "present.7z"
    present.write_bytes(b"archive")
    with store.handle.session() as session, session.begin():
        session.add_all(
            [
                _batch("present", "task", now, archive_path=str(present), entries=[{"relative_path": "a"}]),
                _batch("moved", "task", now, archive_path=str(tmp_path / "moved.7z")),
                _batch("unbuilt", "task", now, status="building"),
                _batch("other-task", "other", now, archive_path=str(present)),
            ]
        )

    assert store.local_archives("task") == [store.get("present")]
    assert store.local_archives("missing-task") == []


def test_create_counts_task_and_global_sequences_from_same_local_day_only(
    store: Store, tmp_path: Path
) -> None:
    task = TaskConfig.model_validate(
        {
            "id": "seq-task",
            "name": "序号",
            "source_dir": str(tmp_path / "source"),
            "output_dir": str(tmp_path / "output"),
            "manifest_dir": str(tmp_path / "manifest"),
            "batch_name_template": "{sequence}-{global_sequence}",
        }
    )
    now = datetime.now(timezone.utc)
    with store.handle.session() as session, session.begin():
        session.add_all(
            [
                _batch("same-1", task.id, now),
                _batch("same-2", task.id, now),
                _batch("other-today", "other", now),
                _batch("same-old", task.id, now - timedelta(days=2)),
            ]
        )

    batch = store.create("new-batch", task.public(), [], "目录结构")

    assert batch["batch_name"] == "000003-000004"


def _legacy_summary(store: Store) -> dict:
    """旧实现的整表载入口径，作为窄查询结果的对照。"""
    with store.handle.session() as session:
        rows = list(session.scalars(select(BatchRow)))
        completed = [row for row in rows if row.status in ("completed", "cleaning", "cleanup_failed")]
        today = datetime.now(tz=ZoneInfo(settings.TZ)).date()
        completed_today = [
            row
            for row in completed
            if store._published_on_local_day(  # pylint: disable=protected-access
                row.status, row.created_at, row.data.get("published_at"), today
            )
        ]
        return {
            "archived_files": sum(row.data["file_count"] for row in completed),
            "archive_count": len(completed),
            "source_bytes": sum(row.data["source_bytes"] for row in completed),
            "archive_bytes": sum(row.data["archive_size"] for row in completed),
            "today_archived_files": sum(row.data["file_count"] for row in completed_today),
            "today_archive_count": len(completed_today),
            "today_archive_bytes": sum(row.data["archive_size"] for row in completed_today),
            "failed_batches": sum(
                row.status in ("failed", "manifest_pending", "cleanup_failed") for row in rows
            ),
        }


def test_summary_matches_full_snapshot_totals_across_local_day_boundary_and_large_sizes(
    store: Store,
) -> None:
    local_timezone = ZoneInfo(settings.TZ)
    midnight = datetime.now(local_timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    just_after = (midnight + timedelta(seconds=1)).astimezone(timezone.utc)
    just_before = (midnight - timedelta(seconds=1)).astimezone(timezone.utc)

    def published(batch_id: str, status: str, created: datetime, published_at: datetime | None, size: int):
        extra = {"published_at": published_at.isoformat()} if published_at else {}
        return _batch(
            batch_id,
            "task",
            created,
            status=status,
            file_count=32,
            source_bytes=size * 2,
            archive_size=size,
            **extra,
        )

    with store.handle.session() as session, session.begin():
        session.add_all(
            [
                published("today-large", "completed", just_before, just_after, 5_000_000_000),
                published("yesterday", "completed", just_before, just_before, 3_000_000_000),
                published("legacy-today", "cleaning", just_after, None, 7),
                published("cleanup-failed", "cleanup_failed", just_after, just_after, 11),
                published("failed", "failed", just_after, None, 13),
                published("manifest", "manifest_pending", just_after, just_after, 17),
                published("building", "building", just_after, None, 19),
            ]
        )

    summary = store.summary()

    assert {key: summary[key] for key in _legacy_summary(store)} == _legacy_summary(store)
    assert summary["archive_count"] == 4
    assert summary["archive_bytes"] == 8_000_000_018
    assert summary["source_bytes"] == 16_000_000_036
    assert summary["today_archive_count"] == 3
    assert summary["today_archive_bytes"] == 5_000_000_018
    assert summary["today_archived_files"] == 96
    assert summary["failed_batches"] == 3


def test_staging_tasks_reads_task_snapshots_in_listing_order(store: Store, tmp_path: Path) -> None:
    def config(output: str, name: str) -> TaskConfig:
        return TaskConfig.model_validate(
            {
                "id": "staging-task",
                "name": name,
                "source_dir": str(tmp_path / "source"),
                "output_dir": str(tmp_path / output),
                "manifest_dir": str(tmp_path / "manifest"),
            }
        )

    current = config("current", "当前")
    now = datetime.now(timezone.utc)
    with store.handle.session() as session, session.begin():
        session.add_all(
            [
                _batch("old-a", "staging-task", now - timedelta(hours=2), task=config("old", "旧名").public()),
                _batch("old-b", "staging-task", now - timedelta(hours=1), task=config("old", "新名").public()),
                _batch("unfinished", "staging-task", now, status="building", task=current.public()),
                _batch("broken", "staging-task", now, task={"id": "broken"}),
                BatchRow(id="no-task", task_id="x", status="completed", created_at=now.isoformat(), data={}),
            ]
        )
    manager = manager_module.ArchiveManager()
    manager._tasks = [current]  # pylint: disable=protected-access
    manager._store = lambda: store  # pylint: disable=protected-access

    result = manager._staging_tasks()  # pylint: disable=protected-access

    # 旧实现按完整批次列表逐条读取 task 快照；新查询必须给出相同的任务、输出目录与保留批次。
    legacy: dict[tuple[str, str], tuple[TaskConfig, set[str]]] = {(current.id, current.output_dir): (current, set())}
    for batch in store.batches(page=1, page_size=100000)["items"]:
        try:
            task = manager._snapshot_task_for_maintenance(batch.get("task") or {})  # pylint: disable=protected-access
        except (TypeError, ValueError):
            continue
        legacy.setdefault((task.id, task.output_dir), (task, set()))
    expected = [(task, {batch["id"] for batch in store.unfinished(task.id)}) for task, _ in legacy.values()]
    assert result == expected
    by_output = {task.output_dir: (task.name, keep) for task, keep in result}
    assert by_output[str(tmp_path / "current")] == ("当前", {"unfinished"})
    assert by_output[str(tmp_path / "old")] == ("新名", {"unfinished"})
    assert list(store.task_snapshots()) == [
        batch.get("task") or {} for batch in store.batches(page=1, page_size=100000)["items"]
    ]
