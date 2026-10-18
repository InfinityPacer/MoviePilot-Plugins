"""素材图片解码、尺寸校验、缩略图与自动校准"""

from __future__ import annotations

import base64
import binascii
import io
from typing import Any

from .constants import (
    AVATAR_SIZE,
    IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_SIDE,
    PREVIEW_SIZE,
    PackError,
)
from .schema import (
    codex_pet_version,
    parse_calibration,
)


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
    """将已解码图片编码为 PNG data URL，供缩略图和头像直接使用"""
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
