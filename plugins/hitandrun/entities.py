import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.core.context import TorrentInfo


# 确认状态
class ConfirmationStatus(Enum):
    PENDING = "Pending"  # 待确认
    CONFIRMED = "Confirmed"  # 已确认


@dataclass
class TorrentHistory(TorrentInfo):
    time: Optional[float] = field(default_factory=time.time)  # 时间戳

    @classmethod
    def from_torrent_info(cls, torrent_info: TorrentInfo):
        """从TorrentInfo实例创建TorrentHistory实例"""
        # 使用字典解包初始化TorrentTask
        return cls(**torrent_info.__dict__)


@dataclass
class TorrentTask(TorrentHistory):
    hr_status: Optional[ConfirmationStatus] = ConfirmationStatus.PENDING  # 确认状态
    hr_duration: Optional[float] = None  # H&R时间
    ratio: Optional[float] = field(default=0)  # 分享率
    downloaded: Optional[float] = field(default=0)  # 下载量
    uploaded: Optional[float] = field(default=0)  # 上传量
    seeding_time: Optional[float] = field(default=0)  # 做种时间
    deleted: Optional[bool] = field(default=False)  # 是否已删除
