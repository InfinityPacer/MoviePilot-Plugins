"""批次名称在创建时冻结；UUID 始终承担关联和文件唯一性。"""

import re
from datetime import datetime
from pathlib import Path
from string import Formatter
from zoneinfo import ZoneInfo

FIELDS = {"task_name", "date", "time", "id", "sequence"}


def batch_relative_directory(batch: dict) -> Path:
    """成品与外部清单共享可读布局；更深分组目录在扁平布局中以下划线连接。"""
    task = batch["task"]
    parts = []
    if task.get("grouping", "directory_date") in ("directory", "directory_date"):
        group = batch.get("group", ".").split(" | ", 1)[0]
        for part in group.split("/"):
            clean = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "_", part).strip(" .")
            if clean and clean != "全部文件":
                parts.append(clean)
    name = batch.get("batch_name") or batch["id"][:6]
    if task.get("archive_layout", "directory") == "flat":
        return Path("_".join([*parts, name]))
    return Path(*parts, name)


def validate_template(template: str) -> None:
    """只允许简单占位符和单层文件名，避免格式表达式改变路径语义。"""
    if not template.strip() or len(template) > 160:
        raise ValueError("命名模板不能为空且不能超过160个字符")
    if re.search(r'[\\/:*?"<>|\x00-\x1f\x7f]', template):
        raise ValueError("命名模板不能包含路径分隔符或文件名保留字符")
    for _literal, field, spec, conversion in Formatter().parse(template):
        if field is not None and (spec or conversion or not (field in FIELDS or (field.startswith("%") and re.fullmatch(r"(?:%[A-Za-z]|[^%]){1,80}", field)))):
            raise ValueError("命名模板仅支持任务名、日期时间和批次 ID 占位符")


def frozen_names(task: dict, batch_id: str, created_at: str, sequence: int = 1) -> dict:
    """生成可读名与跨目录唯一的包名；长度为摘要和临时文件后缀预留空间。"""
    moment = datetime.fromisoformat(created_at).astimezone(ZoneInfo(task["timezone"]))
    values = {
        "task_name": re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "_", task["name"]),
        "date": moment.strftime("%Y%m%d"),
        "time": moment.strftime("%H%M%S"),
        "id": batch_id[:6],
        "sequence": f"{sequence:04d}",
    }
    label_template = task.get("batch_name_template", "{date}_{sequence}")
    file_template = task.get("archive_name_template", "{id}")
    validate_template(label_template)
    validate_template(file_template)
    def render(template: str) -> str:
        parts = []
        for literal, field, _spec, _conversion in Formatter().parse(template):
            parts.append(literal)
            if field is not None:
                parts.append(moment.strftime(field) if field.startswith("%") else str(values[field]))
        return "".join(parts).strip(" .")

    label = render(label_template)
    stem = render(file_template)
    if not label or not stem:
        raise ValueError("命名模板生成的名称不能为空")
    if len(stem.encode("utf-8")) > 180:
        raise ValueError("归档文件名过长，请缩短任务名或文件名模板")
    return {"batch_name": label, "archive_name": f"{stem}.{task['format']}"}
