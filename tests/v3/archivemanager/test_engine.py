"""归档引擎契约测试：格式、加密、流式摘要和严格成员校验。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


# 依赖安装不属于插件仓测试门禁；未安装归档后端时只跳过引擎实测。
pytest.importorskip("py7zr")
pytest.importorskip("pyzipper")

_ENGINE_PATH = Path(__file__).parents[3] / "plugins.v3" / "archivemanager" / "engine.py"
_SPEC = importlib.util.spec_from_file_location("archivemanager_engine", _ENGINE_PATH)
assert _SPEC and _SPEC.loader
engine = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = engine
_SPEC.loader.exec_module(engine)


def _task(source: Path, archive_format: str = "7z", *, encryption: str = "none", encrypt_names: bool = False) -> dict:
    return {
        "id": "task-1",
        "name": "测试归档",
        "source_dir": str(source),
        "format": archive_format,
        "compression": "normal",
        "encryption": encryption,
        "encrypt_names": encrypt_names,
        "password": "secret-pass" if encryption == "aes256" else "",
        "password_version": "v1",
        "timezone": "Asia/Shanghai",
    }


def _entries(source: Path, *, include_special: bool = True) -> list[dict]:
    result = []
    for path in sorted(source.iterdir(), key=lambda item: item.name):
        if not include_special and ("\\" in path.name or "\n" in path.name):
            continue
        info = path.lstat()
        result.append(
            {
                "relative_path": path.name,
                "size": info.st_size,
                "mtime_ns": info.st_mtime_ns,
                "ctime_ns": info.st_ctime_ns,
                "device": info.st_dev,
                "inode": info.st_ino,
            }
        )
    return result


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "plain.txt").write_bytes(b"plain text\n" * 100)
    (source / "empty.bin").write_bytes(b"")
    (source / "literal\\name.bin").write_bytes(b"backslash")
    (source / "line\nname.bin").write_bytes(b"newline")
    return source


@pytest.mark.parametrize("archive_format", ["7z", "zip"])
@pytest.mark.parametrize("compression", ["store", "fast", "normal", "high"])
def test_eight_format_and_compression_combinations(source_dir: Path, tmp_path: Path, archive_format: str, compression: str):
    task = _task(source_dir, archive_format)
    task["compression"] = compression
    destination = tmp_path / f"archive-{archive_format}-{compression}"

    manifest = engine.build_archive(task, _entries(source_dir, include_special=False), destination, "batch-1")
    restored = engine.verify_archive(destination)

    assert restored == manifest
    assert manifest["schema_version"] == 1
    assert all(item["archive_path"].startswith("files/") for item in manifest["files"])
    assert "password" not in manifest


@pytest.mark.parametrize(
    ("archive_format", "encrypt_names"),
    [("7z", False), ("7z", True), ("zip", False)],
)
def test_encrypted_archives_verify_and_keep_password_out_of_manifest(
    source_dir: Path, tmp_path: Path, archive_format: str, encrypt_names: bool
):
    task = _task(source_dir, archive_format, encryption="aes256", encrypt_names=encrypt_names)
    destination = tmp_path / f"encrypted-{archive_format}-{encrypt_names}"

    manifest = engine.build_archive(task, _entries(source_dir, include_special=False), destination, "batch-encrypted")
    assert engine.verify_archive(destination, "secret-pass") == manifest
    assert "secret-pass" not in json.dumps(manifest, ensure_ascii=False)


def test_wrong_password_fails_without_echoing_password(source_dir: Path, tmp_path: Path):
    task = _task(source_dir, "zip", encryption="aes256")
    destination = tmp_path / "wrong-password.zip"
    engine.build_archive(task, _entries(source_dir, include_special=False), destination, "batch-password")

    with pytest.raises(Exception) as error:
        engine.verify_archive(destination, "wrong-secret")
    assert "wrong-secret" not in str(error.value)


def test_corruption_is_detected(source_dir: Path, tmp_path: Path):
    destination = tmp_path / "corrupt.7z"
    engine.build_archive(_task(source_dir), _entries(source_dir, include_special=False), destination, "batch-corrupt")
    data = bytearray(destination.read_bytes())
    data[len(data) // 2] ^= 0x01
    destination.write_bytes(data)

    with pytest.raises(Exception):
        engine.verify_archive(destination)


def test_special_names_and_gnu_checksum_escaping(source_dir: Path, tmp_path: Path):
    destination = tmp_path / "special.zip"
    manifest = engine.build_archive(_task(source_dir, "zip"), _entries(source_dir), destination, "batch-special")
    assert {item["relative_path"] for item in manifest["files"]} >= {"literal\\name.bin", "line\nname.bin"}
    assert engine.verify_archive(destination) == manifest

    with zipfile.ZipFile(destination) as archive:
        checksums = archive.read("SHA256SUMS")
    assert b"\\\\" in checksums
    assert b"\\n" in checksums
    parsed = engine._parse_sha256sums(checksums)
    assert "files/literal\\name.bin" in parsed
    assert "files/line\nname.bin" in parsed


def test_member_set_is_strict(source_dir: Path, tmp_path: Path):
    destination = tmp_path / "extra.zip"
    engine.build_archive(_task(source_dir, "zip"), _entries(source_dir), destination, "batch-extra")
    with zipfile.ZipFile(destination, "a") as archive:
        archive.writestr("unexpected.txt", b"unexpected")

    with pytest.raises(Exception, match="成员集合"):
        engine.verify_archive(destination)


def test_hashes_match_source_bytes(source_dir: Path, tmp_path: Path):
    destination = tmp_path / "hashes.7z"
    manifest = engine.build_archive(_task(source_dir), _entries(source_dir, include_special=False), destination, "batch-hashes")
    for item in manifest["files"]:
        assert item["sha256"] == hashlib.sha256((source_dir / item["relative_path"]).read_bytes()).hexdigest()
    assert engine.sha256_file(destination) == hashlib.sha256(destination.read_bytes()).hexdigest()


def test_stale_source_snapshot_is_rejected(source_dir: Path, tmp_path: Path):
    entries = _entries(source_dir, include_special=False)
    path = source_dir / "plain.txt"
    path.write_bytes(path.read_bytes() + b"changed")

    with pytest.raises(Exception, match="发生变化"):
        engine.build_archive(_task(source_dir), entries, tmp_path / "stale.7z", "batch-stale")


def test_source_symlink_and_symlink_parent_are_rejected(source_dir: Path, tmp_path: Path):
    target = source_dir / "plain.txt"
    link = source_dir / "link.txt"
    link.symlink_to(target)
    info = link.lstat()
    entries = [{
        "relative_path": "link.txt",
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
        "device": info.st_dev,
        "inode": info.st_ino,
    }]
    with pytest.raises(Exception):
        engine.build_archive(_task(source_dir), entries, tmp_path / "link.7z", "batch-link")


def test_cli_outputs_one_json_line_and_does_not_echo_password(source_dir: Path, tmp_path: Path):
    destination = tmp_path / "cli.zip"
    task = _task(source_dir, "zip", encryption="aes256")
    request = {
        "action": "build",
        "task": task,
        "entries": _entries(source_dir, include_special=False),
        "destination": str(destination),
        "batch_id": "batch-cli",
    }
    result = subprocess.run(
        [engine.sys.executable, str(_ENGINE_PATH)],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 1
    assert json.loads(result.stdout)["success"] is True

    wrong = subprocess.run(
        [engine.sys.executable, str(_ENGINE_PATH)],
        input=json.dumps({"action": "verify", "path": str(destination), "password": "wrong-secret"}),
        text=True,
        capture_output=True,
        check=False,
    )
    assert wrong.returncode != 0
    assert len(wrong.stdout.splitlines()) == 1
    assert "wrong-secret" not in wrong.stdout
