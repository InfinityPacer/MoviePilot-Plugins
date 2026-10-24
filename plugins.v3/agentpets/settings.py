"""舞台活动参数范围与默认配置"""

SCALE_RANGE = (0.6, 1.6)
SPEED_RANGE = (0.5, 2.0)
PEEK_ANGLE_RANGE = (0.0, 45.0)
DEFAULT_PEEK_ANGLES = {"bottom": 0.0, "left": 35.0, "right": 35.0}
PEEK_EDGES = ("bottom", "left", "right")
ROAM_MODES = ("surfaces", "floor", "free")
DEFAULT_SETTINGS = {"scale": 1.0, "speed": 1.0, "roam": "surfaces", "movement": "auto"}
DIALOGUE_MODES = ("off", "interaction", "occasional")
DIALOGUE_VOICES = ("default", "ying", "neutral", "lively", "wry")


def default_dialogue(key: str) -> dict[str, str]:
    """Keep legacy Ying speech and leave other unconfigured stage Pets silent."""
    return {"mode": "interaction" if key == "ying" else "off",
            "voice": "default" if key == "ying" else "neutral"}


def parse_dialogue(value: object) -> dict[str, str] | None:
    """Read optional preferences without migrating or rewriting existing data."""
    if not isinstance(value, dict):
        return None
    valid_voice = value.get("voice") in DIALOGUE_VOICES
    return {"mode": value.get("mode") if value.get("mode") in DIALOGUE_MODES and valid_voice else "off",
            "voice": value.get("voice") if valid_voice else "neutral"}
