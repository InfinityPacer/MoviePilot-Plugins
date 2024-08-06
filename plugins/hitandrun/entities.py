import json
import time
from datetime import datetime
from enum import Enum
from typing import Optional

import pytz
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.context import TorrentInfo


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


class TorrentHistory(BaseModel):
    site: Optional[int] = None  # 站点ID
    site_name: Optional[str] = None  # 站点名称
    title: Optional[str] = None  # 种子名称
    description: Optional[str] = None  # 种子副标题
    enclosure: Optional[str] = None  # 种子链接
    page_url: Optional[str] = None  # 详情页面
    size: float = 0  # 种子大小
    pubdate: Optional[str] = None  # 发布时间
    hit_and_run: bool = False  # HR
    time: Optional[float] = Field(default_factory=time.time)
    hash: Optional[str] = None  # 种子Hash
    task_type: TaskType = TaskType.NORMAL  # 任务类型

    @classmethod
    def from_torrent_info(cls, torrent_info: TorrentInfo):
        """通过TorrentInfo实例化"""
        # 使用字典解包初始化TorrentTask
        return cls(**torrent_info.__dict__)

    # 模型配置
    class Config:
        extra = "ignore"
        arbitrary_types_allowed = True

    def to_dict(self, **kwargs):
        """
        返回字典
        """
        json_str = self.json(**kwargs)
        instance = json.loads(json_str)
        return instance

    @classmethod
    def from_dict(cls, data: dict):
        """
        实例化
        """
        config_json = json.dumps(data)
        return cls.parse_raw(config_json)


class TorrentTask(TorrentHistory):
    hr_status: Optional[HNRStatus] = HNRStatus.PENDING  # H&R状态
    hr_duration: Optional[float] = None  # H&R时间（小时）
    hr_ratio: Optional[float] = None  # H&R分享率
    hr_deadline_days: Optional[float] = None  # H&R满足要求的期限（天数）
    ratio: Optional[float] = 0.0  # 分享率
    downloaded: Optional[float] = 0.0  # 下载量
    uploaded: Optional[float] = 0.0  # 上传量
    seeding_time: Optional[float] = 0.0  # 做种时间（秒）
    deleted: Optional[bool] = False  # 是否已删除
    time: Optional[float] = Field(default_factory=time.time)

    @property
    def identifier(self) -> str:
        """
        获取种子标识符
        """
        parts = [self.title, self.description]
        return " | ".join(part.strip() for part in parts if part and part.strip())

    @property
    def deadline_time(self) -> float:
        """
        获取截止时间的 Unix 时间戳
        """
        deadline_time = self.time + self.hr_deadline_days * 86400
        return deadline_time

    def formatted_deadline(self) -> str:
        """
        获取格式化的截止时间
        """
        deadline_time_local = datetime.fromtimestamp(self.deadline_time, pytz.timezone(settings.TZ))
        return deadline_time_local.strftime('%Y-%m-%d %H:%M')

    def remain_time(self, additional_seed_time: Optional[float] = 0.0) -> float:
        """
        剩余时间（小时）
        """
        # 计算所需做种总时间（小时）
        required_seeding_hours = (self.hr_duration or 0) + (additional_seed_time or 0)
        # 计算已做种时间（小时）
        seeding_hours = self.seeding_time / 3600 if self.seeding_time else 0
        # 计算剩余做种时间
        remain_hours = required_seeding_hours - seeding_hours
        # 确保剩余时间不小于0
        return max(remain_hours, 0)

    @staticmethod
    def format_to_chinese(value):
        return value.to_chinese() if hasattr(value, "to_chinese") else value
