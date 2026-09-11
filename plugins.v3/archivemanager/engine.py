"""独立归档引擎：流式构建、只读校验与不落盘读回验证。

本模块不保存密码，也不依赖插件实例状态。源文件在打包前后都会重新核对
设备号、inode、大小、mtime 和 ctime；实际写入归档的字节同时参与 SHA-256
计算，避免先算哈希再打包造成校验对象不一致。
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import py7zr
import pyzipper

_CHUNK_SIZE = 1024 * 1024
_MAX_METADATA_BYTES = 32 * 1024 * 1024
_IDENTITY_FIELDS = ("size", "mtime_ns", "ctime_ns", "device", "inode")
_ARCHIVE_FORMATS = {"7z", "zip"}
_COMPRESSION_LEVELS = {"store": None, "fast": 1, "normal": 6, "high": 9}
_SEVEN_ZIP_PRESETS = {"fast": 1, "normal": 5, "high": 9}
_METADATA_NAMES = frozenset(("manifest.md", "manifest.json", "SHA256SUMS"))


class ArchiveError(ValueError):
    """归档输入、源文件或制品校验失败。"""


def sha256_file(path: str | Path) -> str:
    """以固定大小分块读取文件并返回 SHA-256 十六进制摘要。"""

    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_task(task: Mapping[str, Any]) -> dict[str, Any]:
    """校验跨插件调用契约；密码只保留在本次进程内。"""

    if not isinstance(task, Mapping):
        raise ArchiveError("task 必须是对象")
    required = (
        "id",
        "name",
        "source_dir",
        "format",
        "compression",
        "encryption",
        "encrypt_names",
        "password",
        "password_version",
        "timezone",
    )
    missing = [key for key in required if key not in task]
    if missing:
        raise ArchiveError(f"task 缺少字段: {', '.join(missing)}")
    result = {key: task[key] for key in required}
    if not isinstance(result["id"], str) or not result["id"]:
        raise ArchiveError("task.id 必须是非空字符串")
    if not isinstance(result["name"], str) or not result["name"]:
        raise ArchiveError("task.name 必须是非空字符串")
    if not isinstance(result["source_dir"], (str, Path)):
        raise ArchiveError("task.source_dir 必须是路径")
    if result["format"] not in _ARCHIVE_FORMATS:
        raise ArchiveError("format 只支持 7z 或 zip")
    if result["compression"] not in _COMPRESSION_LEVELS:
        raise ArchiveError("compression 只支持 store、fast、normal、high")
    if result["encryption"] not in {"none", "aes256"}:
        raise ArchiveError("encryption 只支持 none 或 aes256")
    if not isinstance(result["encrypt_names"], bool):
        raise ArchiveError("encrypt_names 必须是布尔值")
    if not isinstance(result["password"], str):
        raise ArchiveError("password 必须是字符串")
    if not isinstance(result["password_version"], str):
        raise ArchiveError("password_version 必须是字符串")
    if not isinstance(result["timezone"], str):
        raise ArchiveError("timezone 必须是字符串")
    try:
        ZoneInfo(result["timezone"])
    except Exception as exc:
        raise ArchiveError("timezone 不是有效时区") from exc
    if result["encryption"] == "aes256" and not result["password"]:
        raise ArchiveError("启用 AES-256 时必须提供密码")
    if result["encrypt_names"] and (result["format"] != "7z" or result["encryption"] != "aes256"):
        raise ArchiveError("encrypt_names 仅适用于 7z AES-256")
    return result


def _validate_relative_path(value: Any) -> str:
    """保留反斜杠和换行等合法文件名，同时拒绝越界和空路径分量。"""

    if not isinstance(value, str) or not value:
        raise ArchiveError("relative_path 必须是非空字符串")
    if "\x00" in value or value.startswith("/"):
        raise ArchiveError("relative_path 不是安全的相对路径")
    components = value.split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise ArchiveError("relative_path 不能包含空路径分量或 ..")
    return value


def _prepare_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise ArchiveError("entries 必须是数组")
    prepared = []
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, Mapping):
            raise ArchiveError("entries 的每项必须是对象")
        missing = [key for key in ("relative_path", *_IDENTITY_FIELDS) if key not in item]
        if missing:
            raise ArchiveError(f"entry 缺少字段: {', '.join(missing)}")
        relative_path = _validate_relative_path(item["relative_path"])
        if relative_path in seen:
            raise ArchiveError(f"entry 重复: {relative_path!r}")
        seen.add(relative_path)
        identity: dict[str, Any] = {"relative_path": relative_path}
        for key in _IDENTITY_FIELDS:
            value = item[key]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ArchiveError(f"entry.{key} 必须是整数")
            if key == "size" and value < 0:
                raise ArchiveError("entry.size 不能为负数")
            identity[key] = value
        identity["archive_path"] = f"files/{relative_path}"
        identity["sha256"] = None
        prepared.append(identity)
    return sorted(prepared, key=lambda item: item["relative_path"])


def _archive_identity(stat_result: os.stat_result) -> dict[str, int]:
    return {
        "size": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
        "ctime_ns": stat_result.st_ctime_ns,
        "device": stat_result.st_dev,
        "inode": stat_result.st_ino,
    }


def _assert_identity(stat_result: os.stat_result, entry: Mapping[str, Any]) -> None:
    actual = _archive_identity(stat_result)
    expected = {key: entry[key] for key in _IDENTITY_FIELDS}
    if actual != expected:
        raise ArchiveError(f"源文件在归档期间发生变化: {entry['relative_path']!r}")
    if not stat.S_ISREG(stat_result.st_mode):
        raise ArchiveError(f"源文件不是普通文件: {entry['relative_path']!r}")


def _absolute_lexical(path: str | Path) -> Path:
    # abspath 只做词法归一化，不解析符号链接；后续逐级 O_NOFOLLOW 检查祖先。
    return Path(os.path.abspath(os.fspath(path)))


def _open_flags(*, directory: bool) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    return flags


def _open_dir_fd(path: Path) -> int:
    """逐级打开目录，拒绝包括父级在内的符号链接。"""

    absolute = _absolute_lexical(path)
    fd = os.open(os.sep, _open_flags(directory=True))
    try:
        for component in absolute.parts[1:]:
            if component in {"", ".", ".."}:
                continue
            next_fd = os.open(component, _open_flags(directory=True), dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _open_relative_file(source_dir: str | Path, relative_path: str) -> int:
    root_fd = _open_dir_fd(Path(source_dir))
    parent_fd = root_fd
    try:
        components = relative_path.split("/")
        for component in components[:-1]:
            next_fd = os.open(component, _open_flags(directory=True), dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = next_fd
        return os.open(components[-1], _open_flags(directory=False), dir_fd=parent_fd)
    finally:
        os.close(parent_fd)


@contextmanager
def _source_fd(source_dir: str | Path, entry: Mapping[str, Any]):
    fd = _open_relative_file(source_dir, entry["relative_path"])
    try:
        initial = os.fstat(fd)
        _assert_identity(initial, entry)
        yield fd
        _assert_identity(os.fstat(fd), entry)
    finally:
        os.close(fd)


def _check_current_source(source_dir: str | Path, entry: Mapping[str, Any]) -> None:
    """重新从目录 fd 打开源路径，发现替换、删除或新建符号链接。"""

    with _source_fd(source_dir, entry):
        pass


class _HashingReader(io.BufferedReader):
    """供 py7zr.writef 使用的流式读取器，哈希只覆盖真正读出的字节。"""

    def __init__(self, raw: io.RawIOBase):
        super().__init__(raw)
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = super().read(size)
        self.digest.update(data)
        self.bytes_read += len(data)
        return data

    def readinto(self, buffer: Any) -> int:
        count = super().readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
            self.bytes_read += count
        return count


def _copy_and_hash(source: io.BufferedIOBase, target: Any, expected_size: int) -> str:
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(_CHUNK_SIZE):
        digest.update(chunk)
        target.write(chunk)
        size += len(chunk)
    if size != expected_size:
        raise ArchiveError("源文件读取大小与扫描快照不一致")
    return digest.hexdigest()


def _manifest_json(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", "\\r").replace("\n", "\\n")


def _manifest_markdown(manifest: Mapping[str, Any], manifest_json_sha256: str) -> bytes:
    lines = [
        "# 归档清单",
        "",
        f"- 批次 ID：`{_markdown_cell(manifest['batch_id'])}`",
        f"- 任务：`{_markdown_cell(manifest['task_name'])}`（`{_markdown_cell(manifest['task_id'])}`）",
        f"- 源目录：`{_markdown_cell(manifest['source_dir'])}`",
        f"- 创建时间：`{_markdown_cell(manifest['created_at'])}`（{_markdown_cell(manifest['timezone'])}）",
        f"- 格式：`{manifest['format']}` / 压缩：`{manifest['compression']}` / 加密：`{manifest['encryption']}`",
        f"- 密码版本：`{_markdown_cell(manifest['password_version'])}`（密码不会写入归档）",
        f"- `manifest.json` SHA256：`{manifest_json_sha256}`",
        "",
        "## 恢复步骤",
        "1. 将归档文件完整下载，并在需要时使用对应密码打开归档。",
        "2. 解压到恢复目录，确认 `files/` 下的相对路径保持不变。",
        "3. 在同时包含 `SHA256SUMS` 的目录执行 `sha256sum -c SHA256SUMS`。",
        "4. 仅在校验通过后，将 `files/` 下的文件恢复到源目录；密码版本用于选择正确的历史密码。",
        "",
        "## 文件摘要",
        "",
        "| 相对路径 | 大小 | SHA256 |",
        "| --- | ---: | --- |",
    ]
    for item in manifest["files"]:
        lines.append(f"| `{_markdown_cell(item['relative_path'])}` | {item['size']} | `{item['sha256']}` |")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _gnu_escape_filename(name: str) -> tuple[bytes, bool]:
    raw = name.encode("utf-8")
    if not any(char in raw for char in (b"\\", b"\n", b"\r")):
        return raw, False
    escaped = bytearray()
    for char in raw:
        if char == 0x5C:
            escaped.extend(b"\\\\")
        elif char == 0x0A:
            escaped.extend(b"\\n")
        elif char == 0x0D:
            escaped.extend(b"\\r")
        else:
            escaped.append(char)
    return bytes(escaped), True


def _checksum_line(digest: str, name: str) -> bytes:
    escaped_name, escaped = _gnu_escape_filename(name)
    prefix = b"\\" if escaped else b""
    return prefix + digest.encode("ascii") + b"  " + escaped_name + b"\n"


def _sha256sums(manifest: Mapping[str, Any], manifest_json_sha256: str, manifest_md_sha256: str) -> bytes:
    lines = [_checksum_line(item["sha256"], item["archive_path"]) for item in manifest["files"]]
    lines.append(_checksum_line(manifest_json_sha256, "manifest.json"))
    lines.append(_checksum_line(manifest_md_sha256, "manifest.md"))
    return b"".join(lines)


def _seven_zip_filters(task: Mapping[str, Any]) -> list[dict[str, int]]:
    if task["compression"] == "store":
        filters: list[dict[str, int]] = [{"id": py7zr.FILTER_COPY}]
    else:
        filters = [{"id": py7zr.FILTER_LZMA2, "preset": _SEVEN_ZIP_PRESETS[task["compression"]]}]
    if task["encryption"] == "aes256":
        # 显式追加 AES-256-SHA256 filter，避免依赖 py7zr 的隐式默认压缩链。
        filters.append({"id": py7zr.FILTER_CRYPTO_AES256_SHA256})
    return filters


def _zip_info(archive: Any, name: str, size: int, compression: int, level: int | None) -> Any:
    info = archive.zipinfo_cls(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.file_size = size
    info.compress_type = compression
    info._compresslevel = level
    info.create_system = 3
    info.external_attr = 0o600 << 16
    return info


def _write_zip_bytes(archive: Any, name: str, data: bytes, compression: int, level: int | None) -> None:
    info = _zip_info(archive, name, len(data), compression, level)
    archive.writestr(info, data)


def _write_sources_7z(archive: Any, source_dir: str | Path, records: list[dict[str, Any]]) -> None:
    for record in records:
        with _source_fd(source_dir, record) as fd:
            raw = os.fdopen(os.dup(fd), "rb", buffering=0)
            reader = _HashingReader(raw)
            try:
                archive.writef(reader, record["archive_path"])
                if reader.bytes_read != record["size"]:
                    raise ArchiveError("源文件读取大小与扫描快照不一致")
                record["sha256"] = reader.digest.hexdigest()
            finally:
                reader.close()
        _check_current_source(source_dir, record)


def _write_sources_zip(
    archive: Any,
    source_dir: str | Path,
    records: list[dict[str, Any]],
    compression: int,
    level: int | None,
) -> None:
    for record in records:
        with _source_fd(source_dir, record) as fd:
            raw = os.fdopen(os.dup(fd), "rb", buffering=0)
            source = io.BufferedReader(raw)
            try:
                info = _zip_info(archive, record["archive_path"], record["size"], compression, level)
                with archive.open(info, "w", force_zip64=True) as target:
                    record["sha256"] = _copy_and_hash(source, target, record["size"])
            finally:
                source.close()
        _check_current_source(source_dir, record)


def _new_manifest(task: Mapping[str, Any], batch_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "batch_id": batch_id,
        "task_id": task["id"],
        "task_name": task["name"],
        "source_dir": str(task["source_dir"]),
        "created_at": _datetime.datetime.now(_datetime.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "timezone": task["timezone"],
        "format": task["format"],
        "compression": task["compression"],
        "encryption": task["encryption"],
        "encrypt_names": task["encrypt_names"],
        "password_version": task["password_version"],
        "files": records,
    }


def build_archive(
    task: dict,
    entries: list[dict],
    destination: str | Path,
    batch_id: str,
) -> dict:
    """流式创建归档并原子发布，返回不含密码的 manifest。"""

    normalized_task = _validate_task(task)
    records = _prepare_entries(entries)
    if normalized_task["format"] == "7z" and any("\\" in item["relative_path"] for item in records):
        # 7z 的路径字段按库规范把反斜杠当目录分隔符，拒绝静默改变恢复路径。
        raise ArchiveError("7z 不支持包含反斜杠的源文件名，请改用 ZIP")
    if not isinstance(batch_id, str) or not batch_id:
        raise ArchiveError("batch_id 必须是非空字符串")
    destination_path = Path(destination)
    if not destination_path.name or destination_path.exists() and destination_path.is_dir():
        raise ArchiveError("destination 必须是归档文件路径")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = _new_manifest(normalized_task, batch_id, records)
    temp_path: Path | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.", suffix=".part", dir=destination_path.parent
        )
        os.close(fd)
        temp_path = Path(temp_name)
        os.chmod(temp_path, 0o600)
        if normalized_task["format"] == "7z":
            with py7zr.SevenZipFile(
                temp_path,
                "w",
                filters=_seven_zip_filters(normalized_task),
                password=normalized_task["password"] if normalized_task["encryption"] == "aes256" else None,
                header_encryption=normalized_task["encrypt_names"],
            ) as archive:
                _write_sources_7z(archive, normalized_task["source_dir"], records)
                manifest_json = _manifest_json(manifest)
                manifest_md = _manifest_markdown(manifest, _sha256_bytes(manifest_json))
                checksums = _sha256sums(manifest, _sha256_bytes(manifest_json), _sha256_bytes(manifest_md))
                archive.writestr(manifest_md, "manifest.md")
                archive.writestr(manifest_json, "manifest.json")
                archive.writestr(checksums, "SHA256SUMS")
        else:
            compression = pyzipper.ZIP_STORED if normalized_task["compression"] == "store" else pyzipper.ZIP_DEFLATED
            level = _COMPRESSION_LEVELS[normalized_task["compression"]]
            encryption_kwargs = {"nbits": 256} if normalized_task["encryption"] == "aes256" else None
            archive_kwargs = {
                "compression": compression,
                "compresslevel": level,
            }
            if encryption_kwargs is not None:
                archive_kwargs.update({"encryption": pyzipper.WZ_AES, "encryption_kwargs": encryption_kwargs})
            with pyzipper.AESZipFile(temp_path, "w", **archive_kwargs) as archive:
                if normalized_task["encryption"] == "aes256":
                    archive.setpassword(normalized_task["password"].encode("utf-8"))
                _write_sources_zip(archive, normalized_task["source_dir"], records, compression, level)
                manifest_json = _manifest_json(manifest)
                manifest_md = _manifest_markdown(manifest, _sha256_bytes(manifest_json))
                checksums = _sha256sums(manifest, _sha256_bytes(manifest_json), _sha256_bytes(manifest_md))
                _write_zip_bytes(archive, "manifest.md", manifest_md, compression, level)
                _write_zip_bytes(archive, "manifest.json", manifest_json, compression, level)
                _write_zip_bytes(archive, "SHA256SUMS", checksums, compression, level)
        os.replace(temp_path, destination_path)
        temp_path = None
        return manifest
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


class _MetadataBudget:
    def __init__(self, limit: int = _MAX_METADATA_BYTES):
        self.limit = limit
        self.used = 0

    def claim(self, size: int) -> None:
        if size < 0 or self.used + size > self.limit:
            raise ArchiveError("归档元数据超过 32 MiB 限制")
        self.used += size


class _VerifySink:
    """py7zr WriterFactory 使用的流式摘要接收器；仅元数据保留有限字节。"""

    def __init__(self, budget: _MetadataBudget, capture: bool):
        self._budget = budget
        self._capture = capture
        self._data = bytearray() if capture else None
        self._digest = hashlib.sha256()
        self._size = 0

    def write(self, data: bytes | bytearray) -> int:
        self._digest.update(data)
        self._size += len(data)
        if self._capture:
            self._budget.claim(len(data))
            self._data.extend(data)
        return len(data)

    def read(self, size: int | None = None) -> bytes:
        if self._data is None:
            return b""
        if size is None:
            return bytes(self._data)
        return bytes(self._data[:size])

    def seek(self, offset: int, whence: int = 0) -> int:
        return offset

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None

    def size(self) -> int:
        return self._size

    def __sizeof__(self) -> int:
        return self._size

    @property
    def digest(self) -> str:
        return self._digest.hexdigest()

    @property
    def data(self) -> bytes | None:
        return bytes(self._data) if self._data is not None else None


class _VerifyFactory:
    def __init__(self, budget: _MetadataBudget):
        self.budget = budget
        self.sinks: dict[str, _VerifySink] = {}

    def create(self, filename: str) -> _VerifySink:
        sink = _VerifySink(self.budget, filename in _METADATA_NAMES)
        self.sinks[filename] = sink
        return sink


def _metadata_bytes(sink: _VerifySink, name: str) -> bytes:
    data = sink.data
    if data is None:
        raise ArchiveError(f"未读取元数据成员: {name}")
    return data


def _unescape_gnu_filename(value: bytes) -> bytes:
    output = bytearray()
    index = 0
    escapes = {ord("n"): b"\n", ord("r"): b"\r", ord("\\"): b"\\", ord("t"): b"\t"}
    while index < len(value):
        if value[index] != 0x5C:
            output.append(value[index])
            index += 1
            continue
        index += 1
        if index >= len(value) or value[index] not in escapes:
            raise ArchiveError("SHA256SUMS 文件名转义无效")
        output.extend(escapes[value[index]])
        index += 1
    return bytes(output)


def _parse_sha256sums(data: bytes) -> dict[str, str]:
    if not data.endswith(b"\n"):
        raise ArchiveError("SHA256SUMS 缺少末尾换行")
    result: dict[str, str] = {}
    # splitlines() 会丢弃末尾换行，因此不能再切掉最后一项；这里已先确认末尾换行。
    for line in data[:-1].split(b"\n"):
        escaped = line.startswith(b"\\")
        if escaped:
            line = line[1:]
        if len(line) < 66 or line[64:66] not in (b"  ", b" *"):
            raise ArchiveError("SHA256SUMS 行格式无效")
        digest = line[:64].decode("ascii")
        if len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
            raise ArchiveError("SHA256SUMS 摘要无效")
        filename = line[66:]
        if escaped:
            filename = _unescape_gnu_filename(filename)
        try:
            name = filename.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ArchiveError("SHA256SUMS 文件名不是 UTF-8") from exc
        if not name or name in result:
            raise ArchiveError("SHA256SUMS 文件名重复或为空")
        result[name] = digest.lower()
    return result


def _parse_manifest(data: bytes, archive_format: str) -> dict[str, Any]:
    if len(data) > _MAX_METADATA_BYTES:
        raise ArchiveError("manifest.json 超过 32 MiB 限制")
    try:
        manifest = json.loads(
            data.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ArchiveError("manifest.json 无法解析") from exc
    if not isinstance(manifest, dict) or "password" in manifest:
        raise ArchiveError("manifest.json 结构无效")
    required = {
        "schema_version",
        "batch_id",
        "task_id",
        "task_name",
        "source_dir",
        "created_at",
        "timezone",
        "format",
        "compression",
        "encryption",
        "encrypt_names",
        "password_version",
        "files",
    }
    if not required.issubset(manifest):
        raise ArchiveError("manifest.json 缺少字段")
    if manifest["schema_version"] != 1 or manifest["format"] != archive_format:
        raise ArchiveError("manifest schema 或格式不匹配")
    if manifest["format"] not in _ARCHIVE_FORMATS or manifest["compression"] not in _COMPRESSION_LEVELS:
        raise ArchiveError("manifest 的归档选项无效")
    if manifest["encryption"] not in {"none", "aes256"} or not isinstance(manifest["encrypt_names"], bool):
        raise ArchiveError("manifest 的加密选项无效")
    if manifest["format"] == "zip" and manifest["encrypt_names"]:
        raise ArchiveError("ZIP 不支持隐藏文件名")
    try:
        ZoneInfo(manifest["timezone"])
    except Exception as exc:
        raise ArchiveError("manifest 的 timezone 无效") from exc
    if not isinstance(manifest["files"], list):
        raise ArchiveError("manifest.files 必须是数组")
    seen: set[str] = set()
    for item in manifest["files"]:
        if not isinstance(item, dict):
            raise ArchiveError("manifest.files 项无效")
        for key in (*_IDENTITY_FIELDS, "relative_path", "archive_path", "sha256"):
            if key not in item:
                raise ArchiveError("manifest.files 项缺少字段")
        relative_path = _validate_relative_path(item["relative_path"])
        if relative_path in seen or item["archive_path"] != f"files/{relative_path}":
            raise ArchiveError("manifest.files 路径无效或重复")
        seen.add(relative_path)
        for key in _IDENTITY_FIELDS:
            if isinstance(item[key], bool) or not isinstance(item[key], int) or (key == "size" and item[key] < 0):
                raise ArchiveError("manifest.files 元数据无效")
        if not isinstance(item["sha256"], str) or len(item["sha256"]) != 64:
            raise ArchiveError("manifest.files SHA256 无效")
    return manifest


def _validate_member_names(actual_names: list[str]) -> None:
    if len(actual_names) != len(set(actual_names)):
        raise ArchiveError("归档成员名称重复")
    name_bytes = sum(len(name.encode("utf-8")) for name in actual_names)
    if name_bytes > _MAX_METADATA_BYTES:
        raise ArchiveError("归档成员元数据超过 32 MiB 限制")


def _check_member_names(actual_names: list[str], manifest: Mapping[str, Any]) -> set[str]:
    _validate_member_names(actual_names)
    expected = {item["archive_path"] for item in manifest["files"]} | set(_METADATA_NAMES)
    actual = set(actual_names)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ArchiveError(f"归档成员集合不匹配，缺失={missing!r}，多余={extra!r}")
    return expected


def _verify_content(
    manifest: dict[str, Any],
    names: list[str],
    digests: Mapping[str, str],
    metadata: Mapping[str, bytes],
) -> dict[str, Any]:
    _check_member_names(names, manifest)
    manifest_json = metadata["manifest.json"]
    manifest_md = metadata["manifest.md"]
    checksum_data = metadata["SHA256SUMS"]
    expected_manifest_json_sha = _sha256_bytes(manifest_json)
    expected_md = _manifest_markdown(manifest, expected_manifest_json_sha)
    if manifest_md != expected_md:
        raise ArchiveError("manifest.md 摘要或内容不匹配")
    checksums = _parse_sha256sums(checksum_data)
    expected_checksums = {item["archive_path"]: item["sha256"] for item in manifest["files"]}
    expected_checksums.update(
        {
            "manifest.json": expected_manifest_json_sha,
            "manifest.md": _sha256_bytes(manifest_md),
        }
    )
    if checksums != expected_checksums:
        raise ArchiveError("SHA256SUMS 严格集合不匹配")
    for name, expected_digest in checksums.items():
        if digests.get(name) != expected_digest:
            raise ArchiveError(f"成员 SHA256 不匹配: {name!r}")
    for item in manifest["files"]:
        if digests.get(item["archive_path"]) != item["sha256"]:
            raise ArchiveError(f"源文件 SHA256 不匹配: {item['relative_path']!r}")
    return manifest


def _archive_format(path: Path) -> str:
    with open(path, "rb") as source:
        magic = source.read(6)
    if magic == b"7z\xbc\xaf'\x1c":
        return "7z"
    if magic.startswith(b"PK"):
        return "zip"
    raise ArchiveError("无法识别归档格式")


def _verify_7z(path: Path, password: str) -> dict[str, Any]:
    budget = _MetadataBudget()
    with py7zr.SevenZipFile(path, "r", password=password or None) as archive:
        names = archive.getnames()
        _validate_member_names(names)
        factory = _VerifyFactory(budget)
        archive.extractall(factory=factory)
    if set(_METADATA_NAMES) - factory.sinks.keys():
        raise ArchiveError("归档缺少必要元数据")
    metadata = {name: _metadata_bytes(factory.sinks[name], name) for name in _METADATA_NAMES}
    manifest = _parse_manifest(metadata["manifest.json"], "7z")
    digests = {name: sink.digest for name, sink in factory.sinks.items()}
    return _verify_content(manifest, names, digests, metadata)


def _verify_zip(path: Path, password: str) -> dict[str, Any]:
    budget = _MetadataBudget()
    password_bytes = password.encode("utf-8") if password else None
    names: list[str] = []
    digests: dict[str, str] = {}
    metadata: dict[str, bytes] = {}
    with pyzipper.AESZipFile(path, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        _validate_member_names(names)
        for info in infos:
            capture = info.filename in _METADATA_NAMES
            if capture and info.file_size > _MAX_METADATA_BYTES:
                raise ArchiveError("归档元数据超过 32 MiB 限制")
            digest = hashlib.sha256()
            buffer = bytearray() if capture else None
            with archive.open(info, "r", pwd=password_bytes) as source:
                while chunk := source.read(_CHUNK_SIZE):
                    digest.update(chunk)
                    if buffer is not None:
                        budget.claim(len(chunk))
                        buffer.extend(chunk)
            digests[info.filename] = digest.hexdigest()
            if buffer is not None:
                metadata[info.filename] = bytes(buffer)
    if set(_METADATA_NAMES) - metadata.keys():
        raise ArchiveError("归档缺少必要元数据")
    manifest = _parse_manifest(metadata["manifest.json"], "zip")
    return _verify_content(manifest, names, digests, metadata)


def verify_archive(path: str | Path, password: str = "") -> dict:
    """流式读取并校验归档，不将任何成员解压到磁盘。"""

    if not isinstance(password, str):
        raise ArchiveError("password 必须是字符串")
    archive_path = Path(path)
    if not archive_path.is_file():
        raise ArchiveError("归档文件不存在")
    archive_format = _archive_format(archive_path)
    if archive_format == "7z":
        return _verify_7z(archive_path, password)
    return _verify_zip(archive_path, password)


def _cli_error(exc: Exception, secret: str = "") -> str:
    message = str(exc) or type(exc).__name__
    if secret:
        message = message.replace(secret, "***")
    return message


def main() -> int:
    """stdin/stdout 单行 JSON CLI；异常信息不回显密码。"""

    request: dict[str, Any] = {}
    secret = ""
    try:
        parsed = json.load(sys.stdin)
        if not isinstance(parsed, dict):
            raise ArchiveError("stdin JSON 必须是对象")
        request = parsed
        action = request.get("action")
        if action == "build":
            task = request["task"]
            candidate = task.get("password", "") if isinstance(task, dict) else ""
            secret = candidate if isinstance(candidate, str) else ""
            data = build_archive(task, request["entries"], request["destination"], request["batch_id"])
        elif action == "verify":
            candidate = request.get("password", "")
            secret = candidate if isinstance(candidate, str) else ""
            data = verify_archive(request["path"], secret)
        else:
            raise ArchiveError("action 只支持 build 或 verify")
        print(json.dumps({"success": True, "data": data}, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"success": False, "message": _cli_error(exc, secret)}, ensure_ascii=False, separators=(",", ":")
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
