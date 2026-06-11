"""域 ③：EpisodesRefresh 集数覆盖——P 状态时限制搜索范围为已播出集。"""
from typing import Callable, Optional

from app.schemas.event import SubscribeEpisodesRefreshEventData

from ..engine.scope import build_scope
from ..shared.log import detail
from ..shared.media import count_aired_episodes


class PendingRefresh:
    """EpisodesRefresh 事件处理：待定时覆盖 total 为已播出集数。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 subscribe_get_fn: Optional[Callable] = None,
                 tmdb_episodes_fn: Optional[Callable] = None,
                 scope_builder_fn: Callable = build_scope):
        """注入任务存储与 scope-first 查询能力。"""
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_get = subscribe_get_fn
        self._tmdb_episodes = tmdb_episodes_fn
        self._scope_builder = scope_builder_fn

    def handle_refresh(self, data: SubscribeEpisodesRefreshEventData):
        """处理 SubscribeEpisodesRefreshEventData，待定/blocked 时覆盖 total。

        data 为主程序 event.event_data（链式事件数据类）；覆盖结果写回 data.total_episode/updated，
        主程序只回读该数据类，不读 wrapper 直属性。
        """
        subscribe_id = data.subscribe_id
        if subscribe_id is None:
            return

        if not self._is_pending_or_blocked(subscribe_id):
            return

        mediainfo = data.mediainfo
        season = data.season or 0
        current_total = data.current_total_episode or 0

        episodes = self._get_scope_episodes(subscribe_id, mediainfo, season)
        aired_count = count_aired_episodes(episodes) if episodes else 0

        if not aired_count:
            return

        max_effective = self._get_max_effective_total(subscribe_id)
        effective = max(max_effective, aired_count)
        self._save_max_effective_total(subscribe_id, effective)

        if current_total <= 0 or effective < current_total:
            original = current_total if current_total > 0 else "缺失"
            detail(f"待定集数覆盖：订阅 {subscribe_id} 锁定为已播出集数 {effective}（原 {original}），限制搜索范围")
            data.total_episode = effective
            data.updated = True
            data.source = "subscribeassistantenhanced"
            data.reason = f"待定中，锁定为已播出集数 {effective}"

    def _is_pending_or_blocked(self, subscribe_id: int) -> bool:
        """检查订阅是否处于待定或被守门否决状态。"""
        sid = str(subscribe_id)
        data = self._read("subscribes")
        task = data.get(sid, {})
        return task.get("state") in ("P",)

    def _get_scope_episodes(self, subscribe_id: int, mediainfo, season: int) -> list:
        """按订阅 episode_group 构建统一 scope，不从主季 season_info 猜测范围。"""
        if not mediainfo or not self._subscribe_get or not self._tmdb_episodes:
            return []
        subscribe = self._subscribe_get(subscribe_id)
        if not subscribe:
            return []
        return self._scope_builder(subscribe, mediainfo, self._tmdb_episodes).episodes

    def _get_max_effective_total(self, subscribe_id: int) -> int:
        """读取持久化的 max_effective_total。"""
        sid = str(subscribe_id)
        data = self._read("subscribes")
        return data.get(sid, {}).get("max_effective_total", 0)

    def _save_max_effective_total(self, subscribe_id: int, value: int):
        """持久化 max_effective_total，保证单调递增。"""
        sid = str(subscribe_id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task["max_effective_total"] = value
            data[sid] = task
            return data

        self._update("subscribes", updater)
