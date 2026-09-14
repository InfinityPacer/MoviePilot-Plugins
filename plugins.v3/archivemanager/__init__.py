"""压缩归档：任务配置、认证 API 和单工作队列的宿主适配入口。"""

import copy
import threading
import traceback
from collections import deque
from functools import partial
from pathlib import Path
from uuid import uuid4

from app import schemas
from app.plugins import _PluginBase
from app.schemas.types import NotificationType
from app.sdk.logging import logger
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, Field, ValidationError

from .capacity import CapacityWait, allowance, fit_batch
from .catalog import remove_catalog, write_catalog
from .config import (
    NotificationConfig,
    TaskConfig,
    container_timezone,
    overlap,
    parse_config,
    validate_paths,
)
from .runner import Runner, cleanup_stale_staging, remove_staging, staging_size
from .scanner import Cancelled, partition, scan, scan_tree
from .store import BatchRow, DirectoryRow, FileRow, Store, TaskRow


class TaskRequest(BaseModel):
    """任务执行与停止请求；运行时空标识表示提交全部任务。"""

    task_id: str = ""


class BatchRequest(BaseModel):
    """按稳定批次标识重试或补全文档。"""

    batch_id: str  # 原批次 ID，保持成品名称不变


class BatchCleanupRequest(BaseModel):
    """清理批次账本，可选同步清理本地归档产物。"""

    batch_ids: list[str] = Field(min_length=1)
    delete_artifacts: bool = False


class ReclaimRequest(BaseModel):
    """回收所有已发布批次仍保留的源文件。"""


class PreviewRequest(BaseModel):
    """未保存草稿的只读预览请求。"""

    task: dict = Field(default_factory=dict)  # 与任务配置相同的字段结构


class ArchiveManager(_PluginBase):
    """只归档本地普通文件；上传及云端状态由用户的外部工具负责。"""

    plugin_name = "压缩归档"
    plugin_desc = "文件压缩归档，支持独立清单、校验和可选加密。"
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/archivemanager.png"
    plugin_version = "0.1.2"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "archivemanager_"
    plugin_order = 30
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._notifications = NotificationConfig()
        self._tasks: list[TaskConfig] = []
        self._config_error = ""
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: deque = deque()
        self._running: dict | None = None
        self._previews: dict[str, dict] = {}
        self._closing = False
        self._manual_stop_tasks: set[str] = set()

    def init_plugin(self, config: dict | None = None):
        """重载先等待旧工作进程退出；数据库由宿主在此方法返回后建表。"""
        self.stop_service()
        self._stop = threading.Event()
        self._closing = False
        self._tasks = []
        self._enabled = False
        self._config_error = ""
        value = copy.deepcopy(config or {"enabled": False, "tasks": []})
        self._notifications = NotificationConfig()
        try:
            self._notifications = NotificationConfig.model_validate(value)
            # 宿主配置接口直接回传配置，因此密码单独放入插件数据，不留在表单模型。
            secrets = self.get_data("task_passwords") or {}
            resolved = copy.deepcopy(value)
            for task in resolved.get("tasks", []):
                key = task.get("id", "")
                version = str(task.get("password_version", "1"))
                if task.get("password"):
                    secrets[key] = {"version": version, "password": task["password"]}
                elif key in secrets and secrets[key]["version"] == version:
                    task["password"] = secrets[key]["password"]
            for task in value.get("tasks", []):
                task["password"] = ""
                task["password_set"] = task.get("id") in secrets
            self.save_data("task_passwords", secrets)
            self.update_config(value)
            self._tasks = parse_config(resolved)
            self._enabled = bool(value.get("enabled", False))
            logger.info(
                f"压缩归档配置加载完成：enabled={self._enabled} tasks={len(self._tasks)} "
                f"scheduled={sum(task.enabled for task in self._tasks)} auto_continue="
                f"{sum(task.enabled and task.auto_continue for task in self._tasks)}"
            )
            for task in self._tasks:
                logger.info(
                    f"压缩归档任务配置：task={task.name}({task.id[:6]}) enabled={task.enabled} "
                    f"source={task.source_dir} output={task.output_dir} manifest={task.manifest_dir} "
                    f"cron={task.cron} format={task.format} compression={task.compression} "
                    f"encrypted={task.encryption != 'none'} verify={task.verify} "
                    f"delete_source={task.delete_source} auto_continue={task.auto_continue}"
                )
        except (ValueError, OSError, TypeError, KeyError) as exc:
            # Pydantic 的原始错误包含 input_value，不能将可能含密码的输入记录到日志。
            self._config_error = self._safe_error(exc)
            logger.error(f"压缩归档配置未生效：{self._config_error}")

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            return "；".join(
                ".".join(str(part) for part in error["loc"]) + ": " + error["msg"]
                for error in exc.errors(include_input=False, include_context=False)
            )
        return str(exc)[:500]

    def get_state(self) -> bool:
        return self._enabled and not self._config_error

    def get_database_models(self):
        """声明插件隔离表，不向宿主主库注册业务表。"""
        return [BatchRow, FileRow, DirectoryRow, TaskRow]

    def get_database_migrations(self):
        """交由宿主在激活插件前升级独立库，迁移声明优先于模型自动建表。"""
        return Path(__file__).resolve().parent / "migrations"

    def _store(self) -> Store:
        return Store(self.get_database())

    def get_service(self) -> list[dict]:
        """每个启用任务独立 Cron，重入在队列入口合并。"""
        if not self.get_state():
            return []
        services = [
            {
                "id": f"ArchiveManager_{task.id}",
                "name": f"压缩归档 · {task.name}",
                "trigger": CronTrigger.from_crontab(task.cron, timezone=container_timezone()),
                "func": partial(self._enqueue_task, task.id),
                "kwargs": {},
            }
            for task in self._tasks
            if task.enabled
        ]
        if any(task.enabled and task.auto_continue for task in self._tasks):
            services.append(
                {
                    "id": "ArchiveManager_resume",
                    "name": "压缩归档 · 自动续跑",
                    "trigger": "interval",
                    "func": self._resume_waiting,
                    "kwargs": {"seconds": 1200},
                }
            )
        return services

    def _resume_waiting(self):
        """只续跑用户已启动的周期；失败等用户重试，不循环提交失败批次。"""
        for task in self._tasks:
            if task.enabled and task.auto_continue:
                state = self._store().task_state(task.id)
                if state["active"] and state["phase"] not in ("waiting_retry", "stopped"):
                    self._enqueue_task(task.id)

    def _check_execution_paths(self, task: TaskConfig):
        """检查实际执行快照，包含其他停用但已排队任务，防止旧路径绕过隔离。"""
        candidates = [other for other in self._tasks if other.id != task.id and other.enabled]
        with self._lock:
            candidates.extend(job["task"] for job in self._queue if job["task"].id != task.id)
            running = copy.deepcopy(self._running)
        if running and running["task_id"] != task.id:
            other = self._task(running["task_id"])
            if running["batch_id"]:
                other = TaskConfig.model_validate(
                    {**self._store().get(running["batch_id"])["task"], "password": other.password}
                )
            candidates.append(other)
        for other in candidates:
            if not all((other.source_dir, other.output_dir, other.manifest_dir)):
                continue
            source = Path(task.source_dir).resolve()
            other_source = Path(other.source_dir).resolve()
            if any(
                overlap(source, Path(root).resolve())
                for root in (other.source_dir, other.output_dir, other.manifest_dir)
            ) or any(overlap(other_source, Path(root).resolve()) for root in (task.output_dir, task.manifest_dir)):
                raise ValueError("实际执行目录与其他任务重叠；请先调整任务或历史批次的目录归属")

    def _task(self, task_id: str) -> TaskConfig:
        for task in self._tasks:
            if task.id == task_id:
                return task.model_copy(deep=True)
        raise ValueError("任务不存在或配置未生效，请先保存有效配置")

    def _enqueue_task(self, task_id: str, batch_id: str = "", *, repair: bool = False) -> str:
        if not self.get_state():
            raise ValueError("插件未启用，不能执行归档")
        task = self._task(task_id)
        if not repair:
            validate_paths(task)
            self._check_execution_paths(task)
            if batch_id:
                snapshot = self._store().get(batch_id)["task"]
                frozen = TaskConfig.model_validate({**snapshot, "password": task.password})
                self._check_execution_paths(frozen)
        # 手动执行停用任务也遵守跨任务源目录边界。
        active = [t.model_dump() for t in self._tasks]
        for item in active:
            if item["id"] == task_id:
                item["enabled"] = True
        if not repair:
            parse_config({"tasks": active})
        with self._lock:
            if self._closing:
                raise ValueError("插件正在关闭，请稍后重试")
            if self._running and self._running["task_id"] == task_id and self._running["kind"] != "preview":
                if batch_id:
                    raise ValueError("任务正在运行，请结束后再操作指定批次")
                logger.debug(f"压缩归档任务已在运行，复用作业：task={task.name}({task.id[:6]})")
                return self._running["job_id"]
            for job in self._queue:
                if job["task"].id == task_id and job["kind"] != "preview":
                    if batch_id and job["batch_id"] != batch_id:
                        raise ValueError("任务已有排队操作，请完成后再操作指定批次")
                    logger.debug(f"压缩归档任务已在队列，复用作业：task={task.name}({task.id[:6]})")
                    return job["id"]
            job_id = uuid4().hex
            self._queue.append(
                {"id": job_id, "kind": "repair" if repair else "run", "task": task, "batch_id": batch_id}
            )
            logger.info(
                f"压缩归档作业入队：job={job_id[:6]} kind={'repair' if repair else 'run'} "
                f"task={task.name}({task.id[:6]}) batch={batch_id[:6] or '-'} queue={len(self._queue)}"
            )
            self._start_worker()
            return job_id

    def _start_worker(self):
        """调用方持锁；线程只在需要时启动，不抢跑宿主建表阶段。"""
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._work, name="ArchiveManager", daemon=True)
            self._thread.start()

    def _phase(self, phase: str, batch_id: str = ""):
        with self._lock:
            if self._running:
                self._running.update(phase=phase, batch_id=batch_id)

    def _notify_event(self, event: str, task: TaskConfig, title: str, detail: str):
        """推送失败不能改变归档结果，密码也不能进入消息通道。"""
        if not self._notifications.notify or event not in self._notifications.notify_events:
            return
        message = f"任务：{task.name}\n{detail}"
        if task.password:
            message = message.replace(task.password, "***")
        try:
            self.post_message(mtype=NotificationType.Plugin, title=f"压缩归档：{title}", text=message)
        except Exception:  # noqa: BLE001  通知通道失败不得触发归档重试或中断后续批次
            logger.warning("压缩归档通知发送失败，请检查消息通道")

    def _execute_batch(self, runner: Runner, store: Store, batch: dict, task: TaskConfig):
        """只在批次首次完成时通知，恢复已完成成品不重复报告成功。"""
        runner.execute(batch, task)
        result = store.get(batch["id"])
        name = result.get("batch_name", result["id"])
        if result["status"] == "cleanup_failed":
            self._notify_event("failure", task, "源文件清理失败", f"批次：{name}\n{result['error']}")
        elif result["status"] == "completed" and batch["status"] != "completed":
            self._notify_event("success", task, "归档成功", f"批次：{name}\n文件数：{result['file_count']}\n归档文件：{result['archive_path']}")

    def _work(self):
        """预览和运行共用串行队列，停止会取消当前动作并保留已发布结果。"""
        while True:
            with self._lock:
                if not self._queue or self._closing:
                    self._running = None
                    self._thread = None
                    return
                job = self._queue.popleft()
                self._stop.clear()
                task = job["task"]
                self._running = {
                    "task_id": task.id,
                    "batch_id": "",
                    "phase": "scanning",
                    "job_id": job["id"],
                    "kind": job["kind"],
                }
                logger.info(
                    f"压缩归档作业开始：job={job['id'][:6]} kind={job['kind']} "
                    f"task={task.name}({task.id[:6]}) batch={job['batch_id'][:6] or '-'}"
                )
            previous_phase = ""
            try:
                store = self._store()
                previous_phase = store.task_state(task.id)["phase"]
                if job["kind"] == "reclaim":
                    batch = store.get(job["batch_id"])
                    self._phase("cleaning", batch["id"])
                    runner = Runner(store, self._stop, self._phase)
                    runner.reclaim(batch, task)
                    logger.info(
                        f"压缩归档空间回收完成：job={job['id'][:6]} task={task.name}({task.id[:6]}) "
                        f"batch={batch['id'][:6]}"
                    )
                elif job["kind"] == "repair":
                    batch = store.get(job["batch_id"])
                    self._phase("manifest_pending", batch["id"])
                    path = write_catalog(batch)
                    store.save(batch["id"], manifest_path=path)
                    logger.info(
                        f"压缩归档清单补全完成：job={job['id'][:6]} task={task.name}({task.id[:6]}) "
                        f"batch={batch['id'][:6]} manifest={path}"
                    )
                    self._notify_event("other", task, "清单已补全", f"批次：{batch.get('batch_name', batch['id'])}")
                elif job["kind"] == "preview":
                    entries, skipped = scan(task, self._stop)
                    entries = store.exclude_reserved(task.id, entries)
                    batches = partition(task, entries)
                    result = {
                        "file_count": len(entries),
                        "total_bytes": sum(e["size"] for e in entries),
                        "batch_count": len(batches),
                        "skipped_count": skipped,
                        "batches": [
                            {
                                "group": b["group"],
                                "file_count": len(b["entries"]),
                                "total_bytes": b["total_bytes"],
                                "oversized": bool(task.max_bytes and b["total_bytes"] > task.max_bytes),
                            }
                            for b in batches[:200]
                        ],
                    }
                    logger.info(
                        f"压缩归档预览完成：job={job['id'][:6]} task={task.name}({task.id[:6]}) "
                        f"files={result['file_count']} bytes={result['total_bytes']} "
                        f"batches={result['batch_count']} skipped={result['skipped_count']}"
                    )
                    with self._lock:
                        self._previews[job["id"]] = {"status": "complete", "data": result, "message": ""}
                else:
                    runner = Runner(
                        store,
                        self._stop,
                        self._phase,
                        cleanup_cancelled=lambda task_id=task.id: task_id in self._manual_stop_tasks,
                    )
                    if job["batch_id"]:
                        batch = store.get(job["batch_id"])
                        self._check_execution_paths(
                            TaskConfig.model_validate({**batch["task"], "password": task.password})
                        )
                        self._execute_batch(runner, store, batch, task)
                        store.set_task_state(task.id, active=task.auto_continue, phase="history", reason="")
                        continue
                    self._execute_cycle(task, store, runner)
            except Exception as exc:  # noqa: BLE001  队列边界必须把任意插件错误持久化并继续服务后续作业
                message = self._safe_error(exc)
                if task.password:
                    message = message.replace(task.password, "***")
                if job["kind"] == "preview":
                    with self._lock:
                        self._previews[job["id"]] = {"status": "failed", "data": None, "message": message}
                elif isinstance(exc, CapacityWait):
                    self._store().set_task_state(
                        task.id, active=task.auto_continue, phase="waiting_capacity", reason=message
                    )
                    logger.warning(
                        f"压缩归档作业等待容量：job={job['id'][:6]} task={task.name}({task.id[:6]}) "
                        f"reason={message}"
                    )
                elif not isinstance(exc, Cancelled):
                    trace = traceback.format_exc().replace(task.password, "***") if task.password else traceback.format_exc()
                    logger.error(
                        f"压缩归档作业失败：job={job['id'][:6]} task={task.name}({task.id[:6]}) "
                        f"kind={job['kind']} error_type={type(exc).__name__} error={message}\n{trace[-8000:]}"
                    )
                    self.save_data("last_error", {"task_id": task.id, "message": message})
                    self._store().set_task_state(
                        task.id, active=task.auto_continue, phase="waiting_retry", reason=message
                    )
                    self._notify_event("failure", task, "归档失败", message)
                else:
                    self._store().set_task_state(task.id, active=False, phase="stopped", reason="已停止")
                    logger.info(
                        f"压缩归档作业已停止：job={job['id'][:6]} task={task.name}({task.id[:6]})"
                    )
            finally:
                with self._lock:
                    self._running = None
                    self._manual_stop_tasks.discard(task.id)
            if job["kind"] != "preview":
                state = self._store().task_state(task.id)
                if state["phase"] == "waiting_capacity" and previous_phase != "waiting_capacity":
                    self._notify_event("other", task, "等待空间", state["reason"])

    def _execute_cycle(self, task: TaskConfig, store: Store, runner: Runner):
        """历史快照优先，容量不足作为可恢复等待而非归档失败。"""
        store.set_task_state(task.id, active=task.auto_continue, reason="")
        completed = 0
        unfinished = store.unfinished(task.id)[: task.max_batches]
        initial_state = store.task_state(task.id)
        logger.info(
            f"压缩归档周期开始：task={task.name}({task.id[:6]}) phase={initial_state['phase']} "
            f"history_remaining={initial_state['history_remaining']} unfinished_batches={len(unfinished)} "
            f"max_batches={task.max_batches}"
        )
        for batch in unfinished:
            logger.info(
                f"压缩归档恢复未完成批次：task={task.name}({task.id[:6]}) "
                f"batch={batch['id'][:6]} status={batch['status']}"
            )
            self._check_execution_paths(TaskConfig.model_validate({**batch["task"], "password": task.password}))
            self._execute_batch(runner, store, batch, task)
            completed += 1
        recoverable_ids = {batch["id"] for batch in store.unfinished(task.id)}
        removed_staging = cleanup_stale_staging(task, recoverable_ids)
        if removed_staging:
            logger.info(
                f"压缩归档清理不可恢复暂存：task={task.name}({task.id[:6]}) count={removed_staging}"
            )
        state = store.task_state(task.id)
        capacity = allowance(task, store.local_archives(task.id))
        if state.get("initialized") and not capacity["budget"]:
            store.set_task_state(task.id, phase="waiting_capacity", **capacity)
            logger.warning(
                f"压缩归档周期容量受限：task={task.name}({task.id[:6]}) "
                f"pending_archives={capacity['pending_archives']} pending_bytes={capacity['pending_bytes']} "
                f"free_bytes={capacity['free_bytes']} budget_bytes={capacity['budget']} reason={capacity['reason']}"
            )
            return
        # 持久化当前扫描阶段，避免配置重载后任务仍显示为“已停止”。
        store.set_task_state(task.id, active=task.auto_continue, phase="scanning", reason="")
        self._phase("scanning")
        entries, directories, skipped = scan_tree(task, self._stop, stable=True)
        entries = store.inventory(task.id, entries, task.source_dir, task.public())
        pending_directories = store.inventory_directories(task.id, directories, task.public())
        groups = partition(task, entries)
        directory_map = {entry["relative_path"]: entry for entry in directories}
        file_ancestor_paths = {
            parent.as_posix()
            for entry in entries
            for parent in Path(entry["relative_path"]).parents
            if parent.as_posix() != "."
        }
        standalone_directories = [
            entry for entry in pending_directories if entry["relative_path"] not in file_ancestor_paths
        ]
        if standalone_directories:
            limit = task.max_files or len(standalone_directories)
            for offset in range(0, len(standalone_directories), limit):
                groups.append(
                    {
                        "group": "目录结构",
                        "entries": [],
                        "directories": standalone_directories[offset : offset + limit],
                        "total_bytes": 0,
                    }
                )
        logger.info(
            f"压缩归档扫描完成：task={task.name}({task.id[:6]}) eligible_files={len(entries)} "
            f"eligible_directories={len(pending_directories)} eligible_bytes={sum(entry['size'] for entry in entries)} "
            f"batches={len(groups)} skipped={skipped} age_days={task.archive_age_days} "
            f"stability_seconds={task.stability_seconds}"
        )
        while groups and completed < task.max_batches:
            if self._stop.is_set():
                raise Cancelled("已停止")
            capacity = allowance(task, store.local_archives(task.id))
            directory_only = not groups[0]["entries"] and groups[0].get("directories")
            selected = groups[0] if directory_only and capacity["budget"] else (
                fit_batch(groups[0], capacity["budget"]) if capacity["budget"] else None
            )
            if selected is None:
                capacity["reason"] = capacity["reason"] or "剩余容量不足以容纳下一份完整文件，等待空间或调整容量上限"
                store.set_task_state(task.id, phase="waiting_capacity", **capacity)
                logger.warning(
                    f"压缩归档下一批无法容纳：task={task.name}({task.id[:6]}) "
                    f"group={groups[0]['group']} next_file_bytes="
                    f"{groups[0]['entries'][0]['size'] if groups[0]['entries'] else 0} "
                    f"budget_bytes={capacity['budget']} reason={capacity['reason']}"
                )
                return
            selected_directories = list(selected.get("directories", []))
            if selected["entries"]:
                required_paths = {
                    parent.as_posix()
                    for entry in selected["entries"]
                    for parent in Path(entry["relative_path"]).parents
                    if parent.as_posix() != "."
                }
                selected_directories = [directory_map[path] for path in sorted(required_paths) if path in directory_map]
            batch = store.create(
                uuid4().hex, task.public(), selected["entries"], selected["group"], selected_directories
            )
            logger.info(
                f"压缩归档批次已创建：task={task.name}({task.id[:6]}) batch={batch['id'][:6]} "
                f"name={batch['batch_name']} group={selected['group']} files={len(selected['entries'])} "
                f"directories={len(selected_directories)} source_bytes={selected['total_bytes']}"
            )
            self._execute_batch(runner, store, batch, task)
            completed += 1
            remaining = groups[0]["entries"][len(selected["entries"]) :]
            if remaining:
                groups[0] = {**groups[0], "entries": remaining, "total_bytes": sum(e["size"] for e in remaining)}
            else:
                groups.pop(0)
        state = store.task_state(task.id)
        capacity = allowance(task, store.local_archives(task.id))
        if groups:
            store.set_task_state(task.id, phase="history" if state["history_remaining"] else "incremental", **capacity)
        elif state["history_remaining"]:
            store.set_task_state(
                task.id, phase="waiting_retry", reason="历史队列仍有失败或暂不可处理的文件，请检查归档记录"
            )
        else:
            # 历史刚清空时续跑一次以处理初次快照之后达到归档年龄的文件。
            was_history = state["phase"] == "history"
            store.set_task_state(
                task.id,
                active=bool(task.auto_continue and was_history),
                phase="incremental" if was_history else "idle",
                **capacity,
            )
        final_state = store.task_state(task.id)
        logger.info(
            f"压缩归档周期结束：task={task.name}({task.id[:6]}) completed_batches={completed} "
            f"phase={final_state['phase']} history_remaining={final_state['history_remaining']} "
            f"pending_archives={final_state['pending_archives']} pending_bytes={final_state['pending_bytes']} "
            f"free_bytes={final_state['free_bytes']}"
        )

    def stop_service(self):
        """同步等待扫描/工作子进程退出后返回，防止卸载后继续写库或删除文件。"""
        with self._lock:
            self._closing = True
            self._stop.set()
            for job in self._queue:
                if job["kind"] == "preview":
                    self._previews[job["id"]] = {"status": "failed", "data": None, "message": "已停止"}
            self._queue.clear()
            worker = self._thread
        if worker and worker.is_alive():
            logger.info("压缩归档服务停止中：等待当前扫描或归档工作安全退出")
        if worker and worker is not threading.current_thread():
            worker.join()
            logger.info("压缩归档服务已停止")

    @staticmethod
    def get_render_mode():
        return "vue", "frontend/dist/assets"

    def get_form(self):
        """表单默认模型；完整任务编辑由联邦组件承担。"""
        return [], {"enabled": False, "notify": False, "notify_events": ["failure"], "tasks": []}

    # 本插件只有联邦配置页；设为 None 避免宿主把已启用实例识别为数据页。
    get_page = None

    @staticmethod
    def get_command():
        return []

    @staticmethod
    def _response(data=None, message="", success=True):
        return schemas.Response(success=success, message=message, data=data)

    def api_summary(self):
        data = self._store().summary()
        with self._lock:
            data.update(
                running=copy.deepcopy(self._running),
                queued=[job["task"].id for job in self._queue],
                config_error=self._config_error,
            )
        data["last_error"] = self.get_data("last_error")
        data["tasks"] = [self._store().task_state(task.id) for task in self._tasks]
        return self._response(data)

    @staticmethod
    def _public_batch(batch: dict, detail=False) -> dict:
        """新查询接口不暴露内部快照，成品缺失只表示本地不可用。"""
        value = {key: val for key, val in batch.items() if key not in ("task", "entries", "manifest")}
        value["archive_available"] = bool(batch["archive_path"] and Path(batch["archive_path"]).is_file())
        value["manifest_available"] = bool(batch["manifest_path"] and Path(batch["manifest_path"]).is_file())
        if detail:
            value["files"] = batch["manifest"]["files"] if batch["manifest"] else batch["entries"]
            value["options"] = {
                key: batch["task"][key]
                for key in (
                    "format",
                    "compression",
                    "encryption",
                    "encrypt_names",
                    "password_version",
                    "source_dir",
                    "output_dir",
                    "manifest_dir",
                )
            }
        return value

    def api_batches(self, task_id: str = "", status: str = "", page: int = 1, page_size: int = 30):
        result = self._store().batches(task_id, status, max(1, page), max(1, min(page_size, 100)))
        result["items"] = [self._public_batch(batch) for batch in result["items"]]
        return self._response(result)

    def api_batch(self, batch_id: str):
        try:
            return self._response(self._public_batch(self._store().get(batch_id), True))
        except ValueError as exc:
            return self._response(success=False, message=str(exc))

    def api_files(
        self,
        task_id: str = "",
        directory: str = "",
        query: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 30,
    ):
        return self._response(
            self._store().files(task_id, directory, query, status, max(1, page), max(1, min(page_size, 100)))
        )

    def api_preview_start(self, request: PreviewRequest):
        try:
            value = dict(request.task)
            if value.get("encryption") == "aes256" and not value.get("password"):
                existing = self._task(value["id"])
                if existing.password_version == str(value.get("password_version", "1")):
                    value["password"] = existing.password
            task = TaskConfig.model_validate(value)
            validate_paths(task)
            with self._lock:
                if self._closing:
                    raise ValueError("插件正在关闭")
                if len(self._previews) >= 20:
                    complete = next(
                        (key for key, result in self._previews.items() if result["status"] != "running"), None
                    )
                    if complete:
                        self._previews.pop(complete)
                    else:
                        raise ValueError("预览队列已满")
                job_id = uuid4().hex
                self._previews[job_id] = {"status": "running", "data": None, "message": ""}
                self._queue.append({"id": job_id, "kind": "preview", "task": task, "batch_id": ""})
                self._start_worker()
            return self._response({"job_id": job_id})
        except (ValueError, KeyError) as exc:
            return self._response(success=False, message=self._safe_error(exc))

    def api_preview(self, job_id: str):
        with self._lock:
            result = copy.deepcopy(self._previews.get(job_id))
        return self._response(result, success=result is not None, message="" if result else "预览已过期，请重新预览")

    def _reclaimable_batches(self) -> list[dict]:
        return self._store().reclaimable_batches()

    @staticmethod
    def _snapshot_task_for_maintenance(snapshot: dict) -> TaskConfig:
        """清理产物和暂存只需要路径契约，不应因历史密码未加载而失败。"""
        return TaskConfig.model_validate(
            {**snapshot, "password": "", "encryption": "none", "encrypt_names": False}
        )

    def _staging_tasks(self) -> list[tuple[TaskConfig, set[str]]]:
        """收集当前配置和历史快照中的暂存目录，保留仍可恢复批次。"""
        store = self._store()
        values: dict[tuple[str, str], tuple[TaskConfig, set[str]]] = {}
        for task in self._tasks:
            values[(task.id, task.output_dir)] = (task, set())
        for batch in store.batches(page=1, page_size=100000)["items"]:
            snapshot = batch.get("task") or {}
            try:
                task = self._snapshot_task_for_maintenance(snapshot)
            except (TypeError, ValueError):
                continue
            values.setdefault((task.id, task.output_dir), (task, set()))
        for key, (task, _) in list(values.items()):
            values[key] = (task, {batch["id"] for batch in store.unfinished(task.id)})
        return list(values.values())

    def _staging_reclaim_preview(self) -> tuple[int, int]:
        count = 0
        total = 0
        for task, keep_ids in self._staging_tasks():
            item_count, item_bytes = staging_size(task, keep_ids)
            count += item_count
            total += item_bytes
        return count, total

    def _cleanup_reclaimable_staging(self) -> tuple[int, int]:
        count = 0
        total = 0
        for task, keep_ids in self._staging_tasks():
            item_count, item_bytes = staging_size(task, keep_ids)
            removed = cleanup_stale_staging(task, keep_ids)
            if removed:
                count += removed
                total += item_bytes
                logger.info(
                    f"压缩归档回收空间清理孤儿暂存：task={task.name}({task.id[:6]}) count={removed} bytes={item_bytes}"
                )
        return count, total

    @staticmethod
    def _reclaim_estimated_bytes(batches: list[dict]) -> int:
        return sum(
            int(entry.get("size", 0))
            for batch in batches
            for entry in (batch.get("manifest") or {}).get("files", [])
        )

    def api_reclaim_preview(self, request: ReclaimRequest):
        """只统计可回收源文件，供确认框展示，不加入队列。"""
        del request
        try:
            batches = self._reclaimable_batches()
            files = sum(len((batch.get("manifest") or {}).get("files", [])) for batch in batches)
            staging_count, staging_bytes = self._staging_reclaim_preview()
            return self._response(
                {
                    "batch_count": len(batches),
                    "file_count": files,
                    "estimated_bytes": self._reclaim_estimated_bytes(batches) + staging_bytes,
                    "staging_count": staging_count,
                    "staging_bytes": staging_bytes,
                }
            )
        except (ValueError, OSError) as exc:
            return self._response(success=False, message=self._safe_error(exc))

    def api_reclaim(self, request: ReclaimRequest):
        """批量回收所有已发布批次的源文件，归档包和清单保持不变。"""
        del request
        try:
            batches = self._reclaimable_batches()
            staging_count, staging_bytes = self._cleanup_reclaimable_staging()
            with self._lock:
                queued = {job["batch_id"] for job in self._queue if job["kind"] == "reclaim"}
                running = self._running.get("batch_id") if self._running else ""
                jobs = []
                for batch in batches:
                    if batch["id"] in queued or batch["id"] == running:
                        continue
                    task = self._snapshot_task_for_maintenance(batch["task"])
                    job_id = uuid4().hex
                    jobs.append({"id": job_id, "kind": "reclaim", "task": task, "batch_id": batch["id"]})
                self._queue.extend(jobs)
                if jobs:
                    self._start_worker()
            estimated_bytes = self._reclaim_estimated_bytes(batches)
            return self._response(
                {
                    "queued": len(jobs),
                    "found": len(batches),
                    "estimated_bytes": estimated_bytes + staging_bytes,
                    "staging_removed": staging_count,
                    "staging_bytes": staging_bytes,
                }
            )
        except (ValueError, OSError) as exc:
            return self._response(success=False, message=self._safe_error(exc))

    def api_run(self, request: TaskRequest):
        try:
            if request.task_id:
                return self._response({"job_id": self._enqueue_task(request.task_id), "task_count": 1})
            if not self._tasks:
                raise ValueError("没有可运行的归档任务")
            # 先检查全部任务，再统一入队，避免路径错误导致只提交一部分任务。
            for task in self._tasks:
                validate_paths(task)
                self._check_execution_paths(task)
            job_ids = [self._enqueue_task(task.id) for task in self._tasks]
            return self._response({"job_ids": job_ids, "task_count": len(job_ids)})
        except (ValueError, OSError) as exc:
            return self._response(success=False, message=self._safe_error(exc))

    def api_stop(self, request: TaskRequest):
        target_ids = {task.id for task in self._tasks if not request.task_id or task.id == request.task_id}
        for task in self._tasks:
            if task.id in target_ids:
                self._store().set_task_state(task.id, active=False, phase="stopped", reason="已停止")
        with self._lock:
            running_task_id = self._running.get("task_id") if self._running else None
            if running_task_id and running_task_id in target_ids:
                self._manual_stop_tasks.add(running_task_id)
            if not request.task_id or (self._running and self._running["task_id"] == request.task_id):
                self._stop.set()
            for job in self._queue:
                if (not request.task_id or job["task"].id == request.task_id) and job["kind"] == "preview":
                    self._previews[job["id"]] = {"status": "failed", "data": None, "message": "已停止"}
            self._queue = deque(job for job in self._queue if request.task_id and job["task"].id != request.task_id)
        return self._response({"stopping": True})

    @staticmethod
    def _artifact_paths(batch: dict) -> list[Path]:
        """只允许删除批次快照中归档输出目录内的已发布文件。"""
        archive_value = str(batch.get("archive_path") or "").strip()
        if not archive_value:
            return []
        archive = Path(archive_value)
        output = Path(str(batch["task"].get("output_dir") or "")).resolve()
        resolved = archive.resolve(strict=False)
        try:
            resolved.relative_to(output)
        except ValueError as exc:
            raise ValueError("归档包路径不在该任务输出目录内，拒绝删除") from exc
        if archive.is_symlink() or (archive.exists() and not archive.is_file()):
            raise ValueError(f"归档包不是普通文件，拒绝删除：{archive}")
        checksum = archive.with_name(archive.name + ".sha256")
        if checksum.is_symlink() or (checksum.exists() and not checksum.is_file()):
            raise ValueError(f"归档校验文件不是普通文件，拒绝删除：{checksum}")
        manifest_value = str(batch.get("manifest_path") or "").strip()
        if manifest_value:
            manifest_root = Path(str(batch["task"].get("manifest_dir") or "")).resolve()
            manifest_path = Path(manifest_value).resolve(strict=False)
            try:
                manifest_path.relative_to(manifest_root)
            except ValueError as exc:
                raise ValueError("清单路径不在该任务清单目录内，拒绝删除") from exc
        return [archive, checksum]

    def api_cleanup(self, request: BatchCleanupRequest):
        """清理批次账本；源文件永远不在此入口中删除或修改。"""
        ids = list(dict.fromkeys(request.batch_ids))
        try:
            with self._lock:
                batches = [self._store().get(batch_id) for batch_id in ids]
                allowed = {"completed", "failed", "cancelled", "superseded"}
                for batch in batches:
                    if batch["status"] not in allowed:
                        raise ValueError(f"批次正在执行或等待恢复，不能清理：{batch.get('batch_name', batch['id'])}")
                    if self._running and self._running.get("batch_id") == batch["id"]:
                        raise ValueError("批次正在执行，不能清理")
                    if any(job.get("batch_id") == batch["id"] for job in self._queue):
                        raise ValueError("批次正在队列中，不能清理")
                cleanup_tasks: dict[tuple[str, str], TaskConfig] = {}
                for batch in batches:
                    task = self._snapshot_task_for_maintenance(batch["task"])
                    cleanup_tasks[(task.id, task.output_dir)] = task
                    remove_staging(task, batch["id"])
                    if request.delete_artifacts:
                        for path in self._artifact_paths(batch):
                            if path.is_file():
                                path.unlink()
                        remove_catalog(batch)
                # 清理时顺便扫描同一任务的暂存根目录，处理旧版本手工停止留下的孤儿目录。
                # 仍处于可恢复阶段的批次必须保留，避免清理动作破坏恢复链路。
                for task in cleanup_tasks.values():
                    recoverable_ids = {batch["id"] for batch in self._store().unfinished(task.id)}
                    removed = cleanup_stale_staging(task, recoverable_ids)
                    if removed:
                        logger.info(
                            f"压缩归档清理批次时移除孤儿暂存：task={task.name}({task.id[:6]}) count={removed}"
                        )
                result = self._store().clean_batches(ids)
            return self._response(result)
        except (ValueError, OSError) as exc:
            return self._response(success=False, message=self._safe_error(exc))

    def api_retry(self, request: BatchRequest):
        try:
            batch = self._store().get(request.batch_id)
            if batch["status"] == "completed":
                raise ValueError("批次已经完成；可使用清单补全重新生成外部文档")
            if batch["status"] == "superseded":
                raise ValueError("该批次源文件已变化，请运行任务重新分批")
            current = self._task(batch["task_id"])
            if not batch["archive_sha256"] and batch["task"] != current.public():
                self._store().supersede(batch["id"])
                return self._response({"job_id": self._enqueue_task(batch["task_id"])})
            return self._response({"job_id": self._enqueue_task(batch["task_id"], batch["id"])})
        except (ValueError, OSError) as exc:
            return self._response(success=False, message=self._safe_error(exc))

    def api_repair(self, request: BatchRequest):
        try:
            batch = self._store().get(request.batch_id)
            if not batch["manifest"]:
                raise ValueError("归档尚未生成，不能补全文档")
            return self._response({"job_id": self._enqueue_task(batch["task_id"], batch["id"], repair=True)})
        except (ValueError, OSError) as exc:
            return self._response(success=False, message=self._safe_error(exc))

    def get_api(self):
        """所有插件操作使用宿主认证，不暴露匿名运行和清理入口。"""
        routes = [
            ("summary", "GET", self.api_summary, "归档概览"),
            ("batches", "GET", self.api_batches, "批次列表"),
            ("batch", "GET", self.api_batch, "批次详情"),
            ("files", "GET", self.api_files, "文件目录"),
            ("preview", "POST", self.api_preview_start, "开始只读预览"),
            ("preview", "GET", self.api_preview, "预览结果"),
            ("run", "POST", self.api_run, "运行归档"),
            ("reclaim/preview", "POST", self.api_reclaim_preview, "预览可回收源文件"),
            ("reclaim", "POST", self.api_reclaim, "回收源文件"),
            ("stop", "POST", self.api_stop, "停止归档"),
            ("retry", "POST", self.api_retry, "重试批次"),
            ("cleanup", "POST", self.api_cleanup, "清理批次"),
            ("repair", "POST", self.api_repair, "补全清单"),
        ]
        return [
            {
                "path": f"/{path}",
                "endpoint": endpoint,
                "methods": [method],
                "auth": "bear",
                "summary": title,
                "response_model": schemas.Response[dict],
            }
            for path, method, endpoint, title in routes
        ]
