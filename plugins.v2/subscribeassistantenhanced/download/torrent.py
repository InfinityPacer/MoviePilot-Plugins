"""TorrentInfo 标准化结构 + TorrentAdapter（QB/TR 封装）。"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TorrentInfo:
    """QB/TR 种子信息标准化结构，保留旧版下载任务判定需要的核心字段。"""
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
        """QB 种子字典 → TorrentInfo，按旧版以 size 作为目标下载体积。"""
        total_size = torrent.get("total_size", 0)
        target_size = torrent.get("size") or total_size
        downloaded = torrent.get("downloaded", 0)
        seeding_time = torrent.get("completion_on", torrent.get("seeding_time", 0))
        progress = _progress_fraction(downloaded, target_size or total_size)
        completed, completion_time = _completion_status(
            state=torrent.get("state", ""),
            seeding_time=seeding_time,
            downloaded=downloaded,
            target_size=target_size,
            dltime=torrent.get("dltime", 0),
        )
        return TorrentInfo(
            hash=torrent.get("hash", ""),
            title=torrent.get("name", ""),
            state=torrent.get("state", ""),
            progress=progress,
            total_size=total_size,
            target_size=target_size,
            downloaded=downloaded,
            uploaded=torrent.get("uploaded", 0),
            ratio=torrent.get("ratio", 0.0),
            dltime=torrent.get("dltime", 0),
            seeding_time=seeding_time,
            iatime=torrent.get("inactive_seeding_time", torrent.get("last_activity", 0)),
            avg_upspeed=torrent.get("up_limit", 0),
            add_time=torrent.get("added_on_str", ""),
            add_on=torrent.get("added_on", 0),
            tags=_parse_tags(torrent.get("tags", "")),
            tracker=torrent.get("tracker", ""),
            tracker_responses=_get_qb_tracker_responses(torrent),
            completed=completed,
            completion_time=completion_time,
        )

    @staticmethod
    def from_tr(torrent) -> TorrentInfo:
        """TR 种子对象 → TorrentInfo，按旧版优先使用 size_when_done 作为目标体积。"""
        total_size = _get_attr(torrent, "total_size", "totalSize", default=0)
        target_size = total_size
        fields = getattr(torrent, "fields", None)
        if fields is None or "size_when_done" in fields:
            target_size = getattr(torrent, "size_when_done", total_size)
        downloaded = _get_attr(torrent, "downloaded_ever", "downloadedEver", default=None)
        if downloaded is None:
            downloaded = int(total_size * (getattr(torrent, "progress", 0.0) or 0) / 100)
        dltime = int(getattr(torrent, "secondsDownloading", 0))
        seeding_time = int(getattr(torrent, "secondsSeeding", 0))
        progress = _progress_fraction(downloaded, target_size or total_size)
        completed, completion_time = _completion_status(
            state=getattr(torrent, "status", ""),
            seeding_time=seeding_time,
            downloaded=downloaded,
            target_size=target_size,
            dltime=dltime,
        )
        ratio = _get_attr(torrent, "ratio", "uploadRatio", default=0.0) or 0.0
        uploaded = _get_attr(torrent, "uploaded_ever", "uploadedEver", default=None)
        if uploaded is None:
            uploaded = int(downloaded * ratio)
        added_date = getattr(torrent, "addedDate", None)
        return TorrentInfo(
            hash=getattr(torrent, "hashString", ""),
            title=getattr(torrent, "name", ""),
            state=getattr(torrent, "status", ""),
            progress=progress,
            total_size=total_size,
            target_size=target_size,
            downloaded=downloaded,
            uploaded=uploaded,
            ratio=ratio,
            dltime=dltime,
            seeding_time=seeding_time,
            iatime=int(getattr(torrent, "idleSeconds", 0) or 0),
            avg_upspeed=int(getattr(torrent, "rateUpload", 0)),
            add_time=str(added_date or ""),
            add_on=int(added_date.timestamp()) if hasattr(added_date, "timestamp") else 0,
            tags=list(getattr(torrent, "labels", [])),
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
                       target_size: int, dltime: int) -> tuple[bool, float]:
    """按旧版订阅助手口径判断完成：做种、已有做种时长或已下载达到目标体积。"""
    if state in ["seeding", "seed_pending"]:
        return True, 0.0
    if seeding_time:
        return True, 0.0
    if downloaded >= target_size:
        return True, 0.0
    return False, dltime


def _progress_fraction(downloaded: int, target_size: int) -> float:
    """返回 0-1 的下载进度，内部复用旧版百分比口径并做边界裁剪。"""
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
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _get_qb_tracker_responses(torrent) -> list:
    """按旧版 qB 口径读取 tracker.msg，过滤禁用 tier 和空响应。"""
    trackers = getattr(torrent, "trackers", []) or []
    responses = []
    for tracker in trackers:
        if getattr(tracker, "tier", 0) == -1:
            continue
        msg = getattr(tracker, "msg", "")
        if msg:
            responses.append(str(msg))
    return responses


def _get_tr_tracker(torrent) -> str:
    trackers = getattr(torrent, "trackers", [])
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
        msg = _get_attr(t, "last_announce_result", "lastAnnounceResult", default="")
        if msg:
            responses.append(str(msg))
    return responses
