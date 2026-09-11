"""压缩归档：任务配置、认证 API 和单工作队列的宿主适配入口。"""

import copy
import threading
from collections import deque
from functools import partial
from pathlib import Path
from uuid import uuid4

from app import schemas
from app.schemas.types import NotificationType
from app.plugins import _PluginBase
from app.sdk.logging import logger
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, Field, ValidationError

from .capacity import CapacityWait, allowance, fit_batch
from .catalog import write_catalog
from .config import NotificationConfig, TaskConfig, overlap, parse_config, validate_paths
from .runner import Runner
from .scanner import Cancelled, partition, scan
from .store import BatchRow, FileRow, Store, TaskRow


class TaskRequest(BaseModel):
    """任务执行与停止请求。"""

    task_id: str = ""  # 空标识仅用于停止全部队列


class BatchRequest(BaseModel):
    """按稳定批次标识重试或补全文档。"""

    batch_id: str  # 原批次 ID，保持成品名称不变


class PreviewRequest(BaseModel):
    """未保存草稿的只读预览请求。"""

    task: dict = Field(default_factory=dict)  # 与任务配置相同的字段结构


class ArchiveManager(_PluginBase):
    """只归档本地普通文件；上传及云端状态由用户的外部工具负责。"""

    plugin_name = "压缩归档"  # 市场显示名
    plugin_desc = "文件压缩归档，支持独立清单、校验和可选加密。"  # 用户可见能力
    plugin_icon = "archivemanager.png"  # 本地验收临时使用主程序前端的图标副本
    plugin_version = "0.1.0"  # 插件版本
    plugin_author = "InfinityPacer"  # 维护者
    author_url = "https://github.com/InfinityPacer"  # 维护者主页
    plugin_config_prefix = "archivemanager_"  # 配置项命名空间
    plugin_order = 30  # 市场排序
    auth_level = 1  # 使用权限等级

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

    def init_plugin(self, config: dict = None):
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
        return [BatchRow, FileRow, TaskRow]

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
                "trigger": CronTrigger.from_crontab(task.cron, timezone=task.timezone),
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
                    "kwargs": {"seconds": 60},
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
                return self._running["job_id"]
            for job in self._queue:
                if job["task"].id == task_id and job["kind"] != "preview":
                    if batch_id and job["batch_id"] != batch_id:
                        raise ValueError("任务已有排队操作，请完成后再操作指定批次")
                    return job["id"]
            job_id = uuid4().hex
            self._queue.append(
                {"id": job_id, "kind": "repair" if repair else "run", "task": task, "batch_id": batch_id}
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
            previous_phase = ""
            try:
                store = self._store()
                previous_phase = store.task_state(task.id)["phase"]
                if job["kind"] == "repair":
                    batch = store.get(job["batch_id"])
                    self._phase("manifest_pending", batch["id"])
                    path = write_catalog(batch)
                    store.save(batch["id"], manifest_path=path)
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
                    with self._lock:
                        self._previews[job["id"]] = {"status": "complete", "data": result, "message": ""}
                else:
                    runner = Runner(store, self._stop, self._phase)
                    if job["batch_id"]:
                        batch = store.get(job["batch_id"])
                        self._check_execution_paths(
                            TaskConfig.model_validate({**batch["task"], "password": task.password})
                        )
                        self._execute_batch(runner, store, batch, task)
                        store.set_task_state(task.id, active=task.auto_continue, phase="history", reason="")
                        continue
                    self._execute_cycle(task, store, runner)
            except Exception as exc:
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
                elif not isinstance(exc, Cancelled):
                    logger.error(f"压缩归档任务 {task.id}：{message}")
                    self.save_data("last_error", {"task_id": task.id, "message": message})
                    self._store().set_task_state(
                        task.id, active=task.auto_continue, phase="waiting_retry", reason=message
                    )
                    self._notify_event("failure", task, "归档失败", message)
                else:
                    self._store().set_task_state(task.id, active=False, phase="stopped", reason="已停止")
                    self._notify_event("other", task, "任务已停止", "归档已停止，已发布成品和清单保留。")
            finally:
                with self._lock:
                    self._running = None
            if job["kind"] != "preview":
                state = self._store().task_state(task.id)
                if state["phase"] == "waiting_capacity" and previous_phase != "waiting_capacity":
                    self._notify_event("other", task, "等待空间", state["reason"])

    def _execute_cycle(self, task: TaskConfig, store: Store, runner: Runner):
        """历史快照优先，容量不足作为可恢复等待而非归档失败。"""
        store.set_task_state(task.id, active=task.auto_continue, reason="")
        completed = 0
        for batch in store.unfinished(task.id)[: task.max_batches]:
            self._check_execution_paths(TaskConfig.model_validate({**batch["task"], "password": task.password}))
            self._execute_batch(runner, store, batch, task)
            completed += 1
        state = store.task_state(task.id)
        capacity = allowance(task, store.local_archives(task.id))
        if state.get("initialized") and not capacity["budget"]:
            store.set_task_state(task.id, phase="waiting_capacity", **capacity)
            return
        self._phase("scanning")
        entries, _skipped = scan(task, self._stop, stable=True)
        entries = store.inventory(task.id, entries, task.source_dir, task.public())
        groups = partition(task, entries)
        while groups and completed < task.max_batches:
            if self._stop.is_set():
                raise Cancelled("已停止")
            capacity = allowance(task, store.local_archives(task.id))
            selected = fit_batch(groups[0], capacity["budget"]) if capacity["budget"] else None
            if selected is None:
                capacity["reason"] = capacity["reason"] or "剩余容量不足以容纳下一份完整文件，等待空间或调整容量上限"
                store.set_task_state(task.id, phase="waiting_capacity", **capacity)
                return
            batch = store.create(uuid4().hex, task.public(), selected["entries"], selected["group"])
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
        if worker and worker is not threading.current_thread():
            worker.join()

    @staticmethod
    def get_render_mode():
        return "vue", "frontend/dist/assets"

    def get_form(self):
        """表单默认模型；完整任务编辑由联邦组件承担。"""
        return [], {"enabled": False, "notify": False, "notify_events": ["failure"], "tasks": []}

    def get_page(self):
        return None

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

    def api_run(self, request: TaskRequest):
        try:
            return self._response({"job_id": self._enqueue_task(request.task_id)})
        except (ValueError, OSError) as exc:
            return self._response(success=False, message=self._safe_error(exc))

    def api_stop(self, request: TaskRequest):
        for task in self._tasks:
            if not request.task_id or task.id == request.task_id:
                self._store().set_task_state(task.id, active=False, phase="stopped", reason="已停止")
        with self._lock:
            if not request.task_id or (self._running and self._running["task_id"] == request.task_id):
                self._stop.set()
            for job in self._queue:
                if (not request.task_id or job["task"].id == request.task_id) and job["kind"] == "preview":
                    self._previews[job["id"]] = {"status": "failed", "data": None, "message": "已停止"}
            self._queue = deque(job for job in self._queue if request.task_id and job["task"].id != request.task_id)
        return self._response({"stopping": True})

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
            ("stop", "POST", self.api_stop, "停止归档"),
            ("retry", "POST", self.api_retry, "重试批次"),
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
