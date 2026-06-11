"""域 ③：待定进入/退出判定——P 来源分治。"""
import time
from typing import Callable, Optional

from app.log import logger

from ..engine.types import CompletionSignal, PendingTimeoutManagerProtocol
from ..shared.config import PluginConfig
from ..shared.log import detail
from ..shared.media import get_tv_season_air_date, parse_date
from ..shared.subscribe import format_subscribe
from ..shared.update import update_subscribe


class PendingJudge:
    """订阅待定进入/退出判定，区分 pending_judge 和 guard_veto 来源。"""

    def __init__(self, config: PluginConfig,
                 evaluate_fn: Callable,
                 subscribe_oper,
                 timeout_manager: PendingTimeoutManagerProtocol,
                 task_data_read: Callable,
                 task_data_update: Callable):
        self._config = config
        self._evaluate = evaluate_fn
        self._subscribe_oper = subscribe_oper
        self._timeout = timeout_manager
        self._read = task_data_read
        self._update = task_data_update

    def should_enter_pending(self, subscribe, mediainfo, episodes: list,
                              signal: Optional[CompletionSignal] = None) -> tuple[bool, str]:
        """判断是否应进入待定状态（OR 逻辑）。"""
        season_air_date = get_tv_season_air_date(mediainfo, subscribe.season)
        air_date = parse_date(season_air_date or mediainfo.first_air_date)

        pending_days = self._config.auto_tv_pending_days
        if pending_days and air_date:
            from datetime import date, timedelta
            if air_date + timedelta(days=pending_days) > date.today():
                return True, f"上映窗口期内（距开播 {pending_days} 天）"

        ep_count = len(episodes) if episodes else 0
        pending_episodes = self._config.auto_tv_pending_episodes
        if pending_episodes and ep_count <= pending_episodes:
            return True, f"集数不足（{ep_count} ≤ {pending_episodes}）"

        if self._config.pending_use_volatility and signal and not signal.stable:
            return True, "total_episode 数据不稳定"

        if episodes and not any(ep.air_date for ep in episodes):
            return True, "本季无任何 air_date 信息"

        return False, ""

    def check_exit(self, subscribe, mediainfo, tmdb_episodes_fn) -> bool:
        """检查待定是否应退出。返回 True 表示已退出。"""
        task_data = self._read_subscribe_task(subscribe)
        if not task_data or task_data.get("state") != "P":
            return False

        source = task_data.get("source", "pending_judge")
        signal: CompletionSignal = self._evaluate(subscribe, mediainfo)

        if source == "pending_judge":
            if signal.completed:
                self._exit_pending(subscribe, "信号确认完结")
                return True
            if not signal.stable:
                return False
            episodes = tmdb_episodes_fn(
                subscribe.tmdbid,
                subscribe.season,
                episode_group=subscribe.episode_group,
            )
            should_stay, _ = self.should_enter_pending(subscribe, mediainfo, episodes, signal)
            if not should_stay:
                self._exit_pending(subscribe, "待定条件不再满足")
                return True
            return False

        elif source == "guard_veto":
            if signal.completed:
                self._exit_pending(subscribe, "信号确认完结")
                return True
            return False

        return False

    def _exit_pending(self, subscribe, reason: str):
        """退出待定的完整操作序列。"""
        sid = subscribe.id
        logger.info(f"待定退出：{format_subscribe(subscribe)} 退出待定（{reason}），状态置为 R")
        if self._subscribe_oper:
            update_subscribe(self._subscribe_oper, sid, {"state": "R"})
        self._timeout.clear_block(sid)
        self._update_subscribe_task(subscribe, {
            "state": "R",
            "exit_reason": reason,
            "exit_at": time.time(),
        })

    def mark_pending(self, subscribe, source: str = "pending_judge",
                     reason: str = ""):
        """写入 P 状态。"""
        sid = subscribe.id
        detail(f"待定进入：{format_subscribe(subscribe)} 写 P 状态（来源={source}，原因={reason}）")
        if self._subscribe_oper:
            update_subscribe(self._subscribe_oper, sid, {"state": "P"})
        self._update_subscribe_task(subscribe, {
            "state": "P",
            "source": source,
            "reason": reason,
            "since": time.time(),
        })

    def _read_subscribe_task(self, subscribe) -> dict:
        """读取订阅的任务数据。"""
        sid = str(subscribe.id)
        data = self._read("subscribes")
        return data.get(sid, {})

    def _update_subscribe_task(self, subscribe, updates: dict):
        """更新订阅的任务数据。"""
        sid = str(subscribe.id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task.update(updates)
            data[sid] = task
            return data

        self._update("subscribes", updater)
