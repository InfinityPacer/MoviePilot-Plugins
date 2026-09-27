"""单轮归档规划：扫描、刷新账本并只保留本轮可能执行的批次候选。"""

from dataclasses import dataclass
from pathlib import Path
from threading import Event

from .config import TaskConfig
from .scanner import partition, scan_tree
from .store import Store


@dataclass(slots=True)
class CyclePlan:  # pylint: disable=too-many-instance-attributes  # 执行状态与日志统计的只读快照
    """一轮执行所需的最小状态；全量扫描结果在规划返回后即可释放。"""

    groups: list[dict]  # 按执行顺序排列、已截断到本轮批次上限的候选批次
    directory_map: dict[str, dict]  # 仅包含 groups 中文件祖先目录的元数据，用于写入批次目录快照
    has_more: bool  # 截断后是否仍有本轮不会处理的候选批次，决定周期结束时的阶段
    eligible_files: int  # 本轮可归档文件总数，用于日志
    eligible_directories: int  # 本轮尚未归档的目录版本数，用于日志
    eligible_bytes: int  # 本轮可归档源字节数，用于日志
    batch_count: int  # 截断前的候选批次总数，用于日志
    skipped: int  # 扫描跳过的条目数，用于日志


def _ancestors(relative_path: str) -> list[str]:
    """返回文件在源目录内的全部祖先目录相对路径，不含根目录。"""
    return [parent.as_posix() for parent in Path(relative_path).parents if parent.as_posix() != "."]


def _directory_groups(task: TaskConfig, entries: list, directories: list[dict]) -> list[dict]:
    """没有待归档文件落在其下的目录版本单独成批，保留空目录与目录元数据。"""
    covered = {path for entry in entries for path in _ancestors(entry["relative_path"])}
    standalone = [entry for entry in directories if entry["relative_path"] not in covered]
    size = task.max_files or len(standalone)
    return [
        {
            "group": "目录结构",
            "entries": [],
            "directories": standalone[offset : offset + size],
            "total_bytes": 0,
        }
        for offset in range(0, len(standalone), size)
    ]


def plan_cycle(task: TaskConfig, stop: Event, store: Store, limit: int) -> CyclePlan:
    """扫描并刷新账本后只保留前 ``limit`` 个候选批次。

    执行循环每次只从首个候选批次取可容纳前缀，剩余部分仍留在首位，因此一轮最多触及
    ``limit`` 个候选批次；其后的候选在本轮不会被读取，下一轮会重新扫描并按账本重新分批。
    截断只减少常驻内存，不改变批次内容、顺序和续跑语义。
    """
    entries, directories, skipped = scan_tree(task, stop, stable=True)
    entries = store.inventory(task.id, entries, task.source_dir, task.public())
    pending_directories = store.inventory_directories(task.id, directories, task.public())
    groups = partition(task, entries)
    groups.extend(_directory_groups(task, entries, pending_directories))
    batch_count = len(groups)
    del groups[limit:]
    required_paths = {
        path
        for group in groups
        for entry in group["entries"]
        for path in _ancestors(entry["relative_path"])
    }
    return CyclePlan(
        groups=groups,
        directory_map={
            entry["relative_path"]: entry
            for entry in directories
            if entry["relative_path"] in required_paths
        },
        has_more=batch_count > len(groups),
        eligible_files=len(entries),
        eligible_directories=len(pending_directories),
        eligible_bytes=sum(entry["size"] for entry in entries),
        batch_count=batch_count,
        skipped=skipped,
    )
