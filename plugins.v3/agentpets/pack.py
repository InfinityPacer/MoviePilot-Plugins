"""素材包格式校验、精灵图校验与插件数据目录存储。

素材包是一张精灵图加一份描述 JSON；格式见插件 README 的「素材包格式」。
这里是格式的唯一权威实现，前端配置页只做即时提示，最终以此处校验为准。
"""

from __future__ import annotations

import base64
import binascii
import io
import hashlib
import json
import math
import re
import time
from copy import deepcopy
from functools import wraps
from threading import RLock
from pathlib import Path
from typing import Any
from uuid import uuid4

# 素材包 ID 同时作为形象 key 写入用户选择，规则与宿主形象 key 一致。
ID_PATTERN = re.compile(r"[a-z0-9_-]{1,32}")
# 帧名和动作名沿用宿主动作命名风格（如 happy-jump）。
NAME_PATTERN = re.compile(r"[a-z0-9_-]{1,32}")

BUILTIN_PACK_ID = "projector-cat"
# 与同插件其他形象的 key 共用命名空间（小映为 ying），素材包不能占用。
RESERVED_IDS = frozenset({BUILTIN_PACK_ID, "ying"})

# 宿主 renderer 模式的动作名；random_actions 只能取其中的值，宿主随机池从这里挑选。
HOST_ACTIONS = (
    "wave", "sit", "eye-roll", "faint", "disassemble", "happy-jump", "sleep", "stretch",
    "peek", "scan", "charge", "spin-cheer", "shy", "confused", "nod", "wake",
)
# 宿主 intent；actions 中可用它们为没有专属映射的动作提供回落。
HOST_INTENTS = (
    "idle", "thinking", "speaking", "notify", "success", "warning", "error",
    "dragging", "docked", "sleeping", "reaction",
)

MAX_JSON_BYTES = 64 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_SIDE = 4096
MAX_GRID_SIDE = 16
MAX_ACTIONS = 64
MAX_SEQUENCE = 64
MAX_RANDOM_ACTIONS = 16
MAX_PACKS = 20
MAX_PREVIEW_CHARS = 64 * 1024
DEFAULT_FRAME_MS = 160
FRAME_MS_RANGE = (40, 5000)
PREVIEW_SIZE = 128
AVATAR_SIZE = 128

# 只接受这四种位图；按文件头判定，不信任客户端声明的类型。
IMAGE_TYPES = {
    "png": ("image/png", "png"),
    "webp": ("image/webp", "webp"),
    "gif": ("image/gif", "gif"),
    "jpeg": ("image/jpeg", "jpg"),
}


class PackError(ValueError):
    """素材包或精灵图不合规；消息直接展示给配置页用户。"""


DEFAULT_CALIBRATION = {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0,
                       "baseline": 1.0, "offset_x": 0.0, "offset_y": 0.0}


def parse_calibration(raw: Any = None) -> dict[str, float]:
    """所有帧共用一个参考框，坐标为单格图片比例；只改变显示，不改原图。"""
    if raw is None:
        return dict(DEFAULT_CALIBRATION)
    if not isinstance(raw, dict) or set(raw) - set(DEFAULT_CALIBRATION):
        raise PackError("显示校准字段无效")
    result = dict(DEFAULT_CALIBRATION)
    for key, value in raw.items():
        low, high = (-0.25, 0.25) if key.startswith("offset_") else (0.0, 1.0)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
            raise PackError(f"显示校准 {key} 超出范围")
        result[key] = round(float(value), 4)
    if result["right"] - result["left"] < 0.1 - 1e-6 or result["bottom"] - result["top"] < 0.1 - 1e-6:
        raise PackError("有效显示区域的宽高至少为原格子的 10%")
    if not result["top"] < result["baseline"] <= result["bottom"]:
        raise PackError("脚底基线必须在显示区域内")
    return result


def suggest_calibration(content: bytes, pack: dict[str, Any]) -> dict[str, float]:
    """以全部已定义帧的透明边界合并参考框，以 idle 帧脚底给出建议。"""
    from PIL import Image

    validate_sheet(content, pack)
    with Image.open(io.BytesIO(content)) as source:
        source.seek(0)
        sheet = source.convert("RGBA")
    cols, rows = pack["grid"]["cols"], pack["grid"]["rows"]
    width, height = sheet.width // cols, sheet.height // rows
    boxes = []
    idle = None
    indices = set(pack["frames"].values())
    version = codex_pet_version(pack)
    if version:
        for row, count in enumerate((6, 8, 8, 4, 5, 8, 6, 6, 6)):
            indices.update(row * 8 + column for column in range(count))
        if version == "v2":
            indices.update(range(72, 88))
    for index in indices:
        x, y = index % cols * width, index // cols * height
        box = sheet.crop((x, y, x + width, y + height)).getchannel("A").getbbox()
        if box:
            boxes.append(box)
            if index == pack["frames"]["idle"]:
                idle = box
    if not boxes:
        raise PackError("素材没有可识别的非透明内容，请手动校准")
    left, top = min(v[0] for v in boxes) / width, min(v[1] for v in boxes) / height
    right, bottom = max(v[2] for v in boxes) / width, max(v[3] for v in boxes) / height
    if right - left < 0.1:
        left, right = max(0, right - 0.1), min(1, max(right, left + 0.1))
    if bottom - top < 0.1:
        top, bottom = max(0, bottom - 0.1), min(1, max(bottom, top + 0.1))
    return parse_calibration({"left": left, "top": top, "right": right, "bottom": bottom,
                              "baseline": max(top + 0.001, idle[3] / height if idle else bottom)})


def _text(value: Any, field: str, limit: int, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise PackError(f"{field} 必须是非空字符串")
    value = value.strip()
    if len(value) > limit:
        raise PackError(f"{field} 不能超过 {limit} 个字符")
    return value


def _int(value: Any, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PackError(f"{field} 必须是整数")
    if not low <= value <= high:
        raise PackError(f"{field} 必须在 {low} 到 {high} 之间")
    return value


def is_http_url(value: Any) -> bool:
    return isinstance(value, str) and len(value) <= 2048 and re.match(r"https?://[^\s]+$", value) is not None


def _image_ref(value: Any, field: str) -> str:
    """可选的预览图或头像地址，只接受 http(s) 或图片 data URL。"""
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value) > MAX_PREVIEW_CHARS:
        raise PackError(f"{field} 必须是不超过 64KB 的字符串")
    if is_http_url(value) or value.startswith("data:image/"):
        return value
    raise PackError(f"{field} 只支持 http(s) 地址或 data:image URL")


def _action(key: str, value: Any, frames: dict[str, int]) -> dict[str, Any]:
    """规整单个动作；允许直接写帧名列表作为简写。"""
    if isinstance(value, list):
        value = {"frames": value}
    if not isinstance(value, dict):
        raise PackError(f"actions.{key} 必须是对象或帧名列表")
    sequence = value.get("frames")
    if not isinstance(sequence, list) or not 1 <= len(sequence) <= MAX_SEQUENCE:
        raise PackError(f"actions.{key}.frames 必须是 1 到 {MAX_SEQUENCE} 个帧名")
    for name in sequence:
        if not isinstance(name, str) or name not in frames:
            raise PackError(f"actions.{key} 引用了未定义的帧 {name!r}")
    frame_ms = value.get("frame_ms", DEFAULT_FRAME_MS)
    frame_ms = _int(frame_ms, f"actions.{key}.frame_ms", *FRAME_MS_RANGE)
    loop = value.get("loop", False)
    if not isinstance(loop, bool):
        raise PackError(f"actions.{key}.loop 必须是布尔值")
    return {"frames": list(sequence), "frame_ms": frame_ms, "loop": loop}


def codex_pet_version(pack: dict[str, Any]) -> str | None:
    """识别显式 Codex 标记或旧导入包的关键动作布局，不仅凭网格猜测来源。"""
    grid = pack.get("grid")
    if not isinstance(grid, dict) or grid.get("cols") != 8:
        return None
    rows = grid.get("rows")
    if not isinstance(rows, int):
        return None
    version = {9: "v1", 11: "v2"}.get(rows)
    if version is None:
        return None
    declared = pack.get("codex_version")
    if declared is not None:
        return version if declared == version else None
    frames, actions = pack.get("frames"), pack.get("actions")
    if not isinstance(frames, dict) or not isinstance(actions, dict):
        return None
    # 兼容早期精简素材包和旧导入器，帧名可不同，但原生行与关键动画必须一致。
    for key, indices in (("idle", range(6)), ("wave", range(24, 28)), ("happy-jump", range(32, 37))):
        action = actions.get(key)
        sequence = action.get("frames") if isinstance(action, dict) else action
        if not isinstance(sequence, list) or len(sequence) < len(indices):
            return None
        if any(not isinstance(name, str) for name in sequence):
            return None
        if [frames.get(name) for name in sequence[:len(indices)]] != list(indices):
            return None
    return version


def parse_pack(raw: Any) -> dict[str, Any]:
    """校验并规整素材包 JSON（字符串或已解析对象），返回规范结构。

    规范结构：``id``、``name``、``description``、``sheet``、``grid``、``frames``、
    ``actions``、``random_actions``、``preview``、``avatar``。``sheet`` 原样保留，是否必须为 URL
    由调用方按添加方式决定。
    """
    if isinstance(raw, (str, bytes)):
        if len(raw) > MAX_JSON_BYTES:
            raise PackError("素材包 JSON 不能超过 64KB")
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise PackError(f"素材包 JSON 解析失败：{exc}") from exc
    if not isinstance(raw, dict):
        raise PackError("素材包 JSON 顶层必须是对象")

    pack_id = raw.get("id", "")
    if pack_id not in ("", None) and (not isinstance(pack_id, str) or not ID_PATTERN.fullmatch(pack_id)):
        raise PackError("id 只能包含小写字母、数字、- 和 _，长度 1 到 32")

    grid = raw.get("grid")
    if not isinstance(grid, dict):
        raise PackError("grid 必须是包含 cols 和 rows 的对象")
    cols = _int(grid.get("cols"), "grid.cols", 1, MAX_GRID_SIDE)
    rows = _int(grid.get("rows"), "grid.rows", 1, MAX_GRID_SIDE)

    frames_raw = raw.get("frames")
    if not isinstance(frames_raw, dict) or not frames_raw:
        raise PackError("frames 必须是帧名到格子索引的非空对象")
    frames: dict[str, int] = {}
    for name, index in frames_raw.items():
        if not NAME_PATTERN.fullmatch(str(name)):
            raise PackError(f"帧名 {name!r} 只能包含小写字母、数字、- 和 _")
        frames[name] = _int(index, f"frames.{name}", 0, cols * rows - 1)
    if "idle" not in frames:
        raise PackError("frames 必须包含 idle 帧，作为所有动作的回落")

    actions_raw = raw.get("actions", {})
    if not isinstance(actions_raw, dict) or len(actions_raw) > MAX_ACTIONS:
        raise PackError(f"actions 必须是对象，最多 {MAX_ACTIONS} 项")
    actions: dict[str, dict[str, Any]] = {}
    for key, value in actions_raw.items():
        if not NAME_PATTERN.fullmatch(str(key)):
            raise PackError(f"动作名 {key!r} 只能包含小写字母、数字、- 和 _")
        actions[key] = _action(key, value, frames)

    random_raw = raw.get("random_actions", [])
    if not isinstance(random_raw, list) or len(random_raw) > MAX_RANDOM_ACTIONS:
        raise PackError(f"random_actions 必须是列表，最多 {MAX_RANDOM_ACTIONS} 项")
    random_actions: list[str] = []
    for name in random_raw:
        if name not in HOST_ACTIONS:
            raise PackError(f"random_actions 中的 {name!r} 不是宿主动作名")
        if name not in random_actions:
            random_actions.append(name)

    sheet = raw.get("sheet", "")
    if sheet not in ("", None) and (not isinstance(sheet, str) or len(sheet) > 2048):
        raise PackError("sheet 必须是不超过 2048 个字符的图片路径或 URL")

    pack = {
        "id": pack_id or "",
        "name": _text(raw.get("name"), "name", 40),
        "description": _text(raw.get("description"), "description", 120, required=False),
        "sheet": sheet or "",
        "grid": {"cols": cols, "rows": rows},
        "frames": frames,
        "actions": actions,
        "random_actions": random_actions,
        "preview": _image_ref(raw.get("preview"), "preview"),
        "avatar": _image_ref(raw.get("avatar"), "avatar"),
    }
    declared = raw.get("codex_version")
    if declared is not None:
        if declared not in ("v1", "v2"):
            raise PackError("codex_version 只支持 v1 或 v2")
        pack["codex_version"] = declared
        if codex_pet_version(pack) is None:
            raise PackError("codex_version 与网格不匹配，v1 为 8×9，v2 为 8×11")
    version = codex_pet_version(pack)
    if version:
        pack["codex_version"] = version
    if "calibration" in raw:
        pack["calibration"] = parse_calibration(raw["calibration"])
    if "action_mappings" in raw:
        pack["action_mappings"] = validate_mappings(pack, raw["action_mappings"])
    return pack


def decode_image(data_url: str) -> tuple[bytes, str, str]:
    """解码配置页上传的 data URL，返回（字节、MIME、扩展名）。"""
    if not isinstance(data_url, str) or "," not in data_url or not data_url.startswith("data:"):
        raise PackError("精灵图必须以 data URL 形式上传")
    header, payload = data_url.split(",", 1)
    if ";base64" not in header:
        raise PackError("精灵图 data URL 必须使用 base64 编码")
    if len(payload) > MAX_IMAGE_BYTES * 4 // 3 + 8:
        raise PackError("精灵图不能超过 4MB")
    try:
        content = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PackError("精灵图 base64 内容无效") from exc
    mime, ext = sniff_image(content)
    return content, mime, ext


def sniff_image(content: bytes) -> tuple[str, str]:
    """按文件头识别图片类型并检查大小。"""
    if len(content) > MAX_IMAGE_BYTES:
        raise PackError("精灵图不能超过 4MB")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        kind = "png"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        kind = "webp"
    elif content[:6] in (b"GIF87a", b"GIF89a"):
        kind = "gif"
    elif content.startswith(b"\xff\xd8\xff"):
        kind = "jpeg"
    else:
        raise PackError("精灵图只支持 PNG、WebP、GIF 或 JPEG")
    return IMAGE_TYPES[kind]


def image_size(content: bytes) -> tuple[int, int]:
    """读取图片尺寸，同时确认内容可被解码。"""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise PackError("精灵图内容无法解码") from exc
    if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
        raise PackError(f"精灵图边长不能超过 {MAX_IMAGE_SIDE} 像素")
    return width, height


def _idle_frame(content: bytes, pack: dict[str, Any]):
    """从精灵图中裁出 idle 帧（RGBA）。"""
    from PIL import Image

    cols, rows = pack["grid"]["cols"], pack["grid"]["rows"]
    index = pack["frames"]["idle"]
    with Image.open(io.BytesIO(content)) as image:
        image.seek(0)
        cell_w, cell_h = image.width // cols, image.height // rows
        left, top = (index % cols) * cell_w, (index // cols) * cell_h
        return image.convert("RGBA").crop((left, top, left + cell_w, top + cell_h))


def _data_url(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def first_frame_preview(content: bytes, pack: dict[str, Any]) -> str:
    """裁出 idle 帧并缩成小缩略图，返回 PNG data URL，供宿主形象列表显示。"""
    frame = _idle_frame(content, pack)
    frame.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE))
    return _data_url(frame)


def first_frame_avatar(content: bytes, pack: dict[str, Any]) -> str:
    """从 idle 帧裁出方形头像，返回 PNG data URL，供 Agent 面板显示。

    取角色不透明区域的顶部、以其宽度为边长的正方形，通常落在头部和上半身；
    没有透明背景的图按整格处理。
    """
    from PIL import Image

    frame = _idle_frame(content, pack)
    left, top, right, bottom = frame.getchannel("A").getbbox() or (0, 0, frame.width, frame.height)
    side = min(right - left, bottom - top)
    center = (left + right) // 2
    x0 = max(0, min(center - side // 2, frame.width - side))
    avatar = frame.crop((x0, top, x0 + side, top + side))
    avatar.thumbnail((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    return _data_url(avatar)


def validate_sheet(content: bytes, pack: dict[str, Any]) -> tuple[str, str]:
    """校验精灵图类型、尺寸与网格是否匹配，返回（MIME、扩展名）。"""
    mime, ext = sniff_image(content)
    width, height = image_size(content)
    cols, rows = pack["grid"]["cols"], pack["grid"]["rows"]
    if width < cols or height < rows:
        raise PackError("精灵图尺寸小于网格行列数")
    if width % cols or height % rows:
        raise PackError(f"精灵图尺寸 {width}x{height} 不能被网格 {cols}x{rows} 整除")
    return mime, ext


_PACKS_LOCK = RLock()


def _serialized(method):
    """每个进程串行更新素材列表，避免不同字段的保存互相覆盖。"""
    @wraps(method)
    def wrapped(*args, **kwargs):
        with _PACKS_LOCK:
            return method(*args, **kwargs)
    return wrapped


STAGE_TRIGGERS = (
    "idle", "blink", "talk", "think", "jump", "wave", "held", "fall", "sit",
    "walk-left", "walk-right", "doze", "confused", "alert", "victory", "busy",
)
MAPPING_KEYS = frozenset(
    [f"action.{key}" for key in HOST_ACTIONS]
    + [f"intent.{key}" for key in HOST_INTENTS]
    + [f"stage.{key}" for key in STAGE_TRIGGERS]
)
CODEX_ACTIONS = (
    "idle", "running-right", "running-left", "waving", "jumping", "failed", "waiting", "running", "review",
    "wave", "notify", "happy-jump", "success", "faint", "error", "thinking", "charge", "speaking", "warning",
    "eye-roll", "scan",
)
LOOK_DIRECTIONS = (
    "000", "022-5", "045", "067-5", "090", "112-5", "135", "157-5",
    "180", "202-5", "225", "247-5", "270", "292-5", "315", "337-5",
)


def pack_revision(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_mappings(pack: dict[str, Any], mappings: Any) -> dict[str, str]:
    if not isinstance(mappings, dict) or len(mappings) > len(MAPPING_KEYS):
        raise PackError("动作映射必须是有效对象")
    available = set(pack.get("actions", {}))
    version = codex_pet_version(pack)
    if version:
        available.update(CODEX_ACTIONS)
    if version == "v2":
        available.update(f"look-{direction}" for direction in LOOK_DIRECTIONS)
    if any(key not in MAPPING_KEYS or not isinstance(value, str) or value not in available for key, value in mappings.items()):
        raise PackError("动作映射包含不支持的触发条件或动画")
    return dict(mappings)


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
        self._get_data = get_data
        self._save_data = save_data
        self._dir = data_path / "packs"

    def list(self) -> list[dict[str, Any]]:
        records = self._get_data(self.DATA_KEY) or []
        return [record for record in records if isinstance(record, dict) and ID_PATTERN.fullmatch(record.get("id", ""))]

    def get(self, pack_id: str) -> dict[str, Any] | None:
        return next((record for record in self.list() if record["id"] == pack_id), None)

    def image_path(self, record: dict[str, Any]) -> Path | None:
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
               mappings: dict[str, str] | None = None, expected_mappings: dict[str, str] | None = None) -> dict[str, Any]:
        """只更新显示名称或映射；原始动画、图片、ID 与其他字段保持原样。"""
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


def load_builtin_pack(dist_dir: Path) -> dict[str, Any]:
    """读取随联邦产物分发的内置素材包描述。"""
    path = dist_dir / "packs" / BUILTIN_PACK_ID / "pack.json"
    pack = parse_pack(path.read_text(encoding="utf-8"))
    pack["id"] = BUILTIN_PACK_ID
    return pack
