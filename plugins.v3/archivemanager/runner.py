"""单批归档事务：文件系统发布与数据库阶段通过幂等恢复衔接。"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Event

from .capacity import CapacityWait, allowance
from .catalog import atomic_write, write_catalog
from .config import TaskConfig, validate_paths
from .naming import batch_relative_directory
from .scanner import Cancelled, identity


def run_engine(payload: dict, stop: Event) -> dict:
    """密码经匿名管道进入短生命周期进程，不出现在 argv、环境或临时文件。"""
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("engine.py"))],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    request = json.dumps(payload, ensure_ascii=True)
    try:
        while True:
            if stop.is_set():
                raise Cancelled("已停止归档")
            try:
                stdout, _stderr = process.communicate(input=request, timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                request = None
        if process.returncode:
            raise RuntimeError("归档工作进程异常退出")
        response = json.loads(stdout)
        if not response["success"]:
            raise RuntimeError(response["message"])
        return response["data"]
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


def digest(path: Path, stop: Event) -> str:
    """计算磁盘文件摘要，支持停止，不跟随末级符号链接。"""
    import hashlib

    result = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        while data := stream.read(1024 * 1024):
            if stop.is_set():
                raise Cancelled("已停止校验")
            result.update(data)
    return result.hexdigest()


def check_stop(stop: Event) -> None:
    if stop.is_set():
        raise Cancelled("已停止归档")


class Runner:
    """只负责一个批次；外部队列保证同一插件实例串行运行。"""

    def __init__(self, store, stop: Event, phase):
        self.store = store
        self.stop = stop
        self.phase = phase

    def execute(self, batch: dict, current_task: TaskConfig) -> None:
        """使用批次冻结配置恢复；当前任务只提供同版本密码。"""
        password = current_task.password if batch["task"]["encryption"] != "none" else ""
        if batch["task"]["encryption"] != "none" and current_task.password_version != batch["task"]["password_version"]:
            raise ValueError("历史批次需要原密码版本；请恢复任务密码及版本后重试")
        task = TaskConfig.model_validate({**batch["task"], "password": password})
        batch_id = batch["id"]
        output = Path(task.output_dir)
        published = output / batch_relative_directory(batch)
        staging = output.parent / ".archivemanager-staging" / task.id / batch_id
        archive_name = batch.get("archive_name") or f"{batch_id}.{task.format}"
        archive_path = published / archive_name
        if batch.get("archive_path"):
            archive_path = Path(batch["archive_path"])
            published = archive_path.parent
        try:
            validate_paths(task)
            check_stop(self.stop)
            if not published.exists() and batch["archive_sha256"]:
                # 只允许恢复 rename 前已持久化的同一成品，不能因外部移走成品就重新打包。
                stage_archive = staging / archive_name
                if not stage_archive.is_file() or digest(stage_archive, self.stop) != batch["archive_sha256"]:
                    raise ValueError("已记录成品不在本地；请恢复原归档包，或仅补全外部清单")
                if task.verify:
                    actual = run_engine(
                        {"action": "verify", "path": str(stage_archive), "password": password}, self.stop
                    )
                    if actual != batch["manifest"]:
                        raise ValueError("暂存成品清单与账本不一致")
                with stage_archive.open("rb") as stream:
                    os.fsync(stream.fileno())
                atomic_write(staging / f"{archive_name}.sha256", f"{batch['archive_sha256']}  {archive_name}\n")
                output.mkdir(parents=True, exist_ok=True)
                published.parent.mkdir(parents=True, exist_ok=True)
                os.rename(staging, published)
                fd = os.open(published.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            # 重启时成品存在优先走校验/补文档，不把相同批次再次压缩覆盖。
            if not published.exists():
                self.phase("building", batch_id)
                self.store.save(batch_id, status="building", error="")
                output.mkdir(parents=True, exist_ok=True)
                staging.mkdir(parents=True, exist_ok=True)
                if os.stat(staging).st_dev != os.stat(output).st_dev:
                    raise ValueError("暂存区与输出目录不在同一文件系统，无法原子发布")
                stage_archive = staging / archive_name
                # 仅清理本批次可重建的工作文件，绝不触碰已发布目录。
                for child in staging.iterdir():
                    partial = re.fullmatch(r"\." + re.escape(archive_name) + r"\.[a-z0-9_]{8}\.part", child.name)
                    if (
                        (child.name not in (archive_name, archive_name + ".sha256") and not partial)
                        or child.is_symlink()
                        or not child.is_file()
                    ):
                        raise ValueError("批次暂存区包含非预期文件")
                    child.unlink()
                required = batch["source_bytes"] + max(64 * 1024**2, batch["source_bytes"] // 10)
                capacity = allowance(task, self.store.local_archives(task.id))
                if (
                    shutil.disk_usage(staging).free < required + task.min_free_bytes
                    or batch["source_bytes"] > capacity["budget"]
                ):
                    raise CapacityWait(capacity["reason"] or "归档目标剩余容量不足，等待外部清理")
                engine_task = task.model_dump()
                engine_task["timezone"] = task.timezone
                manifest = run_engine(
                    {
                        "action": "build",
                        "task": engine_task,
                        "entries": batch["entries"],
                        "destination": str(stage_archive),
                        "batch_id": batch_id,
                    },
                    self.stop,
                )
                verified = False
                if task.verify:
                    self.phase("verifying", batch_id)
                    self.store.save(batch_id, status="verifying")
                    actual = run_engine(
                        {"action": "verify", "path": str(stage_archive), "password": password}, self.stop
                    )
                    if actual != manifest:
                        raise ValueError("归档读回清单与打包结果不一致")
                    verified = True
                archive_hash = digest(stage_archive, self.stop)
                # 读回可能命中页缓存；删源前必须先把归档数据持久化到文件系统。
                with stage_archive.open("rb") as stream:
                    os.fsync(stream.fileno())
                atomic_write(staging / f"{archive_name}.sha256", f"{archive_hash}  {archive_name}\n")
                # 在 rename 前提交摘要和清单，崩溃后有依据识别已经发布的成品。
                batch = self.store.save(
                    batch_id,
                    status="publishing",
                    manifest=manifest,
                    verified=verified,
                    archive_path=str(archive_path),
                    archive_sha256=archive_hash,
                    archive_size=stage_archive.stat().st_size,
                )
                self.phase("publishing", batch_id)
                check_stop(self.stop)
                published.parent.mkdir(parents=True, exist_ok=True)
                os.rename(staging, published)
                fd = os.open(published.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            else:
                if published.is_symlink() or not batch["manifest"] or not batch["archive_sha256"]:
                    raise ValueError("已存在的成品缺少可信恢复快照，不允许覆盖")
                if digest(archive_path, self.stop) != batch["archive_sha256"]:
                    raise ValueError("已发布归档 SHA-256 不匹配")
                # 发布后的源文件可能已经删除，恢复只从已核验成品继续。
                if task.verify:
                    actual = run_engine(
                        {"action": "verify", "path": str(archive_path), "password": password}, self.stop
                    )
                    if actual != batch["manifest"]:
                        raise ValueError("恢复归档清单与账本不一致")
                    batch = self.store.save(batch_id, verified=True)
                atomic_write(published / f"{archive_name}.sha256", f"{batch['archive_sha256']}  {archive_name}\n")
            check_stop(self.stop)
            batch = self.store.save(batch_id, status="manifest_pending", error="")
            self.phase("manifest_pending", batch_id)
            path = write_catalog({**batch, "status": "completed"})
            batch = self.store.save(
                batch_id, status="cleaning" if task.delete_source else "publishing", manifest_path=path
            )
            self.store.complete_files(batch)
            if task.delete_source:
                self._cleanup(batch, task)
            else:
                self.store.save(batch_id, status="completed")
        except CapacityWait:
            self.store.save(batch_id, status="interrupted", error="等待空间")
            raise
        except Cancelled:
            self.store.save(
                batch_id,
                status="interrupted" if published.exists() else "cancelled",
                error="用户已停止；源文件清理不会继续",
            )
            raise
        except Exception as exc:
            state = self.store.get(batch_id)["status"]
            status = (
                "cleanup_failed"
                if state in ("cleaning", "cleanup_failed")
                else "manifest_pending"
                if published.exists() and state in ("publishing", "manifest_pending", "completed")
                else "failed"
            )
            message = str(exc).replace(password, "***") if password else str(exc)
            self.store.save(batch_id, status=status, error=message[:500])
            raise RuntimeError(message) from None

    def _cleanup(self, batch: dict, task: TaskConfig) -> None:
        """完整成品和外部文档可用后才逐项清理；每次删除意图先落盘。"""
        if not batch["verified"]:
            raise ValueError("清理源文件需要完整校验通过")
        archive = Path(batch["archive_path"])
        if digest(archive, self.stop) != batch["archive_sha256"]:
            raise ValueError("清理前归档摘要不匹配")
        archive_identity = identity(archive)
        batch = self.store.save(batch["id"], status="cleaning")
        self.phase("cleaning", batch["id"])
        failed = False
        for entry in batch["manifest"]["files"]:
            check_stop(self.stop)
            relative = entry["relative_path"]
            if batch["cleanup"].get(relative) in ("deleted", "missing", "changed"):
                continue
            source = Path(task.source_dir) / relative
            expected = {key: entry[key] for key in ("size", "mtime_ns", "ctime_ns", "device", "inode")}
            result = "retained"
            try:
                if not source.exists():
                    result = "missing"
                elif any(part.is_symlink() for part in (source, *source.parents)) or identity(source) != expected:
                    result = "changed"
                elif digest(source, self.stop) != entry["sha256"] or identity(source) != expected:
                    result = "changed"
                else:
                    # 意图文档失败就停止，不出现“已删除但从未记录该成员”的新操作。
                    cleanup = {**batch["cleanup"], relative: "deleting"}
                    batch = self.store.save(batch["id"], cleanup=cleanup)
                    write_catalog(batch)
                    check_stop(self.stop)
                    if identity(archive) != archive_identity or identity(source) != expected:
                        raise ValueError("清理前源文件或归档包已变化")
                    source.unlink()
                    result = "deleted"
            except FileNotFoundError:
                if not archive.exists():
                    raise ValueError("成品已被外部移走，停止源文件清理") from None
                result = "missing"
            except PermissionError:
                result = "failed"
                failed = True
            batch = self.store.save(batch["id"], cleanup={**batch["cleanup"], relative: result})
            write_catalog(batch)
            self.store.file_result(batch["id"], relative, result)
        status = "cleanup_failed" if failed else "completed"
        batch = self.store.save(batch["id"], status=status, error="部分源文件无权限删除" if failed else "")
        write_catalog(batch)
