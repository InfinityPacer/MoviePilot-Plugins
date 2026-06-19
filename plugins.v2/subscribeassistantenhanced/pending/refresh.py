"""域 ③：EpisodesRefresh 待定观察。

P 状态只保护订阅生命周期，不覆盖主程序计算出的 total_episode。
"""
from typing import Callable, Optional

from app.schemas.event import SubscribeEpisodesRefreshEventData


class PendingRefresh:
    """EpisodesRefresh 事件处理：保留域边界，不修改搜索目标范围。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 subscribe_get_fn: Optional[Callable] = None,
                 tmdb_episodes_fn: Optional[Callable] = None,
                 scope_builder_fn: Optional[Callable] = None):
        """保留依赖注入签名，兼容插件初始化和测试构造。"""
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_get = subscribe_get_fn
        self._tmdb_episodes = tmdb_episodes_fn
        self._scope_builder = scope_builder_fn

    def handle_refresh(self, data: SubscribeEpisodesRefreshEventData):
        """待定状态不覆盖 total_episode，主程序继续使用自己的刷新结果。"""
        return None
