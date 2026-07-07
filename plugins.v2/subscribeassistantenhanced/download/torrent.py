"""TorrentInfo 标准化结构 + TorrentAdapter（QB/TR 封装）。"""
import time
from dataclasses import dataclass, field
from typing import Any, Optional

QB_COMPLETE_STATES = {
    "uploading",
    "stalledUP",
    "checkingUP",
    "pausedUP",
    "stoppedUP",
    "queuedUP",
    "forcedUP",
}


@dataclass
class TorrentInfo:
    """QB/TR 种子信息标准化结构，保留下载任务判定需要的核心字段。"""
    hash: str = ""
    title: str = ""
    state: str = ""
    progress: float = 0.0
    total_size: int = 0
    target_size: int = 0
    downloaded: int = 0
    uploaded: int = 0
    ratio: float = 0.0
    dltime: int = 0
    seeding_time: int = 0
    iatime: int = 0
    avg_upspeed: int = 0
    add_time: str = ""
    add_on: int = 0
    tags: list = field(default_factory=list)
    tracker: str = ""
    tracker_responses: list = field(default_factory=list)
    completed: bool = False
    completion_time: float = 0.0


class TorrentAdapter:
    """种子操作统一接口，内部按下载器类型分发 QB/TR 映射。"""

    @staticmethod
    def from_qb(torrent: dict) -> TorrentInfo:
        """QB 种子字典 → TorrentInfo，以 size 作为已选文件目标体积。"""
        state = _get_attr(torrent, "state", default="")
        total_size = _as_int(_get_attr(torrent, "total_size", default=0))
        target_size = _positive_int(_get_attr(torrent, "size", default=None)) or total_size
        downloaded = _as_int(_get_attr(torrent, "downloaded", default=0))
        seeding_time = _qb_seeding_time(torrent)
        progress = _progress_fraction(downloaded, target_size or total_size)
        completed, completion_time = _completion_status(
            state=state,
            seeding_time=seeding_time,
            downloaded=downloaded,
            target_size=target_size,
            dltime=_as_int(_get_attr(torrent, "dltime", default=0)),
            state_complete=_is_qb_complete_state(torrent, state),
        )
        return TorrentInfo(
            hash=_get_attr(torrent, "hash", default=""),
            title=_get_attr(torrent, "name", default=""),
            state=state,
            progress=progress,
            total_size=total_size,
            target_size=target_size,
            downloaded=downloaded,
            uploaded=_as_int(_get_attr(torrent, "uploaded", default=0)),
            ratio=_as_float(_get_attr(torrent, "ratio", default=0.0)),
            dltime=_as_int(_get_attr(torrent, "dltime", default=0)),
            seeding_time=seeding_time,
            iatime=_as_int(_get_attr(torrent, "inactive_seeding_time", "last_activity", default=0)),
            avg_upspeed=_as_int(_get_attr(torrent, "up_limit", default=0)),
            add_time=_get_attr(torrent, "added_on_str", default=""),
            add_on=_as_int(_get_attr(torrent, "added_on", default=0)),
            tags=_parse_tags(_get_attr(torrent, "tags", default="")),
            tracker=_get_attr(torrent, "tracker", default=""),
            tracker_responses=_get_qb_tracker_responses(torrent),
            completed=completed,
            completion_time=completion_time,
        )

    @staticmethod
    def from_tr(torrent) -> TorrentInfo:
        """TR 种子对象 → TorrentInfo，优先使用 size_when_done 作为已选文件目标体积。"""
        total_size = _as_int(_get_attr(torrent, "total_size", "totalSize", default=0))
        target_size = total_size
        fields = _get_attr(torrent, "fields", default=None)
        if fields is None or "size_when_done" in fields or "sizeWhenDone" in fields:
            target_size = _positive_int(
                _get_attr(torrent, "size_when_done", "sizeWhenDone", default=None)
            ) or total_size
        downloaded = _get_attr(torrent, "downloaded_ever", "downloadedEver", default=None)
        if downloaded is None:
            downloaded = int(total_size * (_get_attr(torrent, "progress", default=0.0) or 0) / 100)
        downloaded = _as_int(downloaded)
        dltime = int(_get_attr(torrent, "seconds_downloading", "secondsDownloading", default=0) or 0)
        seeding_time = int(_get_attr(torrent, "seconds_seeding", "secondsSeeding", default=0) or 0)
        state = _get_attr(torrent, "status", default="")
        progress = _progress_fraction(downloaded, target_size or total_size)
        completed, completion_time = _completion_status(
            state=state,
            seeding_time=seeding_time,
            downloaded=downloaded,
            target_size=target_size,
            dltime=dltime,
        )
        ratio = _get_attr(torrent, "ratio", "uploadRatio", default=0.0) or 0.0
        uploaded = _get_attr(torrent, "uploaded_ever", "uploadedEver", default=None)
        if uploaded is None:
            uploaded = int(downloaded * ratio)
        added_date = _get_attr(torrent, "added_date", "addedDate", default=None)
        return TorrentInfo(
            hash=_get_attr(torrent, "hashString", default=""),
            title=_get_attr(torrent, "name", default=""),
            state=state,
            progress=progress,
            total_size=total_size,
            target_size=target_size,
            downloaded=downloaded,
            uploaded=uploaded,
            ratio=ratio,
            dltime=dltime,
            seeding_time=seeding_time,
            iatime=int(_get_attr(torrent, "idle_seconds", "idleSeconds", default=0) or 0),
            avg_upspeed=int(_get_attr(torrent, "rate_upload", "rateUpload", default=0) or 0),
            add_time=str(added_date or ""),
            add_on=int(added_date.timestamp()) if hasattr(added_date, "timestamp") else 0,
            tags=list(_get_attr(torrent, "labels", default=[]) or []),
            tracker=_get_tr_tracker(torrent),
            tracker_responses=_get_tr_tracker_responses(torrent),
            completed=completed,
            completion_time=completion_time,
        )

    @staticmethod
    def get_info(torrent: Any, dl_type: str) -> TorrentInfo:
        """统一入口，按 dl_type 分发。"""
        if dl_type == "qbittorrent":
            return TorrentAdapter.from_qb(torrent)
        elif dl_type == "transmission":
            return TorrentAdapter.from_tr(torrent)
        raise ValueError(f"不支持的下载器类型: {dl_type}")

    @staticmethod
    def get_tags(info: TorrentInfo) -> list[str]:
        """获取种子标签列表。"""
        return info.tags

    @staticmethod
    def is_completed(info: TorrentInfo) -> tuple[bool, float]:
        """判断种子是否已完成下载，返回 (completed, completion_time)。"""
        return info.completed, info.completion_time

    @staticmethod
    def progress_percent(info: TorrentInfo) -> float:
        """获取下载进度百分比 0-100，目标体积优先使用已选择文件大小。"""
        return _progress_percent(info.downloaded, info.target_size or info.total_size)


def _completion_status(state: str, seeding_time: int, downloaded: int,
                       target_size: int, dltime: int,
                       state_complete: bool = False) -> tuple[bool, float]:
    """判断种子是否完成：下载器完成态优先，体积兜底必须有有效目标大小。"""
    if state_complete or state in ["seeding", "seed_pending"]:
        return True, 0.0
    if _positive_int(seeding_time):
        return True, 0.0
    if _positive_int(target_size) and downloaded >= target_size:
        return True, 0.0
    return False, dltime


def _is_qb_complete_state(torrent, state: str) -> bool:
    """使用 qB SDK 的 state_enum.is_complete；普通 dict 按 SDK 状态集合兜底。"""
    try:
        state_enum = getattr(torrent, "state_enum", None)
    except Exception:
        state_enum = None
    try:
        if state_enum is not None and bool(getattr(state_enum, "is_complete", False)):
            return True
    except Exception:
        pass
    return str(state or "") in QB_COMPLETE_STATES


def _qb_seeding_time(torrent) -> int:
    """qB completion_on 是完成时间戳；小于等于 0 表示未完成，不能当做种时长。"""
    completion_on = _as_int(_get_attr(torrent, "completion_on", default=0))
    if completion_on > 0:
        return max(0, int(time.time()) - completion_on)
    return _positive_int(_get_attr(torrent, "seeding_time", default=0))


def _progress_fraction(downloaded: int, target_size: int) -> float:
    """返回 0-1 的下载进度，内部复用百分比计算并做边界裁剪。"""
    return _progress_percent(downloaded, target_size) / 100


def _progress_percent(downloaded: int, target_size: int) -> float:
    """按已下载体积与目标体积计算 0-100 下载百分比。"""
    try:
        downloaded_value = float(downloaded or 0)
        target_value = float(target_size or 0)
    except (TypeError, ValueError):
        return 0.0
    if target_value <= 0:
        return 0.0
    return max(0.0, min(downloaded_value / target_value * 100, 100.0))


def _as_int(value, default: int = 0) -> int:
    """把 SDK 原始数值统一为 int，异常值按默认值处理。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _positive_int(value) -> int:
    """只接受正整数；下载目标大小和做种时间的 0/负数都视为无效。"""
    value = _as_int(value)
    return value if value > 0 else 0


def _as_float(value, default: float = 0.0) -> float:
    """把 SDK 原始数值统一为 float，异常值按默认值处理。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_tags(tags_str) -> list:
    """解析 QB 标签字符串。"""
    if isinstance(tags_str, list):
        return tags_str
    if not tags_str:
        return []
    return [t.strip() for t in str(tags_str).split(",") if t.strip()]


def _get_attr(obj, *names, default=None):
    """按多个候选属性读取值，兼容下载器 SDK 的 snake/camel 命名差异。"""
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        try:
            value = getattr(obj, name)
        except Exception:
            value = None
        if value is not None:
            return value
        getter = getattr(obj, "get", None)
        if callable(getter):
            try:
                value = getter(name, None)
            except Exception:
                value = None
            if value is not None:
                return value
    return default


def _get_qb_tracker_responses(torrent) -> list:
    """读取 qB tracker.msg，过滤禁用 tier 和空响应。"""
    trackers = _get_attr(torrent, "trackers", default=[]) or []
    responses = []
    for tracker in trackers:
        tier = tracker.get("tier", 0) if isinstance(tracker, dict) else getattr(tracker, "tier", 0)
        if tier == -1:
            continue
        msg = tracker.get("msg", "") if isinstance(tracker, dict) else getattr(tracker, "msg", "")
        if msg:
            responses.append(str(msg))
    return responses


def _get_tr_tracker(torrent) -> str:
    trackers = _get_attr(torrent, "trackers", default=[])
    if trackers:
        first = trackers[0] if isinstance(trackers, list) else None
        if first:
            announce = getattr(first, "announce", None)
            return announce if announce is not None else str(first)
    return ""


def _get_tr_tracker_responses(torrent) -> list:
    trackers = _get_attr(torrent, "tracker_stats", "trackerStats", default=[])
    responses = []
    for t in (trackers or []):
        if _get_attr(t, "tier", default=0) == -1:
            continue
        msg = _get_attr(t, "last_announce_result", "lastAnnounceResult", default="")
        if msg:
            responses.append(str(msg))
    return responses
