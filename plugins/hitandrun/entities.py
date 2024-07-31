import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.core.context import TorrentInfo
from app.utils.string import StringUtils


class HNRStatus(Enum):
    PENDING = "Pending"  # 待确认，等待进行做种或上传下载比的验证
    IN_PROGRESS = "In Progress"  # 进行中，用户正在努力满足做种或分享率要求
    COMPLIANT = "Compliant"  # 已满足，用户已成功满足所有做种和分享率要求
    UNRESTRICTED = "Unrestricted"  # 无限制，用户没有任何做种或分享率限制
    NEEDS_SEEDING = "Needs Seeding"  # 需要做种，用户需要增加做种时间来避免受到惩罚
    OVERDUE = "Overdue"  # 已过期，用户已超过做种期限但未满足要求
    WARNED = "Warned"  # 已警告，用户因未达到做种要求而收到警告
    BANNED = "Banned"  # 已封禁，用户因严重违反做种规则被封禁

    def to_chinese(self):
        descriptions = {
            "Pending": "待确认",
            "In Progress": "进行中",
            "Compliant": "已满足",
            "Unrestricted": "无限制",
            "Needs Seeding": "需要做种",
            "Overdue": "已过期",
            "Warned": "已警告",
            "Banned": "已封禁"
        }
        return descriptions[self.value]


class TaskType(Enum):
    BRUSH = "Brush"  # 刷流
    NORMAL = "Normal"  # 普通
    AUTO_SUBSCRIBE = "Auto Subscribe"  # 自动订阅
    RSS_SUBSCRIBE = "RSS Subscribe"  # RSS订阅

    def to_chinese(self):
        descriptions = {
            "Brush": "刷流",
            "Normal": "普通",
            "Auto Subscribe": "自动订阅",
            "RSS Subscribe": "RSS订阅"
        }
        return descriptions[self.value]


@dataclass
class TorrentHistory(TorrentInfo):
    time: Optional[float] = field(default_factory=time.time)  # 时间戳
    hash: Optional[str] = None  # 种子Hash
    task_type: TaskType = TaskType.NORMAL  # 任务类型

    @classmethod
    def from_torrent_info(cls, torrent_info: TorrentInfo):
        """从TorrentInfo实例创建TorrentHistory实例"""
        # 使用字典解包初始化TorrentTask
        return cls(**torrent_info.__dict__)

    def to_dict(self):
        """
        返回字典
        """
        dicts = super().to_dict()
        dicts["task_type"] = self.task_type.value if self.task_type else None
        return dicts


@dataclass
class TorrentTask(TorrentHistory):
    hr_status: Optional[HNRStatus] = HNRStatus.PENDING  # H&R状态
    hr_duration: Optional[float] = None  # H&R时间
    hr_deadline_days: Optional[float] = None  # H&R满足要求的期限（天数）
    ratio: Optional[float] = field(default=0)  # 分享率
    downloaded: Optional[float] = field(default=0)  # 下载量
    uploaded: Optional[float] = field(default=0)  # 上传量
    seeding_time: Optional[float] = field(default=0)  # 做种时间
    deleted: Optional[bool] = field(default=False)  # 是否已删除

    @staticmethod
    def format_size(value):
        return StringUtils.str_filesize(value) if str(value).replace(".", "", 1).isdigit() else value

    @staticmethod
    def format_duration(value):
        return f"{value} 小时" if value is not None else "N/A"

    @staticmethod
    def format_deadline_days(value):
        return f"{value} 天" if value is not None else "N/A"

    @staticmethod
    def format_to_chinese(value):
        return value.to_chinese() if hasattr(value, "to_chinese") else value

    def to_dict(self):
        """
        返回字典
        """
        dicts = super().to_dict()
        dicts["hr_status"] = self.hr_status.value if self.hr_status else None
        return dicts
