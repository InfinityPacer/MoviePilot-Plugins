import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TorrentTask:
    site: Optional[str] = None  # 站点ID
    site_name: Optional[str] = None  # 站点名称
    title: Optional[str] = None  # 种子标题
    size: Optional[int] = None  # 种子大小
    pubdate: Optional[datetime] = None  # 发布日期
    description: Optional[str] = None  # 描述
    enclosure: Optional[str] = None  # 种子链接
    page_url: Optional[str] = None  # 详情页面
    state: Optional[int] = None  # 1 H&R种子 2 待确认种子 3 普通种子
    duration: Optional[float] = None  # 实际H&R时间
    ratio: Optional[float] = field(default=0)  # 分享率
    downloaded: Optional[float] = field(default=0)  # 下载量
    uploaded: Optional[float] = field(default=0)  # 上传量
    seeding_time: Optional[float] = field(default=0)  # 做种时间
    deleted: Optional[bool] = field(default=False)  # 是否已删除
    time: Optional[float] = field(default_factory=time.time)  # 时间戳

