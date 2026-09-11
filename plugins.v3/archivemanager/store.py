"""插件独立数据库：逐文件版本索引与可恢复批次账本。"""

from datetime import datetime, timezone
from pathlib import Path

from app.sdk.database import plugin_declarative_base
from sqlalchemy import (
    JSON,
    Boolean,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column

from .naming import frozen_names
from zoneinfo import ZoneInfo
from .scanner import fingerprint, identity

Base = plugin_declarative_base()


class BatchRow(Base):
    """批次阶段与不含密码的恢复快照；文件明细另表保存。"""

    __tablename__ = "archive_batch"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 唯一批次 ID
    task_id: Mapped[str] = mapped_column(String(64), index=True)  # 来源任务
    status: Mapped[str] = mapped_column(String(32), index=True)  # 可恢复执行阶段
    created_at: Mapped[str] = mapped_column(String(40), index=True)  # UTC 创建时间
    data: Mapped[dict] = mapped_column(JSON)  # 成品路径、摘要及任务快照，不含密码


class FileRow(Base):
    """每个源文件版本一行；即使成品被上传器移走仍保留去重证据。"""

    __tablename__ = "archive_file"
    __table_args__ = (UniqueConstraint("task_id", "fingerprint"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 内部行标识
    task_id: Mapped[str] = mapped_column(String(64), index=True)  # 任务边界
    fingerprint: Mapped[str] = mapped_column(String(64))  # 路径与文件版本指纹
    relative_path: Mapped[str] = mapped_column(Text)  # 完整源相对路径
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # 已预留的批次
    present: Mapped[bool] = mapped_column(Boolean, default=True)  # 最近一次扫描可见
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)  # 文件归档/清理结果
    data: Mapped[dict] = mapped_column(JSON)  # 文件身份、大小、时间与内容摘要
    historical: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # 是否属于初次合格文件快照


class TaskRow(Base):
    """跨运行保存历史快照边界、续跑意图及等待原因。"""

    __tablename__ = "archive_task"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 稳定任务标识
    data: Mapped[dict] = mapped_column(JSON)  # 队列阶段与空间统计，不包含密码


class Store:
    """每次操作独立会话，在线程间不共享 Session，兼容 SQLite 与 PostgreSQL。"""

    def __init__(self, handle):
        self.handle = handle

    def inventory(
        self, task_id: str, entries: list[dict], source_dir: str = "", task_config: dict | None = None
    ) -> list[dict]:
        """刷新最近扫描索引并返回尚未被批次预留的文件。"""
        with self.handle.session() as session, session.begin():
            state = session.get(TaskRow, task_id)
            if state is None:
                state = TaskRow(id=task_id, data={})
                session.add(state)
            fresh = not state.data.get("initialized") or state.data.get("source_dir", "") != source_dir
            rows = {row.fingerprint: row for row in session.scalars(select(FileRow).where(FileRow.task_id == task_id))}
            if fresh:
                for row in rows.values():
                    row.historical = False
                state.data = {
                    **state.data,
                    "initialized": True,
                    "source_dir": source_dir,
                    "history_started_at": datetime.now(timezone.utc).isoformat(),
                    "phase": "history",
                }
            current = {fingerprint(entry) for entry in entries}
            stale = session.scalars(
                select(BatchRow).where(BatchRow.task_id == task_id, BatchRow.status.in_(["failed", "cancelled"]))
            )
            for batch in stale:
                # 未发布的失败快照失效后允许剩余成员重新分批，不能永久锁住未归档文件。
                changed_config = task_config is not None and batch.data["task"] != task_config
                if not batch.data["archive_sha256"] and (
                    changed_config or any(fingerprint(e) not in current for e in batch.data["entries"])
                ):
                    batch.status = "superseded"
                    batch.data = {**batch.data, "error": "源文件版本或任务配置已变化，未归档成员将在本轮重新分批"}
                    for row in rows.values():
                        if row.batch_id == batch.id:
                            row.batch_id = None
                            row.status = "pending"
            session.execute(update(FileRow).where(FileRow.task_id == task_id).values(present=False))
            pending = []
            for entry in entries:
                key = fingerprint(entry)
                row = rows.get(key)
                if row is None:
                    row = FileRow(
                        task_id=task_id,
                        fingerprint=key,
                        relative_path=entry["relative_path"],
                        data=entry,
                        present=True,
                        status="pending",
                        historical=fresh,
                    )
                    session.add(row)
                else:
                    row.present = True
                    if fresh:
                        row.historical = True
                if not row.batch_id:
                    pending.append(entry)
            if source_dir:
                for key, row in rows.items():
                    if row.historical and key not in current and row.status == "pending":
                        # 历史版本已消失或被修改需有明确记录，不把它伪装成已归档。
                        try:
                            current_identity = identity(Path(source_dir) / row.relative_path)
                            if any(current_identity[field] != row.data[field] for field in current_identity):
                                row.status = "changed"
                        except FileNotFoundError:
                            row.status = "missing"
                        except OSError, ValueError:
                            pass
            session.flush()
            historical_pending = list(
                session.scalars(
                    select(FileRow).where(
                        FileRow.task_id == task_id, FileRow.historical.is_(True), FileRow.status == "pending"
                    )
                )
            )
            if historical_pending:
                state.data = {**state.data, "phase": "history"}
                eligible = {row.fingerprint for row in historical_pending if not row.batch_id}
                return [entry for entry in pending if fingerprint(entry) in eligible]
            state.data = {**state.data, "phase": "incremental"}
            return pending

    def task_state(self, task_id: str) -> dict:
        """返回状态快照，历史变化/缺失单独计数，不能计入归档成功。"""
        with self.handle.session() as session:
            row = session.get(TaskRow, task_id)
            data = dict(row.data) if row else {}
            counts = dict(
                session.execute(
                    select(FileRow.status, func.count())
                    .where(FileRow.task_id == task_id, FileRow.historical.is_(True))
                    .group_by(FileRow.status)
                ).all()
            )
            return {
                "task_id": task_id,
                "phase": "idle",
                "active": False,
                "reason": "",
                "pending_archives": 0,
                "pending_bytes": 0,
                "free_bytes": 0,
                **data,
                "history_total": sum(counts.values()),
                "history_remaining": counts.get("pending", 0),
                "history_archived": sum(counts.get(key, 0) for key in ("archived", "deleted", "retained", "failed")),
                "history_unavailable": sum(counts.get(key, 0) for key in ("changed", "missing")),
            }

    def supersede(self, batch_id: str) -> None:
        """仅未发布失败快照可废弃重建；保留原失败记录，不删除任何用户文件。"""
        with self.handle.session() as session, session.begin():
            row = session.get(BatchRow, batch_id)
            if row is None or row.data["archive_sha256"] or row.status not in ("failed", "cancelled"):
                raise ValueError("该批次不能按新配置重新分批")
            row.status = "superseded"
            row.data = {**row.data, "error": "已采用新配置重新分批"}
            session.execute(update(FileRow).where(FileRow.batch_id == batch_id).values(batch_id=None, status="pending"))

    def set_task_state(self, task_id: str, **changes) -> None:
        """持久化续跑意图，重启后无需重新捕获历史边界。"""
        with self.handle.session() as session, session.begin():
            row = session.get(TaskRow, task_id)
            if row is None:
                session.add(TaskRow(id=task_id, data=changes))
            else:
                row.data = {**row.data, **changes}

    def local_archives(self, task_id: str) -> list[dict]:
        """只统计确实仍在本地的成品；文件消失不等于上传成功。"""
        with self.handle.session() as session:
            records = [
                self._serialize(row) for row in session.scalars(select(BatchRow).where(BatchRow.task_id == task_id))
            ]
        return [batch for batch in records if batch["archive_path"] and Path(batch["archive_path"]).is_file()]

    def exclude_reserved(self, task_id: str, entries: list[dict]) -> list[dict]:
        """预览只查询去重证据，不刷新扫描状态。"""
        with self.handle.session() as session:
            known = set(
                session.scalars(
                    select(FileRow.fingerprint).where(FileRow.task_id == task_id, FileRow.batch_id.is_not(None))
                )
            )
        return [entry for entry in entries if fingerprint(entry) not in known]

    def create(self, batch_id: str, task: dict, entries: list[dict], group: str) -> dict:
        """先预留全部成员并提交快照，再允许工作进程创建归档。"""
        created_at = datetime.now(timezone.utc).isoformat()
        local_day = datetime.fromisoformat(created_at).astimezone(ZoneInfo(task["timezone"])).date()
        sequence = 1
        # 序号按任务和容器本地日期递增；批次名称冻结后不会因重试改变。
        with self.handle.session() as sequence_session:
            for row in sequence_session.scalars(select(BatchRow).where(BatchRow.task_id == task["id"])).all():
                if datetime.fromisoformat(row.created_at).astimezone(ZoneInfo(task["timezone"])).date() == local_day:
                    sequence += 1
        data = {
            **frozen_names(task, batch_id, created_at, sequence),
            "task": task,
            "task_name": task["name"],
            "entries": entries,
            "group": group,
            "file_count": len(entries),
            "source_bytes": sum(e["size"] for e in entries),
            "archive_size": 0,
            "archive_path": "",
            "manifest_path": "",
            "archive_sha256": "",
            "verified": False,
            "error": "",
            "cleanup": {},
            "manifest": None,
        }
        with self.handle.session() as session, session.begin():
            session.add(BatchRow(id=batch_id, task_id=task["id"], status="building", created_at=created_at, data=data))
            for entry in entries:
                row = session.scalar(
                    select(FileRow).where(FileRow.task_id == task["id"], FileRow.fingerprint == fingerprint(entry))
                )
                if row is None or row.batch_id:
                    raise ValueError("文件版本已经被其他批次预留，请重新扫描")
                row.batch_id = batch_id
                row.status = "pending"
        return self.get(batch_id)

    @staticmethod
    def _serialize(row: BatchRow) -> dict:
        return {**row.data, "id": row.id, "task_id": row.task_id, "status": row.status, "created_at": row.created_at}

    def get(self, batch_id: str) -> dict:
        with self.handle.session() as session:
            row = session.get(BatchRow, batch_id)
            if row is None:
                raise ValueError("归档批次不存在")
            return self._serialize(row)

    def save(self, batch_id: str, *, status: str | None = None, **changes) -> dict:
        """阶段状态和归档摘要在同一事务提交。"""
        with self.handle.session() as session, session.begin():
            row = session.get(BatchRow, batch_id)
            if row is None:
                raise ValueError("归档批次不存在")
            row.data = {**row.data, **changes}
            if status:
                row.status = status
            return self._serialize(row)

    def complete_files(self, batch: dict) -> None:
        """成品和外部文档均成功后，文件版本才计入已归档数量。"""
        manifest_files = {item["relative_path"]: item for item in batch["manifest"]["files"]}
        with self.handle.session() as session, session.begin():
            for row in session.scalars(select(FileRow).where(FileRow.batch_id == batch["id"])):
                row.data = {**manifest_files[row.relative_path], "source_root": row.data.get("source_root", "")}
                row.status = batch["cleanup"].get(row.relative_path, "archived")
                if row.status == "retained":
                    row.status = "archived"
                if row.status in ("deleted", "missing"):
                    row.present = False

    def batches(self, task_id: str = "", status: str = "", page: int = 1, page_size: int = 30) -> dict:
        """分页批次列表；执行快照仅供内部恢复使用。"""
        query = select(BatchRow)
        if task_id:
            query = query.where(BatchRow.task_id == task_id)
        if status:
            query = query.where(BatchRow.status == status)
        with self.handle.session() as session:
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.scalars(
                query.order_by(BatchRow.created_at.desc(), BatchRow.id).offset((page - 1) * page_size).limit(page_size)
            )
            return {"items": [self._serialize(row) for row in rows], "total": total}

    def unfinished(self, task_id: str) -> list[dict]:
        """失败/取消等待显式重试，其余中断阶段在下一轮自动核对恢复。"""
        with self.handle.session() as session:
            rows = session.scalars(
                select(BatchRow)
                .where(
                    BatchRow.task_id == task_id,
                    BatchRow.status.not_in(["completed", "failed", "cancelled", "superseded"]),
                )
                .order_by(BatchRow.created_at)
            )
            return [self._serialize(row) for row in rows]

    def file_result(self, batch_id: str, relative_path: str, result: str) -> None:
        """逐文件清理只更新当前成员，避免每次删除都重写整个批次的数据库行。"""
        with self.handle.session() as session, session.begin():
            row = session.scalar(
                select(FileRow).where(FileRow.batch_id == batch_id, FileRow.relative_path == relative_path)
            )
            if row is not None:
                row.status = result
                if result in ("deleted", "missing"):
                    row.present = False

    def summary(self) -> dict:
        with self.handle.session() as session:
            batch_rows = list(session.scalars(select(BatchRow)))
            completed = [row for row in batch_rows if row.status in ("completed", "cleaning", "cleanup_failed")]

            def count(*states):
                return session.scalar(select(func.count()).select_from(FileRow).where(FileRow.status.in_(states)))

            return {
                "archived_files": sum(row.data["file_count"] for row in completed),
                "archive_count": len(completed),
                "source_bytes": sum(row.data["source_bytes"] for row in completed),
                "archive_bytes": sum(row.data["archive_size"] for row in completed),
                "deleted_files": count("deleted"),
                "failed_batches": sum(
                    row.status in ("failed", "manifest_pending", "cleanup_failed") for row in batch_rows
                ),
                "pending_files": session.scalar(
                    select(func.count())
                    .select_from(FileRow)
                    .where(FileRow.status == "pending", FileRow.present.is_(True))
                ),
            }

    def files(
        self,
        task_id: str = "",
        directory: str = "",
        query: str = "",
        status: str = "",
        page: int = 1,
        page_size: int = 30,
    ) -> dict:
        """按原相对路径检索；目录列表不读取现场文件系统。"""
        statement = select(FileRow)
        if task_id:
            statement = statement.where(FileRow.task_id == task_id)
        if query:
            statement = statement.where(FileRow.relative_path.contains(query, autoescape=True))
        if status:
            statement = statement.where(FileRow.status == status)
        prefix = directory.strip("/") + "/" if directory.strip("/") else ""
        if prefix:
            statement = statement.where(FileRow.relative_path.startswith(prefix, autoescape=True))
        with self.handle.session() as session:
            paths = session.scalars(statement.with_only_columns(FileRow.relative_path))
            directories = sorted({p[len(prefix) :].split("/", 1)[0] for p in paths if "/" in p[len(prefix) :]})
            # 搜索递归匹配；正常浏览只展示当前目录中的文件。
            if not query:
                statement = statement.where(~func.substr(FileRow.relative_path, len(prefix) + 1).contains("/"))
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            rows = session.scalars(
                statement.order_by(FileRow.relative_path, FileRow.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            return {
                "items": [
                    {**row.data, "status": row.status, "batch_id": row.batch_id, "task_id": row.task_id} for row in rows
                ],
                "directories": [{"name": name, "path": prefix + name} for name in directories],
                "total": total,
            }
