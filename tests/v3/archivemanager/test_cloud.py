"""ArchiveManager 云端证明与按证明回收的行为测试。"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import app.plugins.archivemanager as manager_module
import app.plugins.archivemanager.runner as runner_module
import pytest
from app.db.plugin.container import PluginDatabaseHandle
from app.plugins.archivemanager.config import PluginConfig, TaskConfig
from app.plugins.archivemanager.runner import Runner
from app.plugins.archivemanager.scanner import identity
from app.plugins.archivemanager.store import Base, BatchRow, Store
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

pytestmark = pytest.mark.v3


@pytest.fixture
def store(tmp_path: Path):
    """每个用例使用独立插件库，避免批次账本互相影响。"""
    db_path = tmp_path / "archive.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 20})
    factory = sessionmaker(bind=engine)
    handle = PluginDatabaseHandle(
        plugin_id="archivemanager-cloud-test",
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


def _task(tmp_path: Path, **overrides) -> TaskConfig:
    source = tmp_path / "source"
    source.mkdir(parents=True, exist_ok=True)
    values = {
        "id": "cloud-task",
        "name": "云端回收测试",
        "enabled": True,
        "source_dir": str(source),
        "output_dir": str(tmp_path / "output"),
        "manifest_dir": str(tmp_path / "manifest"),
        "archive_age_days": 0,
        "stability_seconds": 1,
        "max_pending_archives": 0,
        "max_pending_bytes": 0,
        "min_free_bytes": 0,
    }
    values.update(overrides)
    return TaskConfig.model_validate(values)


def _entry(source: Path, relative_path: str, content: bytes) -> dict:
    path = source / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "relative_path": relative_path,
        "source_root": str(source.resolve()),
        **identity(path),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _published_batch(
    store: Store,
    task: TaskConfig,
    batch_id: str,
    relative_path: str,
    *,
    archive_sha1: str | None = "a" * 40,
    archive_size: int = 101,
    archive_path: Path | None = None,
    content: bytes | None = None,
) -> dict:
    """创建带已发布清单的账本批次，可选择构造 0.1.6 前的旧摘要结构。"""
    content = content or f"source:{batch_id}".encode()
    entry = _entry(Path(task.source_dir), relative_path, content)
    assert store.inventory(task.id, [entry], task.source_dir, task.public()) == [entry]
    batch = store.create(batch_id, task.public(), [entry], "全部文件")
    path = archive_path or (Path(task.output_dir) / f"{batch_id}.7z")
    manifest = {
        "schema_version": 1,
        "batch_id": batch_id,
        "task_id": task.id,
        "task_name": task.name,
        "created_at": batch["created_at"],
        "files": [entry],
    }
    changes = {
        "archive_path": str(path),
        "archive_size": archive_size,
        "archive_sha256": "b" * 64,
        "verified": True,
        "manifest_path": str(Path(task.manifest_dir) / f"{batch_id}.json"),
        "manifest": manifest,
    }
    if archive_sha1 is not None:
        changes["archive_sha1"] = archive_sha1
    batch = store.save(batch["id"], status="completed", **changes)
    if archive_sha1 is None:
        with store.handle.session() as session, session.begin():
            row = session.get(BatchRow, batch_id)
            data = dict(row.data)
            data.pop("archive_sha1", None)
            row.data = data
    store.complete_files(batch)
    return store.get(batch_id)


def _attest(manager, source: str, items: list[dict]):
    request = manager_module.CloudAttestRequest.model_validate({"source": source, "items": items})
    return manager.api_cloud_attest(request)


def _attest_item(batch: dict, *, sha1: str, size: int | None = None, upload_sha1: str = "") -> dict:
    return {
        "archive_path": batch["archive_path"],
        "cloud_path": f"/Home/archive/{batch['id']}.7z",
        "size": batch["archive_size"] if size is None else size,
        "sha1": sha1,
        "upload_sha1": upload_sha1,
    }


def _runner(store: Store, *, allow_legacy: bool = False, verify_sha256: bool = False) -> Runner:
    return Runner(
        store,
        Event(),
        lambda *_args: None,
        reclaim_legacy_by_upload_record=allow_legacy,
        reclaim_verify_sha256=verify_sha256,
    )


def test_cloud_attest_classifies_records_is_case_insensitive_and_skips_unchanged_writes(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    verified_sha1 = "ab" * 20
    verified = _published_batch(store, task, "verified", "verified.txt", archive_sha1=verified_sha1)
    conflict_a = _published_batch(store, task, "conflict-a", "conflict-a.txt", archive_sha1="2" * 40)
    conflict_b = _published_batch(store, task, "conflict-b", "conflict-b.txt", archive_sha1="3" * 40)
    legacy = _published_batch(store, task, "legacy", "legacy.txt", archive_sha1=None)
    unproven = _published_batch(store, task, "unproven", "unproven.txt", archive_sha1=None)
    manager = manager_module.ArchiveManager()
    manager._settings = PluginConfig(notify=True, notify_events=["failure"])
    messages: list[dict] = []
    monkeypatch.setattr(manager, "_store", lambda: store)
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))
    items = [
        _attest_item(verified, sha1=verified_sha1.upper()),
        _attest_item(conflict_a, sha1="f" * 40),
        _attest_item(conflict_b, sha1="e" * 40, size=conflict_b["archive_size"] + 1),
        _attest_item(legacy, sha1="a" * 40, upload_sha1="A" * 40),
        _attest_item(unproven, sha1="a" * 40),
        {
            "archive_path": str(tmp_path / "unknown.7z"),
            "cloud_path": "/Home/archive/unknown.7z",
            "size": 1,
            "sha1": "f" * 40,
            "upload_sha1": "",
        },
    ]
    updates = {"rows": 0}

    def record_batch_update(_connection, _cursor, statement, parameters, _context, many) -> None:
        if statement.lstrip().upper().startswith("UPDATE ARCHIVE_BATCH"):
            updates["rows"] += len(parameters) if many else 1

    event.listen(store.handle.engine, "before_cursor_execute", record_batch_update)
    try:
        response = _attest(manager, "muvyo-115", items)
        assert response.success is True
        assert response.data == {
            "verified": 1,
            "legacy": 1,
            "conflict": 2,
            "unproven": 1,
            "unknown": 1,
        }
        assert len(messages) == 1
        assert "conflict-a" in messages[0]["text"]
        assert "conflict-b" in messages[0]["text"]

        first_updates = updates["rows"]
        assert first_updates == 5
        cloud_verified = store.get(verified["id"])["cloud"]
        cloud_legacy = store.get(legacy["id"])["cloud"]
        assert cloud_verified["status"] == "verified"
        assert cloud_verified["sha1"] == verified_sha1
        assert cloud_verified["size"] == verified["archive_size"]
        assert cloud_verified["cloud_path"] == f"/Home/archive/{verified['id']}.7z"
        assert cloud_verified["source"] == "muvyo-115"
        assert cloud_verified["confirmed_at"]
        assert cloud_legacy["status"] == "legacy"
        assert cloud_legacy["confirmed_at"]

        updates["rows"] = 0
        second = _attest(manager, "muvyo-115", items)
        assert second.data == response.data
        assert updates["rows"] == 0
        assert store.get(verified["id"])["cloud"]["attested_at"] == cloud_verified["attested_at"]
        assert store.get(verified["id"])["cloud"]["confirmed_at"] == cloud_verified["confirmed_at"]

        cleared = _attest(manager, "muvyo-115", [_attest_item(conflict_a, sha1="2" * 40)])
        assert cleared.data["verified"] == 1
        recovered = store.get(conflict_a["id"])["cloud"]
        assert recovered["status"] == "verified"
        assert recovered["confirmed_at"]
    finally:
        event.remove(store.handle.engine, "before_cursor_execute", record_batch_update)


def test_cloud_attest_route_uses_api_key_while_other_routes_keep_bear_auth() -> None:
    routes = {route["path"]: route for route in manager_module.ArchiveManager().get_api()}

    assert routes["/cloud/attest"]["methods"] == ["POST"]
    assert routes["/cloud/attest"]["auth"] == "apikey"
    assert routes["/reclaim"]["auth"] == "bear"
    assert routes["/batches"]["auth"] == "bear"


def test_cloud_attest_rejects_size_and_upload_digest_mismatches_and_tracks_confirmation_lifecycle(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    size_conflict = _published_batch(
        store, task, "size-conflict", "size-conflict.txt", archive_sha1="ab" * 20
    )
    legacy_size = _published_batch(store, task, "legacy-size", "legacy-size.txt", archive_sha1=None)
    legacy_digest = _published_batch(store, task, "legacy-digest", "legacy-digest.txt", archive_sha1=None)
    timestamped = _published_batch(store, task, "timestamped", "timestamped.txt", archive_sha1="cd" * 20)
    manager = manager_module.ArchiveManager()
    monkeypatch.setattr(manager, "_store", lambda: store)
    first = _attest(
        manager,
        "muvyo-115",
        [
            _attest_item(size_conflict, sha1="ab" * 20, size=size_conflict["archive_size"] + 1),
            _attest_item(legacy_size, sha1="12" * 20, upload_sha1="12" * 20, size=legacy_size["archive_size"] + 1),
            _attest_item(legacy_digest, sha1="12" * 20, upload_sha1="34" * 20),
            _attest_item(timestamped, sha1="CD" * 20),
        ],
    )

    assert first.data == {
        "verified": 1,
        "legacy": 0,
        "conflict": 1,
        "unproven": 2,
        "unknown": 0,
    }
    assert store.get(size_conflict["id"])["cloud"]["status"] == "conflict"
    assert store.get(legacy_size["id"])["cloud"]["status"] == "unproven"
    assert store.get(legacy_digest["id"])["cloud"]["status"] == "unproven"
    assert store.get(legacy_size["id"])["cloud"]["confirmed_at"] is None
    assert store.get(legacy_digest["id"])["cloud"]["confirmed_at"] is None

    original = store.get(timestamped["id"])["cloud"]
    old_confirmed = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    store.save(
        timestamped["id"],
        cloud={**original, "confirmed_at": old_confirmed, "attested_at": old_confirmed},
    )
    changed_metadata = _attest_item(timestamped, sha1="cd" * 20)
    changed_metadata["cloud_path"] = "/Home/archive/renamed-location.7z"
    _attest(manager, "muvyo-115-daily", [changed_metadata])
    after_metadata_change = store.get(timestamped["id"])["cloud"]

    assert after_metadata_change["status"] == "verified"
    assert after_metadata_change["source"] == "muvyo-115-daily"
    assert after_metadata_change["cloud_path"] == "/Home/archive/renamed-location.7z"
    assert after_metadata_change["confirmed_at"] == old_confirmed
    assert after_metadata_change["attested_at"] != old_confirmed

    _attest(manager, "muvyo-115", [_attest_item(timestamped, sha1="ef" * 20)])
    conflicted = store.get(timestamped["id"])["cloud"]
    assert conflicted["status"] == "conflict"
    assert conflicted["confirmed_at"] is None

    _attest(manager, "muvyo-115", [_attest_item(timestamped, sha1="cd" * 20)])
    reconfirmed = store.get(timestamped["id"])["cloud"]
    assert reconfirmed["status"] == "verified"
    assert reconfirmed["confirmed_at"]
    assert datetime.fromisoformat(reconfirmed["confirmed_at"]) > datetime.fromisoformat(old_confirmed)


def test_cloud_attest_request_validates_source_item_limit_size_and_sha1() -> None:
    valid_item = {
        "archive_path": "/volume1/archive.7z",
        "cloud_path": "/Home/archive.7z",
        "size": 1,
        "sha1": "a" * 40,
        "upload_sha1": "",
    }
    with pytest.raises(ValidationError):
        manager_module.CloudAttestRequest.model_validate({"source": "x" * 65, "items": []})
    with pytest.raises(ValidationError):
        manager_module.CloudAttestRequest.model_validate({"source": "muvyo-115", "items": [valid_item] * 5001})
    for field, value in (("size", -1), ("sha1", "a" * 39), ("upload_sha1", "bad")):
        with pytest.raises(ValidationError):
            manager_module.CloudAttestRequest.model_validate(
                {"source": "muvyo-115", "items": [{**valid_item, field: value}]}
            )


def test_sha256_option_rereads_sources_and_retains_content_mismatch(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    batch = _published_batch(
        store,
        task,
        "moved-verified",
        "unchanged.txt",
        archive_sha1="d" * 40,
        content=b"unchanged source",
    )
    changed_path = Path(task.source_dir) / "changed.txt"
    changed_entry = _entry(Path(task.source_dir), "changed.txt", b"original bytes")
    assert store.inventory(task.id, [changed_entry], task.source_dir, task.public()) == [changed_entry]
    second = store.create("moved-changed", task.public(), [changed_entry], "全部文件")
    second_manifest = {
        "schema_version": 1,
        "batch_id": second["id"],
        "task_id": task.id,
        "task_name": task.name,
        "created_at": second["created_at"],
        "files": [changed_entry],
    }
    second = store.save(
        second["id"],
        status="completed",
        archive_path=str(Path(task.output_dir) / "moved-changed.7z"),
        archive_size=200,
        archive_sha256="b" * 64,
        archive_sha1="e" * 40,
        verified=True,
        manifest_path=str(Path(task.manifest_dir) / "moved-changed.json"),
        manifest=second_manifest,
    )
    store.complete_files(second)
    changed_path.write_bytes(b"changed bytes!")
    os.utime(changed_path, ns=(changed_entry["mtime_ns"], changed_entry["mtime_ns"]))
    for batch_data in (batch, store.get(second["id"])):
        assert store.attest_cloud(
            "muvyo-115",
            [_attest_item(batch_data, sha1=batch_data["archive_sha1"])],
        )[0]["verified"] == 1
    monkeypatch.setattr(runner_module, "write_catalog", lambda _batch: None)

    _runner(store, verify_sha256=True).reclaim(store.get(batch["id"]), task)
    _runner(store, verify_sha256=True).reclaim(store.get(second["id"]), task)

    assert not (Path(task.source_dir) / "unchanged.txt").exists()
    assert changed_path.read_bytes() == b"changed bytes!"
    assert store.get(batch["id"])["cleanup"]["unchanged.txt"] == "deleted"
    assert store.get(second["id"])["cleanup"]["changed.txt"] == "changed"
    assert store.get(second["id"])["status"] == "completed"


def test_unconfirmed_and_conflict_batches_are_skipped_without_state_or_notification_changes(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    unconfirmed = _published_batch(store, task, "unconfirmed", "unconfirmed.txt")
    conflict = _published_batch(store, task, "conflict", "conflict.txt", archive_sha1="c" * 40)
    store.attest_cloud("muvyo-115", [_attest_item(conflict, sha1="f" * 40)])
    store.set_task_state(task.id, active=True, phase="waiting_retry", reason="keep existing state")

    manager = manager_module.ArchiveManager()
    manager._settings = PluginConfig(notify=True, notify_events=["failure"])
    manager._enabled = True
    manager._tasks = [task]
    messages: list[dict] = []
    monkeypatch.setattr(manager, "_store", lambda: store)
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))
    monkeypatch.setattr(manager, "_start_worker", lambda: None)

    preview = manager.api_reclaim_preview(manager_module.ReclaimRequest())
    result = manager.api_reclaim(manager_module.ReclaimRequest())

    assert preview.success is True
    assert preview.data["batch_count"] == 0
    assert preview.data["estimated_bytes"] == 0
    assert preview.data["skipped_unconfirmed"] == 1
    assert preview.data["skipped_conflict"] == 1
    assert result.success is True
    assert result.data["found"] == 0
    assert result.data["queued"] == 0
    assert result.data["estimated_bytes"] == 0
    assert result.data["skipped_unconfirmed"] == 1
    assert result.data["skipped_conflict"] == 1
    assert list(manager._queue) == []
    assert messages == []
    assert store.task_state(task.id)["phase"] == "waiting_retry"
    assert store.task_state(task.id)["reason"] == "keep existing state"
    assert (Path(task.source_dir) / "unconfirmed.txt").is_file()
    assert (Path(task.source_dir) / "conflict.txt").is_file()

    with pytest.raises(ValueError, match="不能回收源文件"):
        _runner(store).reclaim(store.get(unconfirmed["id"]), task)
    assert (Path(task.source_dir) / "unconfirmed.txt").is_file()


def test_legacy_batches_require_the_option_and_can_be_reclaimed_when_enabled(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    batch = _published_batch(store, task, "legacy-reclaim", "legacy-source.txt", archive_sha1=None)
    result, conflicts = store.attest_cloud(
        "muvyo-115",
        [_attest_item(batch, sha1="a" * 40, upload_sha1="A" * 40)],
    )

    assert result["legacy"] == 1
    assert conflicts == []
    assert store.reclaimable_batches(allow_legacy=False) == []
    assert store.reclaim_selection(allow_legacy=False)[1]["skipped_legacy_disabled"] == 1
    with pytest.raises(ValueError, match="不能回收源文件"):
        _runner(store).reclaim(store.get(batch["id"]), task)
    assert (Path(task.source_dir) / "legacy-source.txt").is_file()

    monkeypatch.setattr(runner_module, "write_catalog", lambda _batch: None)
    assert [item["id"] for item in store.reclaimable_batches(allow_legacy=True)] == [batch["id"]]
    _runner(store, allow_legacy=True).reclaim(store.get(batch["id"]), task)

    assert not (Path(task.source_dir) / "legacy-source.txt").exists()
    assert store.get(batch["id"])["cleanup"]["legacy-source.txt"] == "deleted"


@pytest.mark.skipif(
    importlib.util.find_spec("py7zr") is None or importlib.util.find_spec("pyzipper") is None,
    reason="归档工作进程依赖未安装",
)
def test_local_archive_reclaim_still_hashes_archive_before_deleting_sources(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    archive = Path(task.output_dir) / "local.7z"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"local archive")
    archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive_sha1 = hashlib.sha1(archive.read_bytes()).hexdigest()
    batch = _published_batch(
        store,
        task,
        "local-archive",
        "local-source.txt",
        archive_sha1=archive_sha1,
        archive_path=archive,
    )
    batch = store.save(batch["id"], archive_sha256=archive_sha256)
    monkeypatch.setattr(runner_module, "write_catalog", lambda _batch: None)

    _runner(store).reclaim(batch, task)

    assert archive.is_file()
    assert not (Path(task.source_dir) / "local-source.txt").exists()
    assert store.get(batch["id"])["cleanup"]["local-source.txt"] == "deleted"


@pytest.mark.skipif(
    importlib.util.find_spec("py7zr") is None or importlib.util.find_spec("pyzipper") is None,
    reason="归档工作进程依赖未安装",
)
def test_real_archive_upload_attest_and_queued_reclaim_user_flow(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    """真实打包成品经外部移走和 API 对账后，由插件队列核验并回收源文件。"""
    task = _task(tmp_path, format="zip", delete_source=False)
    source_entry = _entry(Path(task.source_dir), "real-flow.txt", b"cloud reclaim end-to-end content")
    assert store.inventory(task.id, [source_entry], task.source_dir, task.public()) == [source_entry]
    batch = store.create("real-cloud-flow", task.public(), [source_entry], "全部文件")
    Runner(store, Event(), lambda *_args: None).execute(batch, task)
    published = store.get(batch["id"])
    archive = Path(published["archive_path"])

    assert published["status"] == "completed"
    assert published["verified"] is True
    assert published["archive_sha1"]
    assert archive.is_file()
    archive.unlink()

    manager = manager_module.ArchiveManager()
    manager._settings = PluginConfig(notify=True, notify_events=["failure"])
    manager._enabled = True
    manager._tasks = [task]
    messages: list[dict] = []
    monkeypatch.setattr(manager, "_store", lambda: store)
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))
    monkeypatch.setattr(manager, "_start_worker", lambda: None)
    attested = _attest(
        manager,
        "muvyo-115",
        [
            _attest_item(
                published,
                sha1=published["archive_sha1"].upper(),
                size=published["archive_size"],
            )
        ],
    )
    queued = manager.api_reclaim(manager_module.ReclaimRequest())

    assert attested.success is True
    assert attested.data["verified"] == 1
    assert queued.success is True
    assert queued.data["queued"] == 1
    manager._work()

    assert not archive.exists()
    assert not (Path(task.source_dir) / "real-flow.txt").exists()
    assert store.get(batch["id"])["cleanup"]["real-flow.txt"] == "deleted"
    assert messages == []


def test_encrypted_moved_batch_reclaims_through_plugin_queue_without_failure_notification(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path, encryption="aes256", password="private-test-password")
    batch = _published_batch(
        store,
        task,
        "encrypted-moved",
        "encrypted-source.txt",
        archive_sha1="a" * 40,
    )
    manager = manager_module.ArchiveManager()
    manager._settings = PluginConfig(notify=True, notify_events=["failure"])
    manager._enabled = True
    manager._tasks = [task]
    messages: list[dict] = []
    monkeypatch.setattr(manager, "_store", lambda: store)
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))
    monkeypatch.setattr(manager, "_start_worker", lambda: None)
    monkeypatch.setattr(runner_module, "write_catalog", lambda _batch: None)
    response = _attest(manager, "muvyo-115", [_attest_item(batch, sha1="a" * 40)])
    queued = manager.api_reclaim(manager_module.ReclaimRequest())

    assert response.data["verified"] == 1
    assert queued.success is True
    assert queued.data["queued"] == 1
    manager._work()

    assert not (Path(task.source_dir) / "encrypted-source.txt").exists()
    assert store.get(batch["id"])["cleanup"]["encrypted-source.txt"] == "deleted"
    assert messages == []


def test_auto_reclaim_queues_only_old_confirmations_and_respects_legacy_setting(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    batches = {
        name: _published_batch(store, task, name, f"{name}.txt", archive_sha1=None if name == "old-legacy" else "a" * 40)
        for name in ("old-verified", "recent-verified", "old-legacy", "old-conflict", "old-unconfirmed")
    }
    now = datetime.now(timezone.utc)

    def cloud(status: str, age_days: int | None) -> dict:
        old = now - timedelta(days=age_days) if age_days is not None else now
        return {
            "status": status,
            "sha1": "a" * 40,
            "size": 101,
            "cloud_path": "/Home/archive/item.7z",
            "source": "muvyo-115",
            "attested_at": old.isoformat(),
            "confirmed_at": old.isoformat() if status in ("verified", "legacy") else None,
        }

    for name, status, age_days in (
        ("old-verified", "verified", 6),
        ("recent-verified", "verified", 4),
        ("old-legacy", "legacy", 6),
        ("old-conflict", "conflict", None),
    ):
        store.save(batches[name]["id"], cloud=cloud(status, age_days))

    manager = manager_module.ArchiveManager()
    manager._enabled = True
    manager._settings = PluginConfig(auto_reclaim_days=5)
    monkeypatch.setattr(manager, "_store", lambda: store)
    monkeypatch.setattr(manager, "_start_worker", lambda: None)

    manager._auto_reclaim()

    assert [job["batch_id"] for job in manager._queue] == [batches["old-verified"]["id"]]

    manager._queue.clear()
    manager._settings = PluginConfig(auto_reclaim_days=5, reclaim_legacy_by_upload_record=True)
    manager._auto_reclaim()

    assert {job["batch_id"] for job in manager._queue} == {
        batches["old-verified"]["id"],
        batches["old-legacy"]["id"],
    }
    assert batches["old-unconfirmed"]["id"] not in {job["batch_id"] for job in manager._queue}


def test_reclaim_round_sends_one_summary_notification_after_the_queue_drains(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    first = _published_batch(store, task, "summary-a", "summary-a.txt", archive_sha1="a" * 40)
    second = _published_batch(store, task, "summary-b", "summary-b.txt", archive_sha1="b" * 40)
    pending = _published_batch(store, task, "summary-c", "summary-c.txt", archive_sha1="c" * 40)
    manager = manager_module.ArchiveManager()
    manager._settings = PluginConfig(notify=True, notify_events=["success", "failure"])
    manager._enabled = True
    manager._tasks = [task]
    messages: list[dict] = []
    monkeypatch.setattr(manager, "_store", lambda: store)
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))
    monkeypatch.setattr(manager, "_start_worker", lambda: None)
    monkeypatch.setattr(runner_module, "write_catalog", lambda _batch: None)
    _attest(manager, "muvyo-115", [_attest_item(first, sha1="a" * 40), _attest_item(second, sha1="b" * 40)])
    # 第二个批次的源文件在回收前被改写，应保留并计入"内容有变化"。
    (Path(task.source_dir) / "summary-b.txt").write_bytes(b"rewritten")

    queued = manager.api_reclaim(manager_module.ReclaimRequest())
    assert queued.data["queued"] == 2
    manager._work()

    assert len(messages) == 1
    assert messages[0]["title"] == "压缩归档：空间回收完成"
    text = messages[0]["text"]
    assert "来源：手动回收" in text
    assert "回收批次：2，跳过 0，失败 0" in text
    assert f"删除源文件：1 个，释放 {len(b'source:summary-a')} B" in text
    assert "未删除：内容有变化 1，已不存在 0，无权限 0" in text
    assert (Path(task.source_dir) / "summary-c.txt").exists()
    assert pending["id"] not in {job["batch_id"] for job in manager._queue}


def test_reclaim_summary_reports_failed_batches_as_failure(store: Store, tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path)
    batch = _published_batch(store, task, "summary-fail", "summary-fail.txt", archive_sha1="a" * 40)
    manager = manager_module.ArchiveManager()
    manager._settings = PluginConfig(notify=True, notify_events=["failure"])
    manager._enabled = True
    manager._tasks = [task]
    messages: list[dict] = []
    monkeypatch.setattr(manager, "_store", lambda: store)
    monkeypatch.setattr(manager, "post_message", lambda **message: messages.append(message))
    monkeypatch.setattr(manager, "_start_worker", lambda: None)
    _attest(manager, "muvyo-115", [_attest_item(batch, sha1="a" * 40)])
    manager.api_reclaim(manager_module.ReclaimRequest())

    def broken(*_args, **_kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(runner_module.Runner, "reclaim", broken)
    manager._work()

    titles = [message["title"] for message in messages]
    assert "压缩归档：空间回收有失败" in titles
    summary = next(message for message in messages if message["title"] == "压缩归档：空间回收有失败")
    assert "回收批次：0，跳过 0，失败 1" in summary["text"]


def test_reclaim_checks_identity_without_rereading_sources_by_default(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    kept = _published_batch(store, task, "identity-kept", "kept.txt", archive_sha1="a" * 40)
    rewritten = _published_batch(store, task, "identity-rewritten", "rewritten.txt", archive_sha1="b" * 40)
    for batch in (kept, rewritten):
        assert store.attest_cloud("muvyo-115", [_attest_item(batch, sha1=batch["archive_sha1"])])[0]["verified"] == 1
    # 改写会更新 ctime，身份核对即可发现，无需重读内容。
    (Path(task.source_dir) / "rewritten.txt").write_bytes(b"rewritten later")

    def no_digest(*_args, **_kwargs):
        raise AssertionError("默认回收不应重读源文件")

    monkeypatch.setattr(runner_module, "digest", no_digest)
    monkeypatch.setattr(runner_module, "write_catalog", lambda _batch: None)

    _runner(store).reclaim(store.get(kept["id"]), task)
    _runner(store).reclaim(store.get(rewritten["id"]), task)

    assert not (Path(task.source_dir) / "kept.txt").exists()
    assert store.get(kept["id"])["cleanup"]["kept.txt"] == "deleted"
    assert (Path(task.source_dir) / "rewritten.txt").read_bytes() == b"rewritten later"
    assert store.get(rewritten["id"])["cleanup"]["rewritten.txt"] == "changed"


def test_ctime_only_change_is_reclaimed_after_matching_sha256_and_rechecked_later(
    store: Store, tmp_path: Path, monkeypatch
) -> None:
    task = _task(tmp_path)
    same = _published_batch(store, task, "ctime-same", "same.txt", archive_sha1="a" * 40, content=b"same bytes")
    edited = _published_batch(store, task, "ctime-edited", "edited.txt", archive_sha1="b" * 40, content=b"old bytes")
    for batch in (same, edited):
        assert store.attest_cloud("muvyo-115", [_attest_item(batch, sha1=batch["archive_sha1"])])[0]["verified"] == 1
    monkeypatch.setattr(runner_module, "write_catalog", lambda _batch: None)
    same_path = Path(task.source_dir) / "same.txt"
    edited_path = Path(task.source_dir) / "edited.txt"
    edited_entry = edited["manifest"]["files"][0]
    # chmod 到同一权限只更新 ctime；另一个文件改写为等长内容后恢复 mtime，也只剩 ctime 不同。
    os.chmod(same_path, same_path.stat().st_mode & 0o7777)
    edited_path.write_bytes(b"new bytes")
    os.utime(edited_path, ns=(edited_entry["mtime_ns"], edited_entry["mtime_ns"]))

    _runner(store).reclaim(store.get(same["id"]), task)
    _runner(store).reclaim(store.get(edited["id"]), task)

    assert not same_path.exists()
    assert store.get(same["id"])["cleanup"]["same.txt"] == "deleted"
    assert edited_path.read_bytes() == b"new bytes"
    assert store.get(edited["id"])["cleanup"]["edited.txt"] == "changed"

    # 之前判为 changed 的文件在下次回收时重新判断，内容恢复一致后即可删除。
    edited_path.write_bytes(b"old bytes")
    os.utime(edited_path, ns=(edited_entry["mtime_ns"], edited_entry["mtime_ns"]))
    assert edited["id"] in {batch["id"] for batch in store.reclaimable_batches()}
    _runner(store).reclaim(store.get(edited["id"]), task)

    assert not edited_path.exists()
    assert store.get(edited["id"])["cleanup"]["edited.txt"] == "deleted"


def test_reclaim_preview_counts_only_files_still_waiting(store: Store, tmp_path: Path, monkeypatch) -> None:
    task = _task(tmp_path)
    batch = _published_batch(store, task, "preview-left", "left.txt", archive_sha1="a" * 40)
    assert store.attest_cloud("muvyo-115", [_attest_item(batch, sha1="a" * 40)])[0]["verified"] == 1
    manager = manager_module.ArchiveManager()
    manager._settings = PluginConfig()
    monkeypatch.setattr(manager, "_store", lambda: store)
    entry = batch["manifest"]["files"][0]
    before = manager.api_reclaim_preview(manager_module.ReclaimRequest()).data
    assert (before["batch_count"], before["file_count"], before["estimated_bytes"]) == (1, 1, entry["size"])

    # 清单里已删除的文件不再计入；只剩被保留的文件时批次仍可回收，但文件数和空间只算剩余部分。
    store.cleanup_results(batch["id"], {"left.txt": "deleted"})
    after = manager.api_reclaim_preview(manager_module.ReclaimRequest()).data
    assert (after["file_count"], after["estimated_bytes"]) == (0, 0)
