"""设备编号漂移的去重兼容与真实归档后再扫描回归。"""

from datetime import datetime, timezone
from pathlib import Path
from threading import Event

import app.plugins.archivemanager.scanner as scanner_module
import pytest
from app.db.plugin.container import PluginDatabaseHandle
from app.plugins.archivemanager.config import TaskConfig
from app.plugins.archivemanager.planner import plan_cycle
from app.plugins.archivemanager.runner import Runner, run_engine
from app.plugins.archivemanager.scanner import (
    fingerprint,
    identity,
    identity_matches,
    scan_tree,
)
from app.plugins.archivemanager.store import (
    Base,
    BatchRow,
    DirectoryRow,
    FileRow,
    Store,
)
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import scoped_session, sessionmaker

pytestmark = pytest.mark.v3


@pytest.fixture(name="store")
def store_fixture(tmp_path: Path):
    db_path = tmp_path / "archive.db"
    engine = create_engine(f"sqlite:///{db_path}")
    factory = sessionmaker(bind=engine)
    handle = PluginDatabaseHandle(
        plugin_id="archivemanager-device-test", engine=engine, session_factory=factory,
        scoped_session_factory=scoped_session(factory), db_path=db_path, schema=None, owns_engine=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield Store(handle)
    finally:
        handle.scoped_session_factory.remove()
        handle.dispose()


def _entry(**overrides) -> dict:
    return {
        "source_root": "/recordings", "relative_path": "camera.mp4", "size": 123,
        "mtime_ns": 10, "ctime_ns": 20, "mode": 420, "birthtime_ns": None,
        "device": 64, "inode": 456, **overrides,
    }


def _published(store: Store, entries: list[dict], *, task_id="task", batch_id="published", published=True):
    with store.handle.session() as session, session.begin():
        session.add(BatchRow(
            id=batch_id, task_id=task_id, status="completed" if published else "building",
            created_at=datetime.now(timezone.utc).isoformat(),
            data={"archive_sha256": "a" * 64 if published else "", "entries": entries},
        ))
        session.add_all([
            FileRow(task_id=task_id, fingerprint=fingerprint(entry), relative_path=entry["relative_path"],
                    batch_id=batch_id, present=False, status="archived", data=entry, historical=False)
            for entry in entries
        ])


def test_old_fingerprint_is_reused_after_device_change_without_rewriting_identity(store: Store):
    original = _entry()
    _published(store, [original])
    moved = {**original, "device": 61}
    assert fingerprint(original) != fingerprint(moved)

    for _ in range(2):
        assert store.exclude_reserved("task", [moved]) == []
        assert store.inventory("task", [moved], "/recordings") == []

    with store.handle.session() as session:
        rows = list(session.scalars(select(FileRow)))
        assert len(rows) == 1
        assert rows[0].fingerprint == fingerprint(original)
        assert rows[0].data == original
        assert rows[0].present is True


@pytest.mark.parametrize(("field", "value"), [
    ("source_root", "/other"), ("relative_path", "other.mp4"), ("size", 124),
    ("mtime_ns", 11), ("ctime_ns", 21), ("mode", 384), ("birthtime_ns", 1), ("inode", 457),
])
def test_device_change_does_not_hide_another_file_version(store: Store, field, value):
    original = _entry()
    _published(store, [original])
    changed = {**original, "device": 61, field: value}
    assert store.exclude_reserved("task", [changed]) == [changed]
    assert store.inventory("task", [changed], changed["source_root"]) == [changed]


def test_another_task_and_incomplete_legacy_metadata_are_not_device_aliases(store: Store):
    original = _entry()
    _published(store, [original], task_id="other", batch_id="other")
    legacy = {key: value for key, value in original.items() if key != "mode"}
    _published(store, [legacy])
    moved = {**original, "device": 61}
    assert store.exclude_reserved("task", [moved]) == [moved]
    assert store.inventory("task", [moved], "/recordings") == [moved]


def test_existing_reserved_duplicates_do_not_generate_a_third_archive(store: Store):
    original = _entry()
    duplicate = {**original, "device": 61}
    _published(store, [original])
    _published(store, [duplicate], batch_id="duplicate")
    assert store.inventory("task", [duplicate], "/recordings") == []
    moved_again = {**original, "device": 62}
    assert store.inventory("task", [moved_again], "/recordings") == []
    assert store.exclude_reserved("task", [moved_again]) == []
    with store.handle.session() as session:
        assert len(list(session.scalars(select(FileRow)))) == 2


def test_unpublished_reservation_cannot_hide_a_version_after_device_change(store: Store):
    original = _entry()
    _published(store, [original], published=False)
    moved = {**original, "device": 61}
    assert store.exclude_reserved("task", [moved]) == [moved]
    assert store.inventory("task", [moved], "/recordings") == [moved]


def test_unreserved_pending_after_device_change_keeps_fingerprint_reservation_contract(store: Store):
    original = _entry()
    assert store.inventory("task", [original], "/recordings") == [original]
    moved = {**original, "device": 61}
    assert store.inventory("task", [moved], "/recordings") == [moved]
    task = TaskConfig.model_validate({
        "id": "task", "name": "录像", "source_dir": "/recordings",
        "output_dir": "/archives", "manifest_dir": "/manifests",
    })
    batch = store.create("new-device", task.public(), [moved], "全部文件")
    assert batch["entries"] == [moved]


def test_legacy_pending_duplicate_is_removed_without_blocking_history_or_content_changes(store: Store):
    original = _entry()
    _published(store, [original])
    moved = {**original, "device": 61}
    with store.handle.session() as session, session.begin():
        session.add(FileRow(
            task_id="task", fingerprint=fingerprint(moved), relative_path=moved["relative_path"],
            batch_id=None, present=True, status="pending", historical=True, data=moved,
        ))

    assert store.exclude_reserved("task", [moved]) == []
    assert store.inventory("task", [moved], "/recordings") == []
    assert store.task_state("task")["phase"] == "incremental"
    assert store.task_state("task")["history_remaining"] == 0
    with store.handle.session() as session:
        rows = list(session.scalars(select(FileRow)))
        assert len(rows) == 1
        assert rows[0].batch_id == "published"
        assert rows[0].data == original
        assert session.get(BatchRow, "published").data["entries"] == [original]

    assert store.inventory("task", [moved], "/recordings") == []
    changed = {**moved, "ctime_ns": 21, "size": 124}
    assert store.inventory("task", [changed], "/recordings") == [changed]
    task = TaskConfig.model_validate({
        "id": "task", "name": "录像", "source_dir": "/recordings",
        "output_dir": "/archives", "manifest_dir": "/manifests",
    })
    assert store.create("changed-content", task.public(), [changed], "全部文件")["entries"] == [changed]


def test_legacy_pending_directory_duplicate_is_removed_but_metadata_changes_remain_eligible(store: Store):
    original = {key: value for key, value in _entry(relative_path="folder").items() if key != "size"}
    moved = {**original, "device": 61}
    _published(store, [])
    with store.handle.session() as session, session.begin():
        for entry, batch_id in ((original, "published"), (moved, None)):
            session.add(DirectoryRow(
                task_id="task", fingerprint=fingerprint(entry), relative_path=entry["relative_path"],
                batch_id=batch_id, present=True, status="archived" if batch_id else "pending", data=entry,
            ))
    for _ in range(2):
        assert store.inventory_directories("task", [moved]) == []
    with store.handle.session() as session:
        rows = list(session.scalars(select(DirectoryRow)))
        assert len(rows) == 1
        assert rows[0].batch_id == "published"
        assert rows[0].data == original
    changed = {**moved, "ctime_ns": 21}
    assert store.inventory_directories("task", [changed]) == [changed]


def test_device_lookup_is_batched_instead_of_per_file(store: Store):
    originals = [_entry(relative_path=f"{number}.mp4") for number in range(1001)]
    _published(store, originals)
    moved = [{**entry, "device": 61} for entry in originals]
    queries = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("SELECT"):
            queries.append(statement)

    event.listen(store.handle.engine, "before_cursor_execute", capture)
    try:
        assert store.exclude_reserved("task", moved) == []
    finally:
        event.remove(store.handle.engine, "before_cursor_execute", capture)
    assert len(queries) == 6


@pytest.mark.parametrize(("field", "value"), [
    ("device", 61), ("source_root", "/other"), ("relative_path", "other"),
    ("mtime_ns", 11), ("ctime_ns", 21), ("mode", 384), ("birthtime_ns", 1), ("inode", 457),
])
def test_directory_dedup_only_accepts_device_drift(store: Store, field, value):
    directory = {key: value for key, value in _entry(relative_path="folder").items() if key != "size"}
    _published(store, [])
    with store.handle.session() as session, session.begin():
        session.add(DirectoryRow(
            task_id="task", fingerprint=fingerprint(directory), relative_path="folder",
            batch_id="published", present=False, status="archived", data=directory,
        ))
    current = {**directory, "device": 61, field: value}
    for _ in range(2):
        result = store.inventory_directories("task", [current])
        assert result == ([] if field == "device" else [current])
    if field == "device":
        with store.handle.session() as session:
            rows = list(session.scalars(select(DirectoryRow)))
            assert len(rows) == 1
            assert rows[0].present is True
            assert rows[0].data == directory


def test_unchanged_device_alias_does_not_rewrite_file_rows(store: Store):
    original = _entry()
    _published(store, [original])
    moved = {**original, "device": 61}
    assert store.inventory("task", [moved], "/recordings") == []
    writes = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith(("UPDATE archive_file", "INSERT INTO archive_file")):
            writes.append(statement)

    event.listen(store.handle.engine, "before_cursor_execute", capture)
    try:
        assert store.inventory("task", [moved], "/recordings") == []
    finally:
        event.remove(store.handle.engine, "before_cursor_execute", capture)
    assert writes == []


@pytest.mark.parametrize("legacy_pending", [False, True])
def test_real_worker_archive_then_device_change_produces_no_file_batches(
    store: Store, tmp_path: Path, monkeypatch, legacy_pending: bool,
):
    pytest.importorskip("py7zr")
    pytest.importorskip("pyzipper")
    source = tmp_path / "source"
    source.mkdir()
    folder = source / "folder"
    folder.mkdir()
    path = folder / "camera.mp4"
    path.write_bytes(b"recording contents" * 10)
    task = TaskConfig.model_validate({
        "id": "task", "name": "录像", "enabled": True,
        "source_dir": str(source), "output_dir": str(tmp_path / "output"),
        "manifest_dir": str(tmp_path / "manifest"), "archive_age_days": 0,
        "stability_seconds": 1, "min_free_bytes": 0, "delete_source": False,
    })
    first = plan_cycle(task, Event(), store, 10)
    assert first.eligible_files == 1
    batch = store.create(
        "real-batch", task.public(), first.groups[0]["entries"], "全部文件",
        directories=list(first.directory_map.values()),
    )
    Runner(store, Event(), lambda *_args: None).execute(batch, task)
    published = store.get(batch["id"])
    assert published["status"] == "completed"
    original_entry = published["entries"][0]
    actual_identity = identity
    original_init = scanner_module.FileEntry.__init__
    actual_directory_identity = scanner_module.directory_identity
    actual_directory_metadata = scanner_module._directory_identity

    def remounted_init(self, relative_path, source_root, info):
        original_init(self, relative_path, source_root, info)
        self.device += 1

    def remounted_identity(file_path):
        current = actual_identity(file_path)
        return {**current, "device": current["device"] + 1}

    def remounted_directory_identity(file_path):
        current = actual_directory_identity(file_path)
        return {**current, "device": current["device"] + 1}

    def remounted_directory_metadata(info):
        current = actual_directory_metadata(info)
        return {**current, "device": current["device"] + 1}

    monkeypatch.setattr(scanner_module.FileEntry, "__init__", remounted_init)
    monkeypatch.setattr(scanner_module, "identity", remounted_identity)
    monkeypatch.setattr(scanner_module, "directory_identity", remounted_directory_identity)
    monkeypatch.setattr(scanner_module, "_directory_identity", remounted_directory_metadata)
    # 稳定观察期间设备号一致才合格；旧身份仍不能通过严格身份检查。
    entries, _, skipped = scan_tree(task, Event(), stable=True)
    assert len(entries) == 1 and skipped == 0
    assert not identity_matches(path, original_entry)
    if legacy_pending:
        # 模拟旧版在设备编号变化后已扫描入库，但尚未创建重复批次时升级。
        with store.handle.session() as session, session.begin():
            moved = dict(entries[0])
            session.add(FileRow(
                task_id=task.id, fingerprint=fingerprint(moved), relative_path=moved["relative_path"],
                batch_id=None, present=True, historical=True, status="pending", data=moved,
            ))
            for original_directory in published["directories"]:
                directory = {**original_directory, "device": original_directory["device"] + 1}
                session.add(DirectoryRow(
                    task_id=task.id, fingerprint=fingerprint(directory), relative_path=directory["relative_path"],
                    batch_id=None, present=True, status="pending", data=directory,
                ))
    for _ in range(2):
        second = plan_cycle(task, Event(), store, 10)
        assert second.eligible_files == 0
        assert second.eligible_directories == 0
        assert second.groups == []
        assert store.task_state(task.id)["phase"] == "incremental"
    assert path.read_bytes() == b"recording contents" * 10
    assert store.get(batch["id"])["entries"] == published["entries"]
    restored = run_engine({"action": "verify", "path": published["archive_path"], "password": ""}, Event())
    assert restored == published["manifest"]
