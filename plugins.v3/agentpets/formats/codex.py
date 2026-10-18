"""Codex Pet 清单与动画布局解析，不负责压缩格式、网络或持久化"""

from __future__ import annotations

import json
from typing import Any

from .archive import PackageReader
from ..packs.constants import LOOK_DIRECTIONS, MAX_IMAGE_BYTES, MAX_JSON_BYTES, PackError
from ..packs.images import image_size, sniff_image
from ..packs.schema import parse_pack

_LAYOUTS = {(1536, 1872): ("v1", 9), (1536, 2288): ("v2", 11)}

_ROWS = (
    ("idle", 6, 360, True),
    ("running-right", 8, 140, True),
    ("running-left", 8, 140, True),
    ("waving", 4, 160, False),
    ("jumping", 5, 160, False),
    ("failed", 8, 180, False),
    ("waiting", 6, 220, True),
    ("running", 6, 160, True),
    ("review", 6, 180, False),
)

_ALIASES = {
    "wave": ("waving", 160), "notify": ("waving", 160),
    "happy-jump": ("jumping", 160), "success": ("jumping", 180),
    "faint": ("failed", 180), "error": ("failed", 180),
    "thinking": ("waiting", 220), "charge": ("running", 160),
    "speaking": ("running", 160), "warning": ("review", 180),
    "eye-roll": ("review", 180),
}


def detect_codex_layout(dimensions: tuple[int, int], *, allow_scaled: bool = False) -> tuple[str, int]:
    """识别布局，缩放模式仅接受等比例且所有网格边界为整数的图片"""
    layout = _LAYOUTS.get(dimensions)
    if layout is not None:
        return layout
    width, height = dimensions
    if allow_scaled and width > 0 and height > 0:
        for (canonical_width, canonical_height), candidate in _LAYOUTS.items():
            if (width % 8 == 0 and height % candidate[1] == 0
                    and width * canonical_height == height * canonical_width):
                return candidate
    raise PackError("只支持 Codex Pet v1（1536×1872）或 v2（1536×2288）精灵图及允许的等比布局")


def build_codex_pack(manifest: dict[str, Any], image: bytes, pack_id: str, *, allow_scaled: bool = False) -> dict[str, Any]:
    """将清单和图片转换为规范素材，调用方提供稳定本地 ID，原图字节保持不变"""
    mime, _ = sniff_image(image)
    if mime not in ("image/png", "image/webp"):
        raise PackError("Codex Pet 精灵图只支持 PNG 或 WebP")
    layout = detect_codex_layout(image_size(image), allow_scaled=allow_scaled)
    version, rows = layout
    declared = manifest.get("spriteVersionNumber")
    if declared is not None and (type(declared) is not int or declared != int(version[-1])):
        raise PackError("Codex Pet 声明的版本与精灵图尺寸不匹配")
    name = manifest.get("displayName") or "Codex Pet"
    description = manifest.get("description") or f"从 Codex Pet {version} 精灵图导入"
    if not isinstance(name, str) or not isinstance(description, str):
        raise PackError("Codex Pet 名称和说明必须是字符串")
    frames: dict[str, int] = {}
    actions: dict[str, Any] = {}
    for row_index, (row_name, count, frame_ms, loop) in enumerate(_ROWS):
        sequence = []
        for column in range(count):
            frame = "idle" if row_name == "idle" and column == 0 else f"{row_name}-{column + 1}"
            frames[frame] = row_index * 8 + column
            sequence.append(frame)
        actions[row_name] = {"frames": sequence, "frame_ms": frame_ms, "loop": loop}
    for alias, (original, frame_ms) in _ALIASES.items():
        actions[alias] = {**actions[original], "frames": list(actions[original]["frames"]), "frame_ms": frame_ms}
    look_frames = []
    if version == "v2":
        for index, direction in enumerate(LOOK_DIRECTIONS):
            frame = f"look-{direction}"
            frames[frame] = 72 + index
            look_frames.append(frame)
            actions[frame] = {"frames": [frame], "frame_ms": 160, "loop": False}
    actions["scan"] = {
        "frames": look_frames + look_frames[:1] if look_frames else list(actions["review"]["frames"]),
        "frame_ms": 140, "loop": False,
    }
    pack = parse_pack({
        "id": pack_id,
        "name": name.strip()[:40], "description": description.strip()[:120],
        "codex_version": version, "grid": {"cols": 8, "rows": rows},
        "frames": frames, "actions": actions, "random_actions": ["wave"],
    })
    return pack


def read_codex_package(package: PackageReader) -> tuple[dict[str, Any], bytes]:
    """从任意受限容器中解析 Codex 清单和图片，仅解释此素材格式的文件布局"""
    manifests = [path for path in package.files if path.rsplit("/", 1)[-1].lower() == "pet.json"]
    if len(manifests) != 1:
        raise PackError("Codex Pet 素材必须包含唯一的 pet.json")
    manifest_path = manifests[0]
    try:
        manifest = json.loads(package.read(manifest_path, MAX_JSON_BYTES))
    except PackError:
        raise
    except ValueError as exc:
        raise PackError("Codex Pet 清单已损坏或无法解析") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("spritesheetPath"), str):
        raise PackError("pet.json 必须包含 spritesheetPath")
    image_path = package.resolve(manifest["spritesheetPath"].strip(), relative_to=manifest_path)
    if image_path not in package.files:
        raise PackError("找不到 pet.json 指定的精灵图")
    return manifest, package.read(image_path, MAX_IMAGE_BYTES)
