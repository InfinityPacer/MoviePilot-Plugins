"""ArchiveManager 批次循环内账本查询测试：只读窄列，结果与完整快照一致。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.db.plugin.container import PluginDatabaseHandle
from app.plugins.archivemanager.config import TaskConfig
from app.plugins.archivemanager.store import Base, BatchRow, Store
from app.sdk.config import settings
from sqlalchemy import create_engine
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
