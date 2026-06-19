"""域 ③：EpisodesRefresh 待定观察。

P 状态只保护订阅生命周期，不覆盖主程序计算出的 total_episode。
"""

from app.schemas.event import SubscribeEpisodesRefreshEventData


class PendingRefresh:
    """EpisodesRefresh 事件处理：保留域边界，不修改搜索目标范围。"""

    def handle_refresh(self, data: SubscribeEpisodesRefreshEventData):
        """待定状态不覆盖 total_episode，主程序继续使用自己的刷新结果。"""
        return None
