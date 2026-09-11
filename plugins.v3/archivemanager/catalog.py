"""独立明文文档：不需要 MoviePilot 或数据库即可阅读、检索和重建索引。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import RLock
from urllib.parse import quote
from uuid import uuid4

from .naming import batch_relative_directory


_CATALOG_LOCK = RLock()
_INVALID_COMPONENT = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def atomic_write(path: Path, content: str) -> None:
    """先持久化文件内容，再替换目录项；临时文件只属于本次写入。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def json_text(value: dict) -> str:
    """精确路径以 JSON 转义保存，文档仍使用 UTF-8。"""
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def md(value) -> str:
    """文件名不能破坏 Markdown 表格或被解释为 HTML。"""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\\", "&#92;")
        .replace("|", "&#124;")
        .replace("`", "&#96;")
        .replace("\r", "&#13;")
        .replace("\n", "&#10;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("*", "&#42;")
        .replace("_", "&#95;")
    )


def _safe_component(value: object, fallback: str) -> str:
    """将用户可见名称限制为一个安全且仍可辨认的目录分量。"""
    cleaned = _INVALID_COMPONENT.sub("_", str(value)).strip(" .")
    return cleaned or fallback


def _manifest_data(batch: dict) -> dict:
    value = batch["manifest"]
    if not isinstance(value, dict):
        raise ValueError("归档批次缺少可写入的清单快照")
    return value


def _path_parts(value: str | Path) -> list[str]:
    """统一 POSIX/Windows 分隔符，供跨平台 Markdown 链接使用。"""
    text = str(value).replace("\\", "/")
    return [part for part in text.split("/") if part and part != "."]


def _href(value: str | Path) -> str:
    """逐段 URL 编码，保留目录层次而不暴露内部平台细节。"""
    return "/".join(quote(part, safe="") for part in _path_parts(value))


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"清单文件无法读取：{path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"清单文件结构无效：{path}")
    return value


def _manifest_paths(folder: Path) -> list[Path]:
    """递归发现新布局 manifest.json，同时保留旧版直放 batch-id.json。"""
    paths = {
        path
        for path in folder.rglob("manifest.json")
        if path.is_file() and path.name != "index.json"
    }
    paths.update(
        path
        for path in folder.glob("*.json")
        if path.is_file() and path.name != "index.json"
    )
    return sorted(paths, key=lambda path: path.relative_to(folder).as_posix())


def _record_from_manifest(path: Path, folder: Path) -> dict:
    value = _read_json(path)
    required = (
        "batch_id",
        "task_id",
        "task_name",
        "created_at",
        "archive_name",
        "archive_size",
        "archive_sha256",
        "verified",
    )
    if value.get("schema_version") != 1 or any(key not in value for key in required):
        raise ValueError(f"清单格式不完整：{path.name}")
    # 旧版清单按批次 ID 直接命名；新布局固定使用 manifest.json。
    if path.parent == folder and path.name != "manifest.json" and path.stem != value["batch_id"]:
        raise ValueError(f"清单格式或批次 ID 不匹配：{path.name}")
    relative_json = path.relative_to(folder)
    relative_md = relative_json.with_name("manifest.md") if path.name == "manifest.json" else relative_json.with_suffix(".md")
    record = {
        "batch_name": value.get("batch_name", value["batch_id"]),
        "batch_id": value["batch_id"],
        "task_id": value["task_id"],
        "task_name": value["task_name"],
        "source_dir": value.get("source_dir", ""),
        "created_at": value["created_at"],
        "archive_name": value["archive_name"],
        "archive_size": value["archive_size"],
        "archive_sha256": value["archive_sha256"],
        "verified": value["verified"],
        "manifest_path": relative_md.as_posix(),
        "manifest_json": relative_json.as_posix(),
    }
    return record


def _task_metadata(folder: Path, records: list[dict]) -> dict:
    """从批次元数据重建任务索引头；已有头信息作为空目录时的保留值。"""
    current: dict = {}
    index = folder / "index.json"
    if index.is_file():
        current = _read_json(index)
    first = records[0] if records else {}
    return {
        "schema_version": 1,
        "task_id": current.get("task_id") or first.get("task_id", ""),
        "task_name": current.get("task_name") or first.get("task_name", folder.name),
        "source_dir": current.get("source_dir") or first.get("source_dir", ""),
        "batches": records,
    }


def _folder_matches_task(folder: Path, task_id: str) -> bool:
    """依据索引或批次清单中的 task_id 识别已存在的人类目录。"""
    index = folder / "index.json"
    if index.is_file():
        value = _read_json(index)
        if value.get("task_id") == task_id:
            return True
        if any(item.get("task_id") == task_id for item in value.get("batches", [])):
            return True
    # 崩溃可能发生在批次清单已落盘、任务 index 尚未替换之前，因此递归查元数据。
    for path in _manifest_paths(folder):
        try:
            value = _read_json(path)
        except ValueError:
            continue
        if value.get("task_id") == task_id:
            return True
    return False


def _find_task_folder(root: Path, task_id: str) -> Path | None:
    if not task_id or not root.is_dir():
        return None
    for folder in sorted(
        (path for path in root.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: path.name,
    ):
        if _folder_matches_task(folder, task_id):
            return folder
    return None


def _allocate_task_folder(root: Path, task_id: str, task_name: str) -> Path:
    """用任务名作为目录；同名任务以可读数字后缀区分，并由 task_id 复用。"""
    existing = _find_task_folder(root, task_id)
    if existing is not None:
        return existing
    base = root / _safe_component(task_name, "归档任务")
    if not base.exists() or (base.is_dir() and not any(base.iterdir())):
        return base
    suffix = 2
    while True:
        candidate = base.with_name(f"{base.name} ({suffix})")
        if not candidate.exists() or (candidate.is_dir() and not any(candidate.iterdir())):
            return candidate
        suffix += 1


def _batch_id_in_folder(folder: Path, batch_id: str) -> bool:
    for path in _manifest_paths(folder):
        try:
            if _read_json(path).get("batch_id") == batch_id:
                return True
        except ValueError:
            continue
    return False


def _find_batch_folder(task_folder: Path, batch_id: str) -> Path | None:
    if not batch_id:
        return None
    for path in sorted(
        (item.parent for item in task_folder.rglob("manifest.json") if item.is_file()),
        key=lambda item: item.relative_to(task_folder).as_posix(),
    ):
        if _batch_id_in_folder(path, batch_id):
            return path
    return None


def _allocate_batch_folder(task_folder: Path, relative: Path, batch_id: str) -> Path:
    """在布局目标位置保留 batch_name；同名批次用末级数字后缀。"""
    existing = _find_batch_folder(task_folder, batch_id)
    if existing is not None:
        return existing
    candidate = task_folder / relative
    if not candidate.exists() or (candidate.is_dir() and not any(candidate.iterdir())):
        return candidate
    suffix = 2
    while True:
        alternate = candidate.with_name(f"{candidate.name} ({suffix})")
        if not alternate.exists() or (alternate.is_dir() and not any(alternate.iterdir())):
            return alternate
        suffix += 1


def _catalog_paths(batch: dict, task_folder: Path) -> tuple[Path, Path, Path]:
    """返回批次目录、Markdown 和 JSON；已有 manifest_path 始终优先复用。"""
    manifest_path = str(batch.get("manifest_path") or "").strip()
    if manifest_path:
        markdown = Path(manifest_path)
        if markdown.suffix.lower() == ".json":
            json_path = markdown
            markdown = markdown.with_suffix(".md")
        else:
            json_path = markdown.with_suffix(".json")
        return markdown.parent, markdown, json_path
    relative = batch_relative_directory(batch)
    folder = _allocate_batch_folder(task_folder, relative, str(batch.get("id", "")))
    return folder, folder / "manifest.md", folder / "manifest.json"


def _task_folder_for_manifest_path(path: Path, batch: dict) -> Path | None:
    """从既有清单路径定位原任务目录，支持任务配置改了 manifest_dir。"""
    task_id = str(batch["task_id"])
    current = path.parent
    for ancestor in (current, *current.parents):
        index = ancestor / "index.json"
        if not index.is_file():
            continue
        value = _read_json(index)
        if value.get("task_id") == task_id:
            return ancestor
        for item in value.get("batches", []):
            if item.get("task_id") != task_id:
                continue
            task_dir = item.get("catalog_task")
            if task_dir and (ancestor / task_dir).is_dir():
                return ancestor / task_dir
            return ancestor

    # 旧布局把 batch-id.json 与 batch-id.md 直接放在任务目录；优先识别这一层。
    if current.is_dir() and (current / "manifest.json").is_file() is False:
        for sibling in current.glob("*.json"):
            if sibling.name == "index.json":
                continue
            try:
                if _read_json(sibling).get("batch_id") == batch["id"]:
                    return current
            except ValueError:
                continue
    if path.name not in {"manifest.md", "manifest.json"}:
        return current

    # 新布局的相对目录由命名 helper 决定，按其层级从既有 manifest_path 向上定位。
    relative_parts = len(batch_relative_directory(batch).parts)
    candidate = current
    for _ in range(relative_parts):
        candidate = candidate.parent
    if candidate != current:
        return candidate
    return None


def _record_markdown(batch: dict, record: dict) -> str:
    manifest = _manifest_data(batch)
    task = batch["task"]
    timezone = task["timezone"]
    cleanup = batch.get("cleanup") or {}
    lines = [
        f"# 归档清单 {md(record['batch_name'])}",
        "",
        f"任务：{md(batch['task_name'])}",
        "",
        f"源目录：{md(task['source_dir'])}",
        "",
        f"归档包：{md(record['archive_name'])}（{record['archive_size']} 字节）",
        "",
        f"归档 SHA-256：`{record['archive_sha256']}`",
        "",
        f"格式：{md(task['format'])}；压缩：{md(task['compression'])}；加密：{md(task['encryption'])}；密码版本：{md(task['password_version'])}",
        "",
        f"创建时间：{md(manifest['created_at'])}；分组时区：{md(timezone)}",
        "",
        f"完整读回校验：{'通过' if batch.get('verified') else '未执行'}",
        "",
        "## 恢复与校验",
        "",
        "根据归档包名称取得文件，用支持对应格式和 AES 的 7-Zip 解压到独立目录；加密包使用该密码版本对应的密码。",
        "先将归档包 SHA-256 与本清单或包外 .sha256 文件比较。解压后在清单所在目录运行 `sha256sum -c SHA256SUMS`，校验 files/ 中的文件及包内两份清单。macOS 可使用 `shasum -a 256 -c SHA256SUMS`。",
        "源文件位于 files/，相对路径保持不变。恢复无需原机器路径、MoviePilot 或数据库。精确路径以同批次 JSON 为准。",
        "",
        "## 文件",
        "",
        "| 相对路径 | 字节数 | 修改时间（纳秒） | SHA-256 | 清理结果 |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for item in manifest.get("files", []):
        relative_path = item["relative_path"]
        lines.append(
            f"| {md(relative_path)} | {item['size']} | {item['mtime_ns']} | {item['sha256']} | {md(cleanup.get(relative_path, 'retained'))} |"
        )
    return "\n".join(lines) + "\n"


def write_catalog(batch: dict) -> str:
    """写入批次清单，并更新任务级与共享根级索引。"""
    manifest = _manifest_data(batch)
    task = batch["task"]
    root = Path(task["manifest_dir"])
    if not str(root):
        raise ValueError("任务缺少独立清单目录")
    task_name = str(batch["task_name"])
    task_id = str(batch["task_id"])
    with _CATALOG_LOCK:
        existing_manifest_path = str(batch.get("manifest_path") or "").strip()
        if existing_manifest_path:
            manifest_path = Path(existing_manifest_path)
            task_folder = _task_folder_for_manifest_path(manifest_path, batch)
            if task_folder is None:
                task_folder = _allocate_task_folder(root, task_id, task_name)
            catalog_root = task_folder.parent
        else:
            root.mkdir(parents=True, exist_ok=True)
            task_folder = _allocate_task_folder(root, task_id, task_name)
            catalog_root = root
        _batch_folder, markdown, json_path = _catalog_paths(batch, task_folder)
        record = {
            **manifest,
            "source_dir": task["source_dir"],
            "batch_name": batch.get("batch_name", batch.get("id", manifest.get("batch_id", ""))),
            "archive_name": Path(batch.get("archive_path", "")).name or batch.get("archive_name", ""),
            "archive_path": batch.get("archive_path", ""),
            "archive_size": batch.get("archive_size", 0),
            "archive_sha256": batch.get("archive_sha256", ""),
            "verified": bool(batch.get("verified")),
            "cleanup": batch.get("cleanup") or {},
            "status": batch.get("status", ""),
        }
        atomic_write(json_path, json_text(record))
        atomic_write(markdown, _record_markdown(batch, record))
        rebuild_index(task_folder)
        rebuild_root_index(catalog_root)
        return str(markdown)


def rebuild_root_index(root: Path) -> None:
    """递归汇总共享清单根目录，展示任务名与完整源路径而不暴露 task_id。"""
    with _CATALOG_LOCK:
        root.mkdir(parents=True, exist_ok=True)
        rows: list[dict] = []
        # manifest.json 是批次事实源。无论任务 index 是否已经存在，都先重建它，
        # 覆盖“新批次已落盘、旧任务 index 尚未替换”的崩溃窗口。
        for folder in sorted(
            (path for path in root.iterdir() if path.is_dir() and not path.is_symlink()),
            key=lambda path: path.name,
        ):
            manifest_paths = _manifest_paths(folder)
            if manifest_paths:
                rebuild_index(folder)
            index = folder / "index.json"
            if not index.is_file():
                continue
            value = _read_json(index)
            if value.get("schema_version") != 1 or not isinstance(value.get("batches"), list):
                raise ValueError(f"任务索引格式无效：{index}")
            task_dir = folder.name
            for item in value["batches"]:
                row = {
                    **item,
                    "task_name": item.get("task_name") or value.get("task_name", task_dir),
                    "source_dir": item.get("source_dir") or value.get("source_dir", ""),
                    "catalog_task": task_dir,
                }
                markdown = item.get("manifest_path") or f"{item['batch_id']}.md"
                json_path = item.get("manifest_json") or f"{item['batch_id']}.json"
                row["manifest_path"] = f"{task_dir}/{markdown}"
                row["manifest_json"] = f"{task_dir}/{json_path}"
                rows.append(row)
        rows.sort(key=lambda item: (item.get("created_at", ""), item.get("batch_id", "")))
        atomic_write(root / "index.json", json_text({"schema_version": 1, "batches": rows}))
        lines = [
            "# 归档总索引",
            "",
            "多个归档任务共用此清单根目录；源目录用于区分同名任务对应的不同磁盘。",
            "",
            "| 任务 | 源目录 | 批次 | 创建时间 | 归档包 | 校验 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in rows:
            lines.append(
                f"| {md(item.get('task_name', item.get('catalog_task', '')))} | {md(item.get('source_dir', ''))} | [{md(item.get('batch_name', item['batch_id']))}]({_href(item['manifest_path'])}) | {md(item.get('created_at', ''))} | {md(item.get('archive_name', ''))} | {'通过' if item.get('verified') else '未执行'} |"
            )
        atomic_write(root / "index.md", "\n".join(lines) + "\n")


def rebuild_index(folder: Path) -> None:
    """批次 JSON 是索引事实源；递归布局和损坏条目都不静默丢弃。"""
    with _CATALOG_LOCK:
        records = [
            _record_from_manifest(path, folder)
            for path in _manifest_paths(folder)
        ]
        records.sort(key=lambda item: (item.get("created_at", ""), item.get("batch_id", "")))
        metadata = _task_metadata(folder, records)
        atomic_write(folder / "index.json", json_text(metadata))
        lines = [
            "# 归档索引",
            "",
            "每个批次提供 Markdown 与 JSON 清单。归档包可以独立解压和校验，密码由归档所有者保管。",
            "",
            "| 批次 | 创建时间 | 归档包 | 字节数 | 完整校验 |",
            "| --- | --- | --- | ---: | --- |",
        ]
        for record in records:
            markdown = record.get("manifest_path") or f"{record['batch_id']}.md"
            json_path = record.get("manifest_json") or f"{record['batch_id']}.json"
            lines.append(
                f"| [{md(record['batch_name'])}]({_href(markdown)}) · [JSON]({_href(json_path)}) | {md(record['created_at'])} | {md(record['archive_name'])} | {record['archive_size']} | {'通过' if record['verified'] else '未执行'} |"
            )
        atomic_write(folder / "index.md", "\n".join(lines) + "\n")
