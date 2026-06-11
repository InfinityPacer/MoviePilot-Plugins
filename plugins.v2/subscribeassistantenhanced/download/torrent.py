"""TorrentInfo 标准化结构 + TorrentAdapter（QB/TR 封装）。"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TorrentInfo:
    """QB/TR 种子信息标准化结构，消除下游对原始结构的依赖。"""
    hash: str = ""
    title: str = ""
    state: str = ""
    progress: float = 0.0
    total_size: int = 0
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
        """QB 种子字典 → TorrentInfo。"""
        progress = torrent.get("progress", 0.0)
        return TorrentInfo(
            hash=torrent.get("hash", ""),
            title=torrent.get("name", ""),
            state=torrent.get("state", ""),
            progress=progress,
            total_size=torrent.get("total_size", 0),
            downloaded=torrent.get("downloaded", 0),
            uploaded=torrent.get("uploaded", 0),
            ratio=torrent.get("ratio", 0.0),
            dltime=torrent.get("dltime", 0),
            seeding_time=torrent.get("seeding_time", 0),
            iatime=torrent.get("inactive_seeding_time", torrent.get("last_activity", 0)),
            avg_upspeed=torrent.get("up_limit", 0),
            add_time=torrent.get("added_on_str", ""),
            add_on=torrent.get("added_on", 0),
            tags=_parse_tags(torrent.get("tags", "")),
            tracker=torrent.get("tracker", ""),
            tracker_responses=_parse_tracker_responses_qb(torrent.get("trackers_count", 0)),
            completed=progress >= 1.0,
            completion_time=0.0 if progress >= 1.0 else torrent.get("dltime", 0),
        )

    @staticmethod
    def from_tr(torrent) -> TorrentInfo:
        """TR 种子对象 → TorrentInfo。"""
        progress = getattr(torrent, "progress", 0.0) / 100.0
        added_date = getattr(torrent, "addedDate", None)
        return TorrentInfo(
            hash=getattr(torrent, "hashString", ""),
            title=getattr(torrent, "name", ""),
            state=getattr(torrent, "status", ""),
            progress=progress,
            total_size=getattr(torrent, "totalSize", 0),
            downloaded=getattr(torrent, "downloadedEver", 0),
            uploaded=getattr(torrent, "uploadedEver", 0),
            ratio=getattr(torrent, "uploadRatio", 0.0),
            dltime=int(getattr(torrent, "secondsDownloading", 0)),
            seeding_time=int(getattr(torrent, "secondsSeeding", 0)),
            iatime=int(getattr(torrent, "idleSeconds", 0) or 0),
            avg_upspeed=int(getattr(torrent, "rateUpload", 0)),
            add_time=str(added_date or ""),
            add_on=int(added_date.timestamp()) if hasattr(added_date, "timestamp") else 0,
            tags=list(getattr(torrent, "labels", [])),
            tracker=_get_tr_tracker(torrent),
            tracker_responses=_get_tr_tracker_responses(torrent),
            completed=progress >= 1.0,
            completion_time=0.0 if progress >= 1.0 else getattr(torrent, "secondsDownloading", 0),
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
        """获取下载进度百分比 0-100。"""
        return info.progress * 100


def _parse_tags(tags_str) -> list:
    """解析 QB 标签字符串。"""
    if isinstance(tags_str, list):
        return tags_str
    if not tags_str:
        return []
    return [t.strip() for t in str(tags_str).split(",") if t.strip()]


def _parse_tracker_responses_qb(count) -> list:
    return []


def _get_tr_tracker(torrent) -> str:
    trackers = getattr(torrent, "trackers", [])
    if trackers:
        first = trackers[0] if isinstance(trackers, list) else None
        if first:
            announce = getattr(first, "announce", None)
            return announce if announce is not None else str(first)
    return ""


def _get_tr_tracker_responses(torrent) -> list:
    trackers = getattr(torrent, "trackerStats", [])
    responses = []
    for t in (trackers or []):
        msg = getattr(t, "lastAnnounceResult", "")
        if msg:
            responses.append(str(msg))
    return responses
