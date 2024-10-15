# 该模块定义了用于管理基于YAML配置文件的种子文件分类的类。
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TorrentFilter:
    """数据类，用于存储种子来源的筛选标准，包括标题、分类和标签。"""
    torrent_title: Optional[str] = None  # 用于匹配种子标题的正则表达式
    torrent_category: Optional[str] = None  # 种子必须属于的分类
    torrent_tags: Optional[List[str]] = field(default_factory=list)  # 种子必须具有的标签，多个标签时，任一满足即可

    def __post_init__(self):
        # 移除列表中的空字符串
        self.torrent_tags = [tag for tag in self.torrent_tags if tag.strip()]


@dataclass
class TorrentTarget:
    """数据类，用于存储匹配来源标准的种子的处理设置。"""
    change_directory: Optional[str] = None  # 匹配种子移动到的目录（如果启用auto_category，则忽略此设置）
    change_category: Optional[str] = None  # 为种子指定的新分类
    add_tags: Optional[List[str]] = field(default_factory=list)  # 需要添加到种子的标签
    remove_tags: Optional[List[str]] = field(default_factory=list)  # 需要从种子移除的标签，'@all' 表示移除所有标签
    auto_category: Optional[bool] = False  # 是否启用自动分类管理

    def __post_init__(self):
        # 移除列表中的空字符串
        self.add_tags = [tag for tag in self.add_tags if tag.strip()]
        self.remove_tags = [tag for tag in self.remove_tags if tag.strip()]


@dataclass
class ClassifierConfig:
    """整合种子来源和目标种子设置的数据类。"""
    torrent_filter: TorrentFilter  # 种子来源配置
    torrent_target: TorrentTarget  # 目标种子处理配置
