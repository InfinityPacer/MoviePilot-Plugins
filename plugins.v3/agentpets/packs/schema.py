"""素材描述、校准、动作映射与修订号的纯校验"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from .constants import (
    CODEX_ACTIONS,
    DEFAULT_CALIBRATION,
    DEFAULT_FRAME_MS,
    FRAME_MS_RANGE,
    HOST_ACTIONS,
    ID_PATTERN,
    LOOK_DIRECTIONS,
    MAPPING_KEYS,
    MAX_ACTIONS,
    MAX_GRID_SIDE,
    MAX_JSON_BYTES,
    MAX_PREVIEW_CHARS,
    MAX_RANDOM_ACTIONS,
    MAX_SEQUENCE,
    NAME_PATTERN,
    PackError,
)


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


def _text(value: Any, field: str, limit: int, required: bool = True) -> str:
    """校验必填与可选文本、去除首尾空白并限制长度，失败抛出 PackError"""
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise PackError(f"{field} 必须是非空字符串")
    value = value.strip()
    if len(value) > limit:
        raise PackError(f"{field} 不能超过 {limit} 个字符")
    return value


def _int(value: Any, field: str, low: int, high: int) -> int:
    """只接受范围内的整数，显式排除布尔值避免其冒充数值"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PackError(f"{field} 必须是整数")
    if not low <= value <= high:
        raise PackError(f"{field} 必须在 {low} 到 {high} 之间")
    return value


def is_http_url(value: Any) -> bool:
    """判断素材引用是否为长度受限的 HTTP(S) 地址，不发起网络请求"""
    return isinstance(value, str) and len(value) <= 2048 and re.match(r"https?://[^\s]+$", value) is not None


def _image_ref(value: Any, field: str) -> str:
    """可选的预览图或头像地址，只接受 http(s) 或图片 data URL。"""
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or len(value) > MAX_PREVIEW_CHARS:
        raise PackError(f"{field} 地址过长，内嵌图片不能超过 128 KiB")
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


def pack_revision(record: dict[str, Any]) -> str:
    """以稳定 JSON 序列化生成修订号，用于拒绝覆盖过期素材快照"""
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_mappings(pack: dict[str, Any], mappings: Any) -> dict[str, str]:
    """校验触发条件与动画目标，Codex 素材允许原生及兼容补齐动作"""
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
