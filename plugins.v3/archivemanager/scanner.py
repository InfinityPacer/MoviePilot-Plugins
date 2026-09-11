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

from .config import TaskConfig, validate_paths


class Cancelled(RuntimeError):
    """用户停止或插件关闭，当前未发布批次不得继续。"""


def identity(path: Path) -> dict:
    """记录文件版本，ctime 用于识别保留大小和 mtime 的覆盖写入。"""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("不是普通文件")
    return {
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def fingerprint(entry: dict) -> str:
    """相对路径与文件版本共同参与去重，不跨任务合并同名文件。"""
    import hashlib
    import json

    fields = [
        entry.get("source_root", ""),
        *[entry[key] for key in ("relative_path", "size", "mtime_ns", "ctime_ns", "device", "inode")],
    ]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=True).encode()).hexdigest()


def scan(task: TaskConfig, stop: Event, *, stable: bool = False) -> tuple[list[dict], int]:
    """预览不等待；真实运行等待稳定窗口再核对所有候选版本。"""
    validate_paths(task)
    cutoff = time.time_ns() - int(task.archive_age_days * 86400 * 1_000_000_000)
    root = Path(task.source_dir)
    entries = []
    skipped = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        if stop.is_set():
            raise Cancelled("已停止扫描")
        dirs[:] = sorted(name for name in dirs if not (Path(directory) / name).is_symlink()) if task.recursive else []
        for name in sorted(names):
            if stop.is_set():
                raise Cancelled("已停止扫描")
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()

            def matches(pattern):
                return fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(name, pattern)

            if (task.include_patterns and not any(matches(p) for p in task.include_patterns)) or any(
                matches(p) for p in task.exclude_patterns
            ):
                skipped += 1
                continue
            try:
                item = identity(path)
                if item["mtime_ns"] > cutoff:
                    skipped += 1
                    continue
                entries.append({"relative_path": relative, "source_root": str(root.resolve()), **item})
            except OSError, ValueError:
                skipped += 1
    if stable and entries:
        if stop.wait(task.stability_seconds):
            raise Cancelled("已停止稳定性观察")
        confirmed = []
        for entry in entries:
            try:
                if identity(root / entry["relative_path"]) == {
                    k: entry[k] for k in ("size", "mtime_ns", "ctime_ns", "device", "inode")
                }:
                    confirmed.append(entry)
                else:
                    skipped += 1
            except OSError, ValueError:
                skipped += 1
        entries = confirmed
    return sorted(entries, key=lambda item: (item["mtime_ns"], item["relative_path"])), skipped


def partition(task: TaskConfig, entries: list[dict]) -> list[dict]:
    """按组内时间排序，数量或源字节上限满足任一条件即拆批。"""
    groups = defaultdict(list)
    for item in entries:
        components = []
        if task.grouping in ("directory", "directory_date"):
            components.append("/".join(Path(item["relative_path"]).parts[:-1][: task.directory_depth]) or ".")
        if task.grouping in ("date", "directory_date"):
            fmt = {"hour": "%Y-%m-%d %H", "day": "%Y-%m-%d", "month": "%Y-%m"}[task.time_grain]
            components.append(datetime.fromtimestamp(item["mtime_ns"] / 1e9, ZoneInfo(task.timezone)).strftime(fmt))
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
