"""素材格式限制、保留标识和动作契约"""

import re

class PackError(ValueError):
    """素材包或精灵图不合规；消息直接展示给配置页用户。"""

ID_PATTERN = re.compile(r"[a-z0-9_-]{1,32}")

NAME_PATTERN = re.compile(r"[a-z0-9_-]{1,32}")

BUILTIN_PACK_ID = "projector-cat"

RESERVED_IDS = frozenset({BUILTIN_PACK_ID, "ying"})

HOST_ACTIONS = (
    "wave", "sit", "eye-roll", "faint", "disassemble", "happy-jump", "sleep", "stretch",
    "peek", "scan", "charge", "spin-cheer", "shy", "confused", "nod", "wake",
)

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

MAX_PREVIEW_BYTES = 128 * 1024

MAX_PREVIEW_CHARS = ((MAX_PREVIEW_BYTES + 2) // 3) * 4 + 32

DEFAULT_FRAME_MS = 160

FRAME_MS_RANGE = (40, 5000)

PREVIEW_SIZE = 128

AVATAR_SIZE = 128

IMAGE_TYPES = {
    "png": ("image/png", "png"),
    "webp": ("image/webp", "webp"),
    "gif": ("image/gif", "gif"),
    "jpeg": ("image/jpeg", "jpg"),
}

DEFAULT_CALIBRATION = {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0,
                       "baseline": 1.0, "offset_x": 0.0, "offset_y": 0.0}

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
