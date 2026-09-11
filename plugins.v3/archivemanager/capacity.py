"""归档空间准入：只观察本地成品，不负责上传或上传后的清理。"""

import shutil
from pathlib import Path

from .config import TaskConfig


class CapacityWait(RuntimeError):
    """空间条件暂不满足，保留队列并等待外部变化。"""


def available_space(path: Path) -> int:
    """输出目录尚未创建时查询最近存在的父目录，不产生副作用。"""
    while not path.exists():
        path = path.parent
    return shutil.disk_usage(path).free


def allowance(task: TaskConfig, local: list[dict]) -> dict:
    """源数据按最坏的仅打包大小预留；压缩节省不能提前当作可用空间。"""
    free = available_space(Path(task.output_dir))
    size = sum(Path(batch["archive_path"]).stat().st_size for batch in local if Path(batch["archive_path"]).is_file())
    count = len(local)
    overhead = 64 * 1024**2
    budget = max(0, (free - task.min_free_bytes - overhead) * 10 // 11)
    if task.max_pending_bytes:
        budget = min(budget, max(0, (task.max_pending_bytes - size - overhead) * 10 // 11))
    reason = ""
    if task.max_pending_archives and count >= task.max_pending_archives:
        reason = "本地成品数量达到上限，等待外部工具移走成品"
        budget = 0
    elif budget <= 0:
        reason = "可用空间或成品容量余额不足，等待外部清理或调整输出目录"
    return {"pending_archives": count, "pending_bytes": size, "free_bytes": free, "budget": budget, "reason": reason}


def fit_batch(batch: dict, budget: int) -> dict | None:
    """保持历史时间顺序，只取可以完整容纳的前缀，不拆单个文件。"""
    selected = []
    total = 0
    for entry in batch["entries"]:
        if total + entry["size"] > budget:
            break
        selected.append(entry)
        total += entry["size"]
    if not selected:
        return None
    return {**batch, "entries": selected, "total_bytes": total}
