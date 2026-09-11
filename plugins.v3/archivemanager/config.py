"""任务配置与目录边界；不将业务场景或文件扩展名固化到归档规则。"""

from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .naming import validate_template


def container_timezone() -> str:
    """使用容器运行时的本地时区。"""
    tz = datetime.now().astimezone().tzinfo
    return getattr(tz, "key", None) or "UTC"


class NotificationConfig(BaseModel):
    """插件推送策略，事件使用稳定键与前端多选项对应。"""

    notify: bool = False  # 总推送开关，默认不发送外部消息
    notify_events: list[Literal["success", "failure", "other"]] = Field(default_factory=lambda: ["failure"])


class TaskConfig(BaseModel):
    """一个可独立调度的归档任务；密码只用于构建和读回，不进入清单。"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")  # 数据库中的稳定任务标识
    name: str = Field(default="归档任务", min_length=1, max_length=100)  # 页面与文档显示名
    batch_name_template: str = "{date}_{sequence}"  # 创建时固定的批次名称及目录名
    archive_name_template: str = "{id}"  # 外层文件名模板，不包含扩展名
    archive_layout: Literal["directory", "flat"] = "directory"  # 成品目录按分组嵌套或批次扁平
    enabled: bool = False  # 是否接受定时触发
    source_dir: str = ""  # MoviePilot 可访问的源目录
    output_dir: str = ""  # 仅成品批次目录，供外部上传器读取
    manifest_dir: str = ""  # 明文文档根目录，与源和成品目录分开
    cron: str = "0 2 * * *"  # 五字段 Cron
    timezone: str = Field(default_factory=container_timezone, exclude=True)  # 不向用户暴露
    recursive: bool = True  # 是否递归普通目录
    include_patterns: list[str] = Field(default_factory=list)  # 相对路径或文件名 glob，空为全部
    exclude_patterns: list[str] = Field(default_factory=list)  # 优先排除的 glob
    grouping: Literal["none", "directory", "date", "directory_date"] = "directory_date"  # 批次分组
    directory_depth: int = Field(default=1, ge=1, le=20)  # 分组使用的目录层级
    time_grain: Literal["hour", "day", "month"] = "day"  # 修改时间分组粒度
    max_files: int = Field(default=1000, ge=0, le=100000)  # 每批源文件数，0 为不限制
    max_bytes: int = Field(default=4 * 1024**3, ge=0)  # 每批源字节数，0 为不限制
    max_batches: int = Field(default=10, ge=1, le=10000)  # 一轮运行的最大批数
    archive_age_days: float = Field(default=7, ge=0, le=36500)  # 距最近修改的最小天数，避免处理近期仍可能续写的文件
    stability_seconds: int = Field(default=60, ge=1, le=3600)  # 两次属性观察间隔
    format: Literal["7z", "zip"] = "7z"  # 标准归档容器格式
    compression: Literal["store", "fast", "normal", "high"] = "normal"  # 压缩档位
    encryption: Literal["none", "aes256"] = "none"  # 内容加密方案
    encrypt_names: bool = False  # 7z 头加密，ZIP 不具备此能力
    password: str = ""  # 任务密码，不写入执行快照及清单
    password_version: str = "1"  # 用户维护的历史密码辨认标识
    verify: bool = True  # 发布前完整读回校验
    delete_source: bool = False  # 校验与文档完成后允许逐文件清理
    auto_continue: bool = False  # 等待空间或成品移走后自动继续当前归档周期
    max_pending_archives: int = Field(default=1, ge=0)  # 本地尚存在的成品数量上限，0 不限制
    max_pending_bytes: int = Field(default=0, ge=0)  # 本地成品总字节上限，0 不限制
    min_free_bytes: int = Field(default=1024**3, ge=0)  # 归档后至少保留的磁盘空间

    @model_validator(mode="after")
    def validate_options(self):
        """拒绝不支持的组合；删除不能降低完整校验要求。"""
        ZoneInfo(self.timezone)
        CronTrigger.from_crontab(self.cron, timezone=self.timezone)
        validate_template(self.batch_name_template)
        validate_template(self.archive_name_template)
        if self.encrypt_names and (self.format != "7z" or self.encryption != "aes256"):
            raise ValueError("隐藏文件名仅适用于 7z AES-256 加密")
        if self.encryption == "aes256" and not self.password:
            raise ValueError("启用加密时必须提供密码")
        if self.delete_source:
            self.verify = True
        return self

    def public(self) -> dict:
        """持久化运行快照不携带密码，只保留恢复所需版本标识。"""
        value = self.model_dump(exclude={"password"})
        value["timezone"] = container_timezone()
        return value


def overlap(left: Path, right: Path) -> bool:
    """父子目录也属于重叠，避免扫描自身产物或交叉清理。"""
    return left == right or left in right.parents or right in left.parents


def validate_paths(task: TaskConfig) -> None:
    """只验证路径，不创建目录；预览对文件系统保持只读。"""
    paths = []
    for value in (task.source_dir, task.output_dir, task.manifest_dir):
        if not value or not Path(value).is_absolute():
            raise ValueError("源目录、归档输出目录和独立清单目录必须填写绝对路径")
        path = Path(value)
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("任务目录不能经过符号链接")
        paths.append(path.resolve())
    if any(overlap(a, b) for i, a in enumerate(paths) for b in paths[i + 1 :]):
        raise ValueError("源目录、归档输出目录与独立清单目录不能重叠")
    if not paths[0].is_dir():
        raise ValueError("源目录不存在或不是目录")
    staging = paths[1].parent / ".archivemanager-staging"
    if any(overlap(staging, path) for path in paths):
        raise ValueError("任务目录不能与归档输出旁的 .archivemanager-staging 工作目录重叠")
    if paths[1].exists() and paths[1].stat().st_dev != paths[1].parent.stat().st_dev:
        raise ValueError("输出目录不能直接使用独立卷的挂载根；请选择卷内子目录，例如 /archive/ready")


def parse_config(config: dict) -> list[TaskConfig]:
    """全量验证任务标识和跨任务路径，配置错误时不启动部分任务。"""
    tasks = [TaskConfig.model_validate(item) for item in config.get("tasks", [])]
    if len({task.id for task in tasks}) != len(tasks):
        raise ValueError("任务 ID 不能重复")
    active = [task for task in tasks if task.enabled]
    for task in active:
        validate_paths(task)
    for index, task in enumerate(active):
        for other in active[index + 1 :]:
            roots = (other.source_dir, other.output_dir, other.manifest_dir)
            if any(overlap(Path(task.source_dir).resolve(), Path(root).resolve()) for root in roots):
                raise ValueError("启用任务的源目录不能重叠或包含其他任务的输出")
            if any(
                overlap(Path(other.source_dir).resolve(), Path(root).resolve())
                for root in (task.output_dir, task.manifest_dir)
            ):
                raise ValueError("启用任务的源目录不能包含其他任务的输出")
    return tasks
