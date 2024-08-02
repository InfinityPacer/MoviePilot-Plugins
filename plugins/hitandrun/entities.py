import json
import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

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
        use_enum_values = True

    def to_dict(self, **kwargs):
        """
        返回字典
        """
        config_json = self.json(**kwargs)
        config_mapping = json.loads(config_json)
        return config_mapping


class TorrentTask(TorrentHistory):
    hr_status: Optional[HNRStatus] = HNRStatus.PENDING  # H&R状态
    hr_duration: Optional[float] = None  # H&R时间（小时）
    hr_ratio: Optional[float] = None  # H&R分享率
    hr_deadline_days: Optional[float] = None  # H&R满足要求的期限（天数）
    ratio: Optional[float] = 0.0  # 分享率
    downloaded: Optional[float] = 0.0  # 下载量
    uploaded: Optional[float] = 0.0  # 上传量
    seeding_time: Optional[float] = 0.0  # 做种时间（分钟）
    deleted: Optional[bool] = False  # 是否已删除

    @property
    def identifier(self) -> str:
        """
        获取种子标识符
        :return: 标识符字符串
        """
        return f"{self.title or ''}|{self.description or ''}"

    @staticmethod
    def format_size(value):
        return StringUtils.str_filesize(value) if str(value).replace(".", "", 1).isdigit() else value

    @staticmethod
    def format_duration(value, additional_time=0):
        if not value and not additional_time:
            return "N/A"
        # 格式化浮点数以去除不必要的尾零
        formatted_value = f"{float(value):.1f}".rstrip("0").rstrip(".")
        if additional_time:
            formatted_additional_time = f"{float(additional_time):.1f}"
            return f"{formatted_value}(+{formatted_additional_time}) 小时"
        return f"{formatted_value} 小时"

    @staticmethod
    def format_deadline_days(value):
        if value is None:
            return "N/A"
        # 格式化浮点数以去除不必要的尾随零
        formatted_value = f"{float(value):.1f}"
        return f"{formatted_value} 天"

    @staticmethod
    def format_to_chinese(value):
        return value.to_chinese() if hasattr(value, "to_chinese") else value
