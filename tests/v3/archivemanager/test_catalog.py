"""独立清单目录、批次布局和共享根索引测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.plugins.archivemanager.catalog import rebuild_root_index, write_catalog


pytestmark = pytest.mark.v3


def _task(
    manifest_dir: Path,
    *,
    task_id: str,
    name: str = "相机归档",
    source_dir: str = "/data/sata1/Camera",
    archive_layout: str = "directory",
    grouping: str = "directory",
) -> dict:
    return {
        "id": task_id,
        "name": name,
        "source_dir": source_dir,
        "manifest_dir": str(manifest_dir),
        "archive_layout": archive_layout,
        "grouping": grouping,
        "timezone": "UTC",
        "format": "7z",
        "compression": "normal",
        "encryption": "none",
        "password_version": "1",
    }


def _batch(
    task: dict,
    *,
    batch_id: str,
    batch_name: str,
    group: str,
    archive_name: str | None = None,
    manifest_path: str = "",
) -> dict:
    archive_name = archive_name or f"{batch_name}.7z"
    created_at = "2026-01-28T00:01:00+00:00"
    return {
        "id": batch_id,
        "task_id": task["id"],
        "task_name": task["name"],
        "task": task,
        "group": group,
        "batch_name": batch_name,
        "status": "completed",
        "created_at": created_at,
        "archive_path": f"/backups/{archive_name}",
        "archive_size": 123,
        "archive_sha256": "b" * 64,
        "verified": True,
        "cleanup": {"one.mp4": "retained"},
        "manifest_path": manifest_path,
        "manifest": {
            "schema_version": 1,
            "batch_id": batch_id,
            "task_id": task["id"],
            "task_name": task["name"],
            "source_dir": task["source_dir"],
            "created_at": created_at,
            "timezone": "UTC",
            "format": task["format"],
            "compression": task["compression"],
            "encryption": task["encryption"],
            "password_version": task["password_version"],
            "files": [
                {
                    "relative_path": "one.mp4",
                    "size": 3,
                    "mtime_ns": 1,
                    "sha256": "a" * 64,
                }
            ],
        },
    }


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_directory_layout_mirrors_group_and_batch_and_recurses_links(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    task = _task(root, task_id="disk-1")
    batch = _batch(
        task,
        batch_id="internal-1",
        batch_name="20260128_0001",
        group="XiaomiCamera_00_B888801B9BCD",
    )
    batch["manifest"].pop("source_dir")

    markdown = Path(write_catalog(batch))
    task_dir = root / "相机归档"
    batch_dir = task_dir / "XiaomiCamera_00_B888801B9BCD" / "20260128_0001"
    assert markdown == batch_dir / "manifest.md"
    assert (batch_dir / "manifest.json").is_file()

    task_index = _json(task_dir / "index.json")
    assert task_index["task_id"] == "disk-1"
    assert task_index["batches"][0]["manifest_path"] == (
        "XiaomiCamera_00_B888801B9BCD/20260128_0001/manifest.md"
    )
    root_index = _json(root / "index.json")
    assert root_index["batches"][0]["manifest_path"] == (
        "相机归档/XiaomiCamera_00_B888801B9BCD/20260128_0001/manifest.md"
    )
    root_markdown = (root / "index.md").read_text(encoding="utf-8")
    assert "/data/sata1/Camera" in root_markdown
    assert "XiaomiCamera_00_B888801B9BCD/20260128_0001/manifest.md" in root_markdown


def test_flat_layout_joins_group_and_batch_below_task_directory(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    task = _task(root, task_id="disk-1", archive_layout="flat", grouping="directory_date")
    batch = _batch(
        task,
        batch_id="internal-flat",
        batch_name="20260128_0001",
        group="XiaomiCamera_00_B888801B9BCD | 20260128",
    )

    markdown = Path(write_catalog(batch))
    assert markdown == root / "相机归档" / "XiaomiCamera_00_B888801B9BCD_20260128_0001" / "manifest.md"


def test_same_task_name_uses_readable_suffix_and_reuses_by_task_id(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    first_task = _task(root, task_id="disk-1", source_dir="/data/sata1/Camera")
    second_task = _task(root, task_id="disk-2", source_dir="/data/sata2/Camera")
    first = _batch(first_task, batch_id="first", batch_name="20260128_0001", group="camera")
    second = _batch(second_task, batch_id="second", batch_name="20260128_0001", group="camera")

    first_path = Path(write_catalog(first))
    second_path = Path(write_catalog(second))
    assert first_path.parts[-4:] == ("相机归档", "camera", "20260128_0001", "manifest.md")
    assert second_path.parts[-4:] == ("相机归档 (2)", "camera", "20260128_0001", "manifest.md")
    assert "disk-1" not in first_path.as_posix()
    assert "disk-2" not in second_path.as_posix()

    renamed = {**first, "task_name": "改过的显示名", "task": {**first_task, "name": "改过的显示名"}}
    reused = Path(write_catalog(renamed))
    assert reused == first_path

    root_index = _json(root / "index.json")
    assert {item["source_dir"] for item in root_index["batches"]} == {
        "/data/sata1/Camera",
        "/data/sata2/Camera",
    }
    root_markdown = (root / "index.md").read_text(encoding="utf-8")
    assert "/data/sata1/Camera" in root_markdown
    assert "/data/sata2/Camera" in root_markdown
    assert "disk-1" not in root_markdown
    assert "disk-2" not in root_markdown


def test_batch_name_collision_gets_numeric_suffix_and_manifest_path_wins(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    task = _task(root, task_id="disk-1")
    first = _batch(task, batch_id="first", batch_name="20260128", group="camera")
    second = _batch(task, batch_id="second", batch_name="20260128", group="camera")

    first_path = Path(write_catalog(first))
    second_path = Path(write_catalog(second))
    assert second_path.parent.name == "20260128 (2)"

    updated = {
        **first,
        "batch_name": "renamed-after-publish",
        "manifest_path": str(first_path),
    }
    assert Path(write_catalog(updated)) == first_path
    assert "renamed-after-publish" in first_path.read_text(encoding="utf-8")
    assert not (first_path.parent.parent / "renamed-after-publish").exists()


def test_existing_manifest_path_rebuilds_original_root_after_manifest_dir_change(tmp_path: Path) -> None:
    old_root = tmp_path / "old-catalog"
    new_root = tmp_path / "new-catalog"
    old_task = _task(old_root, task_id="disk-1")
    first = _batch(old_task, batch_id="first", batch_name="20260128_0001", group="camera")
    first_path = Path(write_catalog(first))

    # 模拟任务索引尚未恢复，但批次清单仍在原目录；新配置指向另一清单根。
    (old_root / "相机归档" / "index.json").unlink()
    (old_root / "相机归档" / "index.md").unlink()
    resumed_task = {**old_task, "manifest_dir": str(new_root)}
    resumed = {
        **first,
        "task": resumed_task,
        "manifest_path": str(first_path),
    }
    assert Path(write_catalog(resumed)) == first_path
    assert (old_root / "相机归档" / "index.json").is_file()
    assert not new_root.exists()


def test_root_index_rebuilds_missing_task_indexes_from_batch_manifests(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    first_task = _task(root, task_id="disk-1", source_dir="/data/sata1/Camera")
    second_task = _task(root, task_id="disk-2", source_dir="/data/sata2/Camera")
    write_catalog(_batch(first_task, batch_id="first", batch_name="20260128_0001", group="camera"))
    write_catalog(_batch(second_task, batch_id="second", batch_name="20260128_0001", group="camera"))

    for task_dir in (root / "相机归档", root / "相机归档 (2)"):
        (task_dir / "index.json").unlink()
        (task_dir / "index.md").unlink()
    (root / "index.json").unlink()
    (root / "index.md").unlink()

    rebuild_root_index(root)

    assert (root / "相机归档" / "index.json").is_file()
    assert (root / "相机归档 (2)" / "index.json").is_file()
    root_index = _json(root / "index.json")
    assert {item["task_id"] for item in root_index["batches"]} == {"disk-1", "disk-2"}
    assert {item["source_dir"] for item in root_index["batches"]} == {
        "/data/sata1/Camera",
        "/data/sata2/Camera",
    }


def test_root_index_refreshes_existing_task_index_when_new_manifest_is_present(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    task = _task(root, task_id="disk-1")
    first = _batch(task, batch_id="first", batch_name="20260128_0001", group="camera")
    write_catalog(first)

    second = _batch(task, batch_id="second", batch_name="20260128_0002", group="camera")
    second_record = {
        **second["manifest"],
        "source_dir": task["source_dir"],
        "batch_name": second["batch_name"],
        "archive_name": Path(second["archive_path"]).name,
        "archive_path": second["archive_path"],
        "archive_size": second["archive_size"],
        "archive_sha256": second["archive_sha256"],
        "verified": second["verified"],
        "cleanup": second["cleanup"],
        "status": second["status"],
    }
    second_manifest = root / "相机归档" / "camera" / "20260128_0002" / "manifest.json"
    second_manifest.parent.mkdir(parents=True)
    second_manifest.write_text(json.dumps(second_record, ensure_ascii=False), encoding="utf-8")

    rebuild_root_index(root)

    task_index = _json(root / "相机归档" / "index.json")
    root_index = _json(root / "index.json")
    assert {item["batch_id"] for item in task_index["batches"]} == {"first", "second"}
    assert {item["batch_id"] for item in root_index["batches"]} == {"first", "second"}
