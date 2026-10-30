"""Concrete JSON payloads; TypedDict keeps existing dictionary callers compatible."""

from typing import Literal

from pydantic import ConfigDict
from typing_extensions import NotRequired, TypedDict

class Payload(TypedDict):
    """Reject unexpected fields without converting dictionaries into model objects."""
    __pydantic_config__ = ConfigDict(extra="forbid")


class DialogueData(Payload):
    """Effective per-character speech preferences."""
    mode: Literal["off", "interaction", "occasional"]
    voice: Literal["default", "ying", "neutral", "lively", "wry"]


class PeekAnglesData(Payload):
    """Angles for the three independently calibrated peek edges."""
    bottom: float
    left: float
    right: float


class AppearanceData(Payload):
    """Effective appearance with legacy optional fields left absent."""
    scale: float
    speed: float
    peek_angles: NotRequired[PeekAnglesData]
    dialogue: NotRequired[DialogueData]


class ActivityData(Payload):
    """Shared autonomous movement settings."""
    roam: Literal["surfaces", "floor", "free"]
    movement: Literal["auto", "fixed"]


class SettingsData(AppearanceData, ActivityData):
    """Complete effective settings exposed to the stage."""


class PetSettingsData(AppearanceData):
    """A saved appearance bound to one stable Pet key."""
    key: str


class EditorPetData(Payload):
    """Safe character identity and preview fields for the editor."""
    key: str
    name: str
    description: str
    mode: Literal["stage", "renderer"]
    preview: str
    builtin: bool


class EditorData(Payload):
    """Editor bootstrap data, excluding unrelated plugin configuration."""
    enabled: bool
    settings: SettingsData
    pets: list[EditorPetData]
    pet_settings: dict[str, AppearanceData]


class GridData(Payload):
    """Sprite atlas dimensions."""
    cols: int
    rows: int


class ActionData(Payload):
    """A validated sprite animation and its playback timing."""
    frames: list[str]
    frame_ms: int
    loop: bool
    frame_durations: NotRequired[list[int]]


class CalibrationValues(Payload):
    """Crop, baseline and landmarks shared by every frame."""
    left: float
    top: float
    right: float
    bottom: float
    baseline: float
    offset_x: float
    offset_y: float
    eye_x: float | None
    eye_y: float | None
    left_eye_x: float | None
    left_eye_y: float | None
    right_eye_x: float | None
    right_eye_y: float | None
    head_top_x: float | None
    head_top_y: float | None


class PackSummaryData(Payload):
    """Management summary without the full sprite atlas."""
    id: str
    name: str
    description: str
    builtin: bool
    mode: Literal["stage", "renderer"]
    source: str
    preview: str
    grid: GridData
    frame_count: int
    action_count: int
    revision: str
    mapping_count: int
    calibrated: bool


class PackData(Payload):
    """A full runtime pack with optional built-in and Codex extensions."""
    id: str
    name: str
    description: str
    grid: GridData
    frames: dict[str, int]
    actions: dict[str, ActionData]
    random_actions: list[str]
    preview: str
    avatar: str
    calibration: CalibrationValues
    sheet: NotRequired[str]
    codex_version: NotRequired[Literal["v1", "v2"]]
    action_mappings: NotRequired[dict[str, str]]
    action_baselines: NotRequired[dict[str, float]]


class PackPayload(Payload):
    """Pack data and conditional sprite transfer revision."""
    pack: PackData
    builtin: bool
    sheet_src: str
    sheet_revision: NotRequired[str]


class MappingsData(Payload):
    """Persisted trigger mappings for one pack."""
    id: str
    mappings: dict[str, str]


class MarketInfoData(Payload):
    """Registered market metadata in its existing JSON representation."""
    id: str
    name: str
    description: str
    homepage: str | None


class MarketItemData(Payload):
    """A remote market discovery result, not a local pack."""
    id: str
    name: str
    description: str
    author: str
    license: str
    preview: str | None
    source_url: str | None


class MarketItemsData(Payload):
    """Market-scoped pagination with explicit unknown totals."""
    market_id: str
    page: int
    page_size: int
    items: list[MarketItemData]
    total: int | None
    has_more: bool
