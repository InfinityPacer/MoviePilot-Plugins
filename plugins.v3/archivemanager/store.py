"""插件独立数据库：逐文件版本索引与可恢复批次账本。"""

from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.sdk.database import plugin_declarative_base
from app.sdk.config import settings
from sqlalchemy import (
    JSON,
    Boolean,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column

from .naming import frozen_names
from .scanner import fingerprint, identity

Base = plugin_declarative_base()
# 文件账本按块查询与写入的条目数；低于 SQLite 旧版 999 个绑定参数上限。
INVENTORY_CHUNK = 500


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


class DirectoryRow(Base):
    """目录元数据版本账本；空目录归档后不会在每轮重复生成批次。"""

    __tablename__ = "archive_directory"
    __table_args__ = (UniqueConstraint("task_id", "fingerprint"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)  # 内部行标识
    task_id: Mapped[str] = mapped_column(String(64), index=True)  # 任务边界
    fingerprint: Mapped[str] = mapped_column(String(64))  # 路径与目录元数据指纹
    relative_path: Mapped[str] = mapped_column(Text)  # 完整源相对路径
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # 首次归档批次
    present: Mapped[bool] = mapped_column(Boolean, default=True)  # 最近一次扫描可见
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)  # 元数据归档结果
    data: Mapped[dict] = mapped_column(JSON)  # 目录身份、时间与权限


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
        self, task_id: str, entries: list[Mapping], source_dir: str = "", task_config: dict | None = None
    ) -> list[Mapping]:
        """刷新最近扫描索引并返回尚未被批次预留的文件。

        文件账本可达十万行，这里按 ``INVENTORY_CHUNK`` 分块只查询判定所需的列并批量写入，
        不把整表载入为 ORM 对象，也不常驻全量指纹集合；内存只随扫描结果本身和单个分块增长。
        """
        with self.handle.session() as session, session.begin():
            state = session.get(TaskRow, task_id)
            if state is None:
                state = TaskRow(id=task_id, data={})
                session.add(state)
            fresh = not state.data.get("initialized") or state.data.get("source_dir", "") != source_dir
            if fresh:
                self._bulk_update(session, FileRow.task_id == task_id, historical=False)
                state.data = {
                    **state.data,
                    "initialized": True,
                    "source_dir": source_dir,
                    "history_started_at": datetime.now(timezone.utc).isoformat(),
                    "phase": "history",
                }
            stale = list(
                session.scalars(
                    select(BatchRow).where(
                        BatchRow.task_id == task_id, BatchRow.status.in_(["failed", "cancelled"])
                    )
                )
            )
            current = None
            for batch in stale:
                # 未发布的失败快照失效后允许剩余成员重新分批，不能永久锁住未归档文件。
                if batch.data["archive_sha256"]:
                    continue
                changed_config = task_config is not None and batch.data["task"] != task_config
                if not changed_config and current is None:
                    # 只有存在待判定的失败快照时才需要本轮全部指纹。
                    current = {fingerprint(entry) for entry in entries}
                if changed_config or any(fingerprint(item) not in current for item in batch.data["entries"]):
                    batch.status = "superseded"
                    batch.data = {**batch.data, "error": "源文件版本或任务配置已变化，未归档成员将在本轮重新分批"}
                    self._bulk_update(
                        session,
                        FileRow.task_id == task_id,
                        FileRow.batch_id == batch.id,
                        batch_id=None,
                        status="pending",
                    )
            current = None
            self._bulk_update(session, FileRow.task_id == task_id, present=False)
            seen_values = {"present": True, **({"historical": True} if fresh else {})}
            pending = []
            historical_eligible = []
            for offset in range(0, len(entries), INVENTORY_CHUNK):
                chunk = entries[offset : offset + INVENTORY_CHUNK]
                keys = [fingerprint(entry) for entry in chunk]
                known = {
                    key: (reserved, historical, status)
                    for key, reserved, historical, status in session.execute(
                        select(
                            FileRow.fingerprint,
                            FileRow.batch_id.is_not(None),
                            FileRow.historical,
                            FileRow.status,
                        ).where(FileRow.task_id == task_id, FileRow.fingerprint.in_(keys))
                    )
                }
                if known:
                    self._bulk_update(
                        session,
                        FileRow.task_id == task_id,
                        FileRow.fingerprint.in_(list(known)),
                        **seen_values,
                    )
                created = []
                for key, entry in zip(keys, chunk):
                    flags = known.get(key)
                    if flags is None:
                        created.append(
                            {
                                "task_id": task_id,
                                "fingerprint": key,
                                "relative_path": entry["relative_path"],
                                "data": dict(entry),
                                "present": True,
                                "status": "pending",
                                "historical": fresh,
                            }
                        )
                        # 同一轮重复出现的指纹沿用首次写入结果，保持唯一约束。
                        known[key] = flags = (False, fresh, "pending")
                    reserved, historical, status = flags
                    if reserved:
                        continue
                    pending.append(entry)
                    if (fresh or historical) and status == "pending":
                        historical_eligible.append(entry)
                if created:
                    session.execute(insert(FileRow), created)
            if source_dir:
                self._mark_unseen_history(session, task_id, source_dir)
            historical_pending = session.scalar(
                select(FileRow.id)
                .where(
                    FileRow.task_id == task_id, FileRow.historical.is_(True), FileRow.status == "pending"
                )
                .limit(1)
            )
            if historical_pending is not None:
                state.data = {**state.data, "phase": "history"}
                return historical_eligible
            state.data = {**state.data, "phase": "incremental"}
            return pending

    @staticmethod
    def _bulk_update(session, *conditions, **values) -> None:
        """账本批量更新不加载 ORM 对象；调用方保证会话中没有需要同步的同表对象。"""
        session.execute(
            update(FileRow)
            .where(*conditions)
            .values(**values)
            .execution_options(synchronize_session=False)
        )

    @classmethod
    def _mark_unseen_history(cls, session, task_id: str, source_dir: str) -> None:
        """本轮未见到的历史待归档版本需有明确记录，不把它伪装成已归档。"""
        unseen = session.execute(
            select(FileRow.id, FileRow.relative_path, FileRow.data).where(
                FileRow.task_id == task_id,
                FileRow.historical.is_(True),
                FileRow.status == "pending",
                FileRow.present.is_(False),
            )
        ).all()
        for row_id, relative_path, data in unseen:
            try:
                current_identity = identity(Path(source_dir) / relative_path)
                if any(current_identity[key] != data[key] for key in current_identity):
                    cls._bulk_update(session, FileRow.id == row_id, status="changed")
            except FileNotFoundError:
                cls._bulk_update(session, FileRow.id == row_id, status="missing")
            except OSError, ValueError:
                pass

    def inventory_directories(
        self, task_id: str, directories: list[dict], task_config: dict | None = None
    ) -> list[dict]:
        """刷新目录元数据索引，返回尚未归档的目录版本。"""
        with self.handle.session() as session, session.begin():
            rows = {
                row.fingerprint: row
                for row in session.scalars(select(DirectoryRow).where(DirectoryRow.task_id == task_id))
            }
            current = {fingerprint(entry) for entry in directories}
            stale = session.scalars(
                select(BatchRow).where(BatchRow.task_id == task_id, BatchRow.status.in_(["failed", "cancelled"]))
            )
            for batch in stale:
                changed_config = task_config is not None and batch.data["task"] != task_config
                batch_directories = batch.data.get("directories", [])
                if not batch.data["archive_sha256"] and (
                    changed_config or any(fingerprint(entry) not in current for entry in batch_directories)
                ):
                    batch.status = "superseded"
                    batch.data = {**batch.data, "error": "源目录元数据或任务配置已变化，将在本轮重新分批"}
                    session.execute(
                        update(FileRow).where(FileRow.batch_id == batch.id).values(batch_id=None, status="pending")
                    )
                    session.execute(
                        update(DirectoryRow)
                        .where(DirectoryRow.batch_id == batch.id)
                        .values(batch_id=None, status="pending")
                    )
            session.execute(update(DirectoryRow).where(DirectoryRow.task_id == task_id).values(present=False))
            pending = []
            for entry in directories:
                key = fingerprint(entry)
                row = rows.get(key)
                if row is None:
                    row = DirectoryRow(
                        task_id=task_id,
                        fingerprint=key,
                        relative_path=entry["relative_path"],
                        data=entry,
                        present=True,
                        status="pending",
                    )
                    session.add(row)
                else:
                    row.present = True
                if not row.batch_id:
                    pending.append(entry)
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

    @staticmethod
    def _published_on_local_day(
        status: str, created_at: str, published_at: str | None, target_day
    ) -> bool:
        """按 MoviePilot 配置时区判断批次发布日期；旧批次缺少发布时间时回退到创建时间。"""
        if not published_at:
            if status not in ("completed", "cleaning", "cleanup_failed"):
                return False
            published_at = created_at
        try:
            return datetime.fromisoformat(published_at).astimezone(ZoneInfo(settings.TZ)).date() == target_day
        except (TypeError, ValueError):
            return False

    def daily_archive_bytes(self, local_day=None) -> int:
        """统计 MoviePilot 配置时区日内已发布批次的实际归档包大小，成品移走后仍保留额度记录。

        批次循环每轮都会调用；只取判定所需的列与 JSON 键，不载入含文件明细和清单的完整快照。
        ``archive_size`` 以文本取出再转整数，避免 PostgreSQL 按 32 位 INTEGER 转换大于 2GB 的包。
        """
        target_day = local_day or datetime.now(tz=ZoneInfo(settings.TZ)).date()
        with self.handle.session() as session:
            rows = session.execute(
                select(
                    BatchRow.status,
                    BatchRow.created_at,
                    BatchRow.data["published_at"].as_string(),
                    BatchRow.data["archive_size"].as_string(),
                )
            ).all()
        return sum(
            int(archive_size or 0)
            for status, created_at, published_at, archive_size in rows
            if self._published_on_local_day(status, created_at, published_at, target_day)
        )

    def local_archives(self, task_id: str) -> list[dict]:
        """只统计确实仍在本地的成品；文件消失不等于上传成功。

        先只按成品路径判断仍在本地的批次，再载入这些批次的完整快照；已被外部移走的
        历史批次不再每轮整表反序列化。
        """
        with self.handle.session() as session:
            candidates = session.execute(
                select(BatchRow.id, BatchRow.data["archive_path"].as_string()).where(
                    BatchRow.task_id == task_id
                )
            ).all()
            local_ids = [batch_id for batch_id, path in candidates if path and Path(path).is_file()]
            if not local_ids:
                return []
            rows = {
                row.id: row
                for row in session.scalars(select(BatchRow).where(BatchRow.id.in_(local_ids)))
            }
            return [self._serialize(rows[batch_id]) for batch_id in local_ids if batch_id in rows]

    def exclude_reserved(self, task_id: str, entries: list[Mapping]) -> list[Mapping]:
        """预览只查询去重证据，不刷新扫描状态；按块查询，避免载入全部已预留指纹。"""
        result = []
        with self.handle.session() as session:
            for offset in range(0, len(entries), INVENTORY_CHUNK):
                chunk = entries[offset : offset + INVENTORY_CHUNK]
                keys = [fingerprint(entry) for entry in chunk]
                reserved = set(
                    session.scalars(
                        select(FileRow.fingerprint).where(
                            FileRow.task_id == task_id,
                            FileRow.batch_id.is_not(None),
                            FileRow.fingerprint.in_(keys),
                        )
                    )
                )
                result.extend(entry for key, entry in zip(keys, chunk) if key not in reserved)
        return result

    def create(
        self, batch_id: str, task: dict, entries: list[Mapping], group: str, directories: list[dict] | None = None
    ) -> dict:
        """先预留全部成员并提交快照，再允许工作进程创建归档。"""
        # 扫描阶段的紧凑记录在进入 JSON 快照前转为普通 dict。
        entries = [dict(entry) for entry in entries]
        created_at = datetime.now(timezone.utc).isoformat()
        local_day = datetime.fromisoformat(created_at).astimezone(ZoneInfo(settings.TZ)).date()
        sequence = 1
        global_sequence = 1
        # sequence 按任务递增，global_sequence 跨所有任务递增；两者都按 MoviePilot 配置日期重新计数。
        # 只读取任务与创建时间两列，不反序列化历史批次快照。
        with self.handle.session() as sequence_session:
            for row_task_id, row_created_at in sequence_session.execute(
                select(BatchRow.task_id, BatchRow.created_at)
            ):
                if datetime.fromisoformat(row_created_at).astimezone(ZoneInfo(settings.TZ)).date() != local_day:
                    continue
                global_sequence += 1
                if row_task_id == task["id"]:
                    sequence += 1
        directories = directories or []
        naming_entries = entries or directories
        data = {
            **frozen_names(task, batch_id, created_at, sequence, naming_entries, global_sequence),
            "task": task,
            "task_name": task["name"],
            "entries": entries,
            "directories": directories,
            "group": group,
            "file_count": len(entries),
            "source_bytes": sum(e["size"] for e in entries),
            "archive_size": 0,
            "archive_path": "",
            "manifest_path": "",
            "archive_sha256": "",
            "archive_sha1": "",  # 归档包 SHA-1，仅用于与网盘元数据对账，不参与判定
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
            for entry in directories:
                row = session.scalar(
                    select(DirectoryRow).where(
                        DirectoryRow.task_id == task["id"], DirectoryRow.fingerprint == fingerprint(entry)
                    )
                )
                # 已归档祖先目录会随文件批次再次写入，但只需首次批次拥有账本记录。
                if row is not None and not row.batch_id:
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
            manifest_directories = {item["relative_path"]: item for item in batch["manifest"].get("directories", [])}
            for row in session.scalars(select(DirectoryRow).where(DirectoryRow.batch_id == batch["id"])):
                item = manifest_directories.get(row.relative_path)
                if item is not None:
                    row.data = {**item, "source_root": row.data.get("source_root", "")}
                row.status = "archived"

    def clean_batches(self, batch_ids: list[str]) -> dict:
        """删除批次账本及其文件去重记录，不触碰源文件或外部产物。"""
        ids = list(dict.fromkeys(batch_ids))
        if not ids:
            raise ValueError("至少选择一个归档批次")
        allowed = {"completed", "failed", "cancelled", "superseded"}
        with self.handle.session() as session, session.begin():
            rows = list(session.scalars(select(BatchRow).where(BatchRow.id.in_(ids))))
            found = {row.id for row in rows}
            missing = [batch_id for batch_id in ids if batch_id not in found]
            if missing:
                raise ValueError("部分批次已不存在，请刷新后重试")
            blocked = [row for row in rows if row.status not in allowed]
            if blocked:
                names = "、".join(row.data.get("batch_name", row.id) for row in blocked[:3])
                raise ValueError(f"批次正在执行或等待恢复，不能清理：{names}")
            session.execute(delete(FileRow).where(FileRow.batch_id.in_(ids)))
            session.execute(delete(DirectoryRow).where(DirectoryRow.batch_id.in_(ids)))
            session.execute(delete(BatchRow).where(BatchRow.id.in_(ids)))
            return {
                "batch_count": len(rows),
                "file_count": sum(int(row.data.get("file_count", 0)) for row in rows),
            }

    def reset_data(self) -> dict:
        """清空归档运行账本；任务与插件配置由宿主持久化，不属于这些业务表。"""
        with self.handle.session() as session, session.begin():
            counts = {
                "batch_count": session.scalar(select(func.count()).select_from(BatchRow)) or 0,
                "file_count": session.scalar(select(func.count()).select_from(FileRow)) or 0,
                "directory_count": session.scalar(select(func.count()).select_from(DirectoryRow)) or 0,
                "task_state_count": session.scalar(select(func.count()).select_from(TaskRow)) or 0,
            }
            session.execute(delete(FileRow))
            session.execute(delete(DirectoryRow))
            session.execute(delete(BatchRow))
            session.execute(delete(TaskRow))
            return counts

    def reclaimable_batches(self) -> list[dict]:
        """返回可尝试回收源文件的已发布批次，不要求用户先筛选任务或批次。"""
        with self.handle.session() as session:
            rows = session.scalars(
                select(BatchRow)
                .where(BatchRow.status.in_(["completed", "cleanup_failed"]))
                .order_by(BatchRow.created_at)
            )
            result = []
            for row in rows:
                batch = self._serialize(row)
                if not batch.get("archive_path") or not batch.get("manifest"):
                    continue
                files = session.scalars(select(FileRow).where(FileRow.batch_id == row.id)).all()
                if any(file.status not in ("deleted", "missing") for file in files):
                    result.append(batch)
            return result

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

    def cleanup_intent(self, batch_id: str, relative_path: str) -> None:
        """删除源文件前单独持久化意图，进程中断后可据此恢复。"""
        with self.handle.session() as session, session.begin():
            row = session.get(BatchRow, batch_id)
            if row is None:
                raise ValueError("归档批次不存在")
            cleanup = {**row.data.get("cleanup", {}), relative_path: "deleting"}
            row.data = {**row.data, "cleanup": cleanup}

    def cleanup_results(self, batch_id: str, results: dict[str, str]) -> dict:
        """在同一事务中批量保存清理结果和文件状态，减少逐文件重复写库。"""
        if not results:
            return self.get(batch_id)
        with self.handle.session() as session, session.begin():
            batch = session.get(BatchRow, batch_id)
            if batch is None:
                raise ValueError("归档批次不存在")
            batch.data = {**batch.data, "cleanup": {**batch.data.get("cleanup", {}), **results}}
            rows = {
                row.relative_path: row
                for row in session.scalars(
                    select(FileRow).where(
                        FileRow.batch_id == batch_id, FileRow.relative_path.in_(results)
                    )
                )
            }
            for relative_path, result in results.items():
                row = rows.get(relative_path)
                if row is None:
                    continue
                row.status = result
                if result in ("deleted", "missing"):
                    row.present = False
            session.flush()
            return self._serialize(batch)

    def file_result(self, batch_id: str, relative_path: str, result: str) -> None:
        """兼容单文件状态更新；新清理流程使用 cleanup_results 批量提交。"""
        self.cleanup_results(batch_id, {relative_path: result})

    def summary(self) -> dict:
        """归档概览；页面打开和任务运行期间会被轮询，只读取统计所需的列与 JSON 键。

        大小与数量以文本取出后在 Python 中转整数，避免 PostgreSQL 32 位整数转换溢出。
        """
        published_states = ("completed", "cleaning", "cleanup_failed")
        with self.handle.session() as session:
            completed = session.execute(
                select(
                    BatchRow.status,
                    BatchRow.created_at,
                    BatchRow.data["published_at"].as_string(),
                    BatchRow.data["file_count"].as_string(),
                    BatchRow.data["source_bytes"].as_string(),
                    BatchRow.data["archive_size"].as_string(),
                ).where(BatchRow.status.in_(published_states))
            ).all()
            today = datetime.now(tz=ZoneInfo(settings.TZ)).date()
            completed_today = [
                row for row in completed if self._published_on_local_day(row[0], row[1], row[2], today)
            ]

            def count(*states):
                return session.scalar(select(func.count()).select_from(FileRow).where(FileRow.status.in_(states)))

            def total(rows, index: int) -> int:
                return sum(int(row[index] or 0) for row in rows)

            return {
                "archived_files": total(completed, 3),
                "archive_count": len(completed),
                "source_bytes": total(completed, 4),
                "archive_bytes": total(completed, 5),
                "today_archived_files": total(completed_today, 3),
                "today_archive_count": len(completed_today),
                "today_archive_bytes": total(completed_today, 5),
                "deleted_files": count("deleted"),
                "failed_batches": session.scalar(
                    select(func.count())
                    .select_from(BatchRow)
                    .where(BatchRow.status.in_(["failed", "manifest_pending", "cleanup_failed"]))
                ),
                "pending_files": session.scalar(
                    select(func.count())
                    .select_from(FileRow)
                    .where(FileRow.status == "pending", FileRow.present.is_(True))
                ),
            }

    def task_snapshots(self) -> Iterator[dict]:
        """按批次列表顺序（最新在前）逐条产出批次冻结的任务快照，供暂存清理收集输出目录。

        只读取 ``data.task`` 并分批流式获取，不载入文件明细和清单；缺少快照的旧批次产出空 dict。
        """
        with self.handle.session() as session:
            rows = session.execute(
                select(BatchRow.data["task"].as_json())
                .order_by(BatchRow.created_at.desc(), BatchRow.id)
                .execution_options(yield_per=200)
            )
            for (snapshot,) in rows:
                yield snapshot or {}

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
