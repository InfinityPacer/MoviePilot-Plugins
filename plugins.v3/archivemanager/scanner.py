"""只读目录扫描、稳定性观察和确定性分批。"""

import fnmatch
import os
import stat
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from threading import Event
from zoneinfo import ZoneInfo

from app.sdk.config import settings
from app.sdk.logging import logger

from .config import TaskConfig, validate_paths


class Cancelled(RuntimeError):
    """用户停止或插件关闭，当前未发布批次不得继续。"""


def _birthtime_ns(info: os.stat_result) -> int | None:
    """返回文件系统创建时间；平台未提供时保留为空，不用 ctime 冒充。"""
    value = getattr(info, "st_birthtime_ns", None)
    if value is not None:
        return int(value)
    seconds = getattr(info, "st_birthtime", None)
    return int(seconds * 1_000_000_000) if seconds is not None else None


def _metadata(info: os.stat_result) -> dict:
    return {
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
        "mode": stat.S_IMODE(info.st_mode),
        "birthtime_ns": _birthtime_ns(info),
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def identity(path: Path) -> dict:
    """记录普通文件版本、权限及可用的文件系统创建时间。"""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("不是普通文件")
    return {"size": info.st_size, **_metadata(info)}


def _file_identity(info: os.stat_result) -> dict:
    """从已取得的 DirEntry stat 结果构造文件身份，避免再次 lstat。"""
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("不是普通文件")
    return {"size": info.st_size, **_metadata(info)}


def _directory_identity(info: os.stat_result) -> dict:
    """从已取得的 DirEntry stat 结果构造目录身份，避免再次 lstat。"""
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("不是目录")
    return _metadata(info)


def directory_identity(path: Path) -> dict:
    """记录真实目录的时间、权限和身份，符号链接目录不进入归档。"""
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("不是目录")
    return _metadata(info)


def identity_matches(path: Path, expected: dict) -> bool:
    """兼容旧批次五字段身份，并对新批次追加权限和创建时间核对。"""
    actual = identity(path)
    fields = ["size", "mtime_ns", "ctime_ns", "device", "inode"]
    fields.extend(key for key in ("mode", "birthtime_ns") if key in expected)
    return all(actual[key] == expected[key] for key in fields)


def fingerprint(entry: dict) -> str:
    """相对路径与文件版本共同参与去重，不跨任务合并同名文件。"""
    import hashlib
    import json

    fields = [
        entry.get("source_root", ""),
        *[entry.get(key) for key in ("relative_path", "size", "mtime_ns", "ctime_ns", "mode", "birthtime_ns", "device", "inode")],
    ]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=True).encode()).hexdigest()


def scan_tree(task: TaskConfig, stop: Event, *, stable: bool = False) -> tuple[list[dict], list[dict], int]:
    """扫描普通文件和真实目录；使用 scandir 减少路径对象和重复 lstat。"""
    validate_paths(task)
    cutoff = time.time_ns() - int(task.archive_age_days * 86400 * 1_000_000_000)
    root = Path(task.source_dir)
    source_root = str(root.resolve())
    entries: list[dict] = []
    directories: list[dict] = []
    skipped = 0
    skipped_patterns = 0
    skipped_too_new = 0
    skipped_unreadable = 0
    skipped_unstable = 0
    started = time.monotonic()
    pending_dirs = [(root, "")]
    while pending_dirs:
        if stop.is_set():
            raise Cancelled("已停止扫描")
        current, current_relative = pending_dirs.pop()
        try:
            children = sorted(os.scandir(current), key=lambda item: item.name)
        except OSError, ValueError:
            skipped += 1
            skipped_unreadable += 1
            continue
        child_dirs: list[tuple[Path, str]] = []
        for child in children:
            relative = f"{current_relative}/{child.name}".strip("/")
            try:
                is_symlink = child.is_symlink()
                # os.walk 会静默跳过目录符号链接；保持这一计数语义，文件符号链接仍计为特殊文件。
                if is_symlink and child.is_dir(follow_symlinks=True):
                    continue
                is_dir = child.is_dir(follow_symlinks=False)
                if is_dir:
                    excluded = any(
                        fnmatch.fnmatchcase(relative, pattern)
                        or fnmatch.fnmatchcase(child.name, pattern)
                        for pattern in task.exclude_patterns
                    )
                    if is_symlink or excluded:
                        continue
                    directories.append(
                        {
                            "relative_path": relative,
                            "source_root": source_root,
                            **_directory_identity(child.stat(follow_symlinks=False)),
                        }
                    )
                    if task.recursive:
                        child_dirs.append((Path(child.path), relative))
                    continue
                included = any(
                    fnmatch.fnmatchcase(relative, pattern)
                    or fnmatch.fnmatchcase(child.name, pattern)
                    for pattern in task.include_patterns
                )
                excluded = any(
                    fnmatch.fnmatchcase(relative, pattern)
                    or fnmatch.fnmatchcase(child.name, pattern)
                    for pattern in task.exclude_patterns
                )
                if (task.include_patterns and not included) or excluded:
                    skipped += 1
                    skipped_patterns += 1
                    continue
                item = _file_identity(child.stat(follow_symlinks=False))
                if item["mtime_ns"] > cutoff:
                    skipped += 1
                    skipped_too_new += 1
                    continue
                entries.append({"relative_path": relative, "source_root": source_root, **item})
            except OSError, ValueError:
                skipped += 1
                skipped_unreadable += 1
        pending_dirs.extend(reversed(child_dirs))
    if stable and (entries or directories):
        if stop.wait(task.stability_seconds):
            raise Cancelled("已停止稳定性观察")
        confirmed_entries = []
        for entry in entries:
            try:
                if identity(root / entry["relative_path"]) == {
                    key: entry[key]
                    for key in (
                        "size", "mtime_ns", "ctime_ns", "mode", "birthtime_ns", "device", "inode"
                    )
                }:
                    confirmed_entries.append(entry)
                else:
                    skipped += 1
                    skipped_unstable += 1
            except OSError, ValueError:
                skipped += 1
                skipped_unstable += 1
        entries = confirmed_entries
        confirmed_directories = []
        for entry in directories:
            try:
                if directory_identity(root / entry["relative_path"]) == {
                    key: entry[key]
                    for key in ("mtime_ns", "ctime_ns", "mode", "birthtime_ns", "device", "inode")
                }:
                    confirmed_directories.append(entry)
                else:
                    skipped += 1
                    skipped_unstable += 1
            except OSError, ValueError:
                skipped += 1
                skipped_unstable += 1
        directories = confirmed_directories
    logger.info(
        f"压缩归档扫描统计：task={task.name}({task.id[:6]}) source={root} stable_check={stable} "
        f"eligible={len(entries)} directories={len(directories)} skipped={skipped} "
        f"pattern={skipped_patterns} too_new={skipped_too_new} "
        f"unreadable_or_special={skipped_unreadable} unstable={skipped_unstable} "
        f"elapsed_seconds={time.monotonic() - started:.3f}"
    )
    return (
        sorted(entries, key=lambda item: (item["mtime_ns"], item["relative_path"])),
        sorted(directories, key=lambda item: item["relative_path"]),
        skipped,
    )


def scan(task: TaskConfig, stop: Event, *, stable: bool = False) -> tuple[list[dict], int]:
    """兼容只关心普通文件的预览与测试调用。"""
    entries, _directories, skipped = scan_tree(task, stop, stable=stable)
    return entries, skipped


def partition(task: TaskConfig, entries: list[dict]) -> list[dict]:
    """按组内时间排序，数量或源字节上限满足任一条件即拆批。"""
    groups = defaultdict(list)
    for item in entries:
        components = []
        if task.grouping in ("directory", "directory_date"):
            components.append("/".join(Path(item["relative_path"]).parts[:-1][: task.directory_depth]) or ".")
        if task.grouping in ("date", "directory_date"):
            fmt = {"hour": "%Y-%m-%d %H", "day": "%Y-%m-%d", "month": "%Y-%m"}[task.time_grain]
            components.append(
                datetime.fromtimestamp(item["mtime_ns"] / 1e9, tz=ZoneInfo(settings.TZ)).strftime(fmt)
            )
        groups[" | ".join(components) or "全部文件"].append(item)
    batches = []
    for group, items in groups.items():
        current = []
        size = 0
        for item in items:
            if current and (
                (task.max_files and len(current) >= task.max_files)
                or (task.max_bytes and size + item["size"] > task.max_bytes)
            ):
                batches.append({"group": group, "entries": current, "total_bytes": size})
                current, size = [], 0
            current.append(item)
            size += item["size"]
        if current:
            batches.append({"group": group, "entries": current, "total_bytes": size})
    return sorted(batches, key=lambda batch: (batch["entries"][0]["mtime_ns"], batch["group"]))
