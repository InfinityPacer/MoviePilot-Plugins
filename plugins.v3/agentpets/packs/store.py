"""素材持久化、并发写入与失败恢复"""

from __future__ import annotations

import base64
import hashlib
import re
import time
from copy import deepcopy
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from .constants import (
    BUILTIN_PACK_ID,
    BUILTIN_PACK_IDS,
    CODEX_ACTIONS,
    ID_PATTERN,
    LOOK_DIRECTIONS,
    MAPPING_KEYS,
    MAX_PACKS,
    PackError,
    RESERVED_IDS,
)
from .schema import (
    _text,
    codex_pet_version,
    is_http_url,
    pack_revision,
    parse_calibration,
    parse_pack,
)
from .images import (
    decode_image,
    first_frame_avatar,
    first_frame_preview,
    sniff_image,
    validate_sheet,
)

_PACKS_LOCK = RLock()


def _serialized(method):
    """每个进程串行更新素材列表，避免不同字段的保存互相覆盖。"""
    @wraps(method)
    def wrapped(*args, **kwargs):
        """在唯一进程写锁内执行素材修改，嵌套导入可重入且异常原样传播"""
        with _PACKS_LOCK:
            return method(*args, **kwargs)
    return wrapped


def _write_image(path: Path, content: bytes) -> None:
    """先完整写入同目录临时文件，再原子替换；失败不能留下半张正式图片。"""
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass  # 清理失败不覆盖原异常；临时文件不会被素材记录引用。


class PackStore:
    """用户素材包：元数据存插件数据，上传的精灵图存插件数据目录。"""

    DATA_KEY = "packs"

    def __init__(self, get_data, save_data, data_path: Path):
        """绑定实例级元数据读写回调，图片位置固定为数据目录下的 packs"""
        self._get_data = get_data
        self._save_data = save_data
        self._dir = data_path / "packs"

    def list(self) -> list[dict[str, Any]]:
        """读取记录并过滤非法结构或 ID，未保存素材时返回空列表"""
        records = self._get_data(self.DATA_KEY) or []
        return [record for record in records if isinstance(record, dict) and ID_PATTERN.fullmatch(record.get("id", ""))]

    def get(self, pack_id: str) -> dict[str, Any] | None:
        """按本地 ID 查找素材记录，不存在时返回 None"""
        return next((record for record in self.list() if record["id"] == pack_id), None)

    def image_path(self, record: dict[str, Any]) -> Path | None:
        """解析已上传图片路径，拒绝越出素材目录的记录并返回 None"""
        name = record.get("image_file")
        if not name:
            return None
        path = (self._dir / name).resolve()
        if path.parent != self._dir.resolve():
            return None
        return path

    @_serialized
    def add(self, raw_pack: Any, image: str | None = None) -> dict[str, Any]:
        """校验后保存一个素材包；带 image 时为上传方式，否则 sheet 必须是 http(s) URL。"""
        pack = parse_pack(raw_pack)
        pack_id = pack["id"] or self._derive_id(pack["name"])
        if pack_id in RESERVED_IDS:
            raise PackError(f"{pack_id} 已被内置形象使用，请换一个 ID")
        records = self.list()
        if any(record["id"] == pack_id for record in records):
            raise PackError(f"已存在 ID 为 {pack_id} 的素材包，请先删除或换一个 ID")
        if len(records) >= MAX_PACKS:
            raise PackError(f"最多保存 {MAX_PACKS} 个素材包")

        record: dict[str, Any] = {
            key: pack[key] for key in ("name", "description", "grid", "frames", "actions", "random_actions")
        }
        record.update(id=pack_id, preview=pack["preview"], avatar=pack["avatar"], created_at=int(time.time()))
        if pack.get("codex_version"):
            record["codex_version"] = pack["codex_version"]
        if "calibration" in pack:
            record["calibration"] = pack["calibration"]
        if pack.get("action_mappings"):
            record["action_mappings"] = pack["action_mappings"]
        image_path = None
        previous_image = None
        image_write_started = False
        if image:
            content, _, _ = decode_image(image)
            mime, ext = validate_sheet(content, pack)
            self._dir.mkdir(parents=True, exist_ok=True)
            file_name = f"{pack_id}.{ext}"
            image_path = self._dir / file_name
            record.update(source="upload", image_file=file_name, mime=mime, sheet_url="")
            if not record["preview"]:
                record["preview"] = first_frame_preview(content, pack)
            # 上传方式总有头像；URL 方式不下载远程图片，只在 JSON 显式填写时声明。
            if not record["avatar"]:
                record["avatar"] = first_frame_avatar(content, pack)
        else:
            if not is_http_url(pack["sheet"]):
                raise PackError("没有上传精灵图时，sheet 必须是 http(s) 图片地址")
            record.update(source="url", image_file="", mime="", sheet_url=pack["sheet"])
        try:
            if image_path is not None:
                previous_image = image_path.read_bytes() if image_path.exists() else None
                image_write_started = True
                _write_image(image_path, content)
            self._save_records(records + [record])
        except (PackError, OSError, RuntimeError):
            # 提交可能已成功但回读失败；只有确认没有引用新图时才回收，不能误删已保存的素材。
            if image_path is not None and image_write_started:
                try:
                    referenced = any(self.image_path(item) == image_path.resolve() for item in self.list())
                    if not referenced:
                        if previous_image is None:
                            image_path.unlink(missing_ok=True)
                        else:
                            image_path.write_bytes(previous_image)
                except (OSError, RuntimeError):
                    pass  # 状态不明时保留图片，避免把可恢复数据变成永久丢失。
            raise
        return record

    @_serialized
    def import_pack(self, raw: Any, image: str, mode: str, expected_revision: str | None = None) -> dict[str, Any]:
        """完整包新增/副本/更新；更新使用独立图片文件，保留上次记录和原图。"""
        pack = parse_pack(raw)
        if mode not in ("new", "copy", "replace"):
            raise PackError("导入方式无效")
        records = deepcopy(self.list())
        pack_id = pack["id"] or self._derive_id(pack["name"])
        if mode == "copy":
            occupied = {item["id"] for item in records} | RESERVED_IDS
            stem = pack_id[:26]
            for suffix in range(1, MAX_PACKS + 3):
                candidate = f"{stem}-{suffix}"
                if candidate not in occupied:
                    pack["id"] = candidate
                    break
            else:
                raise PackError("无法生成副本 ID")
        if mode != "replace":
            return self.add(pack, image)
        target = next((item for item in records if item["id"] == pack_id), None)
        if not target or pack_id in RESERVED_IDS:
            raise PackError("要更新的素材不存在或属于内置形象，请导入副本")
        if expected_revision != pack_revision(target):
            raise PackError("素材已在其他页面更改，请重新读取预览后重试")
        if bool(codex_pet_version(target)) != bool(codex_pet_version(pack)):
            raise PackError("入口形象与全屏角色不能互相覆盖，请导入副本")
        content, _, _ = decode_image(image)
        mime, ext = validate_sheet(content, pack)
        file_name = f"{pack_id}-{hashlib.sha256(content).hexdigest()[:24]}.{ext}"
        next_record = {**target, **{key: pack[key] for key in (
            "name", "description", "grid", "frames", "actions", "random_actions")}}
        next_record.pop("codex_version", None)
        if pack.get("codex_version"):
            next_record["codex_version"] = pack["codex_version"]
        next_record.update(
            source="upload", image_file=file_name, mime=mime, sheet_url="",
            preview=pack["preview"] or first_frame_preview(content, pack),
            avatar=pack["avatar"] or first_frame_avatar(content, pack),
            action_mappings=pack.get("action_mappings", {}),
            calibration=parse_calibration(pack.get("calibration")),
        )
        # 先保全可恢复记录；任何失败均不先删除旧图片或旧素材。
        backup_key = f"pack_backup_{pack_id}"
        backup = {"record": deepcopy(target), "saved_at": int(time.time())}
        if self._save_data(backup_key, backup) is False or self._get_data(backup_key) != backup:
            raise PackError("原素材备份未确认，未执行覆盖")
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / file_name
        if path.exists():
            if path.read_bytes() != content:
                raise PackError("目标图片校验不一致，未执行覆盖")
        else:
            _write_image(path, content)
        self._save_records([next_record if item["id"] == pack_id else item for item in records])
        return next_record

    def _save_records(self, records: list[dict[str, Any]]) -> None:
        """保存后核对完整列表，拒绝未落盘或回读不一致的结果。"""
        if self._save_data(self.DATA_KEY, records) is False:
            raise PackError("保存失败，请重试")
        if self.list() != records:
            raise PackError("保存回读不一致，请刷新后核对")

    @_serialized
    def update(self, pack_id: str, *, name: str | None = None, expected_name: str | None = None,
               description: str | None = None, expected_description: str | None = None,
               mappings: dict[str, str] | None = None, expected_mappings: dict[str, str] | None = None) -> dict[str, Any]:
        """只更新显示名称、备注或映射；原始动画、图片、ID 与其他字段保持原样。"""
        records = deepcopy(self.list())
        target = next((record for record in records if record["id"] == pack_id), None)
        if not target or pack_id in RESERVED_IDS:
            raise PackError("此 Pet 不存在或属于内置形象")
        version = codex_pet_version(target)
        if version is None:
            raise PackError("当前仅支持编辑导入的 Codex Pet")
        if name is not None:
            if target["name"] != expected_name:
                raise PackError("名称已在其他页面更改，请刷新后重试")
            target["name"] = _text(name, "名称", 40)
        if description is not None:
            if target.get("description", "") != expected_description:
                raise PackError("备注已在其他页面更改，请刷新后重试")
            target["description"] = _text(description, "备注", 120, required=False)
        if mappings is not None:
            if target.get("action_mappings", {}) != expected_mappings:
                raise PackError("动作映射已在其他页面更改，请刷新后重试")
            available = set(target.get("actions", {})) | set(CODEX_ACTIONS)
            if version == "v2":
                available.update(f"look-{direction}" for direction in LOOK_DIRECTIONS)
            if any(key not in MAPPING_KEYS or value not in available for key, value in mappings.items()):
                raise PackError("动作映射包含不支持的触发条件或动画")
            if mappings:
                target["action_mappings"] = dict(mappings)
            else:
                target.pop("action_mappings", None)
        if self._save_data(self.DATA_KEY, records) is False:
            raise PackError("保存失败，请重试")
        if self.get(pack_id) != target:
            raise PackError("保存回读不一致，请刷新后核对")
        return target

    @_serialized
    def calibrate(self, pack_id: str, value: Any, expected: Any) -> dict[str, Any]:
        """核对旧校准值后保存新值，失败或冲突不得改变原图与其他元数据"""
        records = deepcopy(self.list())
        target = next((item for item in records if item["id"] == pack_id), None)
        if not target or pack_id in RESERVED_IDS:
            raise PackError("此素材不存在或属于内置形象")
        if parse_calibration(target.get("calibration")) != parse_calibration(expected):
            raise PackError("显示校准已在其他页面更改，请刷新后重试")
        target["calibration"] = parse_calibration(value)
        self._save_records(records)
        return target

    @_serialized
    def remove(self, pack_id: str) -> bool:
        """先确认记录持久化删除再回收图片，不存在返回 False，清理失败明确报错"""
        records = self.list()
        target = next((record for record in records if record["id"] == pack_id), None)
        if not target:
            return False
        path = self.image_path(target)
        # 先确认元数据不再引用图片，再回收文件；持久化失败时原图必须仍然可用。
        self._save_records([record for record in records if record["id"] != pack_id])
        if path and path.is_file():
            try:
                path.unlink()
            except OSError as exc:
                raise PackError("素材记录已移除，但图片清理失败，请查看插件日志") from exc
        return True

    def sheet_src(self, record: dict[str, Any]) -> str:
        """前端可直接使用的精灵图地址：URL 原样返回，上传图转成 data URL。"""
        if record.get("source") == "url":
            return record.get("sheet_url", "")
        path = self.image_path(record)
        if not path or not path.is_file():
            raise PackError("素材包的精灵图文件已丢失，请删除后重新添加")
        content = path.read_bytes()
        mime, _ = sniff_image(content)
        return f"data:{mime};base64," + base64.b64encode(content).decode("ascii")

    def _derive_id(self, name: str) -> str:
        """未写 id 时按名称生成；中文等非 ASCII 名称用时间戳兜底。"""
        slug = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")[:24]
        return slug or f"pack-{int(time.time()) % 10**8}"


def load_builtin_pack(dist_dir: Path, key: str = BUILTIN_PACK_ID) -> dict[str, Any]:
    """读取随联邦产物分发的内置素材包描述。"""
    if key not in BUILTIN_PACK_IDS:
        raise PackError("未知内置素材包")
    path = dist_dir / "packs" / key / "pack.json"
    pack = parse_pack(path.read_text(encoding="utf-8"))
    pack["id"] = key
    return pack
