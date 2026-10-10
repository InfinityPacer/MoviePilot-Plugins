"""素材包格式校验、精灵图校验与插件数据目录存储。

素材包是一张精灵图加一份描述 JSON；格式见插件 README 的「素材包格式」。
这里是格式的唯一权威实现，前端配置页只做即时提示，最终以此处校验为准。
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
import time
from pathlib import Path
from typing import Any

# 素材包 ID 同时作为形象 key 写入用户选择，规则与宿主形象 key 一致。
ID_PATTERN = re.compile(r"[a-z0-9_-]{1,32}")
# 帧名和动作名沿用宿主动作命名风格（如 happy-jump）。
NAME_PATTERN = re.compile(r"[a-z0-9_-]{1,32}")

BUILTIN_PACK_ID = "projector-cat"

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

# 只接受这四种位图；按文件头判定，不信任客户端声明的类型。
IMAGE_TYPES = {
    "png": ("image/png", "png"),
    "webp": ("image/webp", "webp"),
    "gif": ("image/gif", "gif"),
    "jpeg": ("image/jpeg", "jpg"),
}


class PackError(ValueError):
    """素材包或精灵图不合规；消息直接展示给配置页用户。"""


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


def _preview(value: Any) -> str:
    """可选的预览图地址，只接受 http(s) 或图片 data URL。"""
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value) > MAX_PREVIEW_CHARS:
        raise PackError("preview 必须是不超过 64KB 的字符串")
    if is_http_url(value) or value.startswith("data:image/"):
        return value
    raise PackError("preview 只支持 http(s) 地址或 data:image URL")


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
        if name not in frames:
            raise PackError(f"actions.{key} 引用了未定义的帧 {name!r}")
    frame_ms = value.get("frame_ms", DEFAULT_FRAME_MS)
    frame_ms = _int(frame_ms, f"actions.{key}.frame_ms", *FRAME_MS_RANGE)
    loop = value.get("loop", False)
    if not isinstance(loop, bool):
        raise PackError(f"actions.{key}.loop 必须是布尔值")
    return {"frames": list(sequence), "frame_ms": frame_ms, "loop": loop}


def parse_pack(raw: Any) -> dict[str, Any]:
    """校验并规整素材包 JSON（字符串或已解析对象），返回规范结构。

    规范结构：``id``、``name``、``description``、``sheet``、``grid``、``frames``、
    ``actions``、``random_actions``、``preview``。``sheet`` 原样保留，是否必须为 URL
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

    return {
        "id": pack_id or "",
        "name": _text(raw.get("name"), "name", 40),
        "description": _text(raw.get("description"), "description", 120, required=False),
        "sheet": sheet or "",
        "grid": {"cols": cols, "rows": rows},
        "frames": frames,
        "actions": actions,
        "random_actions": random_actions,
        "preview": _preview(raw.get("preview")),
    }


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
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PackError("精灵图内容无法解码") from exc
    if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
        raise PackError(f"精灵图边长不能超过 {MAX_IMAGE_SIDE} 像素")
    return width, height


def first_frame_preview(content: bytes, pack: dict[str, Any]) -> str:
    """裁出 idle 帧并缩成小缩略图，返回 PNG data URL，供宿主形象列表显示。"""
    from PIL import Image

    cols, rows = pack["grid"]["cols"], pack["grid"]["rows"]
    index = pack["frames"]["idle"]
    with Image.open(io.BytesIO(content)) as image:
        image.seek(0)
        cell_w, cell_h = image.width // cols, image.height // rows
        left, top = (index % cols) * cell_w, (index // cols) * cell_h
        frame = image.convert("RGBA").crop((left, top, left + cell_w, top + cell_h))
    frame.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE))
    buffer = io.BytesIO()
    frame.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


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

    def add(self, raw_pack: Any, image: str | None = None) -> dict[str, Any]:
        """校验后保存一个素材包；带 image 时为上传方式，否则 sheet 必须是 http(s) URL。"""
        pack = parse_pack(raw_pack)
        pack_id = pack["id"] or self._derive_id(pack["name"])
        if pack_id == BUILTIN_PACK_ID:
            raise PackError(f"{BUILTIN_PACK_ID} 是内置素材包的 ID，请换一个")
        records = self.list()
        if any(record["id"] == pack_id for record in records):
            raise PackError(f"已存在 ID 为 {pack_id} 的素材包，请先删除或换一个 ID")
        if len(records) >= MAX_PACKS:
            raise PackError(f"最多保存 {MAX_PACKS} 个素材包")

        record: dict[str, Any] = {
            key: pack[key] for key in ("name", "description", "grid", "frames", "actions", "random_actions")
        }
        record.update(id=pack_id, preview=pack["preview"], created_at=int(time.time()))
        if image:
            content, _, _ = decode_image(image)
            mime, ext = validate_sheet(content, pack)
            self._dir.mkdir(parents=True, exist_ok=True)
            file_name = f"{pack_id}.{ext}"
            (self._dir / file_name).write_bytes(content)
            record.update(source="upload", image_file=file_name, mime=mime, sheet_url="")
            if not record["preview"]:
                record["preview"] = first_frame_preview(content, pack)
        else:
            if not is_http_url(pack["sheet"]):
                raise PackError("没有上传精灵图时，sheet 必须是 http(s) 图片地址")
            record.update(source="url", image_file="", mime="", sheet_url=pack["sheet"])
        self._save_data(self.DATA_KEY, records + [record])
        return record

    def remove(self, pack_id: str) -> bool:
        records = self.list()
        target = next((record for record in records if record["id"] == pack_id), None)
        if not target:
            return False
        path = self.image_path(target)
        if path and path.is_file():
            path.unlink()
        self._save_data(self.DATA_KEY, [record for record in records if record["id"] != pack_id])
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
